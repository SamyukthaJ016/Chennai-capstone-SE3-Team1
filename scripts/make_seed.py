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


def money(value):
    return Decimal(value).quantize(MONEY_DP, rounding=ROUND_HALF_UP)


def price(value):
    return Decimal(value).quantize(PRICE_DP, rounding=ROUND_HALF_UP)


BANK_ACCOUNTS = [
    ("IN45HDFC0000001234567", "Aarav Mehta",      "+919812345001", "aarav.mehta@example.com",   "485200.00", "HDFC Bank",      "HDFC0001234"),
    ("IN45ICIC0000002345678", "Diya Sharma",      "+919812345002", "diya.sharma@example.com",   "129750.50", "ICICI Bank",     "ICIC0002345"),
    ("IN45SBIN0000003456789", "Rohan Iyer",       "+919812345003", "rohan.iyer@example.com",    "873400.25", "State Bank",     "SBIN0003456"),
    ("IN45AXIS0000004567890", "Meera Nair",       "+919812345004", "meera.nair@example.com",     "64300.00", "Axis Bank",      "UTIB0004567"),
    ("IN45KKBK0000005678901", "Vikram Rao",       "+919812345005", "vikram.rao@example.com",    "251000.75", "Kotak Mahindra", "KKBK0005678"),
    ("IN45YESB0000006789012", "Sanya Kapoor",     "+919812345006", "sanya.kapoor@example.com",       "0.00", "Yes Bank",       "YESB0006789"),
]


CLIENTS = [
    (1, "IN45HDFC0000001234567", "Aarav Mehta",   "aarav.mehta@example.com",   "+919812345001", "ACTIVE"),
    (2, "IN45ICIC0000002345678", "Diya Sharma",   "diya.sharma@example.com",   "+919812345002", "ACTIVE"),
    (3, "IN45SBIN0000003456789", "Rohan Iyer",    "rohan.iyer@example.com",    "+919812345003", "ACTIVE"),
    (4, "IN45AXIS0000004567890", "Meera Nair",    "meera.nair@example.com",    "+919812345004", "SUSPENDED"),
    (5, "IN45KKBK0000005678901", "Vikram Rao",    "vikram.rao@example.com",    "+919812345005", "ACTIVE"),
    (6, "IN45YESB0000006789012", "Sanya Kapoor",  "sanya.kapoor@example.com",  "+919812345006", "CLOSED"),
]


_PLACEHOLDER_HASH = "$2b$12$SEEDDATAONLYnotarealhashXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

AUTH = [(client[3], _PLACEHOLDER_HASH) for client in CLIENTS]


INSTRUMENTS = [
    (1, "RELIANCE",        "true",  ""),
    (2, "TCS",             "true",  ""),
    (3, "INFY",            "true",  ""),
    (4, "HDFCBANK",        "true",  ""),
    (5, "ICICIBANK",       "true",  ""),
    (6, "ITC",             "true",  ""),
    (7, "TATAMOTORS",      "true",  ""),
    (8, "LEGACYCORP",      "false", "2025-11-14 15:30:00"),
]


