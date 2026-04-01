"""
docs.py — LangChain tool for searching vectorized CourtLink2 documentation.

Tools exposed:
    search_courtlink_docs — pgvector cosine-similarity search
"""

from langchain_core.tools import tool

from ..vectorstore import search_docs, format_docs_for_llm


@tool
def search_courtlink_docs(query: str) -> str:
    """
    Search the CourtLink2 documentation for information about how the system
    works. Use this tool when the user asks HOW to do something, asks about
    system architecture, configuration, MQTT topics, API endpoints, workflows,
    components (SmartClient, CCM, Management), or troubleshooting.

    This searches across three embedded documentation files:
        - SmartClient.md  (per-room Zoom endpoint app)
        - Management.md   (central backend REST API + MQTT orchestration)
        - CCM.md          (operator control console)

    Args:
        query: A natural-language question or keyword phrase describing
               what you want to find in the docs.
    """
    try:
        docs = search_docs(query)
        return format_docs_for_llm(docs)
    except Exception as e:
        return f"Error searching documentation: {e}"


ALL_TOOLS = [search_courtlink_docs]
