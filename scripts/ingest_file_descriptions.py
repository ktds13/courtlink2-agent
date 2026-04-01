"""
ingest_file_descriptions.py — Generate LLM descriptions for every CourtLink2
source file and store them as embeddings in the `file_descriptions` pgvector table.

Each file gets a single concise natural-language description produced by GPT
(the same deployment used for chat, e.g. gpt-4.1-mini).  The description is
then embedded with text-embedding-ada-002 and upserted into `file_descriptions`.

The agent's `search_file_descriptions` tool queries this table so it can decide
*which files to open* before reading their raw content with `read_file`.

Usage:
    cd courtlink2-agent
    python scripts/ingest_file_descriptions.py

Optional flags:
    --project CourtLink2.CCM   — regenerate only one project
    --dry-run                  — print descriptions without touching DB or APIs
    --no-skip-existing         — re-describe files that already have a row

Environment variables required (same as ingest_code.py):
    AZURE_OPENAI_ENDPOINT
    AZURE_OPENAI_API_KEY
    AZURE_OPENAI_API_VERSION
    AZURE_OPENAI_DEPLOYMENT_NAME        — chat model used for description generation
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT   — embedding model (default: text-embedding-ada-002)
    DATABASE_URL
"""

import argparse
import os
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
AZURE_OPENAI_DEPLOYMENT_NAME = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.environ.get(
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002"
)
DATABASE_URL = os.environ["DATABASE_URL"]

# Repo root is two levels above this script (courtlink2-agent/scripts/)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ── What to index (mirrors ingest_code.py) ────────────────────────────────────

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

LANGUAGE_MAP = {
    ".cs": "csharp",
    ".xaml": "xaml",
    ".json": "json",
    ".csproj": "xml",
    ".vcxproj": "xml",
    ".h": "cpp",
    ".cpp": "cpp",
}

SKIP_DIRS = {"bin", "obj", ".vs", ".git", "node_modules", "Migrations"}

# Max characters of source code to send to the LLM for description generation.
# Files larger than this are truncated (we only need enough context for a summary).
MAX_CONTENT_FOR_LLM = 6000

# Delay between LLM description calls to respect rate limits (seconds)
LLM_CALL_DELAY = 0.3

# ── File collection ────────────────────────────────────────────────────────────


def iter_source_files(project_dir: Path) -> list[Path]:
    """Return all indexable source files under a project directory."""
    results = []
    for path in project_dir.rglob("*"):
        if any(skip in path.parts for skip in SKIP_DIRS):
            continue
        if path.suffix.lower() in LANGUAGE_MAP:
            results.append(path)
    return sorted(results)


# ── LLM description generation ────────────────────────────────────────────────

_openai = AzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
)

DESCRIPTION_SYSTEM_PROMPT = """\
You are a senior software engineer documenting a C#/.NET codebase called CourtLink2.
CourtLink2 is a distributed video visitation management system used in correctional
facilities. It orchestrates Zoom-based video calls across up to 81 rooms via MQTT,
WebRTC, and a central ASP.NET Core backend.

Given a source file, write a concise description (3–6 sentences) that covers:
1. What this file does and its primary responsibility
2. The key classes, interfaces, or top-level constructs it defines
3. The domain concepts it handles (meetings, calls, devices, MQTT messages, etc.)
4. How it fits into the broader CourtLink2 architecture

Rules:
- Be specific — name key types, methods, or patterns you see
- Do NOT just restate the filename; explain the CONTENT
- Do NOT include boilerplate ("This file is part of…")
- Keep it under 150 words
- Output ONLY the description text, no headings or markdown
"""


