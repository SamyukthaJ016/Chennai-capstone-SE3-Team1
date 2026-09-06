from __future__ import annotations

import pytest

import verify_db as V

ENTITY_TABLES = sorted(V.ENTITY_TABLES)


@pytest.mark.parametrize("table", ENTITY_TABLES)
def test_the_entity_class_exists(table):
    class_name = V.ENTITY_TABLES[table][0]
    assert V.entity_fields(class_name), class_name + " declares no fields"


@pytest.mark.parametrize("table", ENTITY_TABLES)
def test_the_table_has_every_column_its_entity_declares(built_db, table):
    verifier = V.Verifier(built_db)
    want = V.entity_columns(table)
    got = verifier.columns_of(table)
    missing = [c for c in want if c not in got]
    assert not missing, table + " is missing " + str(missing)


@pytest.mark.parametrize("table", ENTITY_TABLES)
def test_the_table_has_no_column_its_entity_does_not_declare(built_db, table):
    verifier = V.Verifier(built_db)
    want = V.entity_columns(table)
    got = verifier.columns_of(table)
    extra = [c for c in got if c not in want]
    assert not extra, table + " has " + str(extra) + " with no matching entity field"


@pytest.mark.parametrize("conname,enum_name", V.ENUM_CONSTRAINTS)
def test_the_check_vocabulary_matches_the_enum(built_db, conname, enum_name):
    import re

    verifier = V.Verifier(built_db)
    definition = verifier.constraint_def(conname)
    assert definition, conname + " does not exist"
    in_sql = set(re.findall(r"'([A-Z][A-Z0-9_]*)'", definition))
    assert in_sql == V.enum_constants(enum_name)


@pytest.mark.parametrize("section,name,check", V.CHECKS,
                         ids=[s + " " + n for s, n, _ in V.CHECKS])
def test_acceptance_check(built_db, section, name, check):
    check(V.Verifier(built_db))


def test_verify_db_leaves_the_database_unchanged(built_db, table_counts):
    before = table_counts(built_db)
    verifier = V.Verifier(built_db)
    for _, _, check in V.CHECKS:
        try:
            check(verifier)
        except V.CheckFailed:
            pass
    assert table_counts(built_db) == before
