"""Helpers for locating bundled application resources.

Works both from source and from a PyInstaller one-file extraction directory.
"""
from __future__ import annotations

import sys
from pathlib import Path


def application_root() -> Path:
    """Return the root containing bundled ``assets`` and ``migrations``."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root).resolve()
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    """Return an absolute path to a packaged resource."""
    return application_root().joinpath(*parts)
