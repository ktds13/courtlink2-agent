"""
devices.py — LangChain tools for CourtLink2 device management.

Tools exposed:
    list_devices — GET /api/devices
    get_device   — GET /api/devices/{id}
"""

import json
from langchain_core.tools import tool

from .api_client import api_get


@tool
def list_devices() -> str:
    """
    List all configured CourtLink2 videoconferencing devices (VC01–VC81).
    Returns each device's ID, name, zone, streaming engine, relay config,
    and current connection/call status as tracked by the Management server.
    """
    try:
        devices = api_get("/api/devices")
        if not devices:
            return "No devices found."
        return json.dumps(devices, indent=2, default=str)
    except Exception as e:
        return f"Error fetching devices: {e}"


@tool
def get_device(device_id: str) -> str:
    """
    Get the current status and configuration of a single CourtLink2 device.

    Use this when troubleshooting a specific device — it shows whether the device
    is online, its current call state (Idle/Scheduled/Started/Paused), operating
    mode (Auto/Manual), and assigned meeting details.

    Args:
        device_id: The device identifier, e.g. 'VC02'.
    """
    try:
        device = api_get(f"/api/devices/{device_id}")
        return json.dumps(device, indent=2, default=str)
    except Exception as e:
        return f"Error fetching device {device_id}: {e}"


ALL_TOOLS = [list_devices, get_device]
