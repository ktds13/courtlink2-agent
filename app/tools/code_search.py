"""
code_search.py — LangChain tool for searching CourtLink2 source code via pgvector.

Tool:
    search_code(query, project, language) -> str
"""

from langchain_core.tools import tool

from ..vectorstore import format_code_for_llm, search_code as _search_code

ALL_TOOLS = []


@tool
def search_code(
    query: str,
    project: str = "",
    language: str = "",
) -> str:
    """Search the CourtLink2 source code using semantic similarity.

    Use this tool when you need to:
    - Find where a specific class, method, or feature is implemented
    - Understand how a component works by reading its code
    - Locate files related to a bug or error
    - Explore the code structure of a project

    Args:
        query: What to search for, e.g. 'MeetingViewModel save command',
               'DeviceItemViewModel MQTT subscription', 'CallController start endpoint'
        project: Optional. Filter to a specific project, e.g. 'CourtLink2.CCM',
                 'CourtLink2.Management', 'CourtLink2.SmartClient', 'CourtLink2.Infrastructure',
                 'CourtLink2.Messaging', 'CourtLink2.Models', 'CourtLink2.API'.
                 Leave empty to search all projects.
        language: Optional. Filter by language: 'csharp', 'xaml', 'json', 'xml', 'cpp'.
                  Leave empty to search all languages.
    """
    try:
        results = _search_code(
            query=query,
            project=project.strip() or None,
            language=language.strip() or None,
        )
        return format_code_for_llm(results)
    except Exception as e:
        return f"Code search error: {e}"


ALL_TOOLS = [search_code]
