# IPEDS Data Sources

4 tables x 3 years, downloaded from the IPEDS Data Center (National Center for
Education Statistics, U.S. Dept. of Education). All free, public, no API key.

## Why 2021–2023, not more recent

Checked directly (not assumed) on 2026-11-09: IPEDS survey components release on
different schedules. `HD2024` (Institutional Characteristics/Directory) and a
general `IC2024` component are already out, but **`EF2024A` (Fall Enrollment),
`GR2024` (Graduation Rates), and `IC2024_AY` (tuition/fees) all return 404** —
not yet released. Since all 4 tables are needed for every year, **2023 is
currently the most recent year where the full set exists.** Re-check this when
revisiting the project — IPEDS releases roughly annually, so 2024 data should
fill in eventually.

## Download pattern

Files live at a predictable direct URL, confirmed by testing (not from official
docs — the IPEDS Data Center itself is an interactive form with no public URL
pattern documented):

```
https://nces.ed.gov/ipeds/datacenter/data/{SURVEY}{YEAR}.zip          # data
https://nces.ed.gov/ipeds/datacenter/data/{SURVEY}{YEAR}_Dict.zip     # dictionary
```

Where `{SURVEY}` is `HD`, `EF...A`, `GR`, or `IC..._AY` (see table below).

## Files

| Table | Survey code | Years | Data URL pattern | Downloaded |
|---|---|---|---|---|
| Institutions (Directory) | `HD` | 2021, 2022, 2023 | `HD{YYYY}.zip` | 2026-11-09 |
| Fall enrollment | `EF...A` | 2021, 2022, 2023 | `EF{YYYY}A.zip` | 2026-11-09 |
| Graduation rates | `GR` | 2021, 2022, 2023 | `GR{YYYY}.zip` | 2026-11-09 |
| Tuition and fees | `IC..._AY` | 2021, 2022, 2023 | `IC{YYYY}_AY.zip` | 2026-11-09 |

## Revised vs. original files

IPEDS re-releases some years' data as a correction after the initial release.
Where both exist, the revised version was kept (original discarded):

- `ef2021a.csv`, `ef2022a.csv` — used the `_rv` (revised) release
- `gr2021.csv`, `gr2022.csv` — used the `_rv` (revised) release
- 2023 files for both surveys have no revision yet (too recently released)
- `hd*.csv` and `ic*_ay.csv` — no revisions exist for any of the 3 years

## Filename normalization

The source zip for `HD2023` unzips to `HD2023.csv` (capitalized), inconsistent
with `hd2021.csv` / `hd2022.csv`. Renamed to lowercase for consistency — matters
because `src/load_ipeds.py`'s file-pattern matching is case-sensitive on Linux/CI
even though Windows ignores it. Same fix applied to the 2023 dictionary file.

## Folder layout

```
data/ipeds/
├── raw/              # unzipped CSVs — hd2021.csv, ef2021a.csv, gr2021.csv, ic2021_ay.csv, ...
└── dictionaries/      # matching .xlsx codebooks, one per survey/year
```
