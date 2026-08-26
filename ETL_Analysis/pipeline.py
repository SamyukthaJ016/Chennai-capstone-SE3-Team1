"""The fourth module: wires extract -> transform -> load and does nothing else.

No parsing, no cleaning, no printing of data. Every line here is either calling
one of the three steps or reporting which step something failed in. If a number
comes out wrong, it came from one of the three modules, not from this one.

Run it:

    python -m ETL_Analysis.pipeline
    python -m ETL_Analysis.pipeline --symbols RELIANCE.NS INFY.NS
    python -m ETL_Analysis.pipeline --live          # once a real key exists

Switching to the live Fauxnance client is the `--live` flag: it swaps which
`extract` callable is bound, and transform and load are untouched.
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import extract_fixtures, load as load_module, transform as transform_module

DEFAULT_SYMBOLS = ["RELIANCE.NS", "INFY.NS", "TATASTEEL.BO"]

log = logging.getLogger("pipeline")


def run(symbols: list[str], extract_fn=None, show_rows: int | None = None,
        repair: bool = True) -> int:
    """Run the pipeline over `symbols`. Returns a process exit code.

    `extract_fn` is injected so the live client can be substituted without
    touching transform or load.
    """
    extract_fn = extract_fn or extract_fixtures.extract

    # --- EXTRACT ---------------------------------------------------------
    payloads = []
    failures = []
    for symbol in symbols:
        try:
            log.info("extract: %s", symbol)
            payloads.append(extract_fn(symbol))
        except Exception as exc:  # noqa: BLE001 - reported per symbol, run continues
            log.error("extract failed for %s: %s", symbol, exc)
            failures.append((symbol, str(exc)))

    if not payloads:
        log.error("no payloads extracted; nothing to transform")
        return 1

    # --- TRANSFORM -------------------------------------------------------
    log.info("transform: %d payload(s) (repair=%s)", len(payloads), repair)
    results = transform_module.transform_many(payloads, repair=repair)

    # --- LOAD ------------------------------------------------------------
    log.info("load: %d result(s)", len(results))
    totals = load_module.load_many(results, show_rows=show_rows)

    _report(totals, failures)
    return 0


def _report(totals: dict, failures: list) -> None:
    print()
    print("=" * 78)
    print("  RUN SUMMARY")
    print("=" * 78)
    print(f"  symbols processed .. {totals['symbols']}")
    print(f"  rows loaded ........ {totals['rows_loaded']}")
    print(f"  rows repaired ...... {totals.get('rows_repaired', 0)}")
    if totals.get("repairs"):
        for code, count in sorted(totals["repairs"].items()):
            print(f"      {code:<20} {count}")
    print(f"  rows quarantined ... {totals['rows_quarantined']}")
    if totals["reasons"]:
        for reason, count in sorted(totals["reasons"].items()):
            print(f"      {reason:<20} {count}")
    if failures:
        print(f"  symbols failed ..... {len(failures)}")
        for symbol, message in failures:
            print(f"      {symbol}: {message}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fauxnance candles ETL pipeline")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS,
                        help="symbols to pull (default: %(default)s)")
    parser.add_argument("--live", action="store_true",
                        help="use the live Fauxnance client instead of fixtures")
    parser.add_argument("--rows", type=int, default=None,
                        help="cap printed rows per symbol")
    parser.add_argument("--strict", action="store_true",
                        help="quarantine every defect instead of repairing "
                             "defects 4, 5 and 6")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(name)s: %(message)s",
    )

    extract_fn = None
    if args.live:
        try:
            from .extract_live import extract as extract_fn  # noqa: F401
        except ImportError as exc:
            log.error("--live needs extract_live.py with a real key: %s", exc)
            return 1

    return run(args.symbols, extract_fn=extract_fn, show_rows=args.rows,
               repair=not args.strict)


if __name__ == "__main__":
    sys.exit(main())
