"""
meetings.py — LangChain tools for CourtLink2 meeting management.

Tools exposed:
    list_meetings             — GET    /api/meetings
    get_meeting               — GET    /api/meetings/{id}
    create_meeting            — POST   /api/meetings
    update_meeting            — PUT    /api/meetings/{id}
    assign_meeting_to_device  — PUT    /api/meetings/{id}  (sets deviceId only, no mode check)
    delete_meeting            — DELETE /api/meetings/{id}
"""

import json
import uuid
from langchain_core.tools import tool

from .api_client import api_get, api_post, api_put, api_delete


@tool
def list_meetings() -> str:
    """
    List all of today's scheduled video visitation meetings from CourtLink2.
    Returns meeting ID, inmate name, display name, device assignment,
    start/end times, and Zoom meeting details.
    """
    try:
        meetings = api_get("/api/meetings")
        if not meetings:
            return "No meetings scheduled for today."
        return json.dumps(meetings, indent=2, default=str)
    except Exception as e:
        return f"Error fetching meetings: {e}"


@tool
def get_meeting(meeting_id: str) -> str:
    """
    Get details of a specific meeting by its ID (GUID string).

    Args:
        meeting_id: The GUID identifier of the meeting.
    """
    try:
        meeting = api_get(f"/api/meetings/{meeting_id}")
        return json.dumps(meeting, indent=2, default=str)
    except Exception as e:
        return f"Error fetching meeting {meeting_id}: {e}"


@tool
def create_meeting(
    display_name: str,
    zoom_meeting_id: str,
    meeting_passcode: str,
    inmate_id: str = "",
    inmate_name: str = "",
    start_time: str = "",
    end_time: str = "",
    device_id: str = "",
) -> str:
    """
    Create a new video visitation meeting in CourtLink2.

    Required fields:
        display_name:    Name shown inside the Zoom meeting room (e.g. 'John Smith - VC02').
        zoom_meeting_id: The Zoom meeting NUMBER — must be a 10 or 11-digit numeric string
                         (e.g. '85012345678'). This is NOT a GUID; it is the actual Zoom
                         meeting number. Invalid values cause async join failures.
        meeting_passcode: The Zoom meeting password / passcode.

    Optional fields:
        inmate_id:       Inmate identifier string. If not provided, a UUID is auto-generated.
        inmate_name:     Human-readable inmate full name (display only).
        start_time:      Scheduled start time ISO 8601 (e.g. '2026-03-25T09:00:00'). Not validated.
        end_time:        Scheduled end time ISO 8601. Not validated.
        device_id:       Room device to pre-assign (e.g. 'VC02'). Can assign later via schedule_call.

    IMPORTANT: The response contains the meeting's 'id' field (a UUID like
    '02dccd11-1a9e-45ab-8504-bbba0843f7f0'). Always extract and remember this 'id'
    from the response — it is needed for schedule_call, assign_meeting_to_device,
    update_meeting, and delete_meeting. Never ask the user for it.
    """
    resolved_inmate_id = inmate_id if inmate_id else str(uuid.uuid4())

    body: dict = {
        "inmateId": resolved_inmate_id,
        "displayName": display_name,
        "zoomMeetingId": zoom_meeting_id,
        "meetingPasscode": meeting_passcode,
    }
    if inmate_name:
        body["inmateName"] = inmate_name
    if start_time:
        body["startTime"] = start_time
    if end_time:
        body["endTime"] = end_time
    if device_id:
        body["deviceId"] = device_id

    try:
        result = api_post("/api/meetings", body)
        meeting_id = result.get("id", "") if isinstance(result, dict) else ""
        note = (
            f"\nNOTE: Meeting id is '{meeting_id}' — use this for all follow-up operations."
            if meeting_id
            else ""
        )
        return f"Meeting created successfully.{note}\n{json.dumps(result, indent=2, default=str)}"
    except Exception as e:
        return f"Error creating meeting: {e}"


