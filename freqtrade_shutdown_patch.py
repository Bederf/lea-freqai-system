"""
Repo-local runtime patches for noisy Freqtrade shutdown behavior.

Import this module before entering the Freqtrade CLI to suppress known
websocket teardown tracebacks during service restarts.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from concurrent.futures import TimeoutError as FutureTimeoutError


logger = logging.getLogger(__name__)


def apply_patch() -> None:
    try:
        import ccxt  # type: ignore
        from freqtrade.exchange import exchange as exchange_mod  # type: ignore
        from freqtrade.exchange import exchange_ws as exchange_ws_mod  # type: ignore
    except Exception:
        return

    Exchange = exchange_mod.Exchange
    ExchangeWS = exchange_ws_mod.ExchangeWS
    ws_logger = exchange_ws_mod.logger
    ex_logger = exchange_mod.logger

    if getattr(ExchangeWS, "_lea_shutdown_patch_applied", False):
        return

    def _task_result_label(task: asyncio.Task) -> str:
        if task.cancelled():
            return "cancelled"
        try:
            result = task.result()
        except Exception as exc:  # pragma: no cover - defensive
            return f"error:{exc.__class__.__name__}"
        return "done" if result is None else str(result)

    async def patched_unwatch_ohlcv(self, pair: str, timeframe: str, candle_type) -> None:
        if getattr(self, "_shutdown_in_progress", False):
            return
        try:
            await self._ccxt_object.un_watch_ohlcv_for_symbols([[pair, timeframe]])
        except ccxt.NotSupported as exc:
            ws_logger.debug("un_watch_ohlcv_for_symbols not supported: %s", exc)
        except ccxt.NetworkError as exc:
            ws_logger.debug(
                "Ignoring websocket unwatch network error for %s/%s during shutdown: %s",
                pair,
                timeframe,
                exc,
            )
        except RuntimeError as exc:
            if "Event loop is closed" in str(exc):
                ws_logger.debug("Skipping websocket unwatch after loop close: %s", exc)
            else:
                ws_logger.exception("Exception in _unwatch_ohlcv")
        except Exception:
            ws_logger.exception("Exception in _unwatch_ohlcv")

    def patched_continuous_stopped(self, task: asyncio.Task, pair: str, timeframe: str, candle_type):
        self._background_tasks.discard(task)
        result = _task_result_label(task)
        ws_logger.info(f"{pair}, {timeframe}, {candle_type} - Task finished - {result}")

        loop = getattr(self, "_loop", None)
        if (
            not getattr(self, "_shutdown_in_progress", False)
            and loop is not None
            and not loop.is_closed()
        ):
            try:
                asyncio.run_coroutine_threadsafe(
                    self._unwatch_ohlcv(pair, timeframe, candle_type), loop=loop
                )
            except RuntimeError as exc:
                ws_logger.debug("Skipping websocket unwatch scheduling after loop close: %s", exc)

        self._klines_scheduled.discard((pair, timeframe, candle_type))
        self._pop_history((pair, timeframe, candle_type))

    def patched_cleanup(self) -> None:
        ws_logger.debug("Patched cleanup called - stopping")
        self._shutdown_in_progress = True
        self._klines_watching.clear()

        for task in list(self._background_tasks):
            task.cancel()

        loop = getattr(self, "_loop", None)
        if loop is not None and not loop.is_closed():
            try:
                fut = asyncio.run_coroutine_threadsafe(asyncio.sleep(0), loop=loop)
                fut.result(timeout=1)
            except (FutureTimeoutError, RuntimeError, Exception):
                pass

            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                pass

        self._thread.join(timeout=5)

        if loop is not None and not loop.is_closed():
            try:
                loop.close()
            except RuntimeError as exc:
                ws_logger.debug("Ignoring loop close runtime error during shutdown: %s", exc)

        ws_logger.debug("Patched cleanup finished")

    def patched_exchange_close(self):
        if self._exchange_ws:
            self._exchange_ws.cleanup()

        ex_logger.debug("Exchange object destroyed, closing async loop")

        def _close_client(client, label: str) -> None:
            if not (
                client
                and inspect.iscoroutinefunction(client.close)
                and getattr(client, "session", None)
            ):
                return
            try:
                self.loop.run_until_complete(client.close())
            except AttributeError as exc:
                if "_abort" in str(exc):
                    ex_logger.debug("Suppressing aiohttp shutdown bug while closing %s: %s", label, exc)
                else:
                    raise
            except RuntimeError as exc:
                if "Event loop is closed" in str(exc):
                    ex_logger.debug("Suppressing closed-loop error while closing %s: %s", label, exc)
                else:
                    raise

        _close_client(getattr(self, "_api_async", None), "async ccxt session")
        _close_client(getattr(self, "_ws_async", None), "ws ccxt session")

        if self.loop and not self.loop.is_closed():
            self.loop.close()

    ExchangeWS._unwatch_ohlcv = patched_unwatch_ohlcv
    ExchangeWS._continuous_stopped = patched_continuous_stopped
    ExchangeWS.cleanup = patched_cleanup
    Exchange.close = patched_exchange_close
    ExchangeWS._lea_shutdown_patch_applied = True

    logger.debug("Applied local Freqtrade shutdown patch.")


apply_patch()