def describe_file(file_path: str, project: str, language: str, content: str) -> str:
    """Call the LLM to generate a natural language description of a source file."""
    # Truncate content if very large — LLM only needs enough to understand the file
    if len(content) > MAX_CONTENT_FOR_LLM:
        content = (
            content[:MAX_CONTENT_FOR_LLM]
            + "\n\n[... file truncated for description ...]"
        )

    user_message = (
        f"Project: {project}\n"
        f"File: {file_path}\n"
        f"Language: {language}\n\n"
        f"```{language}\n{content}\n```"
    )

    response = _openai.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT_NAME,
        messages=[
            {"role": "system", "content": DESCRIPTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()


# ── Embedding ──────────────────────────────────────────────────────────────────


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
            time.sleep(0.25)
    return all_embeddings


# ── Database ───────────────────────────────────────────────────────────────────


def get_existing_paths(conn) -> set[str]:
    """Return the set of file_path values already in file_descriptions."""
    with conn.cursor() as cur:
        cur.execute("SELECT file_path FROM file_descriptions")
        return {row[0] for row in cur.fetchall()}


def upsert_descriptions(conn, rows: list[dict]) -> int:
    """
    Upsert rows into file_descriptions.

    Each dict must have: file_path, project, language, description, embedding (list[float]).
    Uses INSERT … ON CONFLICT (file_path) DO UPDATE so re-running is idempotent.
    """
    with conn.cursor() as cur:
        for row in rows:
            vec_str = "[" + ",".join(map(str, row["embedding"])) + "]"
            cur.execute(
                """
                INSERT INTO file_descriptions
                    (file_path, project, language, description, embedding)
                VALUES (%s, %s, %s, %s, %s::vector)
                ON CONFLICT (file_path) DO UPDATE
                    SET project     = EXCLUDED.project,
                        language    = EXCLUDED.language,
                        description = EXCLUDED.description,
                        embedding   = EXCLUDED.embedding
                """,
                (
                    row["file_path"],
                    row["project"],
                    row["language"],
                    row["description"],
                    vec_str,
                ),
            )
    conn.commit()
    return len(rows)


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate LLM descriptions for CourtLink2 source files and store embeddings."
    )
    parser.add_argument(
        "--project",
        help="Process only this project (directory name), e.g. CourtLink2.CCM",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print descriptions without writing to DB or calling embedding API",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-describe files that already have a row in file_descriptions",
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
            print(f"ERROR: project '{args.project}' not in PROJECTS list.")
            sys.exit(1)

    print("CourtLink2 Agent — File Description Ingestion")
    print(f"  Chat model:      {AZURE_OPENAI_DEPLOYMENT_NAME}")
    print(f"  Embedding model: {AZURE_OPENAI_EMBEDDING_DEPLOYMENT}")
    print("=" * 60)

    conn = None if args.dry_run else psycopg2.connect(DATABASE_URL)
    existing_paths: set[str] = set()
    if conn and not args.no_skip_existing:
        existing_paths = get_existing_paths(conn)
        if existing_paths:
            print(
                f"  Skipping {len(existing_paths)} already-described files "
                f"(use --no-skip-existing to force refresh)\n"
            )

    total_described = 0
    total_skipped = 0

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

            # Filter out already-described files unless forced
            pending_files = []
            for f in files:
                rel = str(f.relative_to(REPO_ROOT)).replace("\\", "/")
                if rel in existing_paths:
                    total_skipped += 1
                else:
                    pending_files.append(f)

            if not pending_files:
                print(
                    f"  {project_label}: all {len(files)} files already described — skip"
                )
                continue

            print(
                f"\n  {project_label}: {len(pending_files)} files to describe "
                f"({len(files) - len(pending_files)} already done)"
            )

            # Describe each file individually (LLM call per file)
            described_rows: list[dict] = []
            for i, path in enumerate(pending_files, 1):
                rel_path = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
                language = LANGUAGE_MAP.get(path.suffix.lower(), "text")

                try:
                    content = path.read_text(encoding="utf-8", errors="replace").strip()
                except Exception as e:
                    print(
                        f"    [{i}/{len(pending_files)}] SKIP {path.name} — read error: {e}"
                    )
                    continue

                if not content:
                    print(
                        f"    [{i}/{len(pending_files)}] SKIP {path.name} — empty file"
                    )
                    continue

                if args.dry_run:
                    # In dry-run mode: still call the LLM to show what descriptions look like,
                    # but skip DB + embedding calls.
                    print(f"    [{i}/{len(pending_files)}] {path.name} ({language})")
                    try:
                        desc = describe_file(rel_path, project_label, language, content)
                        print(f"      → {desc[:120]}{'...' if len(desc) > 120 else ''}")
                    except Exception as e:
                        print(f"      → LLM error: {e}")
                    total_described += 1
                    time.sleep(LLM_CALL_DELAY)
                    continue

                # Generate description
                try:
                    desc = describe_file(rel_path, project_label, language, content)
                except Exception as e:
                    print(
                        f"    [{i}/{len(pending_files)}] ERROR {path.name} — LLM failed: {e}"
                    )
                    time.sleep(1.0)  # back off on error
                    continue

                described_rows.append(
                    {
                        "file_path": rel_path,
                        "project": project_label,
                        "language": language,
                        "description": desc,
                    }
                )

                print(
                    f"    [{i}/{len(pending_files)}] {path.name} — described ({len(desc)} chars)"
                )
                time.sleep(LLM_CALL_DELAY)

                # Embed + upsert in mini-batches of 16 to avoid long pauses at the end
                if len(described_rows) >= 16:
                    _flush(conn, described_rows)
                    total_described += len(described_rows)
                    described_rows = []

            # Flush remaining rows for this project
            if described_rows:
                if not args.dry_run:
                    _flush(conn, described_rows)
                total_described += len(described_rows)

    finally:
        if conn:
            conn.close()

    print()
    if args.dry_run:
        print(f"[DRY RUN] Would have described {total_described} files.")
    else:
        print(
            f"Done. Described {total_described} files, skipped {total_skipped} existing."
        )


def _flush(conn, rows: list[dict]) -> None:
    """Embed descriptions for a batch of rows and upsert into the DB."""
    texts = [r["description"] for r in rows]
    print(f"      Embedding {len(texts)} descriptions...", end=" ", flush=True)
    embeddings = embed_texts(texts)
    for row, emb in zip(rows, embeddings):
        row["embedding"] = emb
    upsert_descriptions(conn, rows)
    print("done")


if __name__ == "__main__":
    main()
