# CourtLink2.SmartClient

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Configuration](#4-configuration)
5. [Module Reference](#5-module-reference)
   - [Zoom SDK Integration](#51-zoom-sdk-integration)
   - [MeetingController](#52-meetingcontroller)
   - [Language Interpretation](#53-language-interpretation)
   - [MainWindow Layout](#54-mainwindow-layout)
   - [TaskBar](#55-taskbar)
   - [AutoDisableWindowDetector](#56-autodisablewindowdetector)
   - [Banner](#57-banner)
   - [DPAPIHelper](#58-dpapihelper)
6. [MQTT Topics](#6-mqtt-topics)
7. [Zoom API Status States](#7-zoom-api-status-states)
8. [Auto vs Manual Mode](#8-auto-vs-manual-mode)
9. [Operator Guide](#9-operator-guide)

---

## 1. Overview

**CourtLink2.SmartClient** is the per-room endpoint application that runs on every videoconferencing workstation inside a courtroom or visitation facility. It:

- Embeds and controls the **Zoom meeting client** via the native Zoom Windows SDK.
- Communicates with **CourtLink2.Management** over MQTT to receive call commands and report device status.
- Provides a minimal WPF overlay showing room information, connection status, and audio/video controls.

### Role in the System

```
Management ──MQTT──► SmartClient  (CallRequest commands)
SmartClient ──MQTT──► Management  (MeetingStatus, ConnectionStatus, DeviceMode)
CCM ──MQTT──► SmartClient         (DeviceControl: pan-tilt, volume, language interp)
```

Each SmartClient instance is identified by a unique `DeviceID` (e.g. `VC01`). All MQTT topics are namespaced per device.

---

## 2. Architecture

```
CourtLink2.SmartClient (WPF Desktop Application)
├── App.xaml.cs             Single-instance mutex + IHost bootstrap
├── AppSetup.cs             DI registration + appsettings binding + DPAPI identity
├── MainWindow.xaml(.cs)    Top-level shell: Zoom embed + floating sub-windows
├── Win32ControlHost.cs     HwndHost: embeds native Zoom window into WPF visual tree
│
├── MQZoomer/               Zoom SDK integration layer
│   ├── ZoomClient.cs               Top-level Zoom SDK facade (auth, join/leave, A/V)
│   ├── MeetingController.cs        Central orchestrator: MQTT commands → Zoom actions
│   ├── ZoomMeetingController.cs    Low-level Zoom meeting API wrapper
│   ├── ZoomMeetingService.cs       Join/leave session logic
│   ├── AVController.cs             Audio/video device selection and mute control
│   ├── AudioIndicatorController.cs Real-time VU meter reading
│   ├── VideoLayoutService.cs       Zoom video layout management
│   ├── LanguageInterpretationController.cs
│   ├── LanguageInterpretationService.cs
│   ├── ShareController.cs          Screen sharing control
│   └── JWTHelper.cs                Zoom SDK JWT token generation
│
├── Services/
│   ├── MqttMessagePubSub.cs        All MQTT publish/subscribe for this device
│   ├── MeetingEventPublisher.cs    Language interp + reset event publishing
│   ├── DeviceStatusPublisher.cs    A/V device connection status publishing
│   ├── DeviceControlService.cs     Handles ControlRequest commands from CCM
│   ├── ScmNotificationManager.cs   Toast notification display
│   ├── MeetingCommandObserver.cs   MQTT → MeetingController command bridge
│   └── AutoDisableWindowDetector.cs  Suppresses unwanted Zoom popup windows
│
├── ViewModel/
│   ├── MainViewModel.cs            Loading state, title image, popup text
│   ├── TaskBarVM.cs                Auth/server status icons, InmateId, clock, mode toggle
│   ├── AVDeviceVM.cs               Camera/mic/speaker detection + mute state
│   ├── AudioIndicatorVM.cs         Real-time VU meter bar values
│   ├── LanguageInterpretationVM.cs Language channel selection state
│   └── BannerViewModel.cs          Room label banner state
│
├── UserControls/
│   ├── TaskBar.xaml(.cs)           Bottom toolbar
│   ├── MeetingForm.xaml(.cs)       Manual meeting join form
│   ├── SettingWindow.xaml(.cs)     Floating A/V settings panel
│   ├── SelfViewWindow.xaml(.cs)    Floating self-video preview
│   ├── SharingUserOverlay.xaml     Screen-share presenter overlay
│   ├── ParticipantCountOverlay     Participant count during screen share
│   ├── LanguageInterpretation.xaml
│   └── Banner.xaml(.cs)            Room label banner
│
└── Infrastructure/
    └── DPAPIHelper.cs              DPAPI-encrypted DeviceID + ClientID storage
```

### Startup Sequence

1. `App.xaml.cs` — acquires a named `Mutex("CourtLink2.SmartClient.SingleInstance")`. If the mutex is already held, the application exits immediately.
2. `AppSetup` builds the `IHost`: loads configuration, reads `DeviceID` and MQTT `ClientId` from DPAPI (Release) or uses hardcoded values (Debug).
3. On `OnStartup`: starts the host, resolves `MainWindow`, connects `MessageBus` to the MQTT broker.
4. `MeetingCommandObserver` subscribes to the MQTT command topic for this device.
5. `MeetingController` publishes an initial `DeviceConnectionRequest` (online) and a full status sync to Management.

---

## 3. Technology Stack

| Category | Library / Version |
|---|---|
| Framework | .NET 8 WPF (`net8.0-windows8.0`) |
| UI Framework | WPF (XAML + C#) |
| UI Theme | MaterialDesignThemes 5.2.1 |
| Reactive Programming | `ReactiveUI` 20.1.63 |
| Zoom Integration | Zoom Windows SDK (`ZOOM_SDK_DOTNET_WRAP` — native C++ wrapper + `Nete2MeetingSDK`) |
| Audio | `NAudio` 2.2.1 (device enumeration, VU meter) |
| JWT | `jose-jwt` 5.1.1 (Zoom SDK authentication token) |
| Messaging | MQTT via `CourtLink2.Messaging` (`MQTTnet`) |
| Configuration | `Microsoft.Extensions.Configuration.Ini` + JSON |
| Notifications | `Notifications.Wpf.Core` (toast notifications) |
| Security | Windows DPAPI (`DPAPIHelper`) for encrypted device identity |
| Logging | NLog 5.4 (file `CourtLink.SCM.log`, Windows Event Log source `SmartClient1`, ID 550) |

---

## 4. Configuration

SmartClient uses layered `appsettings.*.json` files. The environment is controlled by `DOTNET_ENVIRONMENT`. Zoom SDK credentials are stored in a separate `zoomsettings.json` file.

### Configuration Files

| File | Purpose |
|---|---|
| `appsettings.json` | NLog base configuration |
| `appsettings.Development.json` | Full development config (hardcoded DeviceID, MQTT, camera, audio) |
| `appsettings.Production.json` | Production config (DeviceID/ClientId from DPAPI) |
| `zoomsettings.json` | Zoom SDK credentials (ClientID, ClientSecret) — not copied to output |

### Key Settings (`ApplicationSettings`)

#### Identity

| Key | Description |
|---|---|
| `DeviceID` | Unique room identifier (e.g. `VC01`). In Production, read from DPAPI. |

#### MQTT

| Key | Description |
|---|---|
| `MQTT.ServerAddress` | Broker hostname |
| `MQTT.Port` | Broker port |
| `MQTT.ClientId` | MQTT client identifier. In Production, read from DPAPI. |
| `MQTT.ClientCertificate` | Name of the mTLS client certificate |

#### Camera

| Key | Description |
|---|---|
| `Camera.Name` | Camera device name substring to match (e.g. `Brio 505`) |
| `Camera.ZoomTotalSteps` | Number of steps for pan-tilt zoom range |
| `Camera.EnableHDVideo` | `true` to enable 1080p video |
| `Camera.EnableMirrorEffect` | `true` to mirror the local video preview |

#### Audio

| Key | Description |
|---|---|
| `AudioDevices.UseSystemDefault` | `true` to use Windows default audio devices |
| `AudioDevices.Microphones` | Array of microphone device name substrings (in priority order) |
| `AudioDevices.Speakers` | Array of speaker device name substrings (in priority order) |

#### Behaviour

| Key | Description |
|---|---|
| `AuthErrorRetryInterval` | Seconds to wait before retrying Zoom SDK authentication |
| `JoinErrorRetryInterval` | Seconds to wait before retrying a failed meeting join |
| `ShowNotificationInterval` | Seconds between repeated on-screen notifications |
| `ShowPopupInterval` | Seconds between repeated popup message intervals |
| `MaxActiveVideoParticipants` | Maximum simultaneous video tiles shown in Zoom layout |
| `DisplayWinControls` | `true` to show WPF window chrome (title bar, resize handles) |
| `AutoDisableWindows` | Array of window title substrings to automatically hide |

#### Banner

| Key | Description |
|---|---|
| `Banner.Content` | Room label text displayed when not in a meeting |
| `Banner.Style.FontSize` | Font size of the banner text |
| `Banner.Style.Color` | Font colour (hex or named colour) |
| `Banner.Style.FontWeight` | Font weight (e.g. `Bold`) |
| `Banner.Style.Margin` | WPF margin string |

### Example (Development)

```json
{
  "DeviceID": "VC01",
  "MQTT": {
    "ServerAddress": "msg.cl2.sps",
    "Port": 5883,
    "ClientId": "scm1",
    "ClientCertificate": "scm1"
  },
  "Camera": {
    "Name": "Brio 505",
    "EnableHDVideo": true,
    "EnableMirrorEffect": false
  },
  "AudioDevices": {
    "UseSystemDefault": false,
    "Microphones": ["Jabra"],
    "Speakers": ["Jabra"]
  },
  "Banner": {
    "Content": "Courtroom 1",
    "Style": {
      "FontSize": 48,
      "Color": "#FFFFFF",
      "FontWeight": "Bold"
    }
  },
  "AutoDisableWindows": ["Zoom Workplace"]
}
```

### `zoomsettings.json`

```json
{
  "ZoomCredentials": {
    "ClientId": "<Zoom SDK App Client ID>",
    "ClientSecret": "<Zoom SDK App Client Secret>"
  }
}
```

> **Security note:** `zoomsettings.json` is excluded from the build output. Deploy it separately to each workstation and restrict file system permissions.

---

## 5. Module Reference

### 5.1 Zoom SDK Integration

**Files:** `MQZoomer/ZoomClient.cs`, `MQZoomer/ZoomMeetingController.cs`, `MQZoomer/ZoomMeetingService.cs`, `MQZoomer/AVController.cs`, `Win32ControlHost.cs`

`ZoomClient` is the facade over the native **Zoom Windows SDK** (`ZOOM_SDK_DOTNET_WRAP`).

#### Authentication

On startup, `ZoomClient` calls `ZoomSDK.Initialize` and then authenticates using a JWT token generated by `JWTHelper` from the `ZoomCredentials` in `zoomsettings.json`. If authentication fails, it retries after `AuthErrorRetryInterval` seconds.

#### Joining / Leaving Meetings

`ZoomMeetingService` calls `ZoomSDK.GetMeetingService().Join()` with:

| Parameter | Source |
|---|---|
| Meeting ID | `MeetingInfo.ZoomMeetingId` (from MQTT `CallRequest`) |
| Passcode | `MeetingInfo.MeetingPasscode` |
| Display name | `MeetingInfo.DisplayName` |

On a join failure, SmartClient retries after `JoinErrorRetryInterval` seconds and reports the failure to Management via MQTT.

#### Embedding the Zoom Window

`Win32ControlHost` (a WPF `HwndHost`) retrieves the native HWND of the Zoom meeting window from the SDK and parents it inside the WPF visual tree, making the Zoom video view appear as a seamless element of the SmartClient UI.

#### Audio / Video Control (`AVController`)

| Operation | Description |
|---|---|
| Select microphone | Matches `AudioDevices.Microphones` names against the Zoom SDK audio device list |
| Select speaker | Matches `AudioDevices.Speakers` names against the Zoom SDK audio device list |
| Mute / unmute mic | Toggled by CCM `ControlRequest` or operator action |
| Select camera | Matches `Camera.Name` substring against Zoom camera list |
| Enable HD video | Configured by `Camera.EnableHDVideo` |
| Mirror effect | Configured by `Camera.EnableMirrorEffect` |

`DeviceStatusPublisher` reports the current A/V device connection state to Management via MQTT whenever it changes.

#### VU Meter (`AudioIndicatorController`)

`NAudio` continuously reads the audio level from the selected microphone and exposes it as a normalised float. `AudioIndicatorVM` maps this to bar heights for real-time visual feedback in the UI.

---

### 5.2 MeetingController

**File:** `MQZoomer/MeetingController.cs`

The central orchestrator of SmartClient — coordinates MQTT commands from Management with the Zoom SDK lifecycle. This is the most complex module in SmartClient.

#### Responsibilities

- Receives `CallRequest` commands from Management via MQTT (`MeetingCommandObserver` bridge).
- Drives `ZoomClient` join/leave based on command (`Schedule` → queue join; `Start` → trigger join; `Pause` → hold; `Resume` → rejoin; `None`/end → leave).
- Tracks local state: `CallStatus`, `DeviceMode`, `CallMode`, `SessionId`, current `MeetingInfo`.
- Publishes `MeetingStatus` back to Management on every Zoom SDK status change.
- On MQTT reconnect: re-publishes full status sync (meeting status + device connection status).

#### Call Flow

```
Management sends CallRequest (Schedule)
    └─► MeetingController queues meeting info

Management sends CallRequest (Start)
    └─► MeetingController calls ZoomClient.JoinMeeting()
        └─► Zoom SDK fires ZoomApiStatus = CONNECTING → INMEETING
            └─► MeetingController publishes MeetingStatus(Started) via MQTT

Meeting ends (host ends or End command)
    └─► Zoom SDK fires ZoomApiStatus = ENDED / HOST_ENDED
        └─► MeetingController publishes MeetingStatus(Ended) via MQTT
```

#### Session ID Locking

When Management sends a command, it includes a `SessionId`. `MeetingController` validates that the `SessionId` matches the currently active session before executing the command. This prevents stale or duplicate commands from affecting a different session.

---

### 5.3 Language Interpretation

**Files:** `MQZoomer/LanguageInterpretationController.cs`, `MQZoomer/LanguageInterpretationService.cs`, `ViewModel/LanguageInterpretationVM.cs`, `UserControls/LanguageInterpretation.xaml`

Wraps the Zoom SDK's built-in language interpretation feature.

| Operation | Description |
|---|---|
| Join channel | Subscribes to a language interpretation channel by `languageId` |
| Leave channel | Unsubscribes from the current channel |
| Toggle main audio | Enables/disables the main meeting audio while on an interpretation channel |

Commands arrive via MQTT `LanguageInterpretationRequest` on `AppTopics.LanguageInterpretationControlTopic(deviceId)`. Status changes are published via `MeetingEventPublisher`.

---

### 5.4 MainWindow Layout

**File:** `MainWindow.xaml(.cs)`

The top-level WPF window. It acts as a shell that:

- Hosts `Win32ControlHost` — the embedded Zoom video pane.
- Manages floating sub-windows:

| Sub-window | Description |
|---|---|
| `SelfViewWindow` | Floating self-video preview (picture-in-picture) |
| `SettingWindow` | Floating A/V device picker and preview |
| `SharingUserOverlay` | Shows who is currently screen-sharing |
| `ParticipantCountOverlay` | Shows participant count during screen share |

- Repositions all sub-windows automatically when the main window is moved or resized.
- Responds to `ZoomApiStatus` transitions:
  - In meeting → show Zoom video, hide Banner.
  - Not in meeting → hide Zoom video, show Banner.

---

### 5.5 TaskBar

**File:** `UserControls/TaskBar.xaml(.cs)`, `ViewModel/TaskBarVM.cs`

A persistent bottom strip always visible to the room operator (if `DisplayWinControls` is enabled or the workstation is attended).

| Element | Description |
|---|---|
| Zoom auth icon | Green check / red X indicating Zoom SDK authentication state |
| MQTT icon | Green / red indicating MQTT broker connection |
| Server icon | Green / red indicating Management server status |
| InmateId | Displays the current inmate ID when a call is active |
| Meeting ID | Displays the Zoom meeting ID when in a meeting |
| Clock | Live current time display |
| Mode toggle | Auto / Manual mode switch |
| Settings button | Opens floating `SettingWindow` |

---

### 5.6 AutoDisableWindowDetector

**File:** `Services/AutoDisableWindowDetector.cs`

An `IHostedService` that runs on a background timer and finds native Windows windows whose titles contain any string from `AutoDisableWindows[]` in configuration (e.g. `"Zoom Workplace"`). When found, it minimises or hides them, preventing Zoom's own UI from overlapping the SmartClient overlay.

---

### 5.7 Banner

**File:** `UserControls/Banner.xaml(.cs)`, `ViewModel/BannerViewModel.cs`

A full-screen overlay displayed when the room is not in a meeting. Shows the room name/label configured in `Banner.Content`. Style is fully configurable (font size, colour, weight, margin) via `Banner.Style` in `appsettings.json`.

The banner serves as a visual indicator that the workstation is idle and identifies which room it belongs to.

---

### 5.8 DPAPIHelper

**File:** `Infrastructure/DPAPIHelper.cs`

Uses the **Windows Data Protection API (DPAPI)** to encrypt and persist the workstation's unique identity:

| Value | Method |
|---|---|
| `DeviceID` | `GetDeviceID()` / `SetDeviceID(value)` |
| MQTT `ClientId` | `GetClientID()` / `SetClientID(value)` |

DPAPI encrypts data with the Windows user account's credentials, so the encrypted blobs are machine- and user-specific and cannot be copied to another workstation. This provides tamper-resistant device identity.

> In **Debug** builds, `AppSetup` bypasses DPAPI and hardcodes `DeviceID = "VC01"` and `ClientId = "scm1"`.

---

## 6. MQTT Topics

All topics are namespaced by `deviceId` (e.g. `VC01`). Topic patterns are defined in `AppTopics` in the shared `CourtLink2.API` project.

### Published by SmartClient

| Topic | Payload | When |
|---|---|---|
| `DeviceConnectionStatusTopic(deviceId)` | `DeviceConnectionRequest` | On MQTT connect, on A/V device status change, on MQTT will (Offline) |
| `MeetingStatusTopic(deviceId)` | `MeetingStatus` | On every Zoom SDK status change |
| `DeviceSyncModeTopic(deviceId)` | `DeviceSyncModeRequest` | On Auto/Manual mode toggle |
| `MeetingEventTopic(deviceId)` | `MeetingEvent` | On language interpretation events, meeting reset, acknowledgement |
| `DeviceStatusTopic(deviceId)` | `DeviceStatusRequest` | On camera/mic/speaker connection change |

#### MQTT Will Message

On MQTT connect, SmartClient registers a **will message** on `DeviceConnectionStatusTopic(deviceId)` with payload `DeviceConnectionRequest { SCMStatus = Offline }`. The broker publishes this automatically if the SmartClient disconnects unexpectedly, allowing Management to mark the device as offline without waiting for a timeout.

### Subscribed by SmartClient

| Topic | Payload | Handled By | Purpose |
|---|---|---|---|
| `CallCommandTopic(deviceId)` | `CallRequest` | `MeetingCommandObserver` → `MeetingController` | Receives schedule/start/end/pause/resume/cancel commands |
| `DeviceControlTopic(deviceId)` | `ControlRequest` | `DeviceControlService` | Pan-tilt, volume, mute/unmute commands from CCM |
| `DeviceMessageTopic(deviceId)` | `DeviceMessageRequest` | `ScmNotificationManager` | Displays a message box popup |
| `LanguageInterpretationControlTopic(deviceId)` | `LanguageInterpretationRequest` | `MeetingController` | Join/leave language channel commands |
| `MeetingEventAckTopic(deviceId)` | string | `MeetingController` | Acknowledgement of meeting events |

---

## 7. Zoom API Status States

`ZoomClient` tracks its state as a `ZoomApiStatus` enum. `MeetingController` maps each state to a corresponding `MeetingStatus` reported to Management via MQTT.

| `ZoomApiStatus` | Meaning | `MeetingStatus` Published |
|---|---|---|
| `CONNECTING` | Zoom SDK is authenticating or joining | `Connecting` |
| `INMEETING` | Successfully joined and active in meeting | `Started` |
| `PAUSED` | Meeting is held/paused | `Paused` |
| `ENDED` | Meeting ended normally by participant | `Ended` |
| `HOST_ENDED` | Meeting ended by the Zoom host | `HostEnded` |
| `WAITINGFORHOST` | Joined but host has not started yet | `WaitingForHost` |
| `IN_WAITING_ROOM` | Placed in Zoom waiting room | `InWaitingRoom` |
| `JOIN_BREAKOUT_ROOM` | Joined a Zoom breakout room | `InBreakoutRoom` |
| `LEAVE_BREAKOUT_ROOM` | Left a breakout room (returning to main) | `LeavingBreakoutRoom` |
| `FAILED` | Join attempt failed (bad credentials, network) | `Failed` — triggers retry after `JoinErrorRetryInterval` |
| `NETWORK_ERROR_ENDED` | Meeting dropped due to network issue | `NetworkError` — triggers retry |
| `ABNORMAL_ENDED` | Meeting ended abnormally | `AbnormalEnded` |

---

## 8. Auto vs Manual Mode

SmartClient devices operate in one of two modes, toggled via the TaskBar switch or commanded by Management.

### Auto Mode (Default)

- `MeetingController` automatically acts on all `CallRequest` commands received from Management.
- Meeting joins and leaves happen without local operator intervention.
- This is the normal operational mode for attended or unattended courtroom workstations.

### Manual Mode

- Enabled when a local operator presses the mode toggle on the TaskBar, or when Management sets the mode.
- In Manual mode, SmartClient still receives `CallRequest` commands but **requires a matching `SessionId`** before executing them.
- When a host ends a meeting in Manual mode, `MeetingController` generates a new `SessionId` lock. Management must send the matching `SessionId` in the next command to unlock the device.
- This prevents Management from inadvertently taking over a device that a local operator is actively controlling.

### Mode Change Flow

```
Operator toggles mode on TaskBar
    └─► MeetingController updates local DeviceMode
        └─► Publishes DeviceSyncModeRequest to AppTopics.DeviceSyncModeTopic(deviceId)
            └─► Management.DeviceManager updates its DeviceInfo.DeviceMode
                └─► Management publishes DeviceModeStatus back to CCM
```

---

## 9. Operator Guide

### Prerequisites

- Windows 10 (build 19041) or later with WPF/.NET 8 runtime
- Zoom Windows SDK DLLs (bundled in `Libs/`)
- Network access to the MQTT broker (`MQTT.ServerAddress`)
- Valid mTLS client certificate installed in the Windows certificate store
- Camera and audio devices (microphone + speaker) connected before launch

### Initial Workstation Provisioning

Each SmartClient workstation must have a unique `DeviceID` and MQTT `ClientId` stored in DPAPI before the first Production launch.

1. Launch SmartClient in Development mode once to confirm basic connectivity.
2. Use the provisioning utility (or run the following in a privileged process) to write the identity:
   ```csharp
   DPAPIHelper.SetDeviceID("VC01");
   DPAPIHelper.SetClientID("scm1");
   ```
3. Ensure the corresponding certificate (`scm1.pfx`) is installed in the Windows certificate store.
4. Add the certificate's SHA-1 thumbprint to `WhitelistClients` in Management's `appsettings.Production.json`.
5. Switch to the Production environment and relaunch.

### Starting SmartClient

1. Launch **CourtLink2.SmartClient.exe**. Only one instance may run at a time.
2. On startup, the application shows the **Banner** (room label) and the **TaskBar** at the bottom.
3. The TaskBar status icons indicate:
   - Zoom SDK auth (green = authenticated, red = failed)
   - MQTT connection (green = connected)
   - Management server status (green = online)

### Joining a Meeting (Auto Mode)

In normal Auto mode, no operator action is required:
1. An operator at CCM assigns a meeting to this device and clicks **Start**.
2. Management sends a `CallRequest(Schedule)` followed by `CallRequest(Start)` via MQTT.
3. SmartClient automatically joins the Zoom meeting; the Banner disappears and the Zoom video fills the window.
4. When CCM sends **End**, SmartClient leaves the meeting and the Banner reappears.

### Joining a Meeting Manually

If the Management connection is unavailable or the device is in Manual mode:
1. Click **Settings** on the TaskBar to open the settings panel.
2. Navigate to the **Meeting** tab and enter the Meeting ID and Passcode.
3. Click **Join**. SmartClient will join the Zoom meeting directly.

### Switching Modes

- Click the **Auto/Manual** toggle switch in the TaskBar.
- Auto mode (blue) — Management has full remote control.
- Manual mode (grey) — local operator override; remote commands require matching `SessionId`.

### Configuring Audio / Video Devices

1. Click **Settings** on the TaskBar.
2. Select the desired microphone, speaker, and camera from the drop-down lists.
3. The preview pane shows a live camera feed and the VU meter shows microphone level.
4. Changes take effect immediately within the current Zoom meeting.

### Configuring the Room Banner

Update `Banner.Content` in `appsettings.Production.json` to change the room label. Restart SmartClient for the change to take effect.

```json
"Banner": {
  "Content": "Courtroom 1 — Video Visitation",
  "Style": {
    "FontSize": 48,
    "Color": "#FFFFFF",
    "FontWeight": "Bold"
  }
}
```

### Troubleshooting

| Symptom | Likely Cause | Resolution |
|---|---|---|
| Zoom auth icon red on startup | Invalid `ZoomCredentials` in `zoomsettings.json` | Verify ClientID/ClientSecret; check Zoom SDK app status |
| MQTT icon red | Broker unreachable or cert mismatch | Check `MQTT.ServerAddress`/`Port`; verify client cert is trusted |
| Meeting never joins | `JoinErrorRetryInterval` retries exhausted | Check Meeting ID and Passcode; verify network connectivity to Zoom |
| Camera not working | Device name not matching `Camera.Name` | Update `Camera.Name` to match the device name in Device Manager |
| Microphone not working | Device name not matching `AudioDevices.Microphones` | Update the microphone name list in config |
| Zoom Workplace popup appears | `AutoDisableWindows` list missing the window title | Add `"Zoom Workplace"` (or the exact title) to `AutoDisableWindows` |
| Banner not showing room name | `Banner.Content` not set | Update `appsettings.Production.json` and restart |
| Device shows offline in CCM | MQTT disconnected or DPAPI identity wrong | Check MQTT connection; verify `DeviceID` matches Management's device list |
| Manual mode stuck | Session ID mismatch | Operator must manually toggle back to Auto mode from the TaskBar |
