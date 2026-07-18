from pathlib import Path
import unittest


class LeahAIPaperMonitorTest(unittest.TestCase):
    def test_paper_monitor_uses_initialized_stoploss_counter(self):
        strategy = Path("user_data/strategies/LeahAI.py").read_text(encoding="utf-8")

        self.assertIn("self._pf_sl_exits = 0", strategy)
        self.assertIn("self._pf_sl_exits += 1", strategy)
        self.assertIn("sl={self._pf_sl_exits}", strategy)
        self.assertNotIn("_pf_stop_exits", strategy)


if __name__ == "__main__":
    unittest.main()
