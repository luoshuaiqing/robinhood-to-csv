# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
pip install -r requirements.txt
```

Credentials can be provided via `.env` (copy `.env.example`), CLI args, or interactive prompt:

```
RH_USERNAME=your_username
RH_PASSWORD=your_password
RH_DEVICE_TOKEN=your_device_token  # optional; auto-generated if missing
RH_MFA=your_mfa_code               # optional; prompted if MFA is enabled
```

Preferred Robinhood auth/export flow:

- If the user is already logged into Robinhood inside a `cmux` browser surface, use the `robinhood-cmux-export` skill and `python export-from-cmux.py --cmux-surface <surface> --dividends --output-dir exports`.
- Prefer this over manual token copying. The wrapper reads the live browser auth, runs the export, and clears browser auth state after completion unless `--keep-auth` is explicitly requested.

## Running the scripts

```bash
# Export stock trades
python csv-export.py [--username U] [--password P] [--device_token T] [--mfa_code M] [--debug] [--profit] [--dividends]

# Export options trades
python csv-options-export.py [--username U] [--password P] [--device_token T] [--mfa_code M] [--debug] [--profit]
```

Both scripts prompt for a filename at the end (default: `robinhood.csv` / `option-trades.csv`).

## Architecture

The project is a small collection of scripts with no test suite.

- `Robinhood.py` — thin HTTP client wrapping `api.robinhood.com`. Handles OAuth2 login (Bearer token), paginated GET requests via `get_endpoint(name)` / `get_custom_endpoint(url)`, and a handful of quote/order helpers. Supports Python 2/3 via try/except on `urllib`.
- `login_data.py` — `collect_login_data()` orchestrates credential resolution (env vars → CLI args → interactive prompt → MFA retry loop) and calls `Robinhood.login()`.
- `csv-export.py` — fetches stock orders (`/orders/`), resolves instrument URLs to ticker symbols (cached in `cached_instruments` dict to reduce API calls), builds a flat `fields` dict keyed by row index, then writes CSV. Optionally exports dividends (`--dividends`) and calculates profit (`--profit`).
- `csv-options-export.py` — fetches options orders (`/options/orders/`), iterates over legs and executions, fetches contract metadata (strike, expiration, ticker) per leg, and writes CSV.
- `profit_extractor.py` — reads the exported CSV with pandas, applies FIFO matching of buys to sells, detects basic wash sales (30-day window), and writes a `*_profit.csv` with Profit/Wash Sale/Tax columns.

## Key notes

- The `device_token` is required by Robinhood's API. If not supplied, a UUID is auto-generated — but a consistent token avoids repeated MFA challenges. See README for how to extract yours from browser DevTools.
- Pagination: both export scripts loop on `orders['next']` until `None`.
- `csv-options-export.py` has a leftover debug block that always writes `stocks.txt`; this is intentional legacy behavior.
- `profit_extractor.py` uses `raw_input` / `input` compatibility shim for Python 2/3.
