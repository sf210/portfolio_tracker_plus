"""Shared helpers for programs that write src/portfolio_input.xlsx."""

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKBOOK = ROOT / "src" / "portfolio_input.xlsx"
BACKUPS = ROOT / "data" / "backups"


def ensure_closed(path, command):
    """Exit if LibreOffice has the workbook open (its lock file exists)."""
    lock = path.with_name(f".~lock.{path.name}#")
    if lock.exists():
        sys.exit(f"{path.name} is open in LibreOffice ({lock.name} exists); "
                 f"close it and run {command} again.")


def backup(path):
    """Copy the workbook to data/backups/ and return the copy's path."""
    BACKUPS.mkdir(parents=True, exist_ok=True)
    dest = BACKUPS / f"{path.stem}_{datetime.now():%Y%m%d-%H%M%S}{path.suffix}"
    dest.write_bytes(path.read_bytes())
    return dest
