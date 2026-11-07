"""Shared helpers for programs that read or write the portfolio workbook."""

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKBOOK = ROOT / "data" / "portfolio_input.xlsx"
EXAMPLE = ROOT / "examples" / "portfolio_input.example.xlsx"
BACKUPS = ROOT / "data" / "backups"


def outputs_for(path=WORKBOOK):
    """Price files and report path for a workbook.

    The real workbook uses data/prices.csv, data/tips_prices.csv and
    output/portfolio_report.html. Any other workbook gets its own folder,
    data/<stem>/, and its own report, so its prices never overwrite the
    real ones: examples/portfolio_input.example.xlsx ->
    data/portfolio_input.example/ and output/portfolio_report.example.html.
    """
    path = Path(path).resolve()
    if path == WORKBOOK:
        d, report = ROOT / "data", "portfolio_report.html"
    else:
        d = ROOT / "data" / path.stem
        suffix = path.stem.removeprefix("portfolio_input").lstrip("._-")
        report = f"portfolio_report.{suffix or path.stem}.html"
    return {"prices": d / "prices.csv", "tips": d / "tips_prices.csv",
            "report": ROOT / "output" / report}


def require_workbook(path=WORKBOOK):
    """Exit with a hint if the workbook doesn't exist yet."""
    path = Path(path)
    if not path.exists():
        rel = lambda p: p.relative_to(ROOT) if p.is_relative_to(ROOT) else p
        sys.exit(f"No workbook at {rel(path)}. To start, copy the example:\n"
                 f"  cp {rel(EXAMPLE)} {rel(path)}")


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
