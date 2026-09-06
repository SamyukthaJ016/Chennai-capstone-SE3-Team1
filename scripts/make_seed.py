from __future__ import annotations

import argparse
import csv
import io
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db_config import SEED_DIR

PRICE_DP = Decimal("0.0001")
MONEY_DP = Decimal("0.01")

HISTORY_EPOCH = "2026-01-05 09:15:00"


def money(value):
    return Decimal(value).quantize(MONEY_DP, rounding=ROUND_HALF_UP)


def price(value):
    return Decimal(value).quantize(PRICE_DP, rounding=ROUND_HALF_UP)


BANK_ACCOUNTS = [
    ("IN45HDFC0000001234567", 1, "Aarav Mehta",   "+919812345001", "aarav.mehta@example.com",   "485200.00", "HDFC Bank",      "HDFC0001234"),
    ("IN45ICIC0000002345678", 2, "Diya Sharma",   "+919812345002", "diya.sharma@example.com",   "129750.50", "ICICI Bank",     "ICIC0002345"),
    ("IN45SBIN0000003456789", 3, "Rohan Iyer",    "+919812345003", "rohan.iyer@example.com",    "873400.25", "State Bank",     "SBIN0003456"),
    ("IN45AXIS0000004567890", 4, "Meera Nair",    "+919812345004", "meera.nair@example.com",     "64300.00", "Axis Bank",      "UTIB0004567"),
    ("IN45KKBK0000005678901", 5, "Vikram Rao",    "+919812345005", "vikram.rao@example.com",    "251000.75", "Kotak Mahindra", "KKBK0005678"),
    ("IN45YESB0000006789012", 6, "Sanya Kapoor",  "+919812345006", "sanya.kapoor@example.com",       "0.00", "Yes Bank",       "YESB0006789"),
]


CLIENTS = [
    (1, "IN45HDFC0000001234567", "Aarav Mehta",   "aarav.mehta@example.com",   "+919812345001", "ACTIVE",    "125000.00"),
    (2, "IN45ICIC0000002345678", "Diya Sharma",   "diya.sharma@example.com",   "+919812345002", "ACTIVE",     "48250.50"),
    (3, "IN45SBIN0000003456789", "Rohan Iyer",    "rohan.iyer@example.com",    "+919812345003", "ACTIVE",    "310400.75"),
    (4, "IN45AXIS0000004567890", "Meera Nair",    "meera.nair@example.com",    "+919812345004", "SUSPENDED",  "15000.00"),
    (5, "IN45KKBK0000005678901", "Vikram Rao",    "vikram.rao@example.com",    "+919812345005", "ACTIVE",     "92750.25"),
    (6, "IN45YESB0000006789012", "Sanya Kapoor",  "sanya.kapoor@example.com",  "+919812345006", "CLOSED",         "0.00"),
]


_PLACEHOLDER_HASH = "$2b$12$SEEDDATAONLYnotarealhashXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

AUTH = [(client[3], _PLACEHOLDER_HASH) for client in CLIENTS]


INSTRUMENTS = [
    ("RELIANCE",   "Reliance Industries",        "true",  ""),
    ("TCS",        "Tata Consultancy Services",  "true",  ""),
    ("INFY",       "Infosys",                    "true",  ""),
    ("HDFCBANK",   "HDFC Bank",                  "true",  ""),
    ("ICICIBANK",  "ICICI Bank",                 "true",  ""),
    ("ITC",        "ITC",                        "true",  ""),
    ("TATAMOTORS", "Tata Motors",                "true",  ""),
    ("LEGACYCORP", "Legacy Corp",                "false", "2025-11-14 15:30:00"),
]


