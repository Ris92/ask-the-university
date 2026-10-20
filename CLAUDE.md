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
- Claude API — answer generation
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
├── .env                 # ANTHROPIC_API_KEY — NEVER commit
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

**LLM provider is not finalized.** The Stage 1 plan doc was written assuming the
Claude API (`claude-haiku-5-5` — unverified; current Haiku is `claude-haiku-4-5` if
Claude is used). As of 2026-10-20, leaning toward OpenAI instead, not yet decided.
Do not assume either provider when touching `ask.py` or `.env` — confirm first.
Once decided, update this note, `.env`'s key name (`ANTHROPIC_API_KEY` vs.
`OPENAI_API_KEY`), the Costs section below, and `requirements.txt`.

## Dependencies — two requirements files, not one

`requirements.txt` holds only the real runtime dependency tree of the five app
packages (`pypdf`, `chromadb`, `sentence-transformers`, `openai`/`anthropic`,
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
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install pypdf chromadb sentence-transformers anthropic python-dotenv
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

## Never commit

- `.env` (API key)
- `.venv/`
- `data/chroma/` (rebuilt from `data/raw/` by `ingest.py` — not source of truth)

## Costs

Stage 1 runs under $1 total if run locally — embeddings and vector DB are free/local;
only the Claude API answer-generation call is billed (~$0.0006/question). Set a
monthly spend limit in the Anthropic Console as a safety net.
