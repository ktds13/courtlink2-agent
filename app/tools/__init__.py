"""
__init__.py — Aggregate all CourtLink2 agent tools into a single list.
"""

from .docs import ALL_TOOLS as DOCS_TOOLS
from .meetings import ALL_TOOLS as MEETING_TOOLS
from .devices import ALL_TOOLS as DEVICE_TOOLS
from .calls import ALL_TOOLS as CALL_TOOLS
from .system_configs import ALL_TOOLS as CONFIG_TOOLS
from .device_power import ALL_TOOLS as POWER_TOOLS
from .file_search import ALL_TOOLS as FILE_SEARCH_TOOLS
from .code_search import ALL_TOOLS as CODE_SEARCH_TOOLS
from .code_edit import ALL_TOOLS as CODE_EDIT_TOOLS

ALL_TOOLS = (
    DOCS_TOOLS
    + MEETING_TOOLS
    + DEVICE_TOOLS
    + CALL_TOOLS
    + CONFIG_TOOLS
    + POWER_TOOLS
    + FILE_SEARCH_TOOLS
    + CODE_SEARCH_TOOLS
    + CODE_EDIT_TOOLS
)

__all__ = ["ALL_TOOLS"]