ORDERS = [
    (1,  1, "RELIANCE",   "2875.5000", "BUY",  "HOLDING",  40,  "ord-1001-aarav-rel-buy",   "FILLED",    None,        None),
    (2,  1, "RELIANCE",   "2910.2500", "BUY",  "HOLDING",  20,  "ord-1002-aarav-rel-add",   "FILLED",    None,        None),
    (3,  1, "RELIANCE",   "2950.0000", "SELL", "HOLDING",  15,  "ord-1003-aarav-rel-trim",  "FILLED",    None,        None),
    (4,  1, "TCS",        "3840.0000", "BUY",  "POSITION", 25,  "ord-1004-aarav-tcs-in",    "FILLED",    None,        None),
    (5,  1, "TCS",        "3902.7500", "SELL", "POSITION", 25,  "ord-1005-aarav-tcs-out",   "FILLED",    None,        None),

    (6,  2, "INFY",       "1562.0000", "BUY",  "HOLDING",  60,  "ord-1006-diya-infy-buy",   "FILLED",    None,        None),
    (7,  2, "HDFCBANK",   "1698.5000", "SELL", "POSITION", 30,  "ord-1007-diya-hdfc-short", "FILLED",    None,        None),
    (8,  2, "ICICIBANK",  "1042.0000", "BUY",  "HOLDING",  100, "ord-1008-diya-icici-buy",  "REJECTED",  "ORD-400",   "insufficient funds in linked bank account"),

    (9,  3, "RELIANCE",   "2860.0000", "BUY",  "HOLDING",  150, "ord-1009-rohan-rel-buy",   "FILLED",    None,        None),
    (10, 3, "ITC",         "412.7500", "BUY",  "HOLDING",  500, "ord-1010-rohan-itc-buy",   "FILLED",    None,        None),
    (11, 3, "ITC",         "425.0000", "SELL", "HOLDING",  200, "ord-1011-rohan-itc-trim",  "FILLED",    None,        None),
    (12, 3, "TATAMOTORS",  "918.4000", "BUY",  "POSITION", 120, "ord-1012-rohan-tata-in",   "FILLED",    None,        None),
    (13, 3, "TATAMOTORS",  "930.1500", "BUY",  "POSITION", 80,  "ord-1013-rohan-tata-add",  "FILLED",    None,        None),
    (14, 3, "INFY",       "1571.2500", "BUY",  "HOLDING",  25,  "ord-1014-rohan-infy-buy",  "NEW",       None,        None),
    (15, 3, "TCS",        "3888.0000", "BUY",  "POSITION", 10,  "ord-1015-rohan-tcs-new",   "NEW",       None,        None),

    (16, 4, "ICICIBANK",  "1035.5000", "BUY",  "HOLDING",  45,  "ord-1016-meera-icici-buy", "FILLED",    None,        None),
    (17, 4, "ICICIBANK",  "1050.0000", "BUY",  "HOLDING",  30,  "ord-1017-meera-icici-add", "REJECTED",  "ACC-403",   "client account is suspended"),

    (18, 5, "HDFCBANK",   "1705.0000", "BUY",  "POSITION", 50,  "ord-1018-vikram-hdfc-in",  "FILLED",    None,        None),
    (19, 5, "HDFCBANK",   "1712.6000", "SELL", "POSITION", 50,  "ord-1019-vikram-hdfc-out", "FILLED",    None,        None),
    (20, 5, "LEGACYCORP",  "212.3000", "BUY",  "HOLDING",  300, "ord-1020-vikram-legacy",   "FILLED",    None,        None),
    (21, 5, "LEGACYCORP",  "205.0000", "SELL", "HOLDING",  300, "ord-1021-vikram-legacy-x", "CANCELLED", None,        None),

    (22, 6, "RELIANCE",   "2799.0000", "BUY",  "HOLDING",  10,  "ord-1022-sanya-rel-buy",   "FILLED",    None,        None),
    (23, 6, "RELIANCE",   "2830.5000", "SELL", "HOLDING",  10,  "ord-1023-sanya-rel-exit",  "FILLED",    None,        None),
]

ORDER_KEYS = (
    "order_id", "client_id", "instrument_id", "price", "side", "order_type",
    "quantity", "idempotency_key", "status", "failure_code", "failure_reason",
)

ORDER_FIELDS = (
    "order_id", "client_id", "account_id", "instrument_id", "order_type", "side",
    "quantity", "price", "executed_price", "status", "idempotency_key",
    "external_order_id",
)

HOLDING_BOOK = "HOLDING"
POSITION_BOOK = "POSITION"