ORDERS = [
    (1,  1, 1, "2875.5000", "BUY",  "DELIVERY", 40,  "NSE", "ord-1001-aarav-rel-buy",   "SUCCESS",     None),
    (2,  1, 1, "2910.2500", "BUY",  "DELIVERY", 20,  "NSE", "ord-1002-aarav-rel-add",   "SUCCESS",     None),
    (3,  1, 1, "2950.0000", "SELL", "DELIVERY", 15,  "NSE", "ord-1003-aarav-rel-trim",  "SUCCESS",     None),
    (4,  2, 1, "3840.0000", "BUY",  "INTRADAY", 25,  "NSE", "ord-1004-aarav-tcs-in",    "SUCCESS",     None),
    (5,  2, 1, "3902.7500", "SELL", "INTRADAY", 25,  "NSE", "ord-1005-aarav-tcs-out",   "SUCCESS",     None),

    (6,  3, 2, "1562.0000", "BUY",  "DELIVERY", 60,  "NSE", "ord-1006-diya-infy-buy",   "SUCCESS",     None),
    (7,  4, 2, "1698.5000", "SELL", "INTRADAY", 30,  "NSE", "ord-1007-diya-hdfc-short", "SUCCESS",     None),
    (8,  5, 2, "1042.0000", "BUY",  "DELIVERY", 100, "BSE", "ord-1008-diya-icici-buy",  "FAILED",      "insufficient funds in linked bank account"),

    (9,  1, 3, "2860.0000", "BUY",  "DELIVERY", 150, "NSE", "ord-1009-rohan-rel-buy",   "SUCCESS",     None),
    (10, 6, 3,  "412.7500", "BUY",  "DELIVERY", 500, "NSE", "ord-1010-rohan-itc-buy",   "SUCCESS",     None),
    (11, 6, 3,  "425.0000", "SELL", "DELIVERY", 200, "NSE", "ord-1011-rohan-itc-trim",  "SUCCESS",     None),
    (12, 7, 3,  "918.4000", "BUY",  "INTRADAY", 120, "NSE", "ord-1012-rohan-tata-in",   "SUCCESS",     None),
    (13, 7, 3,  "930.1500", "BUY",  "INTRADAY", 80,  "NSE", "ord-1013-rohan-tata-add",  "SUCCESS",     None),
    (14, 3, 3, "1571.2500", "BUY",  "DELIVERY", 25,  "NSE", "ord-1014-rohan-infy-buy",  "IN_PROGRESS", None),
    (15, 2, 3, "3888.0000", "BUY",  "INTRADAY", 10,  "NSE", "ord-1015-rohan-tcs-new",   "RECEIVED",    None),

    (16, 5, 4, "1035.5000", "BUY",  "DELIVERY", 45,  "BSE", "ord-1016-meera-icici-buy", "SUCCESS",     None),
    (17, 5, 4, "1050.0000", "BUY",  "DELIVERY", 30,  "BSE", "ord-1017-meera-icici-add", "FAILED",      "client account is suspended"),

    (18, 4, 5, "1705.0000", "BUY",  "INTRADAY", 50,  "NSE", "ord-1018-vikram-hdfc-in",  "SUCCESS",     None),
    (19, 4, 5, "1712.6000", "SELL", "INTRADAY", 50,  "NSE", "ord-1019-vikram-hdfc-out", "SUCCESS",     None),
    (20, 8, 5,  "212.3000", "BUY",  "DELIVERY", 300, "BSE", "ord-1020-vikram-legacy",   "SUCCESS",     None),
    (21, 8, 5,  "205.0000", "SELL", "DELIVERY", 300, "BSE", "ord-1021-vikram-legacy-x", "IN_PROGRESS", None),

    (22, 1, 6, "2799.0000", "BUY",  "DELIVERY", 10,  "NSE", "ord-1022-sanya-rel-buy",   "SUCCESS",     None),
    (23, 1, 6, "2830.5000", "SELL", "DELIVERY", 10,  "NSE", "ord-1023-sanya-rel-exit",  "SUCCESS",     None),
]

ORDER_FIELDS = (
    "order_id", "instrument_id", "client_id", "price_per_unit", "type",
    "product_type", "quantity", "exchange", "idempotency_key", "status",
)


def order_dict(row):
    keys = (
        "order_id", "instrument_id", "client_id", "price_per_unit", "type",
        "product_type", "quantity", "exchange", "idempotency_key", "status",
        "reason",
    )
    return dict(zip(keys, row))


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
        if o["status"] != "SUCCESS":
            continue

        book = holding if o["product_type"] == "DELIVERY" else positions
        key = (o["client_id"], o["instrument_id"])
        qty, avg = book.get(key, (0, Decimal(0)))

        new_qty, new_avg = apply_fill(
            qty, avg, o["type"], o["quantity"], price(o["price_per_unit"])
        )

        if o["product_type"] == "DELIVERY" and new_qty < 0:
            raise SystemExit(
                "seed data is wrong: order " + str(o["order_id"])
                + " would drive portfolio_holding for client " + str(o["client_id"])
                + " / instrument " + str(o["instrument_id"]) + " to " + str(new_qty)
                + ". A delivery holding cannot go negative."
            )

        book[key] = (new_qty, new_avg)

    return holding, positions


def build_bank_account():
    header = ["account_number", "name", "phone", "email", "balance", "bank_name", "ifsc_code"]
    return header, [list(r) for r in BANK_ACCOUNTS]


def build_clients():
    header = ["client_id", "account_number", "name", "email", "phone", "status"]
    return header, [list(r) for r in CLIENTS]


def build_auth():
    header = ["email", "password"]
    return header, [list(r) for r in AUTH]


