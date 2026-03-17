from datetime import timedelta
import os

import pandas as pd


EPSILON = 1e-9


def first_present_column(frame, candidates):
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    raise KeyError("Missing expected columns: {}".format(", ".join(candidates)))


def sort_trade_frame(frame):
    ordered = frame.copy().reset_index(drop=True)
    ordered["row_sequence"] = ordered.index
    return ordered.sort_values(["trade_timestamp", "row_sequence"]).reset_index(drop=True)


def load_trade_frame(filename):
    handle = pd.read_csv(filename)
    date_col = first_present_column(handle, ["last_transaction_at", "first_execution_at", "created_at"])
    quantity_col = first_present_column(handle, ["cumulative_quantity", "filled_quantity", "quantity"])
    price_col = first_present_column(handle, ["average_price"])
    symbol_col = first_present_column(handle, ["symbol"])
    state_col = first_present_column(handle, ["state"])
    side_col = first_present_column(handle, ["side"])
    fees_col = first_present_column(handle, ["fees"])

    handle["trade_timestamp"] = pd.to_datetime(handle[date_col], format="mixed", utc=True, errors="coerce")
    handle = handle.dropna(subset=["trade_timestamp"])
    handle = sort_trade_frame(handle)
    handle[quantity_col] = pd.to_numeric(handle[quantity_col], errors="coerce").fillna(0)
    handle[price_col] = pd.to_numeric(handle[price_col], errors="coerce").fillna(0)
    handle[fees_col] = pd.to_numeric(handle[fees_col], errors="coerce").fillna(0)

    return handle, {
        "date_col": date_col,
        "quantity_col": quantity_col,
        "price_col": price_col,
        "symbol_col": symbol_col,
        "state_col": state_col,
        "side_col": side_col,
        "fees_col": fees_col,
    }


def build_buy_event(frame_row, event_id, symbol_col, price_col, quantity_col):
    return {
        "event_id": event_id,
        "symbol": frame_row[symbol_col],
        "order_id": frame_row.get("order_id", ""),
        "trade_timestamp": frame_row["trade_timestamp"],
        "row_sequence": frame_row["row_sequence"],
        "price": float(frame_row[price_col]),
        "quantity": float(frame_row[quantity_col]),
        "open_qty": float(frame_row[quantity_col]),
        "wash_reserved_qty": 0.0,
    }


def allocate_sale_to_open_lots(symbol_lots, buy_events, sale_qty, sale_price, fee_amount):
    remaining_to_sell = sale_qty
    fee_per_share = fee_amount / sale_qty if sale_qty else 0.0
    sale_net_per_share = sale_price - fee_per_share
    matched_cost_basis = 0.0
    loss_segments = []

    while remaining_to_sell > EPSILON and symbol_lots:
        lot = symbol_lots[0]
        used_qty = min(remaining_to_sell, lot["open_qty"])
        cost_per_share = lot["price"]
        matched_cost_basis += used_qty * cost_per_share

        if cost_per_share > sale_net_per_share + EPSILON:
            loss_segments.append(
                {
                    "source_buy_event_id": lot["buy_event_id"],
                    "qty": used_qty,
                    "cost_per_share": cost_per_share,
                    "sale_net_per_share": sale_net_per_share,
                    "loss_per_share": cost_per_share - sale_net_per_share,
                }
            )

        lot["open_qty"] -= used_qty
        remaining_to_sell -= used_qty
        buy_events[lot["buy_event_id"]]["open_qty"] = lot["open_qty"]

        if lot["open_qty"] <= EPSILON:
            symbol_lots.pop(0)

    return matched_cost_basis, loss_segments


def eligible_replacement_buy_ids(buy_events, symbol, sale_timestamp, sale_row_sequence):
    replacement_window_start = sale_timestamp - timedelta(days=30)
    replacement_window_end = sale_timestamp + timedelta(days=30)
    eligible = []

    for event_id, event in buy_events.items():
        if event["symbol"] != symbol:
            continue
        if not replacement_window_start <= event["trade_timestamp"] <= replacement_window_end:
            continue
        if event["trade_timestamp"] < sale_timestamp:
            eligible.append(event_id)
            continue
        if event["trade_timestamp"] == sale_timestamp and event["row_sequence"] <= sale_row_sequence:
            continue
        eligible.append(event_id)

    eligible.sort(key=lambda event_id: (buy_events[event_id]["trade_timestamp"], buy_events[event_id]["row_sequence"]))
    return eligible


