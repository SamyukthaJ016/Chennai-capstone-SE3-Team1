from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

for path in (str(REPO_ROOT), str(SCRIPTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from db_config import DbConfig, quote_ident, quote_literal

TEST_DB = os.environ.get("TEST_DBNAME", "trading_platform_test")
SCRATCH_DB = TEST_DB + "_scratch"


def config_for(dbname):
    return DbConfig.resolve(SimpleNamespace(dbname=dbname))


def drop_database(cfg, dbname):
    cfg.run(
        dbname="postgres",
        sql=(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = " + quote_literal(dbname) + " AND pid <> pg_backend_pid();"
        ),
    )
    cfg.run(dbname="postgres", sql="DROP DATABASE IF EXISTS " + quote_ident(dbname) + ";")


def create_database(cfg, dbname):
    drop_database(cfg, dbname)
    cfg.run_or_die(
        "creating " + dbname,
        dbname="postgres",
        sql="CREATE DATABASE " + quote_ident(dbname) + ";",
    )
