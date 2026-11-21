"""Stage 2, Step 5: guardrail tests. Run with: pytest tests/test_guardrails.py"""
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sql_agent import MAX_ROWS, UnsafeSQL, run_sql, validate_sql

BLOCKED_QUERIES = [
    "DROP TABLE institutions",
    "SELECT * FROM institutions; DELETE FROM institutions",
    "SELECT * FROM raw_hd",
    "SELECT * FROM duckdb_tables()",
    "SELECT * FROM read_csv('secrets.csv')",
    "ATTACH 'other.db'",
    "UPDATE institutions SET name = 'x'",
    "SELECT * FROM institutions; SELECT * FROM fall_enrollment",
]


@pytest.mark.parametrize("sql", BLOCKED_QUERIES)
def test_blocked_queries_raise_unsafe_sql(sql):
    with pytest.raises(UnsafeSQL):
        validate_sql(sql)


def test_allowed_query_passes():
    safe_sql = validate_sql("SELECT unit_id, name FROM institutions WHERE state = 'OH'")
    assert "LIMIT" in safe_sql


def test_cte_table_name_is_not_flagged_as_unallowed():
    sql = """
        WITH matched_institution AS (
            SELECT unit_id FROM institutions WHERE name ILIKE '%ohio state%' LIMIT 1
        )
        SELECT unit_id FROM matched_institution
    """
    validate_sql(sql)  # should not raise


def test_row_limit_is_added_when_missing():
    safe_sql = validate_sql("SELECT unit_id FROM institutions")
    assert f"LIMIT {MAX_ROWS}" in safe_sql


def test_existing_row_limit_is_not_overridden():
    safe_sql = validate_sql("SELECT unit_id FROM institutions LIMIT 5")
    assert "LIMIT 5" in safe_sql
    assert f"LIMIT {MAX_ROWS}" not in safe_sql


def test_run_sql_blocks_writes_at_the_database_level():
    # A write that somehow slipped past validate_sql must still fail -
    # the read-only connection is the real safety net, not the parser checks.
    with pytest.raises(duckdb.Error):
        run_sql("DELETE FROM raw_hd")


def test_run_sql_executes_a_real_query():
    columns, rows = run_sql("SELECT state FROM institutions WHERE unit_id = 204796")
    assert columns == ["state"]
    assert rows == [("OH",)]
