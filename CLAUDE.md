# Ask the University

A chat assistant that answers questions about a public university using two tools:

- **RAG over policy documents** — course catalog, academic calendar, grading/withdrawal
  policies, SAP policy, student code of conduct, tuition/refund schedule. Answers cite
  file name + page number.
- **SQL agent over IPEDS data** (later stage) — enrollment, graduation rates, costs,
  pulled from the U.S. Dept. of Education's public IPEDS dataset.

An agent decides which tool to use (or both) and answers with citations. Built in
stages; current stage: **Stage 1 — RAG over documents only** (see
`Stage 1 Plan RAG over University Policy Documents.docx` for the full step-by-step).

Portfolio project — no confidential/employer data. Uses a public university other than
the author's employer.

## Stack

- Python 3.11+
- `pypdf` — PDF text extraction
- `sentence-transformers` (`BAAI/bge-small-en-v1.5`) — local, free embeddings
- `ChromaDB` (`PersistentClient`, on disk) — vector store, cosine space
- OpenAI API (`gpt-4o-mini`) — answer generation
- Flask or FastAPI (later stage) — chat interface
- Databricks Free Edition — optional alternative to local ChromaDB (Delta tables +
  Databricks Vector Search); keep the local version working too since it's easier for
  interviewers to run from GitHub

## Folder layout

```
ask-the-university/
├── data/raw/          # policy PDFs — never commit the PDFs themselves if large; do commit SOURCES.md
├── data/chroma/        # vector index, rebuilt by ingest.py — gitignored
├── src/
│   ├── ingest.py       # extract + chunk + embed + index (Stage 1, Steps 2-3)
│   └── ask.py          # retrieve + answer with citations (Stage 1, Step 4)
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

## Never commit

- `.env` (API key)
- `.venv/`
- `data/chroma/` (rebuilt from `data/raw/` by `ingest.py` — not source of truth)

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
