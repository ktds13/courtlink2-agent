#!/usr/bin/env python3
"""
mcp_server.py — OpenCode MCP server for CourtLink2 knowledge retrieval.

Exposes three semantic-search tools over the pgvector database:
    search_courtlink_docs   : Search system documentation (CCM, Management, SmartClient, SystemDesign)
    search_courtlink_code   : Search C#/XAML/JSON source code chunks across all 20 projects
    search_courtlink_files  : Find files by natural-language description

The server uses stdio transport so OpenCode can launch it as a local subprocess.

Requirements:
    pip install mcp  (or: uv add mcp)

Run standalone (for testing):
    python courtlink2-agent/mcp_server.py

OpenCode launches it automatically via opencode.json MCP config.
"""

import sys
from pathlib import Path

# ── Path setup ─────────────────────────────────────────────────────────────────
# Allow imports from the courtlink2-agent package regardless of where OpenCode
# launches this script from (project root vs agent directory).
_AGENT_DIR = Path(__file__).resolve().parent
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

# ── Environment ────────────────────────────────────────────────────────────────
# Load .env from the courtlink2-agent directory.  OpenCode also passes env vars
# through the MCP server's environment config in opencode.json — those take
# precedence over .env values because os.environ is already set before dotenv runs.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(_AGENT_DIR / ".env", override=False)

# ── Vectorstore imports ─────────────────────────────────────────────────────────
from app.vectorstore import (  # noqa: E402
    format_code_for_llm,
    format_docs_for_llm,
    format_file_descriptions_for_llm,
    search_code,
    search_docs,
    search_file_descriptions,
)

# ── MCP server ─────────────────────────────────────────────────────────────────
from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP(
    "courtlink2",
    instructions=(
        "This server provides semantic search over the CourtLink2 codebase and documentation. "
        "Use search_courtlink_docs for architecture and how-to questions. "
        "Use search_courtlink_files to locate which file implements something. "
        "Use search_courtlink_code for deep code-level understanding."
    ),
)


# ── Tool: search documentation ────────────────────────────────────────────────


@mcp.tool()
def search_courtlink_docs(query: str) -> str:
    """
    Search CourtLink2 system documentation using semantic similarity.

    Covers four embedded documentation sources:
        - CCM.md         — operator control console (WinUI 3), meeting management,
                           device grid, RTSP streaming, PTZ camera, language interpretation
        - Management.md  — central backend REST API + MQTT orchestration, call lifecycle,
                           SQL Server schema, power control, DeviceManager, Wowza streaming
        - SmartClient.md — per-room Zoom endpoint app (WPF), MeetingController, MQTT topics,
                           Auto/Manual modes, Zoom SDK integration, DPAPI identity
        - SystemDesign.md — full system architecture, deployment topology, project dependency
                            graph, entity-relationship diagram, MQTT topic table

    Use for: architecture questions, how-to questions, MQTT topics, REST API endpoints,
    component roles, configuration, operator workflows, call lifecycle, troubleshooting.

    Args:
        query: Natural language question or keyword phrase (e.g. "how does schedule_call work",
               "what MQTT topics does SmartClient publish", "CSV import headers").
    """
    try:
        docs = search_docs(query)
        return format_docs_for_llm(docs)
    except Exception as e:
        return f"Error searching documentation: {e}"


# ── Tool: search source code ───────────────────────────────────────────────────


@mcp.tool()
def search_courtlink_code(
    query: str,
    project: str = "",
    language: str = "",
) -> str:
    """
    Search CourtLink2 source code using semantic similarity.

    Searches class/method-level chunks across the full codebase: C#, XAML, JSON.
    Returns file paths, chunk names, and code content ordered by relevance.

    Use for: finding where a feature is implemented, understanding how something works
    at the code level, identifying the right class/method to modify.

    Available projects (use exact name for filtering):
        CourtLink2.CCM, CourtLink2.Management, CourtLink2.SmartClient,
        CourtLink2.API, CourtLink2.Models, CourtLink2.Messaging,
        CourtLink2.Infrastructure, CourtLink2.Devices, CourtLink2.CameraControl,
        CourtLink2.MeetingSDK, CourtLink2.CMM, CourtLink2.RAD, CourtLink2.Guard,
        CourtLink2.ScreenCaster, CourtLink2.Core, CourtLink2.Simulators.SCM,
        CourtLink2.Simulators.CCM, CourtLink2.CCMAutoTest

    Args:
        query:    Natural language description of the code you're looking for
                  (e.g. "CSV header mapping", "schedule call MQTT publish", "mTLS certificate").
        project:  Optional project filter (e.g. "CourtLink2.CCM").
        language: Optional language filter: "csharp", "xaml", or "json".
    """
    try:
        chunks = search_code(
            query,
            project=project or None,
            language=language or None,
        )
        return format_code_for_llm(chunks)
    except Exception as e:
        return f"Error searching code: {e}"


# ── Tool: search file descriptions ────────────────────────────────────────────


@mcp.tool()
def search_courtlink_files(
    query: str,
    project: str = "",
    language: str = "",
) -> str:
    """
    Find CourtLink2 source files by natural language description.

    Each entry contains an LLM-generated description of what the file does,
    plus its path, project, and language. Use this FIRST when you need to
    locate which file implements something, then use the Read tool to examine
    the exact code with line numbers.

    Recommended workflow for code questions:
        1. search_courtlink_files(query)    → find the right file(s)
        2. Read(file_path)                  → read the file with line numbers
        3. search_courtlink_code(query)     → if you need method-level context

    Args:
        query:    Natural language description of what the file should do
                  (e.g. "CSV parsing for meeting list upload",
                   "DeviceManager in-memory state machine",
                   "Zoom SDK join meeting wrapper").
        project:  Optional project filter (e.g. "CourtLink2.Management").
        language: Optional language filter: "csharp", "xaml", or "json".
    """
    try:
        results = search_file_descriptions(
            query,
            project=project or None,
            language=language or None,
        )
        return format_file_descriptions_for_llm(results)
    except Exception as e:
        return f"Error searching file descriptions: {e}"


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
