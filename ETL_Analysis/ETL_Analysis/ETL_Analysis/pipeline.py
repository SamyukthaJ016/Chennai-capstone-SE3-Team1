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
from pathlib import Path

from . import (extract_fixtures, load as load_module,
               load_print as load_print_module, report as report_module,
               symbols as symbols_module, transform as transform_module)

DEFAULT_SYMBOLS = ["RELIANCE.NS", "INFY.NS", "TATASTEEL.BO"]

log = logging.getLogger("pipeline")


def run(symbols: list[str], extract_fn=None, show_rows: int | None = None,
        repair: bool = True, db_path: str = load_module.DEFAULT_DB_PATH,
        to_console: bool = False,
        report_path: str | None = report_module.DEFAULT_REPORT_PATH,
        inline_js: bool = True) -> int:
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
    if to_console:
        log.info("load: %d result(s) -> console", len(results))
        totals = load_print_module.load_many(results, show_rows=show_rows)
    else:
        log.info("load: %d result(s) -> %s", len(results), db_path)
        try:
            totals = load_module.load_many(results, db_path=db_path)
        except ImportError as exc:
            log.error("%s", exc)
            return 1

    # --- REPORT ----------------------------------------------------------
    # Not an ETL step: renders what the pipeline produced. Written after
    # the load so a report only ever describes data that actually landed.
    if report_path:
        try:
            written = report_module.write_report(
                results, totals.get("run_id", "local"),
                transform_module.metrics, report_path, inline_js=inline_js,
            )
        except report_module.PlotlyMissing as exc:
            log.error("%s", exc)
            log.error("the data loaded fine; only the report was skipped")
            _report(totals, failures)
            return 1
        totals["report_path"] = written
        log.info("report: %s", written)

    _report(totals, failures)
    return 0


def _report(totals: dict, failures: list) -> None:
    print()
    print("=" * 78)
    print("  RUN SUMMARY")
    print("=" * 78)
    if totals.get("db_path"):
        print(f"  store .............. {totals['db_path']}")
        print(f"  run id ............. {totals['run_id']}")
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
    bad = totals.get("reconciliation_failures")
    if bad:
        print(f"  RECONCILIATION FAILED for {len(bad)} run row(s): "
              f"candles_in != kept + quarantined")
        for entry in bad:
            print(f"      {entry}")
    elif totals.get("db_path"):
        print(f"  reconciled ......... candles_in = kept + quarantined")
    if totals.get("report_path"):
        print(f"  report ............. {totals['report_path']}")
    if totals.get("metrics_written"):
        print(f"  metrics stored ..... {totals['metrics_written']}")
    if failures:
        print(f"  symbols failed ..... {len(failures)}")
        for symbol, message in failures:
            print(f"      {symbol}: {message}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fauxnance candles ETL pipeline")
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="symbols to pull. Omit to pull every symbol in "
                             "the universe file (offline runs use the fixture "
                             "symbols instead)")
    parser.add_argument("--exchanges", nargs="+", default=None,
                        metavar="VENUE",
                        help="keep only these venues from the universe file: "
                             "NSE BSE")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap how many symbols to pull from the file")
    parser.add_argument("--list-symbols", action="store_true",
                        help="print the universe file grouped by venue, then "
                             "exit without pulling anything")
    parser.add_argument("--symbol-file", default=None, metavar="PATH",
                        help="read the symbol universe from this file "
                             "instead of the bundled symbols_nse_bse.txt")
    parser.add_argument("--no-quota-check", action="store_true",
                        help="skip the /usage check before a large pull")
    parser.add_argument("--live", action="store_true",
                        help="use the live Fauxnance client instead of fixtures")
    parser.add_argument("--rows", type=int, default=None,
                        help="cap printed rows per symbol")
    parser.add_argument("--db", default=load_module.DEFAULT_DB_PATH,
                        help="DuckDB file to load into (default: %(default)s)")
    parser.add_argument("--print", dest="to_console", action="store_true",
                        help="print to the console instead of loading DuckDB")
    parser.add_argument("--report", default=report_module.DEFAULT_REPORT_PATH,
                        help="HTML report to write (default: %(default)s)")
    parser.add_argument("--no-report", action="store_true",
                        help="skip writing the HTML report")
    parser.add_argument("--cdn-js", action="store_true",
                        help="load Plotly from a CDN instead of embedding it. "
                             "Much smaller file, but it needs a network to "
                             "render, which the sprint's artefact rule forbids")
    parser.add_argument("--strict", action="store_true",
                        help="quarantine every defect instead of repairing "
                             "defects 4, 5 and 6")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(name)s: %(message)s",
    )

    # --- decide the symbol list -----------------------------------------
    # Two cases, and no third. Either you named the symbols, or the universe
    # file is used in full.
    if args.list_symbols:
        universe = symbols_module.load_symbol_file(args.symbol_file)
        grouped = symbols_module.group_by_exchange(universe)
        print(f"\n{len(universe)} symbol(s) in the universe\n")
        for venue, count in grouped.items():
            members = symbols_module.filter_symbols(universe, exchanges=[venue])
            print(f"  {venue:<8} {count:>4}  {', '.join(members[:8])}"
                  f"{' ...' if count > 8 else ''}")
        print()
        return 0

    if args.symbols:
        symbol_list = args.symbols
    elif args.live:
        # No symbols named: pull the whole universe file.
        symbol_list = symbols_module.filter_symbols(
            symbols_module.load_symbol_file(args.symbol_file),
            exchanges=args.exchanges, limit=args.limit,
        )
        if not symbol_list:
            log.error("no symbols left after filtering; nothing to pull")
            return 1
        try:
            plan = symbols_module.plan_pull(
                symbol_list, check_quota=not args.no_quota_check)
        except symbols_module.QuotaTooLow as exc:
            log.error("%s", exc)
            return 1
        log.info("pulling %d symbol(s) from %s%s", len(symbol_list),
                 Path(args.symbol_file).name if args.symbol_file
                 else symbols_module.SYMBOL_FILE.name,
                 f"; {plan['remaining']} request(s) left today"
                 if plan["remaining"] is not None else "")
    else:
        # Offline: the fixtures are the only symbols there are.
        symbol_list = DEFAULT_SYMBOLS

    extract_fn = None
    if args.live:
        try:
            from .extract_live import extract as extract_fn  # noqa: F401
        except ImportError as exc:
            log.error("--live needs extract_live.py with a real key: %s", exc)
            return 1

    return run(symbol_list, extract_fn=extract_fn, show_rows=args.rows,
               repair=not args.strict, db_path=args.db,
               to_console=args.to_console,
               report_path=None if args.no_report else args.report,
               inline_js=not args.cdn_js)


if __name__ == "__main__":
    sys.exit(main())
