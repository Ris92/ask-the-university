# Ask the University

A chat assistant that answers questions about a public university using two tools: RAG over policy documents (Stage 1) and a text-to-SQL agent over public IPEDS enrollment/graduation/tuition data (Stage 2). A later stage will connect both under one agent that routes between them. Built using Ohio State University's publicly available course catalog, academic calendar, grading and withdrawal policies, financial aid SAP policy, student code of conduct, and tuition refund schedule — plus the U.S. Dept. of Education's public IPEDS dataset — all public, unrelated to any employer.

## Demo

```bash
$ python src/ask.py "What is the last day to withdraw from a class with a W?"

The last day to withdraw from a class and receive a grade of W is the tenth Friday
of a semester or summer term, with earlier deadlines for shorter summer sessions [1][2].

[1] academic_policies_guide.pdf, p. 19 (sim 0.76)
[2] academic_policies_guide.pdf, p. 19 (sim 0.752)
```

If the documents don't contain an answer, the app says so rather than guessing. This is the main defense against hallucinated answers, alongside a basic prompt-injection guard that tells the model to treat retrieved text as data, not instructions.

## How it works

Each PDF page is extracted and split into overlapping ~1200-character chunks, which are embedded locally with a free `sentence-transformers` model and stored in a ChromaDB vector index. A question is embedded the same way, matched against the index, and the most similar chunks are handed to `gpt-4o-mini` with strict instructions to answer only from the provided excerpts and cite every claim.

## Setup

```bash
git clone https://github.com/Ris92/ask-the-university.git
cd ask-the-university
pip install -r requirements.txt
echo "OPENAI_API_KEY=sk-..." > .env
python src/ingest.py              # builds the vector index from data/raw/*.pdf (~10 min on CPU)
python src/ask.py "your question here"
```

Policy PDFs aren't included in this repo since they're too large; see `data/raw/SOURCES.md` for where to download the originals.

## Results

Measured against a 20-question test set — 14 answerable, 4 deliberately out-of-scope, and 2 built from genuine ambiguities found in the source text — the app reaches **95% answer accuracy** and **100% retrieval hit rate**. The correct source page was retrieved for every answerable question, meaning the remaining errors came from how the model used retrieved text, not from failed retrieval. One real retrieval bug was found and fixed during evaluation: a correct chunk was narrowly missing the top-ranked cutoff, which raised accuracy from 90% to 95% once corrected.

## Stage 2: SQL agent over IPEDS data

A second tool answers quantitative questions — enrollment, graduation rates, tuition — by generating DuckDB SQL from the question, validating it, running it, and summarizing the result in plain English, instead of retrieving from documents.

### Demo

```bash
$ python src/sql_agent.py "Which 5 public universities in California had the most undergraduates in 2023?"

The five public universities in California with the most undergraduates in 2023 are:
California State University-Fullerton with 37,125 students, California State
University-Long Beach with 34,243 students, San Diego State University with
34,050 students, University of California-San Diego with 33,792 students, and
University of California-Berkeley with 33,078 students. This data comes from
IPEDS for the year 2023.

SQL: SELECT i.name, f.total_students FROM institutions AS i JOIN fall_enrollment AS f
ON i.unit_id = f.unit_id WHERE i.state = 'CA' AND i.control = 'Public'
AND f.level = 'Undergraduate' AND f.year = 2023 ORDER BY f.total_students DESC LIMIT 5
Attempts: 1
```

The SQL is always printed alongside the answer, the same transparency role Stage 1 plays with citations. If a question can't be answered from the available tables (e.g. acceptance rates, majors offered — IPEDS doesn't have them), the agent says so instead of guessing.

### How it works

Four IPEDS surveys (institution directory, fall enrollment, graduation rates, tuition) across 2021–2023 are stacked into a local DuckDB file with clean, readable views (`src/load_ipeds.py`). A question plus a plain-text schema description (`src/schema.md`) is sent to `gpt-4o-mini`, which returns one SQL query. Before it runs, the query passes through layered guardrails — parsed and checked for a single read-only `SELECT`, a table allowlist, a forbidden-function check — then executes on a read-only, external-access-disabled DuckDB connection with a row limit and a query timeout. A database error is sent back to the model for up to 2 retries; a guardrail block is never retried. The result rows are summarized by a second LLM call into a short, cited answer.

### Setup

```bash
pip install duckdb sqlglot
python src/load_ipeds.py         # builds data/ipeds/ipeds.duckdb from data/ipeds/raw/*.csv
python src/sql_agent.py "your question here"
```

Raw IPEDS CSVs aren't included in this repo (too large); see `data/ipeds/SOURCES.md` for download URLs. The matching `.xlsx` code dictionaries are committed.

### Results

Measured against a 25-question test set — 15 answerable, 4 deliberately out-of-scope, 3 genuinely ambiguous, and 3 prompt-injection/attack attempts — run via `eval/run_sql_eval.py`, which scores answerable questions by executing both the agent's SQL and a hand-written gold query and comparing result sets (not SQL text):

- **100% execution accuracy** (15/15 answerable questions)
- **100% refusal accuracy** (7/7 unanswerable + attack questions) — every attack prompt and out-of-scope question was declined without ever reaching the database
- **1.00 average attempts** — no retries needed on this run

## Stack

Python, `pypdf` for text extraction, `sentence-transformers` for free local embeddings, ChromaDB as the vector store, DuckDB for the IPEDS SQL agent, `sqlglot` for SQL validation, and the OpenAI API (`gpt-4o-mini`) for answer generation and SQL generation. See `CLAUDE.md` for full design decisions, conventions, and cost breakdown.
