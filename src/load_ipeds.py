"""Stage 2, Step 2: load the 12 raw IPEDS CSVs into DuckDB and build clean,
decoded views for the SQL agent to query.

Source files are Windows-1252 encoded (not UTF-8 — contains names like
"Saul Jimenez" with accented characters), and hd2023.csv has a UTF-8 BOM
glued onto its UNITID header cell. Both are handled below; verified by
inspecting the raw bytes, not assumed.
"""
from pathlib import Path

import duckdb

RAW = Path("data/ipeds/raw")
DB_PATH = "data/ipeds/ipeds.duckdb"
YEARS = [2021, 2022, 2023]
TABLES = {
    "hd": "hd{y}.csv",
    "ef": "ef{y}a.csv",
    "gr": "gr{y}.csv",
    "ic": "ic{y}_ay.csv",
}


def _has_bom(path: Path) -> bool:
    with open(path, "rb") as f:
        return f.read(3) == b"\xef\xbb\xbf"


def _select_for_year(path: Path, year: int) -> str:
    # Reading the UTF-8 BOM bytes (EF BB BF) as windows-1252 decodes them as
    # three separate characters (i-diaeresis, guillemet, inverted-question) glued
    # onto the next header cell, not a single U+FEFF - verified against the
    # actual decoded column name, not assumed.
    cols = "*"
    if _has_bom(path):
        bom_unitid = "ï»¿UNITID"
        cols = f'* EXCLUDE ("{bom_unitid}"), "{bom_unitid}" AS UNITID'
    # hd2022.csv has a literal tab byte inside a quoted name field ("Ora<TAB>Horn
    # Prouser"), which fools DuckDB's dialect sniffer into guessing tab-delimited
    # and then rejecting the file as ragged. Pinning delim/quote/escape and
    # disabling strict_mode avoids the sniffer entirely; verified this doesn't
    # corrupt that row - it still parses as 5 clean fields (unit_id 497718).
    return (f"SELECT {year} AS year, {cols} FROM read_csv_auto("
            f"'{path.as_posix()}', header=true, all_varchar=true, encoding='windows-1252', "
            f"delim=',', quote='\"', escape='\"', strict_mode=false)")


def build_raw_tables(con: duckdb.DuckDBPyConnection) -> None:
    for name, pattern in TABLES.items():
        selects = [_select_for_year(RAW / pattern.format(y=y), y) for y in YEARS]
        con.execute(f"CREATE OR REPLACE TABLE raw_{name} AS "
                    + " UNION ALL BY NAME ".join(selects))
        count = con.execute(f"SELECT count(*) FROM raw_{name}").fetchone()[0]
        print(f"raw_{name}: {count} rows")


