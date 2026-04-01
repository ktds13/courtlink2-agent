# CourtLink2.CCM — Conference Control Module

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Configuration](#4-configuration)
5. [Module Reference](#5-module-reference)
   - [Meeting Management Panel](#51-meeting-management-panel)
   - [Device Control Panel](#52-device-control-panel)
   - [Live Video Streaming](#53-live-video-streaming)
   - [Language Interpretation](#54-language-interpretation)
   - [Pan-Tilt Camera Control](#55-pan-tilt-camera-control)
6. [MQTT Topics](#6-mqtt-topics)
7. [REST API Calls](#7-rest-api-calls)
8. [Key Models & ViewModels](#8-key-models--viewmodels)
9. [Operator Guide](#9-operator-guide)

---

## 1. Overview

**CourtLink2.CCM** (Conference Control Module) is the operator-facing desktop control console for the CourtLink2 video visitation system. It runs on a supervisor workstation and provides centralized management of all courtroom videoconferencing endpoints.

### Role in the System

| Communicates With | Protocol | Purpose |
|---|---|---|
| CourtLink2.Management | HTTPS (mTLS, port 5055) | Meeting CRUD, device list, call lifecycle commands |
| CourtLink2.Management | MQTT | Receive live stream status, meeting announcements, per-device event streams |
| Wowza Media Server | RTSP (via LibVLC) | Live video playback from courtroom cameras |

Operators use CCM to:
- Schedule and manage inmate video meetings
- Monitor the real-time status of every courtroom device
- Start, pause, resume, and end video calls
- Watch live RTSP camera feeds
- Control pan-tilt cameras and language interpretation channels

---

## 2. Architecture

```
CourtLink2.CCM (WinUI 3 Desktop Application)
├── Program.cs              Single-instance enforcement + COM init + IHost bootstrap
├── App.xaml.cs             IHost start + MainWindow activation
├── AppSetup.cs             DI service registration + appsettings binding
│
├── MainWindow              Top-level shell: DeviceControl + MeetingControl panels
│
├── Controls/               Reusable XAML UserControls
│   ├── DeviceControl       Device grid with zone tabs
│   ├── DeviceItemControl   Individual device tile
│   ├── MeetingControl      Meeting list + CRUD panel
│   ├── InterpretationControl
│   └── PantiltControl
│
├── ViewModel/              ReactiveUI ViewModels (MVVM)
│   ├── DeviceControlViewModel    Grid layout, zone grouping, assignment logic
│   ├── DeviceItemViewModel       Per-device reactive state machine
│   ├── MeetingViewModel          Meeting CRUD, validation, drag-and-drop
│   └── ...
│
├── Services/               IHostedService + background services
│   ├── MessagingService    MQTT lifecycle (connect/disconnect)
│   ├── MeetingManager      MQTT meeting announcement subscriber
│   ├── StreamingManager    MQTT live stream status subscriber
│   └── DeviceControlStream Reactive MQTT event stream per device
│
├── DataProvider/           HTTP client wrappers for Management REST API
│   ├── DeviceDataProvider
│   ├── MeetingDataProvider
│   ├── CallDataProvider
│   └── RoomControlProvider
│
└── Controllers/
    └── PlayerController    LibVLC RTSP playback
```

### Startup Sequence

1. `Program.cs` — checks for an existing instance via `AppInstance.FindOrRegisterForKey("CourtLink2.CCM.SingleInstance")`. If one exists, activates it and exits. Otherwise, initialises COM wrappers and launches `App`.
2. `App.xaml.cs` — builds the `IHost` through `AppSetup`, starts it, and resolves + shows `MainWindow` maximised (with multi-monitor placement support).
3. `MessagingService` (hosted) — connects to the MQTT broker on host start and disconnects on host stop.

---

## 3. Technology Stack

| Category | Library / Version |
|---|---|
| Framework | .NET 8, Windows App SDK 1.7 (`net8.0-windows10.0.19041.0`) |
| UI Framework | WinUI 3 (XAML + C#) via `Microsoft.WindowsAppSDK`, `WinUIEx` |
| Reactive Programming | `ReactiveUI` 20.1.63, `ReactiveUI.WinUI` |
| Messaging | MQTT via `CourtLink2.Messaging` (`MQTTnet`) |
| HTTP | `System.Net.Http` + `Polly.Extensions.Http` (exponential backoff) |
| Media Playback | `LibVLCSharp` 3.9.2, `VideoLAN.LibVLC.Windows` |
| Logging | NLog 5.4 (file + Windows Event Log) |
| Data Utilities | Newtonsoft.Json, `CsvHelper`, `ClosedXML` (Excel) |
| DI / Hosting | `Microsoft.Extensions.Hosting` |
| UI Components | `CommunityToolkit.WinUI.UI.Controls.DataGrid`, `WinUI.TableView` |

---

## 4. Configuration

CCM is configured through layered `appsettings.*.json` files. The active environment is controlled by the `DOTNET_ENVIRONMENT` environment variable (defaults to `Production`).

### Configuration Files

| File | Purpose |
|---|---|
| `appsettings.json` | NLog base configuration (log targets, levels) |
| `appsettings.Development.json` | Full development overrides (API URL, MQTT broker, etc.) |
| `appsettings.Production.json` | Production values |
| `appsettings.CI.json` | CI pipeline values |

### Key Settings (`ApplicationSettings`)

| Key | Type | Description |
|---|---|---|
| `ClientId` | string | Unique identifier for this CCM instance |
| `Api.BaseUrl` | string | Base URL of the Management REST API (e.g. `https://mgt.cl2.sps:5055`) |
| `Api.Timeout` | int | HTTP request timeout in seconds |
| `Api.MaxRetryAttempts` | int | Number of Polly retry attempts on transient failures |
| `MQTT.ServerAddress` | string | MQTT broker hostname (e.g. `msg.cl2.sps`) |
| `MQTT.Port` | int | MQTT broker port (e.g. `5883`) |
| `MQTT.ClientId` | string | MQTT client identifier (e.g. `ccm1`) |
| `MQTT.ClientCertificate` | string | Name of the mTLS client certificate |
| `MQTT.KeepAlive` | int | Keep-alive interval in seconds |
| `MQTT.WillRetain` | bool | Retain the MQTT will message |
| `Streaming.URLTemplate` | string | RTSP URL template with `{EngineIP}` and `{StreamName}` placeholders |
| `Streaming.PlayerOptions` | string | LibVLC player option string |
| `Layout.MaxItemPerRow` | int | Maximum device tiles per row in the device grid |
| `Layout.ItemsStretch` | string | WinUI stretch mode for tiles |
| `Layout.ItemsJustification` | string | WinUI justification for tile rows |
| `PlayerRetryDelay` | int | Seconds to wait before retrying a failed RTSP stream |
| `DisplayOnPrimaryScreen` | bool | Force CCM window to the primary monitor |
| `NotiDuration` | int | Duration in seconds for toast notifications |
| `AlertSoundFilePath` | string | Directory containing the alert audio file |
| `AlertSoundFile` | string | Alert audio file name (WAV) |
| `AlertPlayingDelay` | int | Delay between repeated alert sounds (ms) |
| `RoomFormat` | string | Display name format string for rooms |
| `RequireDeleteConfirmation` | bool | Show confirmation dialog before deleting a meeting |

### Example (Development)

```json
{
  "ClientId": "ccm1",
  "Api": {
    "BaseUrl": "https://mgt.cl2.sps:5055",
    "Timeout": 30,
    "MaxRetryAttempts": 3
  },
  "MQTT": {
    "ServerAddress": "msg.cl2.sps",
    "Port": 5883,
    "ClientId": "ccm1",
    "ClientCertificate": "ccm1"
  },
  "Streaming": {
    "URLTemplate": "rtsp://{EngineIP}/live/{StreamName}"
  }
}
```

---

## 5. Module Reference

### 5.1 Meeting Management Panel

**Files:** `Controls/MeetingControl.xaml(.cs)`, `ViewModel/MeetingViewModel.cs`, `DataProvider/MeetingDataProvider.cs`

This panel displays the list of today's meetings and provides full CRUD operations.

#### Features

| Feature | Description |
|---|---|
| View meetings | Fetches meetings from `GET /api/meetings` on load and on MQTT meeting announcement |
| Create meeting | Opens `MeetingEntryForm` dialog; validates all fields before `POST /api/meetings` |
| Edit meeting | Opens `MeetingEntryForm` pre-populated; calls `PUT /api/meetings/{id}` |
| Delete meeting | Calls `DELETE /api/meetings/{id}`; optionally prompts for confirmation (`RequireDeleteConfirmation`) |
| Bulk import | Parses CSV or Excel (`.xlsx`) files via `CsvHelper` / `ClosedXML`; calls `POST /api/meetings/bulk` |
| Search / filter | Client-side filter on InmateId, DisplayName |
| Drag-and-drop | Drag a meeting row onto a device tile to assign it |

#### Validation Rules (`MeetingViewModel`)

| Field | Rule |
|---|---|
| `InmateId` | Required, numeric |
| `DisplayName` | Required |
| `MeetingId` | Required, 10–11 digits |
| `Passcode` | Required |

Validation errors are surfaced via `INotifyDataErrorInfo` and shown inline in the form.

---

### 5.2 Device Control Panel

**Files:** `Controls/DeviceControl.xaml(.cs)`, `Controls/DeviceItemControl.xaml(.cs)`, `ViewModel/DeviceControlViewModel.cs`, `ViewModel/DeviceItemViewModel.cs`, `ViewModel/DeviceGroupViewModel.cs`, `Services/DeviceControlStream.cs`

This is the main operational panel showing the real-time state of every courtroom device.

#### Layout

Devices are organised into **zone-based tabs** (`DeviceGroupViewModel`). Each tab corresponds to a physical area of the facility. Within each tab, device tiles are arranged in a configurable grid (`MaxItemPerRow`).

#### Per-Device State Machine (`DeviceItemViewModel`)

Each device tile subscribes to four MQTT event streams via `DeviceControlStream`:

| Stream Topic | Event Type | Description |
|---|---|---|
| `call/{deviceId}` | `CallStatus` | Current call phase |
| `meeting-status/{deviceId}` | `MeetingStatus` | Zoom meeting state |
| `connection-status/{deviceId}` | `ConnectionStatus` | Device online/offline |
| `device-mode/{deviceId}` | `DeviceMode` | Auto or Manual mode |

State transitions:

```
Idle → Scheduled → Started → Paused → Resumed → Ended → Idle
                ↘ Cancelled → Idle
```

#### Device Tile Visual States

| State | Colour Style | Available Actions |
|---|---|---|
| Offline | `OfflineControlStyle` | — |
| Idle / Online | `ValidControlStyle` | Assign meeting |
| Scheduled | `PendingControlStyle` | Start, Cancel |
| Started | `CallControlStyle` | Pause, End |
| Paused | `PendingControlStyle` | Resume, End |
| Error | `ErrorControlStyle` | Retry |

#### Conflict Detection

`DeviceControlViewModel` prevents:
- Assigning the same inmate/meeting to two devices simultaneously.
- Starting a call on a device that already has an active call.

#### Zone Tab Badges

Each zone tab shows a notification badge count for devices requiring attention (offline, error, or with pending calls).

---

### 5.3 Live Video Streaming

**Files:** `Services/StreamingManager.cs`, `Controllers/PlayerController.cs`, `Services/MessagingService.cs`

CCM can display live RTSP video feeds from courtroom cameras alongside device tiles.

#### How It Works

1. `StreamingManager` subscribes to `AppTopics.LiveStreamStatus` on MQTT.
2. Management publishes `LiveStreamStatus` records (containing `EngineIP`, `StreamName`, and a short-lived Wowza playback token) on a configurable timer.
3. `StreamingManager` updates `LiveStreamDeviceConnection` objects and notifies the UI.
4. `PlayerController` builds the RTSP URL from `Streaming.URLTemplate`, appending the secure token, then passes it to `LibVLCSharp` for playback inside the device tile.
5. On stream failure, `PlayerController` retries after `PlayerRetryDelay` seconds.

#### RTSP URL Template

```
rtsp://{EngineIP}/live/{StreamName}?token=<wowza_token>
```

---

### 5.4 Language Interpretation

**Files:** `Controls/InterpretationControl.xaml(.cs)`, `ViewModel/LanguageInterpretationViewModel.cs`

Provides a UI panel for monitoring and controlling Zoom language interpretation channels across one or more active meetings. Operators can see which language channels are active and interact with SmartClient endpoints that have joined interpretation channels.

---

### 5.5 Pan-Tilt Camera Control

**Files:** `Controls/PantiltControl.xaml(.cs)`, shared `CourtLink2.CameraControl`

Provides directional (pan/tilt) and zoom controls for PTZ cameras installed in courtrooms. Camera commands are dispatched through the shared `CameraControlService`.

---

## 6. MQTT Topics

### Subscribed by CCM

| Topic Pattern | Payload | Source | Purpose |
|---|---|---|---|
| `AppTopics.CallSubscription` | `CallStatus` | SmartClient (via Management) | Per-device call phase updates |
| `AppTopics.MeetingStatusSubscription` | `MeetingStatus` | SmartClient (via Management) | Zoom meeting state per device |
| `AppTopics.ConnectionStatusSubscription` | `ConnectionStatus` | SmartClient | Device online/offline events |
| `AppTopics.DeviceSyncModeSubscription` | `DeviceSyncModeRequest` | SmartClient | Auto/Manual mode changes |
| `AppTopics.LiveStreamStatus` | `LiveStreamStatus[]` | Management | Wowza stream info + tokens |
| `AppTopics.MeetingAnnounceTopic()` | (trigger) | Management | Signals CCM to reload meeting list |

### Published by CCM

CCM does not publish MQTT messages directly. All state-changing operations (schedule, start, end, pause, resume, cancel) are sent as HTTP requests to the Management REST API, which then dispatches MQTT commands to the SmartClient devices.

---

## 7. REST API Calls

All HTTP calls go to `Api.BaseUrl` using mTLS client certificate authentication. The CCM holds the `Monitor` role, giving it full access.

### Endpoints Used

| Operation | Method | Endpoint | Notes |
|---|---|---|---|
| List devices | `GET` | `/api/devices` | Called on startup |
| Get system configs | `GET` | `/api/systemconfigs` | Called on startup |
| List meetings | `GET` | `/api/meetings` | Called on load + MQTT trigger |
| Create meeting | `POST` | `/api/meetings` | Single meeting creation |
| Update meeting | `PUT` | `/api/meetings/{id}` | Edit existing meeting |
| Upsert by InmateId | `PUT` | `/api/meetings/upsert/{inmateId}` | Create or update by inmate |
| Delete meeting | `DELETE` | `/api/meetings/{id}` | |
| Bulk import meetings | `POST` | `/api/meetings/bulk` | Array of meeting objects |
| Schedule call | `POST` | `/call/schedule` | Assign meeting to device |
| Start call | `PUT` | `/call/start` | Launch Zoom meeting on device |
| End call | `PUT` | `/call/end` | End active Zoom meeting |
| Pause call | `PUT` | `/call/pause` | Pause active Zoom meeting |
| Resume call | `PUT` | `/call/resume` | Resume paused Zoom meeting |
| Cancel call | `PUT` | `/call/cancel` | Cancel a scheduled call |

### Retry Policy

`Polly.Extensions.Http` wraps all HTTP calls with exponential backoff. The number of retries is controlled by `Api.MaxRetryAttempts`.

---

## 8. Key Models & ViewModels

### `ControlDevice` (immutable record)

The core unit of state for a device tile. State transitions are applied immutably via `ControlDeviceExtensions`.

| Property | Type | Description |
|---|---|---|
| `Id` | string | Device identifier |
| `Name` | string | Display name |
| `Status` | `CallStatus` | Current call phase (Idle, Scheduled, Started, Paused, Ended) |
| `Command` | `CallCommand` | Last command issued |
| `ConnectionStatus` | enum | Online / Offline |
| `CallMode` | enum | Active call mode |
| `DeviceMode` | enum | Auto or Manual |
| `MeetingInfo` | `MeetingInfo` | Associated meeting details |
| `SessionId` | string | Current session identifier |

### `DeviceItemViewModel`

Wraps `ControlDevice` with `ReactiveUI` observables. Exposes:
- `ReactiveCommand` for Start, End, Pause, Resume, Cancel actions
- Computed properties for button visibility, tile colour style, and badge count
- Subscription to `DeviceControlStream` for the four MQTT event streams

### `MeetingViewModel`

Manages the meeting list and form state. Key members:

| Member | Description |
|---|---|
| `Meetings` | `ObservableCollection<MeetingInfo>` bound to the list |
| `SelectedMeeting` | Currently selected meeting |
| `SaveCommand` | Validates and saves (create or update) |
| `DeleteCommand` | Deletes selected meeting |
| `ImportCommand` | Opens file picker and bulk-imports |
| `ReloadCommand` | Refreshes from API |
| `HasErrors` | True when validation errors are present |

---

## 9. Operator Guide

### Prerequisites

- Windows 10 (build 19041) or later
- Network access to the Management server (`Api.BaseUrl`) and MQTT broker (`MQTT.ServerAddress`)
- Valid mTLS client certificate installed in the Windows certificate store
- LibVLC runtime (bundled with the installer)

### Starting CCM

1. Launch **CourtLink2.CCM.exe**. Only one instance may run at a time; if another instance is already running, it will be brought to the foreground.
2. The application window opens maximised. The bottom half shows the **Device Control** panel (zone tabs with device tiles); the side panel shows the **Meeting** list.
3. The status bar icons indicate:
   - MQTT broker connection (green = connected)
   - Management API reachability

### Assigning a Meeting to a Device

1. In the **Meetings** panel, locate the inmate's meeting row.
2. Drag the row and drop it onto the desired device tile in the **Device Control** panel.
3. The tile changes to `Scheduled` state (yellow/pending colour).

### Starting a Call

1. Find the device tile showing `Scheduled`.
2. Click the **Start** button on the tile.
3. The tile transitions to `Started` (blue/call colour) once the SmartClient confirms the Zoom meeting has launched.

### Pausing / Resuming a Call

- Click **Pause** on an active (`Started`) tile. The tile moves to `Paused` state.
- Click **Resume** on a `Paused` tile to continue the call.

### Ending a Call

- Click **End** on a `Started` or `Paused` tile.
- The tile returns to `Idle` after the SmartClient confirms the meeting has ended.

### Cancelling a Scheduled Call

- Click **Cancel** on a `Scheduled` tile to release the meeting assignment.

### Creating a Meeting Manually

1. Click **New Meeting** in the Meetings panel.
2. Fill in InmateId, DisplayName, Meeting ID (10–11 digits), and Passcode.
3. Click **Save**.

### Bulk Importing Meetings

1. Click **Import** in the Meetings panel.
2. Select a CSV or Excel (`.xlsx`) file. The file must have columns: `Inmate_ID`, `Inmate_Name`, `Display_Name`, `Room`, `Meeting_ID`, `Passcode`.
3. CCM validates and posts all rows to the Management API. Errors are shown per row.

### Viewing Live Video

- When a camera stream is active, a video thumbnail appears on the device tile.
- Click the thumbnail to expand the RTSP stream in a larger player.
- If the stream stalls, it automatically retries after `PlayerRetryDelay` seconds.

### Troubleshooting

| Symptom | Likely Cause | Resolution |
|---|---|---|
| All tiles show "Offline" | MQTT broker unreachable | Check `MQTT.ServerAddress` and broker service |
| Meeting list empty | Cannot reach Management API | Check `Api.BaseUrl` and certificate |
| RTSP player blank | Wowza stream not active or token expired | Confirm Wowza engine is running; restart Management `StreamingService` |
| Start button disabled | Device already in a call or not `Scheduled` | Verify device state; check for duplicate assignment |
| Alert sound not playing | `AlertSoundFilePath` or `AlertSoundFile` misconfigured | Verify path and WAV file exist |
