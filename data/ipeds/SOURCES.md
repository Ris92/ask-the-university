# IPEDS Data Sources

4 tables x 3 years, downloaded from the IPEDS Data Center (National Center for
Education Statistics, U.S. Dept. of Education). All free, public, no API key.

## Why 2021–2023, not more recent

Checked directly on 2026-11-09, corrected after an initial mistake: HD, EF, and
GR for 2024 **do exist** (`HD2024`, `EF2024A`, `GR2024` all resolve). The first
check wrongly said otherwise because it used a URL base path copied from a
third-party GitHub tool (`/ipeds/datacenter/data/`) instead of verifying against
the live NCES site — that path happens to still work for 2021–2023 files, which
masked the error. The real, current path is `/ipeds/complete-data-files/`
(confirmed from the actual page HTML). Under that path, **`IC2024_AY`
(tuition/fees) is the only one of the 4 tables still unreleased for 2024** — it
returns 404 everywhere, including plausible renamed variants.

**Decision: stayed on 2021–2023 anyway**, to keep all 4 tables on one consistent
year window rather than mixing 2022–2024 for three tables with a 2023 holdover
for tuition. Also worth knowing: even "GR2024" doesn't mean 2024 outcomes — IPEDS's
graduation-rate survey reports 150%-time completion for a cohort that *started*
years earlier (the GR2024 release covers the 2018 four-year cohort and the 2021
two-year cohort), so a newer GR file number is about release recency, not more
current student outcomes. Re-check `IC2024_AY` when revisiting the project —
once it's out, 2022–2024 becomes a viable, fully-consistent option.

## Download pattern

Files live at a predictable direct URL — confirmed by testing against the live
page HTML, not from official docs (the IPEDS Data Center itself is an interactive
form with no publicly documented URL pattern):

```
https://nces.ed.gov/ipeds/complete-data-files/{SURVEY}{YEAR}.zip          # data
https://nces.ed.gov/ipeds/complete-data-files/{SURVEY}{YEAR}_Dict.zip     # dictionary
```

Where `{SURVEY}` is `HD`, `EF...A`, `GR`, or `IC..._AY` (see table below). Note:
`/ipeds/datacenter/data/` (an older path, found via a third-party tool) also
resolves for 2021–2023 files, but `/ipeds/complete-data-files/` is the one
confirmed current on the live site — use that one for anything beyond 2023.

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
