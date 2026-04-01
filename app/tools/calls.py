"""
calls.py — LangChain tools for CourtLink2 call lifecycle management.

The call lifecycle in CourtLink2 follows this state machine:
    (none) → schedule → start → [pause ↔ resume] → end
                     └─────────────────────────────→ cancel

Tools exposed:
    schedule_call  — POST /call/schedule   — assign a meeting to a device
    start_call     — PUT  /call/start      — begin the Zoom session
    pause_call     — PUT  /call/pause      — pause an active call
    resume_call    — PUT  /call/resume     — resume a paused call
    end_call       — PUT  /call/end        — end the call and persist the record
    cancel_call    — PUT  /call/cancel     — cancel a scheduled (not yet started) call
"""

import json
from langchain_core.tools import tool

from .api_client import api_get, api_post, api_put


@tool
def schedule_call(device_id: str, meeting_id: str) -> str:
    """
    Schedule a meeting on a specific CourtLink2 device. This assigns the
    meeting to the device so it is ready to be started. The SmartClient on
    that device will receive the assignment via MQTT.

    The server requires the full meeting details (not just the ID), so this
    tool automatically fetches the meeting record first and sends the complete
    ScheduleRequest body.

    Args:
        device_id:  The device identifier, e.g. 'VC01'.
        meeting_id: The internal GUID of the meeting to schedule (from list_meetings).

    Errors:
        400 "Device not found / offline / manual mode" — check device status with get_device.
        400 "Meeting Id ... does not exist" — the meeting must exist and have been
            created/modified today. Use list_meetings to confirm the ID is correct.
        400 "The meeting is already reserved with room ..." — meeting is already
            scheduled on another device; cancel that assignment first.
    """
    # Fetch the full meeting record — the server requires a nested MeetingInfo object
    try:
        meeting = api_get(f"/api/meetings/{meeting_id}")
    except Exception as e:
        return f"Error fetching meeting {meeting_id}: {e}"

    body = {
        "deviceId": device_id,
        "meeting": {
            "id": meeting.get("id", meeting_id),
            "inmateId": meeting.get("inmateId", ""),
            "inmateName": meeting.get("inmateName", ""),
            "displayName": meeting.get("displayName", ""),
            "zoomMeetingId": meeting.get("zoomMeetingId", ""),
            "meetingPasscode": meeting.get("meetingPasscode", ""),
            "deviceId": meeting.get("deviceId", ""),
            "deviceName": meeting.get("deviceName", ""),
            "startTime": meeting.get("startTime"),
        },
    }

    try:
        result = api_post("/call/schedule", body)
        return f"Call scheduled on {device_id}.\n{json.dumps(result, indent=2, default=str)}"
    except Exception as e:
        return f"Error scheduling call on {device_id}: {e}"


@tool
def start_call(device_id: str) -> str:
    """
    Start the scheduled Zoom call on a device. The SmartClient will join the
    Zoom meeting and the call status will change to 'Started'.

    Args:
        device_id: The device identifier, e.g. 'VC01'.
    """
    try:
        result = api_put("/call/start", params={"deviceId": device_id})
        return (
            f"Call started on {device_id}.\n{json.dumps(result, indent=2, default=str)}"
        )
    except Exception as e:
        return f"Error starting call on {device_id}: {e}"


@tool
def pause_call(device_id: str) -> str:
    """
    Pause an active Zoom call on a device. The SmartClient will leave the Zoom
    meeting temporarily. The call can be resumed afterwards.

    Args:
        device_id: The device identifier, e.g. 'VC01'.
    """
    try:
        result = api_put("/call/pause", params={"deviceId": device_id})
        return (
            f"Call paused on {device_id}.\n{json.dumps(result, indent=2, default=str)}"
        )
    except Exception as e:
        return f"Error pausing call on {device_id}: {e}"


@tool
def resume_call(device_id: str) -> str:
    """
    Resume a previously paused call on a device. The SmartClient will
    re-join the Zoom meeting.

    Args:
        device_id: The device identifier, e.g. 'VC01'.
    """
    try:
        result = api_put("/call/resume", params={"deviceId": device_id})
        return (
            f"Call resumed on {device_id}.\n{json.dumps(result, indent=2, default=str)}"
        )
    except Exception as e:
        return f"Error resuming call on {device_id}: {e}"


@tool
def end_call(device_id: str, meeting_id: str) -> str:
    """
    End an active or paused call. The Management server will persist the call
    record to the database and the SmartClient will leave the Zoom meeting.

    Args:
        device_id:  The device identifier, e.g. 'VC01'.
        meeting_id: The GUID of the active meeting on the device.
    """
    try:
        result = api_put("/call/end", {"deviceId": device_id, "meetingId": meeting_id})
        return (
            f"Call ended on {device_id}.\n{json.dumps(result, indent=2, default=str)}"
        )
    except Exception as e:
        return f"Error ending call on {device_id}: {e}"


@tool
def cancel_call(device_id: str) -> str:
    """
    Cancel a scheduled (not yet started) call on a device. The device will
    return to idle state.

    Args:
        device_id: The device identifier, e.g. 'VC01'.
    """
    try:
        result = api_put("/call/cancel", params={"deviceId": device_id})
        return f"Call cancelled on {device_id}.\n{json.dumps(result, indent=2, default=str)}"
    except Exception as e:
        return f"Error cancelling call on {device_id}: {e}"


ALL_TOOLS = [schedule_call, start_call, pause_call, resume_call, end_call, cancel_call]
