from __future__ import print_function

import collections
from decimal import Decimal, InvalidOperation


def as_decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


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


def maybe_write_debug_file(debug, filename, payload):
    if not debug:
        return

    try:
        with open(filename, "w+") as outfile:
            outfile.write(str(payload))
        print("Debug information written to {}".format(filename))
    except IOError:
        print("Oops. Unable to write file to {}".format(filename))


def prompt_for_filename(default_filename):
    print("Choose a filename or press enter to save to `{}`:".format(default_filename))
    try:
        input = raw_input
    except NameError:
        pass
    filename = input().strip()
    if filename == "":
        filename = default_filename
    return filename


def write_csv(fields, default_filename, filename=None, prompt=True):
    if not fields:
        print("No rows found to export.")
        return None

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

    if not filename:
        filename = prompt_for_filename(default_filename) if prompt else default_filename

    try:
        with open(filename, "w+") as outfile:
            outfile.write(csv)
        print("Wrote {} rows to {}.".format(len(fields), filename))
        return filename
    except IOError:
        print("Oops. Unable to write file to {}.".format(filename))
        return None


def build_stock_history_rows(robinhood, orders):
    fields = collections.defaultdict(dict)
    trade_count = 0
    queued_count = 0
    cached_instruments = {}

    paginated = True
    page = 0
    current_orders = orders
    while paginated:
        for i, order in enumerate(current_orders["results"]):
            executions = order["executions"]

            symbol = cached_instruments.get(order["instrument"], False)
            if not symbol:
                symbol = robinhood.get_custom_endpoint(order["instrument"])["symbol"]
                cached_instruments[order["instrument"]] = symbol

            fields[i + (page * 100)]["symbol"] = symbol

            for key, value in enumerate(order):
                if value != "executions":
                    fields[i + (page * 100)][value] = order[value]

            fields[i + (page * 100)]["num_of_executions"] = len(executions)
            fields[i + (page * 100)]["execution_state"] = order["state"]

            if len(executions) > 0:
                trade_count += 1
                fields[i + (page * 100)]["execution_state"] = ("completed", "partially filled")[
                    order["cumulative_quantity"] < order["quantity"]
                ]
                fields[i + (page * 100)]["first_execution_at"] = executions[0]["timestamp"]
                fields[i + (page * 100)]["settlement_date"] = executions[0]["settlement_date"]
            elif order["state"] == "queued":
                queued_count += 1

        if current_orders["next"] is not None:
            page += 1
            current_orders = robinhood.get_custom_endpoint(str(current_orders["next"]))
        else:
            paginated = False

    return fields, trade_count, queued_count


def export_stock_history(robinhood, debug=False, filename=None, prompt=True):
    print("Pulling trades. Please wait...")
    orders = robinhood.get_endpoint("orders")
    maybe_write_debug_file(debug, "debug.txt", orders)

    fields, trade_count, queued_count = build_stock_history_rows(robinhood, orders)
    if trade_count > 0 or queued_count > 0:
        print(
            "%d queued trade%s and %d executed trade%s found in your account."
            % (queued_count, "s"[queued_count == 1 :], trade_count, "s"[trade_count == 1 :])
        )
    else:
        print("No trade history found in your account.")
        return None, fields

    return write_csv(fields, "robinhood.csv", filename=filename, prompt=prompt), fields


def export_dividends(robinhood, debug=False, filename=None, prompt=True):
    cached_instruments = {}
    fields = collections.defaultdict(dict)
    dividend_count = 0
    queued_dividends = 0

    dividends = robinhood.get_endpoint("dividends")
    maybe_write_debug_file(debug, "debug-dividends.txt", dividends)

    paginated = True
    page = 0
    current_dividends = dividends
    while paginated:
        for i, dividend in enumerate(current_dividends["results"]):
            symbol = cached_instruments.get(dividend["instrument"], False)
            if not symbol:
                symbol = robinhood.get_custom_endpoint(dividend["instrument"])["symbol"]
                cached_instruments[dividend["instrument"]] = symbol

            fields[i + (page * 100)]["symbol"] = symbol

            for key, value in enumerate(dividend):
                if value != "executions":
                    fields[i + (page * 100)][value] = dividend[value]

            fields[i + (page * 100)]["execution_state"] = dividend["state"]

            if dividend["state"] == "pending":
                queued_dividends += 1
            elif dividend["state"] == "paid":
                dividend_count += 1

        if current_dividends["next"] is not None:
            page += 1
            current_dividends = robinhood.get_custom_endpoint(str(current_dividends["next"]))
        else:
            paginated = False

    if dividend_count > 0 or queued_dividends > 0:
        print(
            "%d queued dividend%s and %d executed dividend%s found in your account."
            % (
                queued_dividends,
                "s"[queued_dividends == 1 :],
                dividend_count,
                "s"[dividend_count == 1 :],
            )
        )
    else:
        print("No dividend history found in your account.")
        return None, fields

    return write_csv(fields, "dividends.csv", filename=filename, prompt=prompt), fields