def allocate_wash_sale_matches(row, filled, buy_events, sale_qty, sale_price, fees_col, loss_segments):
    sale_timestamp = row["trade_timestamp"]
    eligible_buy_ids = eligible_replacement_buy_ids(
        buy_events,
        row["symbol"],
        sale_timestamp,
        row["row_sequence"],
    )

    matched_wash_qty = 0.0
    disallowed_loss_amount = 0.0
    replacement_before_qty = 0.0
    replacement_after_qty = 0.0
    replacement_dates = set()
    sale_matches = []

    for segment in loss_segments:
        segment_remaining = segment["qty"]
        if segment_remaining <= EPSILON:
            continue

        for event_id in eligible_buy_ids:
            if segment_remaining <= EPSILON:
                break

            event = buy_events[event_id]
            unreserved_qty = max(event["quantity"] - event["wash_reserved_qty"], 0.0)
            if unreserved_qty <= EPSILON:
                continue

            if event["trade_timestamp"] < sale_timestamp:
                available_qty = min(event["open_qty"], unreserved_qty)
            else:
                available_qty = unreserved_qty

            if available_qty <= EPSILON:
                continue

            matched_qty = min(segment_remaining, available_qty)
            if matched_qty <= EPSILON:
                continue

            event["wash_reserved_qty"] += matched_qty
            segment_remaining -= matched_qty
            matched_wash_qty += matched_qty

            matched_loss = matched_qty * segment["loss_per_share"]
            disallowed_loss_amount += matched_loss

            if event["trade_timestamp"] < sale_timestamp:
                replacement_before_qty += matched_qty
                replacement_side = "before"
            else:
                replacement_after_qty += matched_qty
                replacement_side = "after"
            replacement_dates.add(event["trade_timestamp"].date().isoformat())

            source_buy = filled.iloc[segment["source_buy_event_id"]]
            sale_matches.append(
                {
                    "symbol": row["symbol"],
                    "loss_sale_order_id": row.get("order_id", ""),
                    "loss_sale_date": sale_timestamp.date().isoformat(),
                    "loss_sale_timestamp": sale_timestamp.isoformat(),
                    "loss_sale_quantity": sale_qty,
                    "loss_sale_price": sale_price,
                    "loss_sale_fees": float(row[fees_col]),
                    "source_buy_order_id": source_buy.get("order_id", ""),
                    "source_buy_date": buy_events[segment["source_buy_event_id"]]["trade_timestamp"].date().isoformat(),
                    "source_buy_cost_per_share": segment["cost_per_share"],
                    "replacement_buy_order_id": event["order_id"],
                    "replacement_buy_date": event["trade_timestamp"].date().isoformat(),
                    "replacement_buy_timestamp": event["trade_timestamp"].isoformat(),
                    "replacement_buy_price": event["price"],
                    "matched_quantity": matched_qty,
                    "loss_per_share": segment["loss_per_share"],
                    "disallowed_loss_amount": matched_loss,
                    "replacement_side": replacement_side,
                    "warning": "Estimate based on this account export only. Review before filing taxes.",
                }
            )

    return {
        "matched_wash_qty": matched_wash_qty,
        "disallowed_loss_amount": disallowed_loss_amount,
        "replacement_before_qty": replacement_before_qty,
        "replacement_after_qty": replacement_after_qty,
        "replacement_dates": replacement_dates,
        "sale_matches": sale_matches,
    }


def profit_extractor(csv_val, filename):
    print("What is your tax multiplier -default 0.25 (25%) ?")
    tax_multiplier = ""
    try:
        input = raw_input
        tax_multiplier = float(input().strip())
    except Exception:
        pass
    if not tax_multiplier:
        tax_multiplier = 0.25

    profit_filename = filename.split(".")[0] + "_profit.csv"

    handle_raw, cols = load_trade_frame(filename)
    handle = handle_raw.copy()
    quantity_col = cols["quantity_col"]
    price_col = cols["price_col"]
    symbol_col = cols["symbol_col"]
    state_col = cols["state_col"]
    side_col = cols["side_col"]
    fees_col = cols["fees_col"]
    handle["processed"] = 0
    handle["used"] = False
    handle["Profit"] = 0
    handle["Wash Sale"] = 0
    handle["Tax"] = 0

    for index, row in handle.iterrows():
        if row[state_col] == "filled" and row[side_col] == "sell":
            previous_buys = handle.loc[
                (handle[symbol_col] == row[symbol_col])
                & (handle["trade_timestamp"] <= row["trade_timestamp"])
                & (handle[state_col] == "filled")
                & (handle[side_col] == "buy")
                & (handle["used"] == False)
            ]
            if previous_buys.empty:
                print(index, "missing previous transaction, skipped")
                handle.loc[index, "Profit"] = "missing transaction"
                continue

            ws_buys = handle.loc[
                (handle[symbol_col] == row[symbol_col])
                & (handle["trade_timestamp"] >= row["trade_timestamp"])
                & (handle["trade_timestamp"] <= row["trade_timestamp"] + timedelta(days=30))
                & (handle[state_col] == "filled")
                & (handle[side_col] == "buy")
                & (handle["used"] == False)
            ]

            ws_count = 0
            if not ws_buys.empty:
                for _, buy in ws_buys.iterrows():
                    ws_count += buy[quantity_col]

            number = row[quantity_col]
            buy_list = []

            for buy_index, buy in previous_buys.iterrows():
                available = buy[quantity_col] - buy.processed
                if available > number:
                    handle.loc[buy_index, "processed"] = number
                    buy_list.append((number, float(buy[price_col])))
                    break
                if available == number:
                    handle.loc[buy_index, "processed"] = number
                    handle.loc[buy_index, "used"] = True
                    buy_list.append((number, float(buy[price_col])))
                    break
                if available < number:
                    total_used = buy.processed + available
                    assert total_used == buy[quantity_col]
                    handle.loc[buy_index, "processed"] = total_used
                    handle.loc[buy_index, "used"] = True
                    buy_list.append((available, float(buy[price_col])))
                    number = number - available
            total_sell = float(row[quantity_col]) * float(row[price_col])
            total_buy = 0
            total_ws = 0
            ws_count_temp = ws_count
            for q, p in buy_list:
                total_buy += float(q) * float(p)
                for _ in range(0, int(q)):
                    if ws_count_temp > 0:
                        amount = p - float(row[price_col])
                        if amount > 0:
                            total_ws += amount
                            ws_count_temp -= 1

            if total_ws > 0:
                total_ws += float(row[fees_col]) / float(row[quantity_col]) * (ws_count - ws_count_temp)

            profit = total_sell - total_buy - float(row[fees_col])
            handle.loc[index, "Profit"] = profit
            handle.loc[index, "Wash Sale"] = total_ws
            if profit > 0:
                handle.loc[index, "Tax"] = profit * tax_multiplier

    handle_raw["profit"] = handle["Profit"]
    handle_raw["Wash Sale"] = handle["Wash Sale"]
    tax_row = "Tax(" + str(tax_multiplier) + ")"
    handle_raw[tax_row] = handle["Tax"]
    handle_raw.to_csv(profit_filename)


