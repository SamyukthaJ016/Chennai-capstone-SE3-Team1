from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import pytest

from ETL_Analysis import claims as C
from ETL_Analysis import extract_fixtures as E
from ETL_Analysis import load as L
from ETL_Analysis import store as S
from ETL_Analysis import transform as T


CLAIM_QUERIES = ("QUARTER_STATS_SQL", "RECOVERY_SQL", "REGIME_SQL",
                 "COVERAGE_SQL")


def test_no_claim_query_reads_a_vendor_interpolated_row():
    for name in CLAIM_QUERIES:
        assert "NOT d.synthetic" in getattr(C, name), name


def test_the_universe_keeps_one_listing_per_company():
    assert "primary_listing" in C._UNIVERSE
    assert "PARTITION BY root" in C._UNIVERSE


def test_the_universe_is_derived_rather_than_named():
    for token in ("'NSE'", "'BSE'", ">= 250", "'1d'"):
        assert token not in C._UNIVERSE, token


def test_every_claim_query_is_read_only():
    for name in CLAIM_QUERIES:
        assert S.check_query(C._sql(getattr(C, name), pivot="2026-01-01",
                                    start="2026-01-01", end="2026-04-01"))


def test_the_data_quality_queries_are_where_interpolation_is_read():
    assert "synthetic" in C.VENUE_DISAGREEMENT_SQL
    assert "synthetic" in C.INTERPOLATION_BY_QUARTER_SQL


def test_quarter_labels_convert_to_dates():
    assert C._quarter_start("2026 Q1") == "2026-01-01"
    assert C._quarter_start("2025 Q3") == "2025-07-01"
    assert C._quarter_end_exclusive("2026 Q1") == "2026-04-01"
    assert C._quarter_end_exclusive("2026 Q4") == "2027-01-01"


duckdb = pytest.importorskip("duckdb", reason="the claims are computed in SQL")


SYNTHETIC_SYMBOLS = 25
SYNTHETIC_DAYS_PER_QUARTER = 14


def _synthetic_store(path, symbols=SYNTHETIC_SYMBOLS, quarters=5,
                     crash_quarter=2):
    results = []
    for index in range(symbols):
        name = f"SYM{index:03d}.NS"
        price = 100.0
        rows = []
        for quarter in range(quarters):
            first_of_quarter = date(2025 + quarter // 4,
                                    (quarter % 4) * 3 + 1, 1)
            for day in range(SYNTHETIC_DAYS_PER_QUARTER):
                if quarter == crash_quarter:
                    drift = -0.020 + (index % 5) * 0.0005
                elif quarter > crash_quarter:
                    drift = -0.018 + (index % 11) * 0.008
                else:
                    drift = 0.002 + (index % 7) * 0.0005
                price *= 1 + drift
                rows.append({
                    "symbol": name,
                    "date": first_of_quarter + timedelta(days=day * 4),
                    "interval": "1d",
                    "open": price * 0.995, "high": price * 1.01,
                    "low": price * 0.99, "close": round(price, 4),
                    "adjclose": price, "volume": 10_000 + day,
                    "synthetic": False, "currency": "INR",
                    "repaired": False, "repairs": [],
                })
        results.append({
            "symbol": name, "currency": "INR", "interval": "1d",
            "rows": rows, "quarantined": [],
            "summary": T.summarise_rows(name, rows, [], True),
        })
    L.load_many(results, db_path=str(path))
    return str(path)


@pytest.fixture(scope="module")
def rich_store(tmp_path_factory):
    return _synthetic_store(tmp_path_factory.mktemp("claims") / "w.duckdb")


@pytest.fixture
def rich(rich_store):
    with S.connect(rich_store) as handle:
        yield handle


@pytest.fixture
def findings(rich):
    return C.generate(rich)


def test_the_context_finds_the_selloff_without_being_told(rich):
    context = C.market_context(rich)
    assert context["selloff"] is not None
    assert float(context["selloff"]["median_return_pct"]) < 0
    assert context["rebound"] is not None
    assert context["rebound"]["quarter"] > context["selloff"]["quarter"]


def test_every_claim_is_supported_on_a_rich_store(findings):
    assert findings
    assert all(f.available for f in findings), [
        (f.title, f.reason) for f in findings if not f.available]


def test_every_claim_names_a_magnitude(findings):
    for finding in findings:
        assert re.search(r"\d", finding.headline), finding.id


def test_the_headline_is_built_from_the_measures_it_reports(findings):
    for finding in findings:
        quoted = {f"{abs(m.value):.2f}" for m in finding.measures
                  if m.value is not None}
        quoted |= {f"{abs(m.value):.1f}" for m in finding.measures
                   if m.value is not None}
        quoted |= {f"{abs(m.value):.3f}" for m in finding.measures
                   if m.value is not None}
        assert quoted & set(re.findall(r"\d+\.\d+", finding.headline)), \
            finding.id


def test_the_period_is_derived_from_the_store(findings, rich):
    lo, hi = S.date_bounds(rich)
    for finding in findings:
        assert finding.period
        assert str(hi.year) in finding.period or str(lo.year) in finding.period


def test_every_claim_says_what_to_do_and_what_would_break_it(findings):
    for finding in findings:
        assert len(finding.decision) > 60, finding.id
        assert len(finding.for_developers) > 60, finding.id
        assert len(finding.falsified_if) > 60, finding.id


