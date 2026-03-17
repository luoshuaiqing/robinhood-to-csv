from __future__ import print_function

import argparse
import os

from dotenv import find_dotenv, load_dotenv

from Robinhood import Robinhood
from cmux_auth import clear_cmux_auth
from cmux_auth import clear_env_access_token
from cmux_auth import get_cmux_access_token
from exporters import export_dividends
from exporters import export_options_history
from exporters import export_options_holdings
from exporters import export_stock_history
from exporters import export_stock_holdings
from login_data import collect_login_data
from profit_extractor import export_wash_sale_candidates
from profit_extractor import profit_extractor


def output_path(output_dir, filename):
    return os.path.join(output_dir, filename) if output_dir else filename


parser = argparse.ArgumentParser(
    description="Export Robinhood data using a logged-in cmux browser surface"
)
parser.add_argument("--cmux-surface", required=True, help="cmux browser surface, for example surface:13")
parser.add_argument("--debug", action="store_true", help="store raw JSON output for each export")
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
parser.add_argument(
    "--include-non-filled",
    action="store_true",
    help="include non-filled stock orders in the stock history export",
)
parser.add_argument(
    "--wash-sales",
    action="store_true",
    help="also generate a wash-sale screening CSV for stock history",
)
parser.add_argument(
    "--keep-auth",
    action="store_true",
    help="keep the Robinhood auth state in the cmux browser instead of clearing it after export",
)
args = parser.parse_args()

env_path = find_dotenv()
load_dotenv(env_path)

if args.output_dir and not os.path.isdir(args.output_dir):
    os.makedirs(args.output_dir)

token = get_cmux_access_token(args.cmux_surface)
robinhood = Robinhood()

cleanup_errors = []

try:
    collect_login_data(
        robinhood_obj=robinhood,
        username="",
        password="",
        device_token=None,
        mfa_code=None,
        access_token=token,
    )

    stock_history_filename, _ = export_stock_history(
        robinhood=robinhood,
        debug=args.debug,
        filename=output_path(args.output_dir, "robinhood.csv"),
        prompt=False,
        include_non_filled=args.include_non_filled,
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

    if args.wash_sales and stock_history_filename:
        export_wash_sale_candidates(stock_history_filename)

    print("Complete account export finished.")
    print("Trade history: {}".format(stock_history_filename or "not generated"))
    print("Options history: {}".format(options_history_filename or "not generated"))
    print("Stock holdings: {}".format(stock_holdings_filename or "not generated"))
    print("Options holdings: {}".format(options_holdings_filename or "not generated"))
finally:
    if not args.keep_auth:
        try:
            clear_cmux_auth(args.cmux_surface)
            print("Cleared Robinhood auth state from {}.".format(args.cmux_surface))
        except Exception as exc:
            cleanup_errors.append("cmux browser cleanup failed: {}".format(exc))

        try:
            if clear_env_access_token(env_path):
                print("Cleared RH_ACCESS_TOKEN in {}.".format(env_path))
        except Exception as exc:
            cleanup_errors.append("env cleanup failed: {}".format(exc))

        if cleanup_errors:
            print("Cleanup warnings:")
            for message in cleanup_errors:
                print("- {}".format(message))
            print("This does not clear command history, tool logs, or previously approved command prefixes.")