def build_options_history_rows(robinhood, orders):
    fields = collections.defaultdict(dict)
    trade_count = 0
    queued_count = 0
    page = 0
    row = 0
    current_orders = orders

    paginated = True
    while paginated:
        for i, order in enumerate(current_orders["results"]):
            for j, leg in enumerate(order["legs"]):
                counter = row + (page * 100)
                executions = leg["executions"]
                contract = robinhood.get_custom_endpoint(leg["option"])
                fields[counter]["Leg"] = j + 1
                fields[counter]["Ticker"] = contract["chain_symbol"]
                fields[counter]["Strike_price"] = contract["strike_price"]
                fields[counter]["Expiration_date"] = contract["expiration_date"]
                for key, value in enumerate(leg):
                    if value != "executions":
                        fields[counter][value] = leg[value]
                for key, value in enumerate(order):
                    if value != "legs":
                        fields[counter][value] = order[value]
                if order["state"] == "filled" and executions:
                    trade_count += 1
                    for key, value in enumerate(executions[0]):
                        fields[counter][value] = executions[0][value]
                elif order["state"] == "queued":
                    queued_count += 1
                if leg["side"] == "sell":
                    fields[counter]["Change_in_Buying_Power"] = order["processed_premium"]
                else:
                    fields[counter]["Change_in_Buying_Power"] = "-" + order["processed_premium"]
                row += 1
        if current_orders["next"] is not None:
            page += 1
            current_orders = robinhood.get_custom_endpoint(str(current_orders["next"]))
        else:
            paginated = False

    return fields, trade_count, queued_count


def export_options_history(robinhood, debug=False, filename=None, prompt=True):
    print("Pulling trades. Please wait...")
    orders = robinhood.get_endpoint("optionsOrders")
    maybe_write_debug_file(debug, "debug-options.txt", orders)

    fields, trade_count, queued_count = build_options_history_rows(robinhood, orders)
    if trade_count > 0 or queued_count > 0:
        print(
            "%d queued trade%s and %d executed trade%s found in your account."
            % (queued_count, "s"[queued_count == 1 :], trade_count, "s"[trade_count == 1 :])
        )
    else:
        print("No trade history found in your account.")
        return None, fields

    return write_csv(fields, "option-trades.csv", filename=filename, prompt=prompt), fields


def is_open_stock_position(position):
    return as_decimal(position.get("quantity")) > 0


def build_stock_holdings_rows(robinhood, positions, include_closed):
    rows = collections.defaultdict(dict)
    cached_instruments = {}
    row = 0

    for position in positions:
        if not include_closed and not is_open_stock_position(position):
            continue

        instrument_url = position.get("instrument")
        symbol = ""
        if instrument_url:
            instrument = cached_instruments.get(instrument_url)
            if not instrument:
                instrument = robinhood.get_custom_endpoint(instrument_url)
                cached_instruments[instrument_url] = instrument
            symbol = instrument.get("symbol", "")

        rows[row]["symbol"] = symbol
        rows[row]["is_open_position"] = is_open_stock_position(position)

        for key in position:
            rows[row][key] = position[key]

        row += 1

    return rows


def export_stock_holdings(robinhood, include_closed=False, debug=False, filename=None, prompt=True):
    print("Pulling stock holdings. Please wait...")
    positions = fetch_paginated_results(robinhood, "positions")
    maybe_write_debug_file(debug, "debug-holdings.txt", positions)

    fields = build_stock_holdings_rows(robinhood, positions, include_closed)
    open_count = 0
    closed_count = 0
    for row in fields.values():
        if row.get("is_open_position"):
            open_count += 1
        else:
            closed_count += 1

    print(
        "{} open stock holding{}{} found.".format(
            open_count,
            "s"[open_count == 1 :],
            ""
            if not include_closed
            else " and {} closed position{}.".format(closed_count, "s"[closed_count == 1 :]),
        )
    )
    return write_csv(fields, "stock-holdings.csv", filename=filename, prompt=prompt), fields


def is_open_option_position(position):
    quantity = position.get("quantity")
    if quantity is None:
        quantity = position.get("tradable_quantity")
    return as_decimal(quantity) > 0


def build_options_holdings_rows(robinhood, positions, include_closed):
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

        for key in position:
            rows[row][key] = position[key]

        row += 1

    return rows


def export_options_holdings(robinhood, include_closed=False, debug=False, filename=None, prompt=True):
    print("Pulling options holdings. Please wait...")
    positions = fetch_paginated_results(robinhood, "optionsPositions")
    maybe_write_debug_file(debug, "debug-options-holdings.txt", positions)

    fields = build_options_holdings_rows(robinhood, positions, include_closed)
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
            "s"[open_count == 1 :],
            ""
            if not include_closed
            else " and {} closed position{}.".format(closed_count, "s"[closed_count == 1 :]),
        )
    )
    return write_csv(fields, "option-holdings.csv", filename=filename, prompt=prompt), fields
