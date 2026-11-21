# IPEDS Schema (for SQL generation)

Four views in `data/ipeds/ipeds.duckdb`, built by `load_ipeds.py` from IPEDS data,
years 2021-2023. Every table joins to `institutions` on `unit_id`. There is no
`students`, `courses`, or `admissions` table — only directory info, enrollment
counts, graduation-rate cohorts, and tuition/fees. If a question asks about
anything else (acceptance rate, majors offered, rankings, specific student
records), answer `CANNOT_ANSWER` instead of guessing a query.

## institutions

One row per institution (its most recent directory snapshot, 2021-2023).

| column       | type    | notes |
|---|---|---|
| `unit_id`    | INTEGER | primary key, joins to every other view |
| `name`       | VARCHAR | official IPEDS name, often includes a campus suffix, e.g. `'Ohio State University-Main Campus'`, not `'Ohio State University'` — match with `ILIKE '%ohio state%'` style patterns, not `=`, unless the user gave the exact name |

**Multi-campus disambiguation — always use this pattern for any name-based lookup,
on every view, not only when you expect multiple matches.** An `ILIKE` match on a
university's name can silently return several rows (`'%ohio state university%'`
matches 5 campuses: Lima, Mansfield, Marion, Newark, Main; `'%university of
michigan%'` matches 3: Ann Arbor, Dearborn, Flint). You can't check how many rows
a name pattern matches before committing to the final query, so always resolve
the institution through this CTE first, rather than filtering `institutions.name`
directly inline — it's harmless when a name matches only one row and correct when
it matches several:

```sql
WITH matched_institution AS (
    SELECT m.unit_id
    FROM institutions m
    JOIN fall_enrollment f ON f.unit_id = m.unit_id
    WHERE m.name ILIKE '%<search term>%'
      AND f.year = 2023 AND f.level = 'All students'
    ORDER BY f.total_students DESC
    LIMIT 1
)
```

Then join every other view to `matched_institution.unit_id` instead of filtering
`institutions` by name again. The flagship/main campus is reliably the largest by
enrollment; matching on a literal string like `"Main Campus"` doesn't generalize,
since not every multi-campus system names its flagship that way. Only skip this
pattern if the question explicitly asks to compare multiple campuses, or already
names one exactly (e.g. `'Pennsylvania State University-Main Campus'`).
| `city`       | VARCHAR | |
| `state`      | VARCHAR | 2-letter postal abbreviation, e.g. `'OH'` |
| `control`    | VARCHAR | one of: `'Public'`, `'Private nonprofit'`, `'Private for-profit'`, `'Unknown'` |
| `as_of_year` | INTEGER | which year's directory snapshot `name`/`city`/`state`/`control` came from; not generally useful to filter on |

## fall_enrollment

One row per (institution, year, level) — 3 rows per institution per year.

| column           | type    | notes |
|---|---|---|
| `unit_id`        | INTEGER | |
| `year`           | INTEGER | `2021`, `2022`, or `2023` — the fall term the headcount describes |
| `level`          | VARCHAR | one of: `'All students'`, `'Undergraduate'`, `'Graduate'` |
| `total_students` | INTEGER | headcount |
| `men`            | INTEGER | |
| `women`          | INTEGER | |

`'All students'` is not `'Undergraduate' + 'Graduate'` at every school — some
offer non-degree-seeking programs counted only in the total. Use `level = 'All
students'` for a school's overall enrollment, not a `SUM` across levels.

## graduation_rates

One row per (institution, year) — each institution reports exactly one
`cohort_type` (never both), depending on whether it primarily grants bachelor's
or associate/certificate credentials.

| column               | type    | notes |
|---|---|---|
| `unit_id`            | INTEGER | |
| `year`               | INTEGER | the IPEDS **survey release year**, not the year the cohort graduated — see caveat below |
| `cohort_type`        | VARCHAR | one of: `'bachelor_or_equivalent'` (4-year institutions), `'associate_or_certificate'` (2-year institutions) |
| `cohort_size`         | INTEGER | adjusted cohort (students who started, minus allowed exclusions) |
| `completers_150pct`  | INTEGER | of that cohort, how many completed within 150% of normal time |
| `grad_rate_pct`      | DOUBLE  | `completers_150pct / cohort_size * 100`, rounded to 1 decimal — this is the commonly-cited "six-year graduation rate" (4-year schools) or "three-year rate" (2-year schools) |

**Caveat — `year` lags cohort start by several years.** A `graduation_rates` row
with `year = 2023` reports the outcome of a cohort that *started college* around
2017 (4-year, 150%-of-normal-time = 6 years) or 2021 (2-year, 150% = 3 years). It
does **not** mean "the 2023 graduating class" or "students enrolled in 2023." If
a question asks about a specific *starting* cohort year, this data can't answer
it precisely — say so rather than assuming `year` means cohort-start year.

## tuition

One row per (institution, year, level, residency) — 6 rows per institution per
year.

