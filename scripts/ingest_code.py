"""
ingest_code.py — CourtLink2 Agent source-code ingestion script.

Walks the CourtLink2 repository, chunks source files by logical boundaries
(namespace / class / method for C#; top-level element for XAML/JSON),
generates Azure OpenAI embeddings, and upserts them into the `code_chunks`
pgvector table.

Usage:
    cd courtlink2-agent
    python scripts/ingest_code.py

Optional flags:
    --project CourtLink2.CCM   — ingest only one project (re-run to refresh)
    --dry-run                  — print chunks without hitting the DB or OpenAI
"""

import argparse
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

# Repo root is two levels above this script (courtlink2-agent/scripts/)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ── What to index ──────────────────────────────────────────────────────────────

# Projects to index: (directory name, project label)
PROJECTS = [
    ("CourtLink2.CCM", "CourtLink2.CCM"),
    ("CourtLink2.Management", "CourtLink2.Management"),
    ("CourtLink2.SmartClient", "CourtLink2.SmartClient"),
    ("CourtLink2.CMM", "CourtLink2.CMM"),
    ("CourtLink2.RAD", "CourtLink2.RAD"),
    ("CourtLink2.Infrastructure", "CourtLink2.Infrastructure"),
    ("CourtLink2.Messaging", "CourtLink2.Messaging"),
    ("CourtLink2.Models", "CourtLink2.Models"),
    ("CourtLink2.API", "CourtLink2.API"),
    ("CourtLink2.Core", "CourtLink2.Core"),
    ("CourtLink2.Devices", "CourtLink2.Devices"),
    ("CourtLink2.CameraControl", "CourtLink2.CameraControl"),
    ("CourtLink2.Guard", "CourtLink2.Guard"),
    ("CourtLink2.ScreenCaster", "CourtLink2.ScreenCaster"),
    ("CourtLink2.Simulators.CCM", "CourtLink2.Simulators.CCM"),
    ("CourtLink2.Simulators.SCM", "CourtLink2.Simulators.SCM"),
    ("CourtLink2.MeetingSDK", "CourtLink2.MeetingSDK"),
]

# File extensions and their language labels
LANGUAGE_MAP = {
    ".cs": "csharp",
    ".xaml": "xaml",
    ".json": "json",
    ".csproj": "xml",
    ".vcxproj": "xml",
    ".h": "cpp",
    ".cpp": "cpp",
}

# Directories to skip anywhere in the tree
SKIP_DIRS = {"bin", "obj", ".vs", ".git", "node_modules", "Migrations"}

# Max characters per chunk — chunks larger than this are split further
MAX_CHUNK_CHARS = 3500

# Minimum characters for a chunk to be worth embedding
MIN_CHUNK_CHARS = 60

# ── File collection ────────────────────────────────────────────────────────────


def iter_source_files(project_dir: Path) -> list[Path]:
    """Yield all indexable source files under a project directory."""
    results = []
    for path in project_dir.rglob("*"):
        # Skip unwanted directories
        if any(skip in path.parts for skip in SKIP_DIRS):
            continue
        if path.suffix.lower() in LANGUAGE_MAP:
            results.append(path)
    return sorted(results)


# ── Chunking ───────────────────────────────────────────────────────────────────

# Matches C# namespace, class, struct, interface, enum, record declarations
_CS_SPLIT_RE = re.compile(
    r"^(?:[ \t]*)(?:public|internal|private|protected|static|abstract|sealed|partial|"
    r"file)[\s\w<>,\[\]?]*(?:class|struct|interface|enum|record)\s+\w",
    re.MULTILINE,
)

# Matches top-level XAML elements (opening tags at indent 0 or 4)
_XAML_SPLIT_RE = re.compile(r"^    <\w[\w.:]*", re.MULTILINE)


def _split_by_regex(text: str, pattern: re.Pattern) -> list[str]:
    """Split text at each regex match; keep the match as the start of each part."""
    matches = list(pattern.finditer(text))
    if len(matches) <= 1:
        return [text]
    parts = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parts.append(text[start:end].strip())
    # Prepend any text before the first match
    preamble = text[: matches[0].start()].strip()
    if preamble:
        parts.insert(0, preamble)
    return [p for p in parts if len(p) >= MIN_CHUNK_CHARS]