def export_wash_sale_candidates(filename):
    handle, cols = load_trade_frame(filename)
    quantity_col = cols["quantity_col"]
    price_col = cols["price_col"]
    state_col = cols["state_col"]
    side_col = cols["side_col"]
    fees_col = cols["fees_col"]

    filled = sort_trade_frame(handle.loc[handle[state_col] == "filled"].copy())
    buy_events = {}
    for idx, row in filled.iterrows():
        if row[side_col] == "buy":
            buy_events[idx] = build_buy_event(row, idx, "symbol", price_col, quantity_col)

    summary_rows = []
    detail_rows = []
    open_lots = {}

    for idx, row in filled.iterrows():
        symbol = row["symbol"]
        open_lots.setdefault(symbol, [])

        if row[side_col] == "buy":
            open_lots[symbol].append(
                {
                    "buy_event_id": idx,
                    "price": float(row[price_col]),
                    "open_qty": float(row[quantity_col]),
                }
            )
            continue

        if row[side_col] != "sell":
            continue

        sale_qty = float(row[quantity_col])
        sale_price = float(row[price_col])
        sale_fees = float(row[fees_col])
        if sale_qty <= EPSILON:
            continue

        matched_cost_basis, loss_segments = allocate_sale_to_open_lots(
            open_lots[symbol],
            buy_events,
            sale_qty,
            sale_price,
            sale_fees,
        )

        if not loss_segments:
            continue

        total_loss_amount = sum(segment["qty"] * segment["loss_per_share"] for segment in loss_segments)
        wash_match = allocate_wash_sale_matches(
            row,
            filled,
            buy_events,
            sale_qty,
            sale_price,
            fees_col,
            loss_segments,
        )

        if wash_match["matched_wash_qty"] <= EPSILON:
            continue

        proceeds = sale_qty * sale_price - sale_fees
        summary_rows.append(
            {
                "symbol": symbol,
                "loss_sale_order_id": row.get("order_id", ""),
                "loss_sale_date": row["trade_timestamp"].date().isoformat(),
                "loss_sale_timestamp": row["trade_timestamp"].isoformat(),
                "sale_quantity": sale_qty,
                "sale_price": sale_price,
                "sale_fees": sale_fees,
                "sale_proceeds_net": proceeds,
                "matched_cost_basis_fifo": matched_cost_basis,
                "realized_loss_total_estimate": -total_loss_amount,
                "wash_sale_matched_quantity": wash_match["matched_wash_qty"],
                "replacement_buy_quantity_30d_before": wash_match["replacement_before_qty"],
                "replacement_buy_quantity_30d_after": wash_match["replacement_after_qty"],
                "disallowed_loss_estimate": -wash_match["disallowed_loss_amount"],
                "allowed_loss_estimate": -(total_loss_amount - wash_match["disallowed_loss_amount"]),
                "replacement_buy_dates": ", ".join(sorted(wash_match["replacement_dates"])),
                "match_count": len(wash_match["sale_matches"]),
                "warning": "Estimate based on this account export only. Review before filing taxes.",
            }
        )
        detail_rows.extend(wash_match["sale_matches"])

    output_filename = os.path.splitext(filename)[0] + "_wash_sale_candidates.csv"
    detail_filename = os.path.splitext(filename)[0] + "_wash_sale_lot_matches.csv"
    pd.DataFrame(summary_rows).to_csv(output_filename, index=False)
    pd.DataFrame(detail_rows).to_csv(detail_filename, index=False)
    print("Wrote {} rows to {}.".format(len(summary_rows), output_filename))
    print("Wrote {} rows to {}.".format(len(detail_rows), detail_filename))
    return output_filename
