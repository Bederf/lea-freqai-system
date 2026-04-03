"""
Compatibility shim for environments where this repo-local file does get loaded.
"""

from freqtrade_shutdown_patch import apply_patch


apply_patch()
