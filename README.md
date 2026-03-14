# Robinhood to CSV

Python scripts to export Robinhood data to CSV.

This repo now supports two categories of export:

- Trade history: every stock or options order returned by Robinhood, including closed positions.
- Current holdings: the positions you currently hold, based on Robinhood's positions endpoints.
- Complete account snapshot: one command that exports both history and holdings.

The project is based on the Robinhood library by Rohan Pai. Read the back story on the original stock trade exporter on the [blog post](http://www.onlineaspect.com/2015/12/17/export-robinhood-investments-to-csv).

Works on Python 2.7+ and 3.5+

## Install

```bash
pip install -r requirements.txt
```

Using a virtual environment is recommended:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Credentials

The scripts accept credentials either interactively or through environment variables.

Safest usage:

- Prefer interactive prompts for your password instead of passing `--password` on the command line.
- If you want non-interactive runs, copy `.env.example` to `.env` and keep it local. `.env` is ignored by git in this repo.
- Avoid `--debug` unless you need it, because it writes raw Robinhood API responses to local files.

Supported environment variables:

- `RH_USERNAME`
- `RH_PASSWORD`
- `RH_ACCESS_TOKEN`
- `RH_DEVICE_TOKEN`
- `RH_MFA`

Example:

```bash
cp .env.example .env
```

Then edit `.env` with your values:

```bash
RH_USERNAME=your_robinhood_username
RH_PASSWORD=your_robinhood_password
RH_ACCESS_TOKEN=
RH_MFA=123456
RH_DEVICE_TOKEN=your_device_token
```

If you do not provide a device token, the login helper generates one automatically. If Robinhood prompts for MFA, the scripts will ask for it unless `RH_MFA` or `--mfa_code` is provided.

## Token Login

Robinhood's password login flow is unstable for unofficial clients. This repo now supports a bearer token flow that skips the blocked OAuth password grant.

You can pass a token either through `RH_ACCESS_TOKEN` in `.env` or `--access-token` on the command line.

Example:

```bash
python3 export-all.py --access-token 'your_token_here'
```

Browser token workflow:

1. Log in to Robinhood in your browser.
2. Open developer tools and go to the `Application` or `Storage` tab.
3. Find the Robinhood cookies for `robinhood.com`.
4. Copy the value of `__Host-Web-App-Secondary-Access-Token`.
5. Put that value into `RH_ACCESS_TOKEN` and rerun the exporter.

When `RH_ACCESS_TOKEN` is set, the scripts try token auth first and only fall back to username/password if the token is rejected.

## Safer cmux Flow

If you are logged into Robinhood inside a `cmux` browser surface, use the wrapper below instead of copying tokens by hand:

```bash
python3 export-from-cmux.py --cmux-surface surface:13 --dividends --output-dir exports
```

By default this flow:

- reads the primary Robinhood access token from the logged-in `cmux` browser surface
- runs the full export without writing the token into repo files
- clears Robinhood auth state from that `cmux` browser surface after the export finishes
- blanks `RH_ACCESS_TOKEN` in `.env` if it was set there

Pass `--keep-auth` only if you intentionally want to stay logged in inside that `cmux` browser surface after export.

This cleanup does not erase shell history, agent tool logs, or previously approved command prefixes outside the repo.

## What Each Script Exports

### Complete account snapshot

```bash
python3 export-all.py
```

Default outputs:

- `robinhood.csv`
- `option-trades.csv`
- `stock-holdings.csv`
- `option-holdings.csv`

This is the wrapper command for users who want the full picture of their Robinhood account in one run. It logs in once, exports stock and options trade history, and exports current stock and options holdings.

Optional flags:

- `--output-dir exports` writes all files into a specific directory
- `--include-closed` includes zero-quantity positions in the holdings exports
- `--dividends` also exports `dividends.csv`
- `--profit` also generates profit CSVs for trade history
- `--debug` saves raw API payloads for each export

### Stock trade history

```bash
python3 csv-export.py
```

Default output: `robinhood.csv`

This exports stock order history from the Robinhood `orders` endpoint. Use this when you want buys, sells, execution details, timestamps, and a full trade ledger.

Optional flags:

- `--dividends` exports dividend history to `dividends.csv`
- `--profit` writes an additional profit-oriented CSV
- `--debug` saves the raw API payload to `debug.txt`

### Options trade history

```bash
python3 csv-options-export.py
```

Default output: `option-trades.csv`

This exports options order history from the Robinhood `optionsOrders` endpoint. Use this when you want options trade legs, premiums, and execution details for opened and closed contracts.

Optional flags:

- `--profit` writes an additional profit-oriented CSV
- `--debug` saves the raw API payload to `debug.txt`

### Current stock holdings

```bash
python3 csv-holdings-export.py
```

Default output: `stock-holdings.csv`

This exports stock positions from the Robinhood `positions` endpoint. By default it only keeps open positions with a quantity greater than zero, which makes it a current holdings export rather than a full historical ledger.

Optional flags:

- `--include-closed` keeps zero-quantity positions returned by Robinhood
- `--debug` saves the raw API payload to `debug-holdings.txt`

### Current options holdings

```bash
python3 csv-options-holdings-export.py
```

Default output: `option-holdings.csv`

This exports options positions from the Robinhood `optionsPositions` endpoint. By default it only keeps open positions and enriches each row with contract metadata such as ticker, strike price, expiration date, and option type.

Optional flags:

- `--include-closed` keeps zero-quantity positions returned by Robinhood
- `--debug` saves the raw API payload to `debug-options-holdings.txt`

## History vs Holdings

Trade history and holdings answer different questions:

- `csv-export.py` and `csv-options-export.py` answer: "What orders have I placed?"
- `csv-holdings-export.py` and `csv-options-holdings-export.py` answer: "What do I currently hold?"

Example:

- If you bought AAPL in January and sold it in February, trade history will still contain those orders.
- Current holdings will usually not contain AAPL anymore because the position is closed.

If you want a complete picture of your Robinhood account, run all four scripts:

```bash
python3 csv-export.py
python3 csv-options-export.py
python3 csv-holdings-export.py
python3 csv-options-holdings-export.py
```

Or use the wrapper command:

```bash
python3 export-all.py
```

## Device Token

If you want to reuse Robinhood's browser device token instead of letting the script generate one:

    Go to robinhood.com. Log out if you're already logged in
    Right click > Inspect element
    Click on Network tab
    Enter "token" in the filter input
    With the network monitor open, log in to Robinhood
    You will see requests for "api.robinhood.com" and "/oauth2/token"
    Click the request that is not 0 bytes in size
    Click on Headers, then scroll to the Request Payload section
    Copy the `device_token` value
