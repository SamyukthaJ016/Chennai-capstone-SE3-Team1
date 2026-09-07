from __future__ import annotations

import contextlib
import io

import pytest

from dbenv import (
    SCRATCH_DB,
    TEST_DB,
    config_for,
    create_database,
    drop_database,
)
from db_config import DbError, quote_ident


@pytest.fixture(scope="session")
def server():
    try:
        cfg = config_for("postgres")
    except DbError as exc:
        pytest.skip("no usable psql: " + str(exc))

    reachable, detail = cfg.server_reachable()
    if not reachable:
        first_line = detail.splitlines()[0] if detail else "unreachable"
        pytest.skip(
            "no PostgreSQL server at " + cfg.host + ":" + str(cfg.port)
            + " - " + first_line
        )
    return cfg


@pytest.fixture(scope="session")
def built_db(server):
    import apply_db

    cfg = config_for(TEST_DB)
    reported = io.StringIO()
    with contextlib.redirect_stdout(reported):
        code = apply_db.main(["--dbname", TEST_DB, "--reset"])

    if code != 0:
        output = reported.getvalue()
        detail = "\n".join(
            line for line in output.splitlines()
            if line.startswith("FAILED:") or "ERROR" in line.upper()
        )
        raise AssertionError(
            "apply_db.py --reset could not build " + TEST_DB + ":\n"
            + (detail or output[-2000:])
        )
    yield cfg
    drop_database(cfg, TEST_DB)


@pytest.fixture
def scratch_db(server):
    cfg = config_for(SCRATCH_DB)
    create_database(cfg, SCRATCH_DB)
    yield cfg
    drop_database(cfg, SCRATCH_DB)


@pytest.fixture
def table_counts():
    def counts(cfg):
        rows = cfg.rows(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name;"
        )
        return {
            r[0]: int(cfg.scalar("SELECT count(*) FROM " + quote_ident(r[0]) + ";"))
            for r in rows
        }

    return counts
