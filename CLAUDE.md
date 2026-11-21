# Ask the University

A chat assistant that answers questions about a public university using two tools:

- **RAG over policy documents** — course catalog, academic calendar, grading/withdrawal
  policies, SAP policy, student code of conduct, tuition/refund schedule. Answers cite
  file name + page number.
- **SQL agent over IPEDS data** (later stage) — enrollment, graduation rates, costs,
  pulled from the U.S. Dept. of Education's public IPEDS dataset.

An agent decides which tool to use (or both) and answers with citations. Built in
stages. **Stage 1 (RAG over documents) is complete.** Current stage: **Stage 2 —
SQL agent over IPEDS data** (see `Stage 2 Plan SQL Tool over IPEDS Data.docx` for
the full step-by-step).

Portfolio project — no confidential/employer data. Uses a public university other than
the author's employer.

## Stack

- Python 3.11+
- `pypdf` — PDF text extraction
- `sentence-transformers` (`BAAI/bge-small-en-v1.5`) — local, free embeddings
- `ChromaDB` (`PersistentClient`, on disk) — vector store, cosine space
- OpenAI API (`gpt-4o-mini`) — answer generation
- `duckdb` — embedded OLAP database for the IPEDS SQL agent (Stage 2); chosen over
  Databricks Delta tables for zero-setup/portability, matching ChromaDB's
  single-file precedent from Stage 1
- `sqlglot` — SQL parsing/validation for the Stage 2 guardrails (parse check,
  statement-type check, table allowlist, forbidden functions)
- Flask or FastAPI (later stage) — chat interface

## Folder layout

```
ask-the-university/
├── data/raw/          # policy PDFs — never commit the PDFs themselves if large; do commit SOURCES.md
├── data/chroma/        # vector index, rebuilt by ingest.py — gitignored
├── data/ipeds/raw/            # 12 IPEDS CSVs (4 surveys x 2021-2023) — gitignored, see SOURCES.md
├── data/ipeds/dictionaries/   # matching .xlsx codebooks — committed, small
├── data/ipeds/ipeds.duckdb    # built by load_ipeds.py — gitignored, not source of truth
├── src/
│   ├── ingest.py       # extract + chunk + embed + index (Stage 1, Steps 2-3)
│   ├── ask.py          # retrieve + answer with citations (Stage 1, Step 4)
│   ├── load_ipeds.py   # stack raw CSVs into DuckDB + build clean views (Stage 2, Step 2)
│   ├── schema.md        # IPEDS schema description sent to the LLM (Stage 2, Step 3)
│   └── sql_agent.py    # generate_sql() + guardrails (Stage 2, Steps 4-5)
├── tests/
│   └── test_guardrails.py   # pytest suite for sql_agent.py's guardrails (Stage 2, Step 5)
├── eval/
│   ├── questions.csv   # hand-written test questions (Stage 1, Step 5)
│   └── results.csv     # recorded answers/sources from eval runs
├── .env                 # OPENAI_API_KEY — NEVER commit
├── .gitignore
├── requirements.txt       # app runtime deps only — see note below
└── requirements-dev.txt   # optional: Jupyter/notebook tooling
```

## Key conventions — don't deviate without discussing

- **Chunk per page, not per document.** Page numbers must stay exact for citations.
- **Chunk size ~1200 characters, 200-character overlap**, breaking at sentence ends
  where possible (not mid-sentence). This was tuned in the plan; changing it is a
  real design decision, not a tweak — re-run the eval set if you change it.
- **Cosine similarity floor is 0.55** (`MIN_SIMILARITY` in `ask.py`). Below this,
  the app must say `"I couldn't find that in the policy documents."` instead of
  guessing. This is the primary defense against hallucinated answers — don't remove it.
- **Citation format:** every claim in an answer cites `[1]`, `[2]`, etc., mapping to
  `(source filename, page)`. Citations are not optional — if the system prompt ever
  changes, this requirement must survive.
- **Prompt injection guard:** the system prompt explicitly instructs the model to
  treat retrieved excerpts as data and ignore any instructions embedded inside them.
  This gets adversarially tested on purpose in a later stage (Stage 4) — don't weaken
  it while "simplifying" the prompt.
