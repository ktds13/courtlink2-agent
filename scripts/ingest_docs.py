"""
ingest_docs.py — CourtLink2 Agent doc ingestion script.

Reads the three CourtLink2 markdown documentation files, splits them into
semantic chunks (one chunk per H2/H3 section), generates Azure OpenAI embeddings,
and upserts them into the pgvector `documents` table.

Usage:
    cd courtlink2-agent
    python scripts/ingest_docs.py

Environment variables (from .env):
    AZURE_OPENAI_ENDPOINT              — Azure OpenAI resource endpoint
    AZURE_OPENAI_API_KEY               — Azure OpenAI API key
    AZURE_OPENAI_API_VERSION           — API version (e.g. 2024-10-01-preview)
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT  — Embedding deployment name
    DATABASE_URL                       — PostgreSQL connection string
"""

import os
import re
import sys
import time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from openai import AzureOpenAI

# ── Config ─────────────────────────────────────────────────────────────────────

load_dotenv(Path(__file__).parent.parent / ".env")

AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
AZURE_OPENAI_API_KEY = os.environ["AZURE_OPENAI_API_KEY"]
AZURE_OPENAI_API_VERSION = os.environ["AZURE_OPENAI_API_VERSION"]
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.environ.get(
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002"
)
DATABASE_URL = os.environ["DATABASE_URL"]
EMBED_DIM = 1536

# Docs relative to the repo root (one level above courtlink2-agent/)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS = [
    (REPO_ROOT / "docs" / "SmartClient.md", "SmartClient.md"),
    (REPO_ROOT / "docs" / "Management.md", "Management.md"),
    (REPO_ROOT / "docs" / "CCM.md", "CCM.md"),
    (REPO_ROOT / "docs" / "SystemDesign.md", "SystemDesign.md"),
    (REPO_ROOT / "docs" / "mqtt_analysis.md", "mqtt_analysis.md"),
]

# ── Chunking ───────────────────────────────────────────────────────────────────


def chunk_markdown(text: str, source: str) -> list[dict]:
    """
    Split a markdown document into chunks at H2 (##) and H3 (###) headings.
    Each chunk keeps its heading as the section title.
    Returns a list of {source, section, content} dicts.
    """
    # Split on lines that start with ## or ### (but not ####)
    pattern = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))

    chunks = []
    for i, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()

        # Skip very short chunks (e.g., empty sections, just a heading)
        if len(body) < 80:
            continue

        chunks.append(
            {
                "source": source,
                "section": heading,
                "content": body,
            }
        )

    # If no headings found, treat the entire file as one chunk
    if not chunks:
        chunks.append(
            {
                "source": source,
                "section": source,
                "content": text.strip(),
            }
        )

    return chunks


# ── Embedding ──────────────────────────────────────────────────────────────────

client = AzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
)


def embed_texts(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    """
    Generate embeddings for a list of texts using Azure OpenAI API.
    Uses small batches to stay within Azure token-per-request limits.
    """
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(
            model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT, input=batch
        )
        all_embeddings.extend([item.embedding for item in response.data])
        if i + batch_size < len(texts):
            time.sleep(0.3)  # simple rate-limit guard
    return all_embeddings


# ── Database ───────────────────────────────────────────────────────────────────


def upsert_chunks(conn, chunks: list[dict], embeddings: list[list[float]]) -> int:
    """
    Delete existing rows for the given source files and insert fresh chunks.
    Returns number of rows inserted.
    """
    sources = list({c["source"] for c in chunks})

    with conn.cursor() as cur:
        # Remove stale rows for this source
        cur.execute(
            "DELETE FROM documents WHERE source = ANY(%s)",
            (sources,),
        )

        # Insert new chunks
        for chunk, embedding in zip(chunks, embeddings):
            vec_str = "[" + ",".join(map(str, embedding)) + "]"
            cur.execute(
                """
                INSERT INTO documents (source, section, content, embedding)
                VALUES (%s, %s, %s, %s::vector)
                """,
                (chunk["source"], chunk["section"], chunk["content"], vec_str),
            )

    conn.commit()
    return len(chunks)


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    print("CourtLink2 Agent — Doc Ingestion")
    print("=" * 50)

    # Collect all chunks from all doc files
    all_chunks: list[dict] = []
    for path, source in DOCS:
        if not path.exists():
            print(f"  WARNING: {path} not found — skipping")
            continue
        text = path.read_text(encoding="utf-8")
        chunks = chunk_markdown(text, source)
        all_chunks.extend(chunks)
        print(f"  {source}: {len(chunks)} chunks")

    if not all_chunks:
        print("No chunks found. Aborting.")
        sys.exit(1)

    print(f"\nTotal chunks to embed: {len(all_chunks)}")

    # Generate embeddings
    print(f"Generating embeddings with {AZURE_OPENAI_EMBEDDING_DEPLOYMENT}...")
    texts = [c["content"] for c in all_chunks]
    embeddings = embed_texts(texts)
    print(f"  {len(embeddings)} embeddings generated.")

    # Upsert into PostgreSQL
    print(f"\nConnecting to PostgreSQL...")
    conn = psycopg2.connect(DATABASE_URL)
    try:
        inserted = upsert_chunks(conn, all_chunks, embeddings)
        print(f"  Inserted {inserted} rows into documents table.")
    finally:
        conn.close()

    print("\nIngestion complete.")


if __name__ == "__main__":
    main()