TERMINAL_EVENT = {
    "FILLED": "FILLED",
    "REJECTED": "REJECTED",
    "CANCELLED": "CANCELLED",
}


def order_dict(row):
    return dict(zip(ORDER_KEYS, row))


def account_id_for(order):
    return order["client_id"]


def external_order_id_for(order):
    if order["status"] != "FILLED":
        return None
    return "EXT-" + format(order["order_id"], "06d")


def executed_price_for(order):
    if order["status"] != "FILLED":
        return None
    return price(order["price"])


def apply_fill(qty, avg, side, fill_qty, fill_price):
    signed = fill_qty if side == "BUY" else -fill_qty
    new_qty = qty + signed

    if qty == 0:
        new_avg = fill_price
    elif (qty > 0) == (signed > 0):
        new_avg = (abs(qty) * avg + abs(signed) * fill_price) / abs(new_qty)
    elif new_qty == 0:
        new_avg = Decimal(0)
    elif (new_qty > 0) == (qty > 0):
        new_avg = avg
    else:
        new_avg = fill_price

    return new_qty, price(new_avg)


def settle_orders():
    holding = {}
    positions = {}

    for raw in ORDERS:
        o = order_dict(raw)
        if o["status"] != "FILLED":
            continue

        book = holding if o["order_type"] == HOLDING_BOOK else positions
        key = (o["client_id"], o["instrument_id"])
        qty, avg = book.get(key, (0, Decimal(0)))

        new_qty, new_avg = apply_fill(
            qty, avg, o["side"], o["quantity"], executed_price_for(o)
        )

        if o["order_type"] == HOLDING_BOOK and new_qty < 0:
            raise SystemExit(
                "seed data is wrong: order " + str(o["order_id"])
                + " would drive portfolio_holding for client " + str(o["client_id"])
                + " / instrument " + o["instrument_id"] + " to " + str(new_qty)
                + ". A holding cannot go negative."
            )

        book[key] = (new_qty, new_avg)

    return holding, positions


def build_bank_account():
    header = ["account_number", "client_id", "name", "phone", "email",
              "account_balance", "bank_name", "ifsc_code"]
    return header, [list(r) for r in BANK_ACCOUNTS]


def build_clients():
    header = ["client_id", "account_number", "name", "email", "phone",
              "account_state", "wallet_balance"]
    return header, [list(r) for r in CLIENTS]


def build_auth():
    header = ["email", "password_hash"]
    return header, [list(r) for r in AUTH]


def build_instruments():
    header = ["instrument_id", "instrument_name", "active", "updated_on"]
    return header, [list(r) for r in INSTRUMENTS]


def build_orders():
    header = list(ORDER_FIELDS)
    rows = []
    for raw in ORDERS:
        o = order_dict(raw)
        record = {
            "order_id": o["order_id"],
            "client_id": o["client_id"],
            "account_id": account_id_for(o),
            "instrument_id": o["instrument_id"],
            "order_type": o["order_type"],
            "side": o["side"],
            "quantity": o["quantity"],
            "price": price(o["price"]),
            "executed_price": executed_price_for(o),
            "status": o["status"],
            "idempotency_key": o["idempotency_key"],
            "external_order_id": external_order_id_for(o),
        }
        rows.append([record[field] for field in ORDER_FIELDS])
    return header, rows


