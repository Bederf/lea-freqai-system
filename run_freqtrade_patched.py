#!/usr/bin/env python3
"""
Freqtrade launcher that applies local runtime patches before entering the CLI.
"""

from __future__ import annotations

import sys

import freqtrade_shutdown_patch  # noqa: F401
from freqtrade.main import main


if __name__ == "__main__":
    main(sys.argv[1:])
