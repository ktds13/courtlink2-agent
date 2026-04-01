"""
file_search.py — LangChain tool for finding CourtLink2 source files by semantic description.

Tool:
    search_file_descriptions(query, project, language) -> str

This tool queries the `file_descriptions` pgvector table, where each row holds an
LLM-generated natural language description of a single source file.  It returns
matching file paths with their descriptions, allowing the agent to decide which
files to open with `read_file` — without having to scan raw code.

Recommended agent workflow:
    1. search_file_descriptions(query)  → identify relevant files
    2. read_file(file_path)             → read exact content + line numbers
    3. search_code(query)               → drill down into specific code chunks
"""

from langchain_core.tools import tool

from ..vectorstore import (
    format_file_descriptions_for_llm,
    search_file_descriptions as _search_file_descriptions,
)

ALL_TOOLS = []


@tool
def search_file_descriptions(
    query: str,
    project: str = "",
    language: str = "",
) -> str:
    """Find CourtLink2 source files whose description matches a query.

    Use this tool FIRST when you need to locate which file implements a feature,
    class, or concept — before opening files with read_file.  Each result shows
    the file path, its project, and a plain-English description of what it does.

    Use this for questions like:
    - "Where is meeting scheduling handled?"
    - "Which file manages MQTT subscriptions in the SmartClient?"
    - "Find the file that controls Zoom call lifecycle"
    - "What file contains the device state machine?"

    After getting results, call read_file(file_path) to read the actual source.

    Args:
        query: What you are looking for, described naturally.
               e.g. "MQTT command handling for call scheduling"
               e.g. "meeting CRUD REST API controller"
               e.g. "Zoom SDK join and leave callbacks"
        project: Optional. Restrict to one project, e.g. 'CourtLink2.CCM',
                 'CourtLink2.Management', 'CourtLink2.SmartClient',
                 'CourtLink2.Infrastructure', 'CourtLink2.Messaging',
                 'CourtLink2.Models', 'CourtLink2.API', 'CourtLink2.Devices'.
                 Leave empty to search all projects.
        language: Optional. Filter by language: 'csharp', 'xaml', 'json', 'xml', 'cpp'.
                  Leave empty to search all languages.
    """
    try:
        results = _search_file_descriptions(
            query=query,
            project=project.strip() or None,
            language=language.strip() or None,
        )
        return format_file_descriptions_for_llm(results)
    except Exception as e:
        return f"File description search error: {e}"


ALL_TOOLS = [search_file_descriptions]
