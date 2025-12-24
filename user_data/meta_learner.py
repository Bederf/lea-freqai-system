"""
Contextual Bandit Meta-Learner
Offline script that updates strategy selection Q-values based on trade outcomes

Run this daily or after every N trades:
    python user_data/meta_learner.py

Optimizes for: Consistent small wins (frequent, low-risk profits)
"""
import json
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict


class ContextualBanditLearner:
    """
    Offline learner that updates strategy Q-values from Freqtrade trade history

    Strategy: Epsilon-greedy contextual bandit
    - Context: Market regime (volatility, trend, time)
    - Arms: LeaFreqAIStrategy, HybridAIStrategy
    - Reward: Risk-adjusted PnL optimized for consistency
    """

    def __init__(
        self,
        selector_path="user_data/bandit_selector.json",
        trades_db="user_data/tradesv3.sqlite",
        alpha=0.1,  # Learning rate
        epsilon=0.1  # Exploration rate (10%)
    ):
        self.selector_path = Path(selector_path)
        self.trades_db = Path(trades_db)
        self.alpha = alpha
        self.epsilon = epsilon
        self.load_selector()

    def load_selector(self):
        """Load current selection table or initialize new one"""
        if self.selector_path.exists():
            with open(self.selector_path) as f:
                self.selector = json.load(f)
                print(f"Loaded existing selector from {self.selector_path}")
        else:
            self.selector = {
                "contexts": {},
                "epsilon": self.epsilon,
                "alpha": self.alpha,
                "last_updated": None,
                "total_trades_processed": 0
            }
            print("Initialized new selector (no existing file)")

    def compute_reward(self, trade):
        """
        Compute reward optimized for CONSISTENT SMALL WINS

        Priorities:
        1. Frequent small profits (0.5-2%)
        2. Quick exits (<1 hour)
        3. Heavily penalize losses
        4. Cap upside (don't chase big wins)

        Args:
            trade: Dict/Series with 'profit_ratio', 'close_date', 'open_date'

        Returns:
            float: Reward value (can be negative)
        """
        profit = trade["profit_ratio"]

        # Calculate duration in minutes
        if isinstance(trade["close_date"], str):
            close_time = pd.to_datetime(trade["close_date"])
            open_time = pd.to_datetime(trade["open_date"])
        else:
            close_time = trade["close_date"]
            open_time = trade["open_date"]

        duration_minutes = (close_time - open_time).total_seconds() / 60

        # Cap profit at 2% (don't reward risky moonshots)
        capped_profit = min(profit, 0.02)

        # Base reward
        reward = capped_profit

        # PENALTY 1: Losses hurt 3x (consistency means avoiding losses)
        if profit < 0:
            reward = profit * 3  # -2% becomes -6% reward

        # PENALTY 2: Long holds (want fast turnover for consistency)
        if duration_minutes > 90:  # >1.5h on 5m timeframe is too long
            reward -= 0.01  # -1% penalty

        # BONUS 1: Quick wins (30-60 min ideal for 5m timeframe)
        if profit > 0.005 and duration_minutes < 60:
            reward *= 1.5  # 50% bonus for fast wins

        # BONUS 2: Sweet spot wins (0.5-2% profit range)
        if 0.005 <= profit <= 0.02:
            reward += 0.002  # Extra +0.2% for hitting sweet spot

        return reward

    def extract_context_from_trade(self, trade, metadata_df=None):
        """
        Extract context from trade entry point

        Context components:
        1. Market volatility (low/med/high)
        2. Pair trend (down/flat/up)
        3. Time of day (morning/day/evening)

        Note: In production, context should be logged at trade entry.
        This version reconstructs from available data.
        """
        # Try to get stored context from entry_tag or metadata
        # Format: "bandit_ctx_vol_low_trend_up_hour_day"
        entry_tag = trade.get("enter_tag", "") or trade.get("entry_tag", "")

        if entry_tag and "bandit_ctx_" in entry_tag:
            # Extract context from tag
            context = entry_tag.split("bandit_ctx_")[1]
            return context

        # Fallback: Reconstruct context from trade data
        # (This is less accurate but works for initial learning)

        # Time component from open_date
        if isinstance(trade["open_date"], str):
            open_time = pd.to_datetime(trade["open_date"])
        else:
            open_time = trade["open_date"]

        hour = open_time.hour
        if hour < 8:
            time_regime = "morning"
        elif hour < 16:
            time_regime = "day"
        else:
            time_regime = "evening"

        # For volatility and trend, we'd need historical data
        # Simplified: Use profit magnitude as proxy for volatility
        # (High volatility → larger absolute profits)
        profit_abs = abs(trade["profit_ratio"])
        if profit_abs < 0.015:
            vol_regime = "low"
        elif profit_abs < 0.04:
            vol_regime = "med"
        else:
            vol_regime = "high"

        # Trend: use profit direction as weak signal
        # (Not ideal, but works until we log context properly)
        if trade["profit_ratio"] > 0.01:
            trend_regime = "up"
        elif trade["profit_ratio"] < -0.01:
            trend_regime = "down"
        else:
            trend_regime = "flat"

        context = f"vol_{vol_regime}_trend_{trend_regime}_hour_{time_regime}"
        return context

    def extract_strategy_from_trade(self, trade):
        """
        Extract which strategy was used for this trade

        Can be stored in:
        - strategy column (if logged)
        - enter_tag (if prefixed with strategy name)
        - Fallback: guess from ROI/stoploss values
        """
        # Method 1: Direct strategy column (best)
        if "strategy" in trade and pd.notna(trade["strategy"]):
            strat_name = trade["strategy"]
            if "Lea" in strat_name or "LEA" in strat_name:
                return "LeaFreqAIStrategy"
            elif "Hybrid" in strat_name:
                return "HybridAIStrategy"

        # Method 2: Entry tag contains strategy name
        entry_tag = trade.get("enter_tag", "") or trade.get("entry_tag", "")
        if "lea" in entry_tag.lower():
            return "LeaFreqAIStrategy"
        elif "hybrid" in entry_tag.lower():
            return "HybridAIStrategy"

        # Method 3: Fallback - use stoploss to guess
        # LEA uses -5%, Hybrid uses -10%
        if "stop_loss" in trade and pd.notna(trade["stop_loss"]):
            stop_loss = abs(trade["stop_loss"])
            if stop_loss < 0.07:  # Closer to 5%
                return "LeaFreqAIStrategy"
            else:
                return "HybridAIStrategy"

        # Unknown - skip this trade
        return None

    def update_q_values(self, trades_df):
        """
        Update Q-values using incremental average

        Q(context, strategy) ← Q + α[R - Q]

        Where:
        - Q = current Q-value
        - R = reward from trade
        - α = learning rate
        """
        updates = 0
        skipped = 0

        for idx, trade in trades_df.iterrows():
            context = self.extract_context_from_trade(trade)
            strategy = self.extract_strategy_from_trade(trade)

            if strategy is None:
                skipped += 1
                continue

            reward = self.compute_reward(trade)

            # Initialize context if new
            if context not in self.selector["contexts"]:
                self.selector["contexts"][context] = {}

            # Initialize strategy if new
            if strategy not in self.selector["contexts"][context]:
                self.selector["contexts"][context][strategy] = {
                    "q_value": 0.0,
                    "n_trades": 0,
                    "total_reward": 0.0,
                    "avg_reward": 0.0,
                    "last_updated": None
                }

            ctx_strat = self.selector["contexts"][context][strategy]

            # Update Q-value (incremental average with learning rate)
            old_q = ctx_strat["q_value"]
            new_q = old_q + self.alpha * (reward - old_q)

            # Update all metrics
            ctx_strat["q_value"] = new_q
            ctx_strat["n_trades"] += 1
            ctx_strat["total_reward"] += reward
            ctx_strat["avg_reward"] = ctx_strat["total_reward"] / ctx_strat["n_trades"]
            ctx_strat["last_updated"] = datetime.now().isoformat()

            updates += 1

        print(f"Updated Q-values: {updates} trades processed, {skipped} skipped")
        return updates

    def load_freqtrade_trades(self, since_date=None):
        """
        Load closed trades from Freqtrade SQLite database

        Args:
            since_date: Only load trades after this date (default: all trades)

        Returns:
            DataFrame of closed trades
        """
        if not self.trades_db.exists():
            print(f"ERROR: Trades database not found at {self.trades_db}")
            print("Make sure Freqtrade has run and created trades.")
            return pd.DataFrame()

        conn = sqlite3.connect(self.trades_db)

        # Load only closed trades
        query = "SELECT * FROM trades WHERE is_open = 0"

        if since_date:
            query += f" AND close_date >= '{since_date}'"

        trades = pd.read_sql_query(query, conn)
        conn.close()

        print(f"Loaded {len(trades)} closed trades from database")
        return trades

    def save_selector(self):
        """Save updated selection table to JSON"""
        self.selector["last_updated"] = datetime.now().isoformat()

        # Create backup of old file
        if self.selector_path.exists():
            backup_path = self.selector_path.with_suffix(".json.bak")
            import shutil
            shutil.copy(self.selector_path, backup_path)
            print(f"Backed up old selector to {backup_path}")

        with open(self.selector_path, "w") as f:
            json.dump(self.selector, f, indent=2)

        print(f"Saved selector to {self.selector_path}")

    def print_stats(self):
        """Print current Q-value statistics"""
        print("\n" + "="*60)
        print("CONTEXTUAL BANDIT Q-VALUES")
        print("="*60)

        if not self.selector["contexts"]:
            print("No contexts learned yet. Run trades first.")
            return

        # Sort contexts by total trades
        context_trades = {
            ctx: sum(s["n_trades"] for s in strategies.values())
            for ctx, strategies in self.selector["contexts"].items()
        }
        sorted_contexts = sorted(context_trades.items(), key=lambda x: x[1], reverse=True)

        for context, total_trades in sorted_contexts:
            strategies = self.selector["contexts"][context]

            print(f"\n📊 {context} ({total_trades} trades)")
            print("-" * 60)

            # Sort strategies by Q-value
            sorted_strats = sorted(
                strategies.items(),
                key=lambda x: x[1]["q_value"],
                reverse=True
            )

            for strat_name, data in sorted_strats:
                q = data["q_value"]
                n = data["n_trades"]
                avg = data["avg_reward"]

                # Winner marker
                winner = "⭐" if data == sorted_strats[0][1] else "  "

                # Color code Q-value
                q_str = f"{q:+.4f}"

                print(f"  {winner} {strat_name:25s} | Q={q_str:>8s} | N={n:>4d} | Avg={avg:+.4f}")

        print("\n" + "="*60)

    def run_update(self, since_date=None):
        """
        Main update loop

        Steps:
        1. Load closed trades from Freqtrade DB
        2. Extract context and strategy for each trade
        3. Compute reward
        4. Update Q-values
        5. Save updated selector

        Args:
            since_date: Only process trades after this date
        """
        print("="*60)
        print("CONTEXTUAL BANDIT META-LEARNER")
        print("="*60)
        print(f"Alpha (learning rate): {self.alpha}")
        print(f"Epsilon (exploration): {self.epsilon}")
        print()

        # Load trades
        trades = self.load_freqtrade_trades(since_date)

        if len(trades) == 0:
            print("\nNo trades to process. Exiting.")
            return

        # Update Q-values
        updates = self.update_q_values(trades)

        # Update total processed
        self.selector["total_trades_processed"] = self.selector.get("total_trades_processed", 0) + updates

        # Save
        self.save_selector()

        # Print results
        self.print_stats()

        print("\n✅ Update complete!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Update contextual bandit selector")
    parser.add_argument("--alpha", type=float, default=0.1, help="Learning rate (default: 0.1)")
    parser.add_argument("--epsilon", type=float, default=0.1, help="Exploration rate (default: 0.1)")
    parser.add_argument("--since", type=str, help="Only process trades since this date (YYYY-MM-DD)")

    args = parser.parse_args()

    learner = ContextualBanditLearner(alpha=args.alpha, epsilon=args.epsilon)
    learner.run_update(since_date=args.since)