def build_views(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE VIEW institutions AS
        SELECT DISTINCT ON (unit_id)
            TRY_CAST(UNITID AS INTEGER) AS unit_id,
            INSTNM AS name,
            CITY AS city,
            STABBR AS state,
            CASE TRIM(CONTROL)
                WHEN '1' THEN 'Public'
                WHEN '2' THEN 'Private nonprofit'
                WHEN '3' THEN 'Private for-profit'
                ELSE 'Unknown'
            END AS control,
            year AS as_of_year
        FROM raw_hd
        ORDER BY unit_id, year DESC
    """)

    con.execute("""
        CREATE OR REPLACE VIEW fall_enrollment AS
        SELECT
            TRY_CAST(UNITID AS INTEGER) AS unit_id,
            year,
            CASE TRIM(EFALEVEL)
                WHEN '1' THEN 'All students'
                WHEN '2' THEN 'Undergraduate'
                WHEN '12' THEN 'Graduate'
            END AS level,
            TRY_CAST(EFTOTLT AS INTEGER) AS total_students,
            TRY_CAST(EFTOTLM AS INTEGER) AS men,
            TRY_CAST(EFTOTLW AS INTEGER) AS women
        FROM raw_ef
        WHERE TRIM(EFALEVEL) IN ('1', '2', '12')
    """)

    # GR is one row per (institution, cohort-type), not one row per institution.
    # GRTYPE 2/3 = 4-year ("bachelor's or equivalent") adjusted cohort / completers
    # within 150% of normal time; 29/30 = same for 2-year ("associate or
    # certificate") institutions. Verified against gr2021's dictionary
    # Frequencies sheet, not guessed from the column name.
    con.execute("""
        CREATE OR REPLACE VIEW graduation_rates AS
        WITH base AS (
            SELECT
                TRY_CAST(UNITID AS INTEGER) AS unit_id,
                year,
                TRIM(GRTYPE) AS grtype,
                TRY_CAST(GRTOTLT AS INTEGER) AS total
            FROM raw_gr
            WHERE TRIM(GRTYPE) IN ('2', '3', '29', '30')
        )
        SELECT
            cohort.unit_id,
            cohort.year,
            CASE cohort.grtype
                WHEN '2' THEN 'bachelor_or_equivalent'
                WHEN '29' THEN 'associate_or_certificate'
            END AS cohort_type,
            cohort.total AS cohort_size,
            completers.total AS completers_150pct,
            ROUND(completers.total * 100.0 / NULLIF(cohort.total, 0), 1) AS grad_rate_pct
        FROM base cohort
        JOIN base completers
            ON cohort.unit_id = completers.unit_id AND cohort.year = completers.year
            AND ((cohort.grtype = '2' AND completers.grtype = '3')
                 OR (cohort.grtype = '29' AND completers.grtype = '30'))
        WHERE cohort.grtype IN ('2', '29')
    """)

    # IC_AY stores tuition/fees as 6 separate numbered column-pairs (level x
    # residency). Column meanings verified against the ic2021_ay dictionary's
    # varlist sheet, not guessed from the numbering (which skips 4).
    con.execute("""
        CREATE OR REPLACE VIEW tuition AS
        SELECT TRY_CAST(UNITID AS INTEGER) AS unit_id, year,
               'undergraduate' AS level, 'in_district' AS residency,
               TRY_CAST(TUITION1 AS DOUBLE) AS tuition, TRY_CAST(FEE1 AS DOUBLE) AS fees
        FROM raw_ic
        UNION ALL
        SELECT TRY_CAST(UNITID AS INTEGER), year, 'undergraduate', 'in_state',
               TRY_CAST(TUITION2 AS DOUBLE), TRY_CAST(FEE2 AS DOUBLE)
        FROM raw_ic
        UNION ALL
        SELECT TRY_CAST(UNITID AS INTEGER), year, 'undergraduate', 'out_of_state',
               TRY_CAST(TUITION3 AS DOUBLE), TRY_CAST(FEE3 AS DOUBLE)
        FROM raw_ic
        UNION ALL
        SELECT TRY_CAST(UNITID AS INTEGER), year, 'graduate', 'in_district',
               TRY_CAST(TUITION5 AS DOUBLE), TRY_CAST(FEE5 AS DOUBLE)
        FROM raw_ic
        UNION ALL
        SELECT TRY_CAST(UNITID AS INTEGER), year, 'graduate', 'in_state',
               TRY_CAST(TUITION6 AS DOUBLE), TRY_CAST(FEE6 AS DOUBLE)
        FROM raw_ic
        UNION ALL
        SELECT TRY_CAST(UNITID AS INTEGER), year, 'graduate', 'out_of_state',
               TRY_CAST(TUITION7 AS DOUBLE), TRY_CAST(FEE7 AS DOUBLE)
        FROM raw_ic
    """)


if __name__ == "__main__":
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    build_raw_tables(con)
    build_views(con)
    for view in ("institutions", "fall_enrollment", "graduation_rates", "tuition"):
        n = con.execute(f"SELECT count(*) FROM {view}").fetchone()[0]
        print(f"{view}: {n} rows")
    con.close()