@tool
def update_meeting(
    meeting_id: str,
    inmate_id: str = "",
    inmate_name: str = "",
    display_name: str = "",
    zoom_meeting_id: str = "",
    meeting_passcode: str = "",
    device_id: str = "",
) -> str:
    """
    Update an existing meeting by its ID. Only the fields you provide are changed;
    all other fields retain their current values (read-modify-write).

    The server endpoint is a full-replace PUT, so this tool first fetches the
    current meeting data and merges your changes on top before sending the update.

    Args:
        meeting_id:       The GUID identifier of the meeting to update.
        inmate_id:        Updated inmate identifier (optional).
        inmate_name:      Updated inmate full name (optional).
        display_name:     Updated display name shown in Zoom (optional).
        zoom_meeting_id:  Updated Zoom meeting number — 10 or 11 digits (optional).
        meeting_passcode: Updated Zoom passcode (optional).
        device_id:        Updated device assignment, e.g. 'VC02' (optional).
    """
    overrides = {
        k: v
        for k, v in {
            "inmateId": inmate_id,
            "inmateName": inmate_name,
            "displayName": display_name,
            "zoomMeetingId": zoom_meeting_id,
            "meetingPasscode": meeting_passcode,
            "deviceId": device_id,
        }.items()
        if v
    }

    if not overrides:
        return "No fields provided to update."

    try:
        # Fetch current meeting so we can preserve untouched fields
        current = api_get(f"/api/meetings/{meeting_id}")
    except Exception as e:
        return f"Error fetching meeting {meeting_id} before update: {e}"

    # Build full body from existing values, then apply caller's overrides
    body = {
        "inmateId": current.get("inmateId", ""),
        "inmateName": current.get("inmateName", ""),
        "displayName": current.get("displayName", ""),
        "zoomMeetingId": current.get("zoomMeetingId", ""),
        "meetingPasscode": current.get("meetingPasscode", ""),
        "deviceId": current.get("deviceId") or "",
    }
    body.update(overrides)

    # Strip empty deviceId so the server treats it as "no device"
    if not body["deviceId"]:
        body.pop("deviceId", None)

    try:
        result = api_put(f"/api/meetings/{meeting_id}", body)
        changed = ", ".join(overrides.keys())
        return (
            f"Meeting {meeting_id} updated (changed: {changed}).\n"
            f"{json.dumps(result, indent=2, default=str)}"
        )
    except Exception as e:
        return f"Error updating meeting {meeting_id}: {e}"


@tool
def assign_meeting_to_device(meeting_id: str, device_id: str) -> str:
    """
    Assign a meeting to a specific device by updating the meeting record's deviceId.

    This is a pure data-store operation (PUT /api/meetings/{id}) — it has NO device
    mode check and works regardless of whether the device is in Auto or Manual mode.
    It does NOT dispatch the MQTT schedule command; use schedule_call afterwards if
    you also want to notify the SmartClient.

    Use this when:
    - You want to link a meeting to a device without triggering the schedule flow
    - The device is in Manual mode (schedule_call would be rejected by the server)
    - You want to pre-assign a device before scheduling

    Args:
        meeting_id: The GUID of the meeting to assign.
        device_id:  The device identifier to assign it to, e.g. 'VC01'.
                    Pass an empty string "" to un-assign the device.
    """
    try:
        current = api_get(f"/api/meetings/{meeting_id}")
    except Exception as e:
        return f"Error fetching meeting {meeting_id}: {e}"

    body = {
        "inmateId": current.get("inmateId", ""),
        "inmateName": current.get("inmateName", ""),
        "displayName": current.get("displayName", ""),
        "zoomMeetingId": current.get("zoomMeetingId", ""),
        "meetingPasscode": current.get("meetingPasscode", ""),
    }
    if device_id:
        body["deviceId"] = device_id
    # if device_id is empty, omit deviceId → server sets it to null (un-assign)

    try:
        result = api_put(f"/api/meetings/{meeting_id}", body)
        action = f"assigned to {device_id}" if device_id else "un-assigned from device"
        return (
            f"Meeting {meeting_id} {action}.\n"
            f"{json.dumps(result, indent=2, default=str)}"
        )
    except Exception as e:
        return f"Error assigning meeting {meeting_id} to device: {e}"


@tool
def delete_meeting(meeting_id: str) -> str:
    """
    Delete a meeting by its ID. This is irreversible.

    Args:
        meeting_id: The GUID identifier of the meeting to delete.
    """
    try:
        api_delete(f"/api/meetings/{meeting_id}")
        return f"Meeting {meeting_id} deleted successfully."
    except Exception as e:
        return f"Error deleting meeting {meeting_id}: {e}"


ALL_TOOLS = [
    list_meetings,
    get_meeting,
    create_meeting,
    update_meeting,
    assign_meeting_to_device,
    delete_meeting,
]
