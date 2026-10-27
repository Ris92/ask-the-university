"""Stage 1, Step 2: extract PDF text and split it into overlapping chunks.

Chunk per page, not per document, so page numbers stay exact for citations.
"""

import random
import unicodedata
from pathlib import Path

import chromadb
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

RAW_DIR = Path("data/raw")
CHROMA_DIR = "data/chroma"
COLLECTION = "policies"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"  # free, runs on CPU
CHUNK_SIZE = 1200  # characters, roughly 250-300 tokens
OVERLAP = 200       # characters shared between neighboring chunks

# Some of our PDFs are web pages printed/exported to PDF (e.g. the academic
# policies guide's accordion-style table of contents). That export process
# leaves two kinds of non-content characters in the extracted text:
#   1. Typographic ligatures (e.g. "ﬁrst" instead of "first") - real content,
#      just a non-standard glyph. NFKC normalization fixes these in place.
#   2. Leftover UI icon glyphs (e.g. a collapse/expand arrow from the original
#      web page's TOC), which land in the Private Use Area (U+E000-U+F8FF) -
#      not real text at all, just noise sitting between section headings.
# Found by inspecting raw codepoints across all 6 source PDFs: 651/5238 chunks
# had non-ASCII characters, all either normal smart-quote/dash punctuation
# (harmless) or one of these two cases.
_PUA_RANGE = (0xE000, 0xF8FF)


def _clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in text if not (_PUA_RANGE[0] <= ord(ch) <= _PUA_RANGE[1]))


def extract_pages(pdf_path: Path) -> list[dict]:
    """Return one record per page: file name, page number, cleaned text."""
    reader = PdfReader(pdf_path)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = _clean_text(text)
        text = " ".join(text.split())  # collapse whitespace and line breaks
        if len(text) > 50:              # skip blank or near-blank pages
            pages.append({"source": pdf_path.name, "page": i, "text": text})
    return pages


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> list[str]:
    """Split text into overlapping chunks, breaking at sentence ends where possible."""
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            last_period = text.rfind(". ", start, end)
            if last_period > start + size // 2:
                end = last_period + 1
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = end - overlap
    return chunks


def build_chunks() -> list[dict]:
    records = []
    for pdf in sorted(RAW_DIR.glob("*.pdf")):
        pages = extract_pages(pdf)
        for p in pages:
            for j, chunk in enumerate(chunk_text(p["text"])):
                records.append({
                    "id": f"{p['source']}-p{p['page']}-c{j}",
                    "text": chunk,
                    "source": p["source"],
                    "page": p["page"],
                })
        print(f"{pdf.name}: {len(pages)} pages")
    print(f"Total chunks: {len(records)}")
    return records


def build_index(records: list[dict]) -> None:
    """Embed every chunk and store it in a fresh ChromaDB collection.

    NOTE on latency: this always re-embeds every chunk from scratch - there's
    no caching across runs. Benchmarked on the real corpus (5240 chunks) on
    this machine's CPU: ~30s per 256-chunk batch -> ~10 minutes total for a
    full run, almost entirely from the course bulletin's ~4700 chunks. The
    wipe-and-rebuild of the Chroma collection itself is instant (metadata-only)
    - the ~10 min cost is 100% re-embedding, not Chroma. Every run of this
    script pays that cost in full, whether or not the chunking logic changed.
    """
    model = SentenceTransformer(EMBED_MODEL)
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Start fresh each run so re-ingesting doesn't create duplicates
    if COLLECTION in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION)
    collection = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    batch = 256
    for i in range(0, len(records), batch):
        part = records[i:i + batch]
        embeddings = model.encode(
            [r["text"] for r in part], normalize_embeddings=True
        ).tolist()
        collection.add(
            ids=[r["id"] for r in part],
            documents=[r["text"] for r in part],
            embeddings=embeddings,
            metadatas=[{"source": r["source"], "page": r["page"]} for r in part],
        )
        print(f"Indexed {min(i + batch, len(records))}/{len(records)}")


if __name__ == "__main__":
    records = build_chunks()

    print("\n--- 3 random chunks (sanity check) ---")
    for r in random.sample(records, min(3, len(records))):
        print(f"\n[{r['id']}]")
        print(r["text"][:400])

    print("\n--- building index (this takes ~10 minutes on CPU, see build_index docstring) ---")
    build_index(records)
