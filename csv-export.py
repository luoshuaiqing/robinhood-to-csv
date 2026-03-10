from __future__ import print_function
import argparse

from dotenv import find_dotenv, load_dotenv

from Robinhood import Robinhood
from exporters import export_dividends
from exporters import export_stock_history
from login_data import collect_login_data
from profit_extractor import profit_extractor

logged_in = False

parser = argparse.ArgumentParser(
    description='Export Robinhood trades to a CSV file')
parser.add_argument(
    '--debug', action='store_true', help='store raw JSON output to debug.txt')
parser.add_argument(
    '--username', default='', help='your Robinhood username')
parser.add_argument(
    '--password', default='', help='your Robinhood password')
parser.add_argument(
    '--mfa_code', help='your Robinhood mfa_code')
parser.add_argument(
    '--device_token', help='your device token')
parser.add_argument(
    '--profit', action='store_true', help='calculate profit for each sale')
parser.add_argument(
    '--dividends', action='store_true', help='export dividend payments')
args = parser.parse_args()
username = args.username
password = args.password
mfa_code = args.mfa_code
device_token = args.device_token

load_dotenv(find_dotenv())

robinhood = Robinhood()

# login to Robinhood
logged_in = collect_login_data(robinhood_obj=robinhood, username=username, password=password, device_token=device_token, mfa_code=mfa_code)

filename, _ = export_stock_history(robinhood=robinhood, debug=args.debug)


if args.dividends:
    export_dividends(robinhood=robinhood, debug=args.debug)

if args.profit and filename:
    profit_csv = profit_extractor("", filename)