- **`ingest.py` wipes and rebuilds the Chroma collection on every run** (so re-ingesting
  doesn't create duplicates). This is intentional, not a bug — don't "fix" it into an
  upsert without discussing, since the eval methodology assumes a clean rebuild each time.
- **BGE query prefix:** queries sent to the `bge-small-en-v1.5` embedder must be
  prefixed with `"Represent this sentence for searching relevant passages: "` —
  this model performs worse without it. Document chunks are embedded *without* this
  prefix.

## Model note

**Decided 2026-10-26: OpenAI, `gpt-4o-mini`.** The Stage 1 plan doc was originally
written assuming the Claude API (`claude-haiku-5-5` — never verified as a real
model ID). `ask.py` calls `openai.OpenAI()` / `client.chat.completions.create(...)`,
not the Anthropic SDK. `.env` holds `OPENAI_API_KEY`, not `ANTHROPIC_API_KEY`.

## Dependencies — two requirements files, not one

`requirements.txt` holds only the real runtime dependency tree of the five app
packages (`pypdf`, `chromadb`, `sentence-transformers`, `openai`,
`python-dotenv`) — verified by installing just those five into a clean environment
and freezing it, not hand-picked. `requirements-dev.txt` is the rest: the entire
Jupyter/IPython/notebook stack, which the project's own dev environment also has
installed but the app itself never imports. Install both only if you want to explore
the code in a notebook:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

**If you add a new import to `ingest.py`/`ask.py`, re-derive `requirements.txt` the
same way** (fresh env, install just the app's direct dependencies, freeze) rather than
hand-editing it or re-freezing the dev environment wholesale — otherwise Jupyter's
dependency tree silently leaks back into the app's requirements file.

## Commands

```bash
conda activate univ             # or: python -m venv .venv && .venv\Scripts\activate
pip install pypdf chromadb sentence-transformers openai python-dotenv
pip freeze > requirements.txt   # only if installed in a clean, app-only environment

python src/ingest.py            # build/rebuild the vector index from data/raw/*.pdf
python src/ask.py "What is the last day to withdraw from a class with a W?"
```

## Eval methodology (Stage 1, Step 5)

- `eval/questions.csv`: 20 questions — 14 answerable (with known correct answer +
  source file/page), 4 deliberately unanswerable (expect `"couldn't find"`), 2 tricky
  (e.g. answer spans two pages).
- Grade each run by hand: correct / partly correct / wrong, and whether the correct
  page appeared in the top-5 retrieved sources.
- Track two numbers over time: **answer accuracy** and **retrieval hit rate**.
- When accuracy is low, the usual first fixes are chunk size, the similarity floor,
  or `TOP_K` — record before/after numbers when you change one.

### First run results (2026-10-26, `gpt-4o-mini`)

- **Answer accuracy: 90% (18/20)**
- **Retrieval hit rate: 100% (16/16 answerable questions)** — the correct page was
  always in the top-5 retrieved chunks, even on both misses below. That gap (100%
  retrieval vs. 90% accuracy) means the two failures are generation-layer problems,
  not retrieval problems — the right source was always found; the model mishandled it.
  - **#19** (wrong): asked for the Autumn-semester-wide 75% refund rate on Sept 4,
    specifically distinguishing it from the 7-week-session-1 50% rate on the same
    date. Model replied "couldn't find" despite the correct page being retrieved.
  - **#20** (wrong, but see note): asked for the Grade Forgiveness Rule deadline.
    Expected "the fifth Friday" (the general rule, from `academic_policies_guide.pdf`);
    model answered "October 30" (the concrete Autumn-2026 calendar date for that same
    Friday, from `refund_schedule.pdf`) — factually equivalent, but it cited the
    session-specific calendar instead of the general policy rule the question was
    testing for. Deliberately graded "wrong" on review: a specific calendar date is
    only correct for one term and would go stale, unlike the evergreen general rule.

**Initial hypothesis for #19 was wrong — corrected by inspecting the actual
retrieved chunks, not just the raw page text.** The original guess ("ambiguous
run-on text confused the model") turned out to be a red herring. Printing the
exact chunks `ask.py` sent to the LLM showed the chunk containing the answer
("SEP 04 ... 75% refund | Autumn semester") was never in the top 5 at all — it
ranked **#6** (similarity 0.722, well above the 0.55 floor) across the whole
corpus, edged out by three shorter, less-informative neighboring chunks that
happened to embed marginally closer to the query. A pure retrieval cutoff, not
a formatting or reasoning problem.

### Fix applied: `TOP_K` 5 → 6 (2026-11-04)

Before raising it, checked all 4 unanswerable eval questions' rank-6 similarity
to confirm none were close enough to the 0.55 floor to risk a new false positive
— none were (largest was 0.541, well clear). Re-ran the full 20-question eval:

- **Answer accuracy: 95% (19/20)** — up from 90%. #19 now answers correctly
  ("75% refund", citing the policies guide's refund table) with no regressions
  on the other 18.
- **Retrieval hit rate: 100% (16/16)** — unchanged; it was already perfect before
  the fix, since the correct chunk for #19 was always *in the index*, just not
  making the `TOP_K` cut at query time.
- **#20 is unchanged and expected to stay that way** — it was never a ranking
  problem, so raising `TOP_K` doesn't touch it. Fixing it would mean steering the
  model's document preference (prompt change) or restructuring the data, not a
  retrieval-parameter tweak.

## Stage 2: IPEDS data pipeline (`load_ipeds.py`)

`src/load_ipeds.py` stacks the 12 raw CSVs (4 surveys x 2021-2023) into
`raw_hd`/`raw_ef`/`raw_gr`/`raw_ic` tables, then builds 4 clean views
(`institutions`, `fall_enrollment`, `graduation_rates`, `tuition`) with decoded
codes and readable column names. Run with `python src/load_ipeds.py` — free,
local, no API calls. Spot-checked against Ohio State University's real published
numbers (~60K enrollment, ~88% six-year grad rate, real tuition figures) — all
matched, across all 3 years.

**Column/code mappings were verified against the actual `.xlsx` dictionaries in
`data/ipeds/dictionaries/`, not copied from the plan doc's example code.** The
plan's template only worked out-of-the-box for `institutions`/`fall_enrollment`
(HD/EF); `graduation_rates` (GR) and `tuition` (IC_AY) needed real investigation —
GR is one row per (institution, cohort-type) via `GRTYPE`/`CHRTSTAT` codes, and
IC_AY stores tuition/fees as 6 separate numbered column-pairs by level x residency.
If you touch these views, re-verify against the dictionary rather than guessing
from column names.

**Three real data-quality gotchas found while writing this, all handled in the
script — don't "clean up" these away:**
- **Encoding is Windows-1252, not UTF-8** (`encoding='windows-1252'` on every
  `read_csv_auto`). Confirmed via raw bytes — institution director names contain
  accented characters (e.g. "Saúl Jiménez"). DuckDB's `encoding='latin-1'` alias
  rejects this file as "not latin-1 encoded" even though plain Latin-1 should
  never fail — use `'windows-1252'` specifically.
- **`hd2023.csv` has a UTF-8 BOM** glued onto its first header cell. Decoded
  under windows-1252, this becomes the literal 3-character string `"ï»¿UNITID"`
  (not a single U+FEFF) — `_select_for_year()` detects and renames it. Left
  unfixed, every 2023 institution row would silently get a NULL `unit_id`.
- **`hd2022.csv` has a literal tab byte inside a quoted name field** ("Ora<TAB>Horn
  Prouser"), which fools DuckDB's CSV dialect sniffer into guessing tab-delimited
  and then rejecting the whole file as ragged. Fixed by pinning
  `delim=',', quote='"', escape='"', strict_mode=false` explicitly instead of
  relying on auto-detection — verified this doesn't corrupt that row.
- Several code columns (`GRTYPE`, `EFALEVEL`) are fixed-width and come back
  **space-padded** (`' 2'` not `'2'`) — always `TRIM()` before comparing in a
  `CASE`/`WHERE`. Numeric casts use `TRY_CAST`, not `CAST`, since blank/suppressed
  cells are common in IPEDS and a plain `CAST` would crash the whole query.

## Stage 2: SQL agent (`sql_agent.py`)

`src/sql_agent.py` builds up in the plan's own steps:

- **Step 4 — `generate_sql()`**: OpenAI `gpt-4o-mini` (not Anthropic, same provider
  substitution as `ask.py`) writes DuckDB SQL from `src/schema.md` + the question,
  returned inside `<sql></sql>` tags, or `<sql>CANNOT_ANSWER</sql>` if the question
  is out of scope. Retries pass the previous SQL + DB error back so the model can
  self-correct.
- **Step 5 — guardrails** (`validate_sql()`, `run_sql()`): layered on purpose — if
  one check misses something, the next still blocks it. Parse check (`sqlglot`,
  exactly one statement) -> statement-type check (SELECT only) -> table allowlist
  (`ALLOWED_TABLES` + CTE names) -> forbidden-function check (`read_csv` etc.) ->
  auto-added `LIMIT 200` -> **read-only DuckDB connection** (the real safety net —
  verified it blocks writes against a real base table, not just views) ->
  `enable_external_access = false` -> 10s query timeout via `threading.Timer` +
  `con.interrupt()`. All verified working directly, including a forced-slow
  cross-join to confirm the timeout actually fires. Tests in `tests/test_guardrails.py`
  (run with `pytest tests/test_guardrails.py`).

**Multi-campus name-matching bug found and fixed during Step 4 testing — don't
remove the `matched_institution` CTE pattern from `schema.md`.** An `ILIKE` name
match can legitimately return several institutions at once (Ohio State has 5
campuses, Michigan has 3) — the fix disambiguates by picking the highest-enrollment
match, applied as a standard CTE on every name-based lookup, not only when
ambiguity is expected (the model can't know in advance whether a name is
ambiguous). Verified this generalizes: tested on a school/table combo with no
matching worked example (Indiana University + tuition) and it correctly picked
Bloomington over 7 other matches, including an unrelated school that also
substring-matched ("Indiana University of Pennsylvania").

**Known, deferred issue: nickname/official-name mismatches.** `ILIKE
'%penn state university%'` matches nothing, because IPEDS's official name is
"Pennsylvania State University-Main Campus" — "Penn State" isn't a substring of
"Pennsylvania State". Unlike the multi-campus bug, this returns zero rows
*silently* (looks like "no data" rather than an obvious failure). Decided to
defer fixing this until Step 7's eval shows how often it actually comes up,
rather than guessing at a general fix now.

**Step 6 — `ask_data()` + `summarize()`:** ties `generate_sql()` ->
`validate_sql()` -> `run_sql()` together with a retry loop (`MAX_RETRIES = 2`;
a `duckdb.Error` feeds the error back to the model, a `UnsafeSQL` guardrail
block is returned immediately, never retried). `summarize()` makes a second
OpenAI call to turn the result rows into a 1-3 sentence answer citing IPEDS and
the year(s) shown. Runnable as `python src/sql_agent.py "<question>"`, which
prints the answer and the exact SQL it ran — same transparency role as Stage
1's citations.

### Step 7 eval results (2026-11-20, `gpt-4o-mini`)

`eval/sql_questions.csv` (25 questions: 15 answerable, 4 unanswerable, 3
ambiguous, 3 attack) run through `eval/run_sql_eval.py`, which scores
answerable questions by executing both the gold SQL and the agent's SQL
against the live DuckDB and comparing sorted, float-rounded row sets (not SQL
text — two different queries can both be right). Results saved to
`eval/sql_eval_results.csv`.

- **Execution accuracy: 100% (15/15)** — every answerable question's SQL
  produced the same result set as the hand-written gold query.
- **Refusal accuracy: 100% (7/7)** — all 4 unanswerable questions and all 3
  prompt-injection/attack questions were declined. Notably, the model refused
  all 7 by returning `CANNOT_ANSWER` itself, before any malicious/invalid SQL
  was ever generated — the guardrails in `validate_sql()`/`run_sql()` were
  never actually exercised by this eval set, since nothing unsafe reached them.
- **Average attempts: 1.00 (all 25)** — zero retries needed anywhere; no
  database errors on the first try.
- **Valid SQL rate: 89% (16/18, answerable+ambiguous)** — not a bug. The 2
  "misses" are 2 of the 3 ambiguous questions ("typical cost of attending,"
  "enrollment growth at top universities"), where the model chose
  `CANNOT_ANSWER` over guessing at an underspecified question. The 3rd
  ambiguous question ("biggest university in Texas") it answered by
  enrollment, a reasonable interpretation.

No fixes needed after this first run — unlike Stage 1, nothing here required a
`schema.md` rule change or a `TOP_K`-style parameter tune.

## Never commit

- `.env` (API key)
- `.venv/`
- `data/chroma/` (rebuilt from `data/raw/` by `ingest.py` — not source of truth)
- `data/ipeds/raw/*.csv` (too large; `data/ipeds/SOURCES.md` documents download URLs)
- `data/ipeds/ipeds.duckdb` (rebuilt from `data/ipeds/raw/*.csv` by `load_ipeds.py`)

## Costs

Stage 1 runs under $1 total if run locally — embeddings and vector DB are free/local;
only the OpenAI `gpt-4o-mini` answer-generation call is billed, at $0.15/1M input
tokens and $0.60/1M output tokens.

- **Original estimate** (before measuring): ~4000 input + ~400 output tokens/question
  (5 retrieved chunks + instructions) -> ~$0.00084/question, ~$0.42 for 500 questions.
- **Actually measured** (one real question, via `ask.py`'s printed token counts):
  **1321 input / 78 output tokens -> ~$0.00024/question** — about 3.5x cheaper than
  the estimate above, mostly because the model answered well under the 150-word cap
  set in the system prompt. This is a single data point, not an average — Step 5's
  20-question eval run will give a more reliable per-question cost figure.

Set a monthly spend limit in the OpenAI platform dashboard as a safety net.

**Never call the OpenAI API (run `ask.py`, a batch eval, etc.) without the user's
explicit go-ahead for that specific run.** Even though each call is fractions of a
cent, this is a standing rule, not a one-time approval — ask before every run that
would spend money, don't assume blanket permission carries forward.
