from __future__ import print_function

import argparse
import collections
from decimal import Decimal, InvalidOperation

from dotenv import find_dotenv, load_dotenv

from Robinhood import Robinhood
from login_data import collect_login_data


def as_decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def is_open_option_position(position):
    quantity = position.get("quantity")
    if quantity is None:
        quantity = position.get("tradable_quantity")
    return as_decimal(quantity) > 0


def fetch_paginated_results(robinhood, endpoint_name):
    response = robinhood.get_endpoint(endpoint_name)
    results = []

    while True:
        results.extend(response.get("results", []))
        next_url = response.get("next")
        if not next_url:
            break
        response = robinhood.get_custom_endpoint(str(next_url))

    return results


def build_holdings_rows(robinhood, positions, include_closed):
    rows = collections.defaultdict(dict)
    cached_contracts = {}
    row = 0

    for position in positions:
        if not include_closed and not is_open_option_position(position):
            continue

        option_url = position.get("option")
        contract = {}
        if option_url:
            contract = cached_contracts.get(option_url)
            if not contract:
                contract = robinhood.get_custom_endpoint(option_url)
                cached_contracts[option_url] = contract

        rows[row]["Ticker"] = contract.get("chain_symbol", "")
        rows[row]["Strike_price"] = contract.get("strike_price", "")
        rows[row]["Expiration_date"] = contract.get("expiration_date", "")
        rows[row]["Type"] = contract.get("type", "")
        rows[row]["is_open_position"] = is_open_option_position(position)

        # Preserve the raw API payload so the export remains complete even if the
        # response shape changes over time.
        for key in position:
            rows[row][key] = position[key]

        row += 1

    return rows


def write_csv(fields, default_filename):
    if not fields:
        print("No holdings found.")
        return

    keys = sorted(fields[0].keys())
    csv = ",".join(keys) + "\n"

    for row in fields:
        for idx, key in enumerate(keys):
            if idx > 0:
                csv += ","
            try:
                csv += str(fields[row][key])
            except Exception:
                csv += ""
        csv += "\n"

    print("Choose a filename or press enter to save to `{}`:".format(default_filename))
    try:
        input = raw_input
    except NameError:
        pass
    filename = input().strip()
    if filename == "":
        filename = default_filename

    try:
        with open(filename, "w+") as outfile:
            outfile.write(csv)
        print("Wrote {} rows to {}.".format(len(fields), filename))
    except IOError:
        print("Oops. Unable to write file to {}.".format(filename))


parser = argparse.ArgumentParser(
    description="Export Robinhood options holdings to a CSV file"
)
parser.add_argument("--debug", action="store_true", help="store raw JSON output to debug-options-holdings.txt")
parser.add_argument("--username", default="", help="your Robinhood username")
parser.add_argument("--password", default="", help="your Robinhood password")
parser.add_argument("--mfa_code", help="your Robinhood mfa_code")
parser.add_argument("--device_token", help="your device token")
parser.add_argument(
    "--include-closed",
    action="store_true",
    help="include zero-quantity option positions returned by Robinhood, not just currently open holdings",
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

print("Pulling options holdings. Please wait...")

positions = fetch_paginated_results(robinhood, "optionsPositions")

if args.debug:
    try:
        with open("debug-options-holdings.txt", "w+") as outfile:
            outfile.write(str(positions))
        print("Debug information written to debug-options-holdings.txt")
    except IOError:
        print("Oops. Unable to write file to debug-options-holdings.txt")

fields = build_holdings_rows(
    robinhood=robinhood,
    positions=positions,
    include_closed=args.include_closed,
)

open_count = 0
closed_count = 0
for row in fields.values():
    if row.get("is_open_position"):
        open_count += 1
    else:
        closed_count += 1

print(
    "{} open option holding{}{} found.".format(
        open_count,
        "s" [open_count == 1:],
        "" if not args.include_closed else " and {} closed position{}.".format(
            closed_count, "s" [closed_count == 1:]
        ),
    )
)

write_csv(fields, "option-holdings.csv")
