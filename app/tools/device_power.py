"""
device_power.py — LangChain tool for CourtLink2 device power control.

Uses SNMP relay devices to power on, power off, or reboot room PCs.

Tools exposed:
    control_device_power — POST /api/devicepower
"""

import json
from langchain_core.tools import tool
from typing import Literal

from .api_client import api_post


@tool
def control_device_power(
    device_ids: list[str],
    action: str,
) -> str:
    """
    Control the physical power state of one or more CourtLink2 room PCs
    via SNMP relay devices. This directly controls the power supply to the
    workstation, not the Zoom call.

    IMPORTANT: Powering off a device while a call is active will abruptly
    terminate the Zoom session. Always end the call first.

    Args:
        device_ids: List of device identifiers to control, e.g. ['VC01', 'VC02'].
                    Pass a single device as a one-element list: ['VC01'].
        action:     Power action to perform. Must be one of:
                    - 'On'     — power the device on
                    - 'Off'    — power the device off
                    - 'Reboot' — reboot the device (power cycle)
    """
    valid_actions = {"On", "Off", "Reboot"}
    if action not in valid_actions:
        return f"Invalid action '{action}'. Must be one of: {', '.join(sorted(valid_actions))}."

    if not device_ids:
        return "No device IDs provided."

    body = {"deviceIds": device_ids, "action": action}
    try:
        result = api_post("/api/devicepower", body)
        devices_str = ", ".join(device_ids)
        return f"Power '{action}' sent to [{devices_str}].\n{json.dumps(result, indent=2, default=str)}"
    except Exception as e:
        return f"Error sending power command: {e}"


ALL_TOOLS = [control_device_power]
