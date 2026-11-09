# Ask the University

A RAG-based Q&A app that answers questions about a public university's policies, citing the exact source document and page for every claim. This is Stage 1 of a larger project that will eventually combine this with a text-to-SQL tool over public enrollment/graduation data, with an agent that routes between the two. Built using Ohio State University's publicly available course catalog, academic calendar, grading and withdrawal policies, financial aid SAP policy, student code of conduct, and tuition refund schedule — all public documents, unrelated to any employer.

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

## Stack

Python, `pypdf` for text extraction, `sentence-transformers` for free local embeddings, ChromaDB as the vector store, and the OpenAI API (`gpt-4o-mini`) for answer generation. See `CLAUDE.md` for full design decisions, conventions, and cost breakdown.
