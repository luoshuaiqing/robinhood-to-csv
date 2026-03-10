from __future__ import print_function

import argparse
import os

from dotenv import find_dotenv, load_dotenv

from Robinhood import Robinhood
from exporters import export_dividends
from exporters import export_options_history
from exporters import export_options_holdings
from exporters import export_stock_history
from exporters import export_stock_holdings
from login_data import collect_login_data
from profit_extractor import profit_extractor


def output_path(output_dir, filename):
    return os.path.join(output_dir, filename) if output_dir else filename


parser = argparse.ArgumentParser(
    description="Export a complete Robinhood account snapshot to CSV files"
)
parser.add_argument("--debug", action="store_true", help="store raw JSON output for each export")
parser.add_argument("--username", default="", help="your Robinhood username")
parser.add_argument("--password", default="", help="your Robinhood password")
parser.add_argument("--mfa_code", help="your Robinhood mfa_code")
parser.add_argument("--device_token", help="your device token")
parser.add_argument(
    "--include-closed",
    action="store_true",
    help="include zero-quantity positions in holdings exports",
)
parser.add_argument(
    "--output-dir",
    default="",
    help="directory for generated CSV files; defaults to the current directory",
)
parser.add_argument(
    "--dividends",
    action="store_true",
    help="also export dividends to dividends.csv",
)
parser.add_argument(
    "--profit",
    action="store_true",
    help="also generate profit CSVs for stock and options trade history",
)
args = parser.parse_args()

load_dotenv(find_dotenv())

if args.output_dir and not os.path.isdir(args.output_dir):
    os.makedirs(args.output_dir)

robinhood = Robinhood()
collect_login_data(
    robinhood_obj=robinhood,
    username=args.username,
    password=args.password,
    device_token=args.device_token,
    mfa_code=args.mfa_code,
)

stock_history_filename, _ = export_stock_history(
    robinhood=robinhood,
    debug=args.debug,
    filename=output_path(args.output_dir, "robinhood.csv"),
    prompt=False,
)

options_history_filename, _ = export_options_history(
    robinhood=robinhood,
    debug=args.debug,
    filename=output_path(args.output_dir, "option-trades.csv"),
    prompt=False,
)

stock_holdings_filename, _ = export_stock_holdings(
    robinhood=robinhood,
    include_closed=args.include_closed,
    debug=args.debug,
    filename=output_path(args.output_dir, "stock-holdings.csv"),
    prompt=False,
)

options_holdings_filename, _ = export_options_holdings(
    robinhood=robinhood,
    include_closed=args.include_closed,
    debug=args.debug,
    filename=output_path(args.output_dir, "option-holdings.csv"),
    prompt=False,
)

if args.dividends:
    export_dividends(
        robinhood=robinhood,
        debug=args.debug,
        filename=output_path(args.output_dir, "dividends.csv"),
        prompt=False,
    )

if args.profit and stock_history_filename:
    profit_extractor("", stock_history_filename)

if args.profit and options_history_filename:
    profit_extractor("", options_history_filename)

print("Complete account export finished.")
print("Trade history: {}".format(stock_history_filename or "not generated"))
print("Options history: {}".format(options_history_filename or "not generated"))
print("Stock holdings: {}".format(stock_holdings_filename or "not generated"))
print("Options holdings: {}".format(options_holdings_filename or "not generated"))