| column       | type    | notes |
|---|---|---|
| `unit_id`    | INTEGER | |
| `year`       | INTEGER | the academic year, e.g. `2023` means 2023-24 |
| `level`      | VARCHAR | one of: `'undergraduate'`, `'graduate'` |
| `residency`  | VARCHAR | one of: `'in_district'`, `'in_state'`, `'out_of_state'` |
| `tuition`    | DOUBLE  | nominal USD, not inflation-adjusted |
| `fees`       | DOUBLE  | required fees, nominal USD |

`in_district` and `in_state` are frequently identical (most 4-year publics don't
distinguish the two) — this is expected, not a data error.

## Join rules

- Everything joins to `institutions` on `unit_id`.
- `fall_enrollment`, `graduation_rates`, and `tuition` all have their own `year`
  column — filter each on the year(s) actually asked about, don't assume they
  align (`graduation_rates.year` especially means something different, see above).
- There is no cross-table primary key other than `unit_id`; never join
  `fall_enrollment` to `tuition` or `graduation_rates` directly on `year` alone
  without going through `institutions` first, since `unit_id` is the only
  reliable join key.

## Worked examples

**Q: What was Ohio State's total enrollment in 2023?**
```sql
WITH matched_institution AS (
    SELECT m.unit_id
    FROM institutions m
    JOIN fall_enrollment f ON f.unit_id = m.unit_id
    WHERE m.name ILIKE '%ohio state university%'
      AND f.year = 2023 AND f.level = 'All students'
    ORDER BY f.total_students DESC
    LIMIT 1
)
SELECT f.total_students
FROM matched_institution mi
JOIN fall_enrollment f ON f.unit_id = mi.unit_id
WHERE f.year = 2023 AND f.level = 'All students';
```
Without `matched_institution`, `WHERE i.name ILIKE '%ohio state university%'`
alone would return 5 rows (one per Ohio State campus) instead of the single
answer the question meant.

**Q: Which public universities in Ohio had a six-year graduation rate above 80% in 2023?**
```sql
SELECT i.name, g.grad_rate_pct
FROM institutions i
JOIN graduation_rates g ON i.unit_id = g.unit_id
WHERE i.state = 'OH' AND i.control = 'Public'
  AND g.cohort_type = 'bachelor_or_equivalent' AND g.year = 2023
  AND g.grad_rate_pct > 80
ORDER BY g.grad_rate_pct DESC;
```
No `matched_institution` needed here — this question asks about many schools at
once (filtered by state/control), not one named university, so there's no name
to disambiguate.

**Q: How did out-of-state undergrad tuition at Ohio State change from 2021 to 2023?**
```sql
WITH matched_institution AS (
    SELECT m.unit_id
    FROM institutions m
    JOIN fall_enrollment f ON f.unit_id = m.unit_id
    WHERE m.name ILIKE '%ohio state university%'
      AND f.year = 2023 AND f.level = 'All students'
    ORDER BY f.total_students DESC
    LIMIT 1
)
SELECT t.year, t.tuition
FROM matched_institution mi
JOIN tuition t ON t.unit_id = mi.unit_id
WHERE t.level = 'undergraduate' AND t.residency = 'out_of_state'
  AND t.year IN (2021, 2023)
ORDER BY t.year;
```

**Q: What is Ohio State's six-year graduation rate in 2023?**
```sql
WITH matched_institution AS (
    SELECT m.unit_id
    FROM institutions m
    JOIN fall_enrollment f ON f.unit_id = m.unit_id
    WHERE m.name ILIKE '%ohio state university%'
      AND f.year = 2023 AND f.level = 'All students'
    ORDER BY f.total_students DESC
    LIMIT 1
)
SELECT g.grad_rate_pct
FROM matched_institution mi
JOIN graduation_rates g ON g.unit_id = mi.unit_id
WHERE g.year = 2023 AND g.cohort_type = 'bachelor_or_equivalent';
```

**Q: How has University of Michigan's undergraduate enrollment changed from 2021 to 2023?**
```sql
WITH matched_institution AS (
    SELECT m.unit_id
    FROM institutions m
    JOIN fall_enrollment f ON f.unit_id = m.unit_id
    WHERE m.name ILIKE '%university of michigan%'
      AND f.year = 2023 AND f.level = 'All students'
    ORDER BY f.total_students DESC
    LIMIT 1
)
SELECT f.year, f.total_students
FROM matched_institution mi
JOIN fall_enrollment f ON f.unit_id = mi.unit_id
WHERE f.level = 'Undergraduate' AND f.year IN (2021, 2023)
ORDER BY f.year;
```
Same disambiguation pattern as the Ohio State examples above, applied to a
different view (`fall_enrollment` instead of `graduation_rates`) and a different
school (University of Michigan: Ann Arbor, Dearborn, Flint) — the pattern itself
doesn't change per table.

**Q: What is Ohio State's undergraduate acceptance rate?**
`CANNOT_ANSWER` — this dataset has no admissions data (applications, admits,
acceptance rate). Only directory info, enrollment, graduation rates, and
tuition/fees are available.