def build_instruments():
    header = ["instrument_id", "instrument_name", "is_active", "delisted_on"]
    return header, [list(r) for r in INSTRUMENTS]


def build_orders():
    header = list(ORDER_FIELDS)
    rows = []
    for raw in ORDERS:
        o = order_dict(raw)
        rows.append([o[field] for field in ORDER_FIELDS])
    return header, rows


def build_in_progress():
    header = ["progress_id", "order_id", "instrument_id", "quantity"]
    rows = []
    progress_id = 0
    for raw in ORDERS:
        o = order_dict(raw)
        if o["status"] != "IN_PROGRESS":
            continue
        progress_id += 1
        rows.append([progress_id, o["order_id"], o["instrument_id"], o["quantity"]])
    return header, rows


def build_transaction_success():
    header = ["transaction_id", "order_id", "quantity", "value"]
    rows = []
    txn_id = 0
    for raw in ORDERS:
        o = order_dict(raw)
        if o["status"] != "SUCCESS":
            continue
        txn_id += 1
        value = money(price(o["price_per_unit"]) * o["quantity"])
        rows.append([txn_id, o["order_id"], o["quantity"], value])
    return header, rows


def build_transaction_failures():
    header = ["transaction_id", "order_id", "quantity", "value", "reason_for_failure"]
    rows = []
    txn_id = 0
    for raw in ORDERS:
        o = order_dict(raw)
        if o["status"] != "FAILED":
            continue
        if not o["reason"]:
            raise SystemExit(
                "seed data is wrong: order " + str(o["order_id"])
                + " is FAILED but has no failure reason."
            )
        txn_id += 1
        value = money(price(o["price_per_unit"]) * o["quantity"])
        rows.append([txn_id, o["order_id"], o["quantity"], value, o["reason"]])
    return header, rows


def build_portfolio_holding():
    header = ["holding_id", "client_id", "instrument_id", "quantity", "avg_price"]
    holding, _ = settle_orders()
    rows = []
    for idx, key in enumerate(sorted(holding), start=1):
        qty, avg = holding[key]
        rows.append([idx, key[0], key[1], qty, avg])
    return header, rows


def build_portfolio_positions():
    header = ["position_id", "client_id", "instrument_id", "quantity", "avg_price"]
    _, positions = settle_orders()
    rows = []
    for idx, key in enumerate(sorted(positions), start=1):
        qty, avg = positions[key]
        rows.append([idx, key[0], key[1], qty, avg])
    return header, rows


BUILDERS = [
    ("010_bank_account.csv",         build_bank_account),
    ("020_clients.csv",              build_clients),
    ("030_auth.csv",                 build_auth),
    ("040_instruments.csv",          build_instruments),
    ("050_orders.csv",               build_orders),
    ("060_in_progress.csv",          build_in_progress),
    ("070_transaction_success.csv",  build_transaction_success),
    ("080_transaction_failures.csv", build_transaction_failures),
    ("090_portfolio_holding.csv",    build_portfolio_holding),
    ("100_portfolio_positions.csv",  build_portfolio_positions),
]


def render(header, rows):
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if v is None else str(v) for v in row])
    return buf.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="make_seed.py",
        description="Generate the deterministic seed/ CSV files.",
    )
    parser.add_argument("--check", action="store_true",
                        help="do not write; exit non-zero if seed/ is out of date")
    parser.add_argument("--stdout", metavar="FILENAME",
                        help="print one generated file instead of writing anything")
    args = parser.parse_args(argv)

    generated = [(name, render(*builder())) for name, builder in BUILDERS]

    if args.stdout:
        for name, text in generated:
            if name == args.stdout or name.endswith("_" + args.stdout + ".csv"):
                sys.stdout.write(text)
                return 0
        print("no such seed file: " + args.stdout, file=sys.stderr)
        return 2

    SEED_DIR.mkdir(parents=True, exist_ok=True)

    if args.check:
        stale = []
        for name, text in generated:
            path = SEED_DIR / name
            if not path.is_file():
                stale.append(name + " (missing)")
            elif path.read_text(encoding="utf-8") != text:
                stale.append(name + " (differs)")
        if stale:
            print("seed/ is out of date with make_seed.py:")
            for item in stale:
                print("  " + item)
            print("Run: python scripts/make_seed.py")
            return 1
        print("seed/ matches make_seed.py (" + str(len(generated)) + " files)")
        return 0

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
