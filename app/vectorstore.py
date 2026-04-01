"""
vectorstore.py — pgvector retriever for CourtLink2 docs and source code.

Public functions:
    search_docs(query, top_k) -> list[dict]
        Searches the `documents` table (markdown docs: CCM, Management, SmartClient).
        Returns: source, section, content, score

    search_code(query, top_k, project, language) -> list[dict]
        Searches the `code_chunks` table (full C# / XAML / JSON codebase).
        Returns: file_path, project, chunk_name, language, content, score

    search_file_descriptions(query, top_k, project, language) -> list[dict]
        Searches the `file_descriptions` table (one LLM-generated description per file).
        Returns: file_path, project, language, description, score
        Use this to find *which files* are relevant before reading them with read_file.
"""

import os

import psycopg2
from openai import AzureOpenAI

DATABASE_URL = os.environ["DATABASE_URL"]
AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
AZURE_OPENAI_API_KEY = os.environ["AZURE_OPENAI_API_KEY"]
AZURE_OPENAI_API_VERSION = os.environ["AZURE_OPENAI_API_VERSION"]
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.environ.get(
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002"
)
DEFAULT_TOP_K = int(os.getenv("RAG_TOP_K", "5"))

_openai_client = AzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
)


def _embed(text: str) -> list[float]:
    """Generate a single embedding vector for the given text via Azure OpenAI."""
    response = _openai_client.embeddings.create(
        model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
        input=[text],
    )
    return response.data[0].embedding


def _vec_literal(embedding: list[float]) -> str:
    """Convert a Python float list to a PostgreSQL vector literal."""
    return "[" + ",".join(map(str, embedding)) + "]"


def search_docs(query: str, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """
    Perform cosine-similarity search against the documents table.

    Returns a list of matching document chunks, ordered by relevance.
    """
    embedding = _embed(query)
    vec_str = _vec_literal(embedding)

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    source,
                    section,
                    content,
                    1 - (embedding <=> %s::vector) AS score
                FROM documents
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vec_str, vec_str, top_k),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        {
            "source": row[0],
            "section": row[1],
            "content": row[2],
            "score": round(float(row[3]), 4),
        }
        for row in rows
    ]


def format_docs_for_llm(docs: list[dict]) -> str:
    """
    Format retrieved doc chunks into a readable string for the LLM context.
    """
    if not docs:
        return "No relevant documentation found."

    parts = []
    for doc in docs:
        parts.append(
            f"### [{doc['source']}] {doc['section']}  (relevance: {doc['score']})\n\n"
            f"{doc['content']}"
        )
    return "\n\n---\n\n".join(parts)


# ── Code search ────────────────────────────────────────────────────────────────

DEFAULT_CODE_TOP_K = int(os.getenv("CODE_TOP_K", "6"))


def search_code(
    query: str,
    top_k: int = DEFAULT_CODE_TOP_K,
    project: str | None = None,
    language: str | None = None,
) -> list[dict]:
    """
    Perform cosine-similarity search against the code_chunks table.

    Optionally filter by project name (e.g. 'CourtLink2.CCM') or
    language (e.g. 'csharp', 'xaml', 'json').

    Returns a list of matching code chunks, ordered by relevance.
    """
    embedding = _embed(query)
    vec_str = _vec_literal(embedding)

    # Build optional WHERE clause
    filters = []
    params: list = [vec_str, vec_str]
    if project:
        filters.append("project = %s")
        params.append(project)
    if language:
        filters.append("language = %s")
        params.append(language)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    params.append(top_k)

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    file_path,
                    project,
                    chunk_name,
                    language,
                    content,
                    1 - (embedding <=> %s::vector) AS score
                FROM code_chunks
                {where}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        {
            "file_path": row[0],
            "project": row[1],
            "chunk_name": row[2],
            "language": row[3],
            "content": row[4],
            "score": round(float(row[5]), 4),
        }
        for row in rows
    ]


def format_code_for_llm(chunks: list[dict]) -> str:
    """
    Format retrieved code chunks into a readable string for the LLM context.
    """
    if not chunks:
        return "No relevant code found."

    parts = []
    for chunk in chunks:
        lang = chunk["language"]
        parts.append(
            f"### `{chunk['file_path']}` — {chunk['chunk_name']}  "
            f"[{chunk['project']}]  (relevance: {chunk['score']})\n\n"
            f"```{lang}\n{chunk['content']}\n```"
        )
    return "\n\n---\n\n".join(parts)


# ── File description search ────────────────────────────────────────────────────

DEFAULT_FILE_DESC_TOP_K = int(os.getenv("FILE_DESC_TOP_K", "10"))


def search_file_descriptions(
    query: str,
    top_k: int = DEFAULT_FILE_DESC_TOP_K,
    project: str | None = None,
    language: str | None = None,
) -> list[dict]:
    """
    Perform cosine-similarity search against the file_descriptions table.

    Each row is one source file with an LLM-generated natural language description.
    Use this to find *which files* are relevant to a question before reading their
    raw content with read_file.

    Optionally filter by project name (e.g. 'CourtLink2.CCM') or
    language (e.g. 'csharp', 'xaml', 'json').

    Returns a list of matching files ordered by relevance, each with:
        file_path, project, language, description, score
    """
    embedding = _embed(query)
    vec_str = _vec_literal(embedding)

    filters = []
    params: list = [vec_str, vec_str]
    if project:
        filters.append("project = %s")
        params.append(project)
    if language:
        filters.append("language = %s")
        params.append(language)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    params.append(top_k)

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    file_path,
                    project,
                    language,
                    description,
                    1 - (embedding <=> %s::vector) AS score
                FROM file_descriptions
                {where}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        {
            "file_path": row[0],
            "project": row[1],
            "language": row[2],
            "description": row[3],
            "score": round(float(row[4]), 4),
        }
        for row in rows
    ]


def format_file_descriptions_for_llm(results: list[dict]) -> str:
    """
    Format file description search results into a readable string for the LLM.

    Each entry shows the file path, project, language, relevance score, and
    the LLM-generated description — giving the agent enough context to decide
    which file(s) to open next with read_file.
    """
    if not results:
        return "No matching files found."

    parts = []
    for r in results:
        parts.append(
            f"### `{r['file_path']}`  [{r['project']}]  ({r['language']})  "
            f"relevance: {r['score']}\n\n"
            f"{r['description']}"
        )
    return "\n\n---\n\n".join(parts)
