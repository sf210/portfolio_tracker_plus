# Allocation portfolio tracker

Fetches current prices and builds a self-contained HTML report of portfolio
allocation. Managed with [uv](https://docs.astral.sh/uv/).

## Setup

```bash
uv sync          # creates .venv and installs dependencies (openpyxl)
```

uv auto-syncs before every `uv run`, so this step is optional once the
lockfile exists — the first `uv run` will create the environment.

## Running

The one command for a normal refresh — fetches prices, then builds the report:

```bash
uv run update.py            # add --debug to save raw HTTP responses
```

The individual steps, if you need them separately:

```bash
uv run fetch-prices                 # ETF/fund + TIPS prices -> data/
uv run report                       # -> output/portfolio_report.html
uv run build-input-workbook         # rebuild src/portfolio_input.xlsx
uv run empower-holdings-to-csv      # convert an Empower holdings dump

# equivalent, running the source files directly:
uv run src/fetch_prices.py --debug
uv run src/report.py -o output/portfolio_report.html
```

## Adding a dependency

```bash
uv add <package>     # updates pyproject.toml + uv.lock, installs it
```
