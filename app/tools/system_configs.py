"""
system_configs.py — LangChain tool for CourtLink2 system configuration.

Tools exposed:
    list_system_configs — GET /api/systemconfigs
"""

import json
from langchain_core.tools import tool

from .api_client import api_get


@tool
def list_system_configs() -> str:
    """
    Retrieve all CourtLink2 system configuration records.
    These are key-value pairs stored in the database that control system
    behaviour such as pre-defined operator messages, call durations,
    warning thresholds, and other runtime settings.
    """
    try:
        configs = api_get("/api/systemconfigs")
        if not configs:
            return "No system configurations found."
        return json.dumps(configs, indent=2, default=str)
    except Exception as e:
        return f"Error fetching system configs: {e}"


ALL_TOOLS = [list_system_configs]