def build_order_history():
    header = ["history_id", "order_id", "event_type", "previous_status", "new_status",
              "external_status", "external_order_id", "request_id", "failure_code",
              "failure_reason", "event_timestamp", "created_at"]
    rows = []
    history_id = 0

    def stamp(sequence):
        minute_of_day = 9 * 60 + 15 + sequence
        return "2026-01-05 " + format(minute_of_day // 60, "02d") + ":" \
            + format(minute_of_day % 60, "02d") + ":00"

    for raw in ORDERS:
        o = order_dict(raw)

        history_id += 1
        created_stamp = stamp(history_id)
        rows.append([
            history_id, o["order_id"], "CREATED", None, "NEW", None, None,
            "req-" + format(o["order_id"], "06d"), None, None,
            created_stamp, created_stamp,
        ])

        event = TERMINAL_EVENT.get(o["status"])
        if event is None:
            continue

        history_id += 1
        terminal_stamp = stamp(history_id)
        rows.append([
            history_id, o["order_id"], event, "NEW", o["status"],
            event if o["status"] == "FILLED" else None,
            external_order_id_for(o),
            "req-" + format(o["order_id"], "06d"),
            o["failure_code"], o["failure_reason"],
            terminal_stamp, terminal_stamp,
        ])

    return header, rows


def _portfolio_rows(book):
    rows = []
    for idx, key in enumerate(sorted(book), start=1):
        qty, avg = book[key]
        rows.append([idx, key[0], key[1], qty, avg])
    return rows


def build_portfolio_holding():
    header = ["holding_id", "client_id", "instrument_id", "quantity", "price_per_unit"]
    holding, _ = settle_orders()
    return header, _portfolio_rows(holding)


def build_portfolio_positions():
    header = ["position_id", "client_id", "instrument_id", "quantity", "price_per_unit"]
    _, positions = settle_orders()
    return header, _portfolio_rows(positions)


BUILDERS = [
    ("010_bank_account.csv",        build_bank_account),
    ("020_clients.csv",             build_clients),
    ("030_auth.csv",                build_auth),
    ("040_instruments.csv",         build_instruments),
    ("050_orders.csv",              build_orders),
    ("060_order_history.csv",       build_order_history),
    ("070_portfolio_holding.csv",   build_portfolio_holding),
    ("080_portfolio_positions.csv", build_portfolio_positions),
]


def render(header, rows):
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if v is None else str(v) for v in row])
    return buf.getvalue()


def strays(expected):
    if not SEED_DIR.is_dir():
        return []
    return sorted(
        p.name for p in SEED_DIR.iterdir()
        if p.is_file() and p.suffix.lower() == ".csv" and p.name not in expected
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="make_seed.py",
        description="Generate the deterministic seed/ CSV files.",
    )
    parser.add_argument("--check", action="store_true",
                        help="do not write; exit non-zero if seed/ is out of date")
    parser.add_argument("--prune", action="store_true",
                        help="delete .csv files in seed/ that this script does not generate")
    parser.add_argument("--stdout", metavar="FILENAME",
                        help="print one generated file instead of writing anything")
    args = parser.parse_args(argv)

    generated = [(name, render(*builder())) for name, builder in BUILDERS]
    expected = {name for name, _ in generated}

    if args.stdout:
        for name, text in generated:
            if name == args.stdout or name.endswith("_" + args.stdout + ".csv"):
                sys.stdout.write(text)
                return 0
        print("no such seed file: " + args.stdout, file=sys.stderr)
        return 2

    SEED_DIR.mkdir(parents=True, exist_ok=True)
    left_over = strays(expected)

    if args.check:
        stale = []
        for name, text in generated:
            path = SEED_DIR / name
            if not path.is_file():
                stale.append(name + " (missing)")
            elif path.read_text(encoding="utf-8") != text:
                stale.append(name + " (differs)")
        stale += [name + " (not generated by this script)" for name in left_over]
        if stale:
            print("seed/ is out of date with make_seed.py:")
            for item in stale:
                print("  " + item)
            print("Run: python scripts/make_seed.py --prune")
            return 1
        print("seed/ matches make_seed.py (" + str(len(generated)) + " files)")
        return 0

    if left_over:
        if args.prune:
            for name in left_over:
                (SEED_DIR / name).unlink()
                print("removed seed/" + name)
        else:
            print("seed/ holds .csv file(s) this script does not generate:")
            for name in left_over:
                print("  " + name)
            print("They would still be loaded by apply_db.py. Re-run with --prune "
                  "to delete them.")
            return 1

    total_rows = 0
    for name, text in generated:
        path = SEED_DIR / name
        path.write_text(text, encoding="utf-8", newline="")
        rows = text.count("\n") - 1
        total_rows += rows
        print("wrote " + str(path.relative_to(SEED_DIR.parent)) + "  (" + str(rows) + " rows)")

    print("")
    print(str(len(generated)) + " file(s), " + str(total_rows) + " data row(s) in total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
