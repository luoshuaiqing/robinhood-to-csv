from __future__ import print_function

import argparse

from dotenv import find_dotenv, load_dotenv

from Robinhood import Robinhood
from exporters import export_stock_holdings
from login_data import collect_login_data


parser = argparse.ArgumentParser(
    description="Export Robinhood stock holdings to a CSV file"
)
parser.add_argument("--debug", action="store_true", help="store raw JSON output to debug-holdings.txt")
parser.add_argument("--username", default="", help="your Robinhood username")
parser.add_argument("--password", default="", help="your Robinhood password")
parser.add_argument("--mfa_code", help="your Robinhood mfa_code")
parser.add_argument("--device_token", help="your device token")
parser.add_argument(
    "--include-closed",
    action="store_true",
    help="include zero-quantity positions returned by Robinhood, not just currently open holdings",
)
args = parser.parse_args()

load_dotenv(find_dotenv())

robinhood = Robinhood()
collect_login_data(
    robinhood_obj=robinhood,
    username=args.username,
    password=args.password,
    device_token=args.device_token,
    mfa_code=args.mfa_code,
)

export_stock_holdings(
    robinhood=robinhood,
    include_closed=args.include_closed,
    debug=args.debug,
)