def test_every_claim_names_the_chart_that_supports_it(findings):
    for finding in findings:
        assert "tab" in finding.supported_by.lower(), finding.id


def test_claim_ids_are_unique(findings):
    ids = [f.id for f in findings]
    assert len(ids) == len(set(ids))


def test_the_quarter_table_matches_what_the_charts_expect(rich):
    from ETL_Analysis import charts

    rows = S.records(rich, C._sql(C.QUARTER_STATS_SQL))
    assert rows
    for builder in (charts.dispersion_figure, charts.quarterly_figure,
                    charts.volatility_figure):
        figure = builder(rows)
        assert figure and figure["data"], builder.__name__


def test_a_different_store_produces_different_claims(tmp_path):
    early = _synthetic_store(tmp_path / "early.duckdb", crash_quarter=1)
    late = _synthetic_store(tmp_path / "late.duckdb", crash_quarter=3)

    with S.connect(early) as handle:
        early_claims = {f.id: f.headline for f in C.generate(handle)}
    with S.connect(late) as handle:
        late_claims = {f.id: f.headline for f in C.generate(handle)}

    assert early_claims and late_claims
    for claim_id, headline in early_claims.items():
        assert headline != late_claims[claim_id], claim_id


def test_the_selloff_quarter_named_in_the_claim_is_the_one_in_the_data(
        tmp_path):
    late = _synthetic_store(tmp_path / "late.duckdb", crash_quarter=3)
    with S.connect(late) as handle:
        context = C.market_context(handle)
        findings = C.generate(handle)
    quarter = context["selloff"]["quarter"]
    assert any(quarter in f.headline for f in findings if f.available)


@pytest.fixture(scope="module")
def thin_store(tmp_path_factory):
    path = tmp_path_factory.mktemp("thin") / "w.duckdb"
    payloads, _ = E.extract_many(["RELIANCE.NS", "INFY.NS", "TATASTEEL.BO"])
    L.load_many(T.transform_many(payloads, repair=True), db_path=str(path))
    return str(path)


def test_a_thin_store_yields_no_claims_rather_than_bad_ones(thin_store):
    with S.connect(thin_store) as handle:
        findings = C.generate(handle)
    assert findings
    assert not any(f.available for f in findings)


def test_an_unsupported_claim_says_why(thin_store):
    with S.connect(thin_store) as handle:
        for finding in C.generate(handle):
            assert finding.reason, finding.id
            assert finding.title
            assert finding.headline == ""


def test_the_reason_counts_correctly_in_the_singular(thin_store):
    with S.connect(thin_store) as handle:
        reason = C.generate(handle)[0].reason
    assert "1 symbols" not in reason


def test_generating_never_raises_on_a_store_it_cannot_use(thin_store):
    with S.connect(thin_store) as handle:
        C.generate(handle)


def test_the_document_is_rendered_from_the_generated_claims(rich, tmp_path):
    destination = tmp_path / "claims.md"
    written = C.write_markdown(rich, str(destination), "w.duckdb",
                               generated_at=datetime(2026, 9, 6, 12, 0))
    assert written == str(destination)
    text = destination.read_text(encoding="utf-8")

    for finding in C.generate(rich):
        if finding.available:
            assert finding.title in text
            assert finding.headline.replace(" -- ", " — ") in text


def test_the_document_says_it_is_generated(rich, tmp_path):
    destination = tmp_path / "claims.md"
    C.write_markdown(rich, str(destination), "w.duckdb")
    text = destination.read_text(encoding="utf-8")
    assert "GENERATED FILE" in text
    assert "python -m ETL_Analysis.claims" in text


def test_the_document_names_the_entry_point(rich, tmp_path):
    destination = tmp_path / "claims.md"
    C.write_markdown(rich, str(destination), "w.duckdb")
    text = re.sub(r"\s+", " ", destination.read_text(encoding="utf-8"))
    assert "__main__" in text
    assert "python -m ETL_Analysis.pipeline" in text


def test_the_document_carries_the_disclaimer(rich, tmp_path):
    destination = tmp_path / "claims.md"
    C.write_markdown(rich, str(destination), "w.duckdb")
    text = re.sub(r"\s+", " ", destination.read_text(encoding="utf-8")).lower()
    assert "not for investment use" in text


def test_the_document_reports_unsupported_claims_rather_than_omitting_them(
        thin_store, tmp_path):
    destination = tmp_path / "claims.md"
    with S.connect(thin_store) as handle:
        C.write_markdown(handle, str(destination), "w.duckdb")
    text = destination.read_text(encoding="utf-8")
    assert "Claims this store cannot support" in text
    assert "needs at least" in text


def test_regenerating_over_the_same_store_is_stable(rich):
    stamp = datetime(2026, 9, 6, 12, 0)
    first = C.render_markdown(C.generate(rich), "w.duckdb", stamp)
    second = C.render_markdown(C.generate(rich), "w.duckdb", stamp)
    assert first == second


def test_the_cli_writes_the_document(rich_store, tmp_path):
    destination = tmp_path / "out" / "claims.md"
    assert C.main(["--db", rich_store, "--out", str(destination)]) == 0
    assert destination.is_file()


def test_the_cli_reports_a_store_it_cannot_open(tmp_path, capsys):
    assert C.main(["--db", str(tmp_path / "nothing.duckdb")]) == 1
    assert "Run the pipeline first" in capsys.readouterr().out
