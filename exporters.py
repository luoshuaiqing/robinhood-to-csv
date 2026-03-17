from __future__ import print_function

import collections
import csv
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
    if isinstance(fields, dict):
        rows = [fields[key] for key in sorted(fields.keys())]
    else:
        rows = list(fields)

    if not rows:
        print("No rows found to export.")
        return None

    keys = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)

    if not filename:
        filename = prompt_for_filename(default_filename) if prompt else default_filename

    try:
        with open(filename, "w+") as outfile:
            writer = csv.DictWriter(outfile, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        print("Wrote {} rows to {}.".format(len(rows), filename))
        return filename
    except IOError:
        print("Oops. Unable to write file to {}.".format(filename))
        return None


def money_amount(value):
    if isinstance(value, dict):
        return value.get("amount", "")
    return value or ""


def first_execution(executions):
    if executions:
        return executions[0]
    return {}


def derive_stock_execution_state(order):
    executions = order.get("executions", [])
    if executions:
        if as_decimal(order.get("cumulative_quantity")) < as_decimal(order.get("quantity")):
            return "partially filled"
        return "completed"
    return order.get("state", "")


def build_stock_history_rows(robinhood, orders, include_non_filled=False):
    fields = []
    trade_count = 0
    queued_count = 0
    cached_instruments = {}

    paginated = True
    page = 0
    current_orders = orders
    while paginated:
        for order in current_orders["results"]:
            executions = order.get("executions", [])
            execution = first_execution(executions)
            if not include_non_filled and order.get("state") != "filled":
                if order.get("state") == "queued":
                    queued_count += 1
                continue

            symbol = cached_instruments.get(order["instrument"], False)
            if not symbol:
                symbol = robinhood.get_custom_endpoint(order["instrument"])["symbol"]
                cached_instruments[order["instrument"]] = symbol

            fields.append(
                {
                    "order_id": order.get("id", ""),
                    "symbol": symbol,
                    "side": order.get("side", ""),
                    "state": order.get("state", ""),
                    "execution_state": derive_stock_execution_state(order),
                    "created_at": order.get("created_at", ""),
                    "last_transaction_at": order.get("last_transaction_at", ""),
                    "first_execution_at": execution.get("timestamp", ""),
                    "settlement_date": execution.get("settlement_date", ""),
                    "quantity": order.get("quantity", ""),
                    "filled_quantity": order.get("cumulative_quantity", ""),
                    "average_price": order.get("average_price", ""),
                    "limit_price": order.get("price", ""),
                    "requested_notional_amount": money_amount(order.get("requested_notional_amount"))
                    or money_amount(order.get("dollar_based_amount")),
                    "executed_notional_amount": money_amount(order.get("executed_notional")),
                    "fees": money_amount(order.get("fees")),
                    "market_hours": order.get("market_hours", ""),
                    "time_in_force": order.get("time_in_force", ""),
                    "trigger": order.get("trigger", ""),
                    "order_type": order.get("type", ""),
                    "position_effect": order.get("position_effect", ""),
                    "ref_id": order.get("ref_id", ""),
                    "order_url": order.get("url", ""),
                    "instrument_id": order.get("instrument_id", ""),
                    "trade_date": (execution.get("timestamp") or order.get("last_transaction_at") or "")[:10],
                }
            )

            if len(executions) > 0:
                trade_count += 1
            elif include_non_filled and order.get("state") == "queued":
                queued_count += 1

        if current_orders["next"] is not None:
            page += 1
            current_orders = robinhood.get_custom_endpoint(str(current_orders["next"]))
        else:
            paginated = False

    return fields, trade_count, queued_count


def export_stock_history(robinhood, debug=False, filename=None, prompt=True, include_non_filled=False):
    print("Pulling trades. Please wait...")
    orders = robinhood.get_endpoint("orders")
    maybe_write_debug_file(debug, "debug.txt", orders)

    fields, trade_count, queued_count = build_stock_history_rows(
        robinhood, orders, include_non_filled=include_non_filled
    )
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
    fields = []
    trade_count = 0
    queued_count = 0
    current_orders = orders

    paginated = True
    while paginated:
        for order in current_orders["results"]:
            for j, leg in enumerate(order["legs"]):
                executions = leg.get("executions", [])
                execution = first_execution(executions)
                contract = robinhood.get_custom_endpoint(leg["option"])
                fields.append(
                    {
                        "order_id": order.get("id", ""),
                        "leg": j + 1,
                        "ticker": contract.get("chain_symbol", ""),
                        "option_type": contract.get("type", ""),
                        "expiration_date": contract.get("expiration_date", ""),
                        "strike_price": contract.get("strike_price", ""),
                        "side": leg.get("side", ""),
                        "position_effect": leg.get("position_effect", ""),
                        "state": order.get("state", ""),
                        "created_at": order.get("created_at", ""),
                        "trade_date": execution.get("trade_date", ""),
                        "timestamp": execution.get("timestamp", ""),
                        "settlement_date": execution.get("settlement_date", ""),
                        "quantity": order.get("quantity", ""),
                        "filled_quantity": order.get("processed_quantity", ""),
                        "price_per_contract": order.get("price", ""),
                        "average_net_premium_paid": order.get("average_net_premium_paid", ""),
                        "premium": order.get("premium", ""),
                        "net_amount": order.get("net_amount", ""),
                        "change_in_buying_power": (
                            order.get("processed_premium", "")
                            if leg.get("side") == "sell"
                            else "-" + order.get("processed_premium", "")
                        ),
                        "contract_fees": order.get("contract_fees", ""),
                        "regulatory_fees": order.get("regulatory_fees", ""),
                        "strategy": order.get("strategy", ""),
                        "time_in_force": order.get("time_in_force", ""),
                        "trigger": order.get("trigger", ""),
                        "order_type": order.get("type", ""),
                        "ref_id": order.get("ref_id", ""),
                        "option_id": contract.get("id", ""),
                        "option_url": leg.get("option", ""),
                    }
                )
                if order.get("state") == "filled" and executions:
                    trade_count += 1
                elif order.get("state") == "queued":
                    queued_count += 1
        if current_orders["next"] is not None:
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