def _hard_split(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text into chunks of max_chars, trying to break on blank lines."""
    if len(text) <= max_chars:
        return [text]
    parts = []
    while text:
        if len(text) <= max_chars:
            parts.append(text)
            break
        split_at = text.rfind("\n\n", 0, max_chars)
        if split_at == -1:
            split_at = text.rfind("\n", 0, max_chars)
        if split_at == -1:
            split_at = max_chars
        parts.append(text[:split_at].strip())
        text = text[split_at:].strip()
    return [p for p in parts if len(p) >= MIN_CHUNK_CHARS]


def chunk_file(path: Path, project_dir: Path) -> list[dict]:
    """
    Chunk a single source file into logical pieces.

    Returns a list of dicts with keys:
        file_path, project (dir name), chunk_name, language, content
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    if not text.strip():
        return []

    ext = path.suffix.lower()
    language = LANGUAGE_MAP.get(ext, "text")
    rel_path = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    project = project_dir.name
    file_name = path.name

    # Split strategy by language
    if language == "csharp" and len(text) > MAX_CHUNK_CHARS:
        raw_parts = _split_by_regex(text, _CS_SPLIT_RE)
    elif language == "xaml" and len(text) > MAX_CHUNK_CHARS:
        raw_parts = _split_by_regex(text, _XAML_SPLIT_RE)
    else:
        raw_parts = [text]

    # Further hard-split any oversized parts
    parts: list[str] = []
    for part in raw_parts:
        parts.extend(_hard_split(part))

    chunks = []
    for i, content in enumerate(parts):
        if len(content) < MIN_CHUNK_CHARS:
            continue
        # Build a descriptive chunk name
        if len(parts) == 1:
            chunk_name = file_name
        else:
            # Try to extract class/method name from first line for C#
            first_line = content.split("\n")[0].strip()
            chunk_name = f"{file_name} (part {i + 1})"
            if language == "csharp":
                m = re.search(
                    r"(?:class|struct|interface|enum|record)\s+(\w+)", first_line
                )
                if m:
                    chunk_name = f"{file_name} · {m.group(1)}"

        chunks.append(
            {
                "file_path": rel_path,
                "project": project,
                "chunk_name": chunk_name,
                "language": language,
                "content": content,
            }
        )

    return chunks


# ── Embedding ──────────────────────────────────────────────────────────────────

_openai = AzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
)


def embed_texts(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    """Embed a list of texts using Azure OpenAI, in small batches."""
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = _openai.embeddings.create(
            model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT, input=batch
        )
        all_embeddings.extend([item.embedding for item in response.data])
        if i + batch_size < len(texts):
            time.sleep(0.25)  # rate-limit guard
    return all_embeddings


# ── Database ───────────────────────────────────────────────────────────────────


def upsert_chunks(
    conn, chunks: list[dict], embeddings: list[list[float]], project: str
) -> int:
    """Delete existing rows for the project, then insert fresh chunks."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM code_chunks WHERE project = %s", (project,))
        for chunk, emb in zip(chunks, embeddings):
            vec_str = "[" + ",".join(map(str, emb)) + "]"
            cur.execute(
                """
                INSERT INTO code_chunks
                    (file_path, project, chunk_name, language, content, embedding)
                VALUES (%s, %s, %s, %s, %s, %s::vector)
                """,
                (
                    chunk["file_path"],
                    chunk["project"],
                    chunk["chunk_name"],
                    chunk["language"],
                    chunk["content"],
                    vec_str,
                ),
            )
    conn.commit()
    return len(chunks)


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest CourtLink2 source code into pgvector."
    )
    parser.add_argument("--project", help="Ingest only this project (directory name)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print chunks, skip DB/OpenAI"
    )
    args = parser.parse_args()

    projects = PROJECTS
    if args.project:
        projects = [
            (d, label)
            for d, label in PROJECTS
            if d == args.project or label == args.project
        ]
        if not projects:
            print(f"ERROR: project '{args.project}' not found in PROJECTS list.")
            sys.exit(1)

    print("CourtLink2 Agent — Code Ingestion")
    print("=" * 60)

    conn = None if args.dry_run else psycopg2.connect(DATABASE_URL)

    total_chunks = 0

    try:
        for dir_name, project_label in projects:
            project_dir = REPO_ROOT / dir_name
            if not project_dir.exists():
                print(f"  SKIP {dir_name} (directory not found)")
                continue

            files = iter_source_files(project_dir)
            if not files:
                print(f"  SKIP {dir_name} (no indexable files)")
                continue

            # Chunk all files in this project
            all_chunks: list[dict] = []
            for f in files:
                all_chunks.extend(chunk_file(f, project_dir))

            if not all_chunks:
                print(f"  SKIP {dir_name} (no chunks produced)")
                continue

            print(
                f"\n  {project_label}: {len(files)} files -> {len(all_chunks)} chunks"
            )

            if args.dry_run:
                for c in all_chunks[:3]:
                    print(
                        f"    [{c['language']}] {c['chunk_name']} ({len(c['content'])} chars)"
                    )
                if len(all_chunks) > 3:
                    print(f"    ... and {len(all_chunks) - 3} more")
                total_chunks += len(all_chunks)
                continue

            # Embed
            print(f"    Embedding {len(all_chunks)} chunks...", end=" ", flush=True)
            texts = [c["content"] for c in all_chunks]
            embeddings = embed_texts(texts)
            print("done")

            # Upsert
            inserted = upsert_chunks(conn, all_chunks, embeddings, project_label)
            print(f"    Upserted {inserted} rows into code_chunks.")
            total_chunks += inserted

    finally:
        if conn:
            conn.close()

    print(
        f"\n{'[DRY RUN] ' if args.dry_run else ''}Total: {total_chunks} chunks ingested."
    )
    print("Done.")


if __name__ == "__main__":
    main()
