# CourtLink2 — System Design

CourtLink2 is a distributed video visitation management system for correctional facilities.
It orchestrates Zoom-based video calls across up to 81 room PCs, provides operator control,
room-status displays, screen casting, and power management — all over a shared MQTT broker
and a central ASP.NET Core management server.

---

## Executive Summary

CourtLink2 replaces manual, ad-hoc video call coordination with a fully automated, centrally
managed visitation platform. Facility operators schedule visits through a supervisory console
(CCM), the management server assigns calls to room devices, and room PCs (SmartClient) launch
and control Zoom meetings autonomously.

Key characteristics:

- **Scale**: up to 81 concurrent video visitation rooms (VC01–VC81).
- **Transport**: MQTT (pub/sub) for real-time device commands and status; HTTPS REST for CRUD
  operations and call lifecycle management.
- **Video**: Zoom SDK (C++/CLI interop) embedded directly in each room PC process.
- **Security**: mutual TLS on every HTTP and MQTT connection; role-based access derived from
  certificate CN.
- **Resilience**: retained MQTT messages survive broker restarts; SemaphoreSlim-guarded device
  state prevents concurrent command races.

---

## Solution Architecture

### Project Overview

CourtLink2 is composed of 20 Visual Studio projects organized in five layers.

| Layer | Projects |
|---|---|
| **Shared libraries** | `CourtLink2.API`, `CourtLink2.Models`, `CourtLink2.Messaging`, `CourtLink2.Infrastructure`, `CourtLink2.Core` |
| **Server** | `CourtLink2.Management` |
| **Room client** | `CourtLink2.SmartClient`, `CourtLink2.MeetingSDK`, `CourtLink2.CameraControl`, `CourtLink2.ScreenCaster` |
| **Operator / display clients** | `CourtLink2.CCM`, `CourtLink2.CMM`, `CourtLink2.RAD` |
| **Tools / test** | `CourtLink2.Guard`, `CourtLink2.Simulators.SCM`, `CourtLink2.Simulators.CCM`, `CourtLink2.CCMAutoTest`, `CourtLink2.Devices`, `DeviceController`, `RelayDeviceTest`, `WinForms.EncryptionTools` |

### Dependency Graph

```
CourtLink2.API  ──────────────────────────────────────────────────────────┐
CourtLink2.Models (EF Core / SQL Server)                                   │
CourtLink2.Messaging (MQTTnet / Rx.NET) ──────────────────────────────────┤
CourtLink2.Infrastructure ◄── Messaging                                    │
CourtLink2.Devices (SharpSnmpLib)                                          │
CourtLink2.CameraControl (DirectShowLib)                                   │
                                                                           │
CourtLink2.Management  ◄── API, Infrastructure, Messaging, Models, Devices │
CourtLink2.CCM         ◄── API, Infrastructure, Messaging, CameraControl   │
CourtLink2.SmartClient ◄── API, Infrastructure, Messaging, MeetingSDK,     │
                            CameraControl                                  │
CourtLink2.CMM         ◄── API, Infrastructure                             │
CourtLink2.RAD         ◄── API, Infrastructure                             │
CourtLink2.ScreenCaster◄── Infrastructure                                  │
CourtLink2.Guard       ◄── Infrastructure, Messaging                       │
```

### Deployment Topology

```
┌─────────────────────────────────────────────────────────────────┐
│  Facility Network                                               │
│                                                                 │
│  ┌─────────────────┐     HTTPS mTLS :5055      ┌────────────┐  │
│  │  Management     │◄──────────────────────────►│  CCM       │  │
│  │  Server         │                            │  (Operator)│  │
│  │  (Windows Svc)  │◄──────────────────────────►│  CMM       │  │
│  │  SQL Server DB  │                            │  (Video    │  │
│  └────────┬────────┘                            │   Wall)    │  │
│           │                                     │  RAD       │  │
│           │  MQTT TLS                           │  (Display) │  │
│           ▼                                     └────────────┘  │
│  ┌─────────────────┐                                            │
│  │  MQTT Broker    │                                            │
│  └────────┬────────┘                                            │
│           │  MQTT TLS                                           │
│     ┌─────┴──────────────────────────┐                          │
│     ▼               ▼               ▼                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐   (up to 81)         │
│  │SmartClient│  │SmartClient│  │SmartClient│                    │
│  │  VC01    │  │  VC02    │  │  VC81    │                       │
│  │  + Zoom  │  │  + Zoom  │  │  + Zoom  │                       │
│  │  + PTZ   │  │  + PTZ   │  │  + PTZ   │                       │
│  │  + Screen│  │  + Screen│  │  + Screen│                       │
│  │  Caster  │  │  Caster  │  │  Caster  │                       │
│  └──────────┘  └──────────┘  └──────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Application Descriptions

### CourtLink2.Management

- **Type**: ASP.NET Core Web API + Windows Service (`net8.0`)
- **Port**: 5055 HTTPS (mTLS)
- **Role**: Central authority. Owns the SQL Server database, the `DeviceManager` (in-memory
  device state), the MQTT publishing side of call control, and the SNMP power management relay.
- **Key components**: `DeviceManager.cs` (ConcurrentDictionary of `DeviceInfo`), `CallController`,
  `MeetingsController`, `DevicesController`, `SystemConfigsController`.

### CourtLink2.SmartClient (SCM)

- **Type**: WPF application (`net8.0-windows`)
- **Role**: One instance per room PC. Subscribes to MQTT topics for its device ID, drives the
  Zoom SDK via `MeetingSDK`, controls the PTZ camera via `CameraControl`, and publishes meeting
  status back to the broker.
- **Identity**: Device ID and Zoom client ID are stored encrypted (`DPAPI`) in `DeviceID.dat`
  and `ClientID.dat` on the room PC.
- **Key component**: `MeetingController.cs` — the central Zoom orchestration class.

### CourtLink2.CCM (Central Control Module)

- **Type**: WinUI 3 desktop application (`net8.0-windows10`)
- **Role**: Operator supervisory console. Displays all 81 rooms, their live status, active call
  timers, and mode. Sends device control commands (PTZ, volume, breakout rooms, sign/language
  interpretation). Holds a Monitor-role mTLS certificate.
- **Key component**: `MeetingManager.cs` — subscribes to `meeting/announce` to refresh meeting
  lists from the Management REST API.

### CourtLink2.CMM (Central Media Monitor)

- **Type**: WinUI 3 desktop application (`net8.0-windows10`)
- **Role**: Video wall monitoring. Receives live RTSP streams from all ScreenCaster instances
  via LibVLC and displays them in a grid. Subscribes to `livestreamstatus` for stream metadata.
  Read-only (Viewer role).

### CourtLink2.RAD (Room Allocation Display)

- **Type**: WinUI 3 desktop application (`net8.0-windows10`)
- **Role**: Public-facing display board. Shows room status (idle/scheduled/in-call) using the
  `meeting/status` and `device/mode` retained MQTT topics. Read-only (Viewer role).

### CourtLink2.ScreenCaster

- **Type**: WinForms headless application (`net8.0-windows`)
- **Role**: Runs alongside SmartClient on each room PC. Captures the screen using FFmpeg and
  pushes the stream to a Wowza RTMP endpoint so CMM can display it. Stream metadata published
  via Management's `livestreamstatus` MQTT topic.

### CourtLink2.Guard

- **Type**: WinForms application (`net8.0-windows`)
- **Role**: Developer/admin MQTT diagnostic tool. Can publish arbitrary MQTT messages and
  observe broker traffic. Uses the `Infrastructure` MQTT factory for TLS connections.

### CourtLink2.API

- **Type**: .NET class library (`net8.0`)
- **Role**: Shared contract layer — DTOs, enums, MQTT topic string constants (`AppTopics`).
  No project references; imported by all other projects.

### CourtLink2.Models

- **Type**: .NET class library (`net8.0`)
- **Role**: EF Core entity definitions and SQL Server migrations. Referenced only by Management.

### CourtLink2.Messaging

- **Type**: .NET class library (`net8.0`)
- **Role**: MQTTnet `ManagedMqttClient` wrapper with Rx.NET `IObservable` subscription helpers.
  Provides `IMqttService` used by all MQTT-connected projects.

### CourtLink2.Infrastructure

- **Type**: .NET class library (`net8.0`)
- **Role**: Cross-cutting concerns: `AppSettings` (config binding), HTTP client factory (mTLS),
  MQTT client factory (TLS), AES encryption helper, DPAPI helper.

### CourtLink2.Devices

- **Type**: .NET class library (`net8.0`)
- **Role**: SNMP power control for relay devices via `SharpSnmpLib`. Used by Management to
  power on/off/reboot room PCs through relay switches.

### CourtLink2.CameraControl

- **Type**: .NET class library (`net8.0`)
- **Role**: PTZ camera control using DirectShow COM interop (`DirectShowLib`). Used by both
  SmartClient and CCM to pan, tilt, and zoom the room camera.

### CourtLink2.MeetingSDK

- **Type**: C++/CLI mixed-mode DLL (`vcxproj`)
- **Role**: Wraps the Zoom Windows SDK in a .NET-callable assembly. Exposes events and methods
  for joining, starting, ending, and controlling a Zoom meeting. Loaded by SmartClient at runtime.

### CourtLink2.Simulators.SCM

- **Type**: WPF application (`net8.0-windows`)
- **Role**: Device simulator. Uses `Stateless` state machines to mimic one or more SmartClient
  instances for load testing without needing physical room hardware.

### CourtLink2.Simulators.CCM

- **Type**: WinUI 3 application (`net8.0-windows10`)
- **Role**: Load-test client. Simulates CCM operator actions to stress-test Management and the
  MQTT broker.

### CourtLink2.CCMAutoTest

- **Type**: MSTest project (`net8.0-windows10`)
- **Role**: UI automation tests using Appium / WinAppDriver against the CCM application.

---

## Communication Architecture

CourtLink2 uses two transport layers:

1. **MQTT** — real-time, bidirectional device events and commands (pub/sub).
2. **HTTPS REST** — CRUD operations and call lifecycle commands (request/response).

### MQTT Topics

All topic strings are defined in `CourtLink2.API/AppTopics.cs`. Device-specific topics use a
`{deviceId}` suffix (e.g., `meeting/call/VC01`).

| Topic | Publisher | Subscriber(s) | Payload type | Retained |
|---|---|---|---|---|
| `meeting/call/{deviceId}` | Management | SmartClient | `CallRequest` | Yes |
| `meeting/status/{deviceId}` | SmartClient | Management, CCM, RAD | `MeetingStatus` | Yes |
| `device/connection/{deviceId}` | SmartClient | Management, CCM | `DeviceConnectionRequest` | Yes |
| `device/mode/{deviceId}` | Management | CCM, RAD, SmartClient | `DeviceModeRequest` | Yes |
| `meeting/announce` | Management | CCM | _(empty)_ | No |
| `device/control/{deviceId}` | CCM | SmartClient | `ControlRequest` | No |
| `device/message/{deviceId}` | CCM | SmartClient | `DeviceMessageRequest` | No |
| `device/status/{deviceId}` | SmartClient | CCM | `DeviceStatusRequest` | No |
| `capture/device/{deviceId}` | CMM | SmartClient | `DeviceCaptureRequest` | No |
| `meeting/elapsed/{deviceId}` | SmartClient | CCM, RAD | `ElapsedRequest` | No |
| `device/syncmode/{deviceId}` | SmartClient | Management | `DeviceSyncModeRequest` | No |
| `meeting/event/{deviceId}` | SmartClient | CCM | `MeetingEvent` | Yes |
| `meeting/control/breakoutroom/{deviceId}` | CCM | SmartClient | `BreakoutRoomRequest` | No |
| `meeting/control/signinterpretation/{deviceId}` | CCM | SmartClient | `SignInterpretationRequest` | No |
| `meeting/control/languageinterpretation/{deviceId}` | CCM | SmartClient | `LanguageInterpretationRequest` | No |
| `meeting/eventack/{deviceId}` | SmartClient | CCM | `MeetingEventAck` string | No |
| `serverstatus` | Management | All clients | `ServerStatusRequest` | Yes (LWT) |
| `livestreamstatus` | Management | CCM, CMM | `LiveStreamStatus[]` | Yes |

**Retained topics** allow newly connecting clients (CCM, RAD, SmartClient) to immediately
receive the last-known state for every device without waiting for the next publish.

**`serverstatus`** uses MQTT Last Will and Testament (LWT): if the Management service crashes,
the broker automatically publishes `ServerStatus.Offline` to all subscribers.

### REST API

All REST endpoints are hosted by `CourtLink2.Management` on port 5055 HTTPS with mTLS.
The caller's certificate CN determines role: `*CCM*` → `Monitor` (read/write);
all others → `Viewer` (read-only).

#### Meetings

| Method | Endpoint | Min Role | Description |
|---|---|---|---|
| GET | `/api/Meetings` | Viewer | List today's meetings |
| GET | `/api/Meetings/{id}` | Viewer | Get single meeting by GUID |
| POST | `/api/Meetings` | Monitor | Create meeting |
| POST | `/api/Meetings/bulk` | Monitor | Bulk-replace all meetings for the day |
| PUT | `/api/Meetings/{id}` | Monitor | Update meeting |
| PUT | `/api/Meetings/upsert/{inmateId}` | Monitor | Upsert meeting by inmate ID |
| DELETE | `/api/Meetings/{id}` | Monitor | Delete meeting |

#### Call Lifecycle

| Method | Endpoint | Min Role | Description |
|---|---|---|---|
| POST | `/Call/schedule` | Monitor | Assign meeting to device, publish `meeting/call` |
| PUT | `/Call/cancel?deviceId=` | Monitor | Cancel scheduled call |
| PUT | `/Call/start?deviceId=` | Monitor | Start call (validates Online + Auto mode) |
| PUT | `/Call/end` | Monitor | End call, persist `Call` record to DB |
| PUT | `/Call/pause?deviceId=` | Monitor | Pause active call |
| PUT | `/Call/resume?deviceId=` | Monitor | Resume paused call |

#### Devices & Configuration

| Method | Endpoint | Min Role | Description |
|---|---|---|---|
| GET | `/api/Devices` | Viewer | List all devices with live in-memory state |
| POST | `/api/DevicePower` | Monitor | SNMP relay power On/Off/Reboot |
| GET | `/api/SystemConfigs` | Viewer | Read system config key-value store |

### Call Schedule Sequence

```
CCM Operator          Management Server          MQTT Broker           SmartClient (VC01)
     │                       │                        │                        │
     │  POST /Call/schedule  │                        │                        │
     │──────────────────────►│                        │                        │
     │                       │  validate device state │                        │
     │                       │  set CallStatus=Sched  │                        │
     │                       │  publish retained msg  │                        │
     │                       │───────────────────────►│ meeting/call/VC01      │
     │  200 OK               │                        │───────────────────────►│
     │◄──────────────────────│                        │                        │
     │                       │                        │  meeting/status/VC01   │
     │                       │◄───────────────────────│◄───────────────────────│
     │                       │  update DeviceInfo     │                        │
     │  meeting/status/VC01  │                        │                        │
     │◄────────────────────────────────────────────── │                        │
```

### Call Start Sequence

```
CCM Operator          Management Server          MQTT Broker           SmartClient (VC01)
     │                       │                        │                        │
     │  PUT /Call/start      │                        │                        │
     │──────────────────────►│                        │                        │
     │                       │  validate Online+Auto  │                        │
     │                       │  set CallStatus=Started│                        │
     │                       │  publish CallCommand   │                        │
     │                       │───────────────────────►│ meeting/call/VC01      │
     │  200 OK               │                        │  (Start command)       │
     │◄──────────────────────│                        │───────────────────────►│
     │                       │                        │                        │ join Zoom meeting
     │                       │                        │  meeting/status/VC01   │
     │                       │◄───────────────────────│◄───────────────────────│
     │  meeting/status/VC01  │                        │  (Started)             │
     │◄────────────────────────────────────────────── │                        │
```

---

## Data Model

CourtLink2 uses SQL Server with EF Core 8 for persistence. The database is only accessed by the
Management server; all other components read state from in-memory `DeviceManager` or MQTT.

### Entity-Relationship Diagram

```
┌─────────────────────┐       ┌─────────────────────┐
│   RelayConfigs      │       │  StreamingEngines    │
│─────────────────────│       │─────────────────────│
│ Id (PK)             │       │ Id (PK)              │
│ Name                │       │ Name                 │
│ IP                  │       │ IPAddress            │
│ Port                │       │ UserName             │
│ Community           │       │ Password             │
│ DigitalPorts (JSON) │       └──────────┬──────────┘
└──────────┬──────────┘                  │
           │ FK                          │ FK
           ▼                             ▼
┌─────────────────────────────────────────────────┐
│                    Devices                       │
│─────────────────────────────────────────────────│
│ Id (PK)                                          │
│ Name                                             │
│ ZoneId                                           │
│ RelayDeviceId (FK → RelayConfigs, nullable)      │
│ StreamingEngineId (FK → StreamingEngines,nullable│
│ StreamName                                       │
└───────────────────────┬─────────────────────────┘
                        │ FK (SetNull on delete)
           ┌────────────┴────────────┐
           ▼                         ▼
┌──────────────────────┐  ┌──────────────────────┐
│     Meetings         │  │      Calls            │
│──────────────────────│  │──────────────────────│
│ Id (GUID PK)         │  │ Id (GUID PK)          │
│ InmateId             │  │ Meeting (JSON column) │
│ InmateName           │  │ DeviceId (FK)         │
│ DisplayName          │  │ CreatedTime           │
│ ZoomMeetingId        │  │ StartTime             │
│ MeetingPasscode      │  │ EndTime               │
│ DeviceId (FK,nullable│  └──────────────────────┘
│ StartTime            │
│ EndTime              │
│ CreatedTime          │
│ LastModifiedTime     │
└──────────────────────┘

┌──────────────────────┐
│   SystemConfigs      │
│──────────────────────│
│ Id (PK)              │
│ Key                  │
│ ValueJson            │
└──────────────────────┘
```

### Entity Descriptions

**Devices** — Physical room PCs. Each device has an optional `RelayDeviceId` pointing to the
relay switch that controls its power, and an optional `StreamingEngineId` pointing to the Wowza
server that hosts its RTMP stream.

**Meetings** — Scheduled visitation appointments. `DeviceId` is nullable and set when the
meeting is assigned to a room. Cleared (SetNull) if the device is deleted. Contains Zoom
meeting credentials (`ZoomMeetingId`, `MeetingPasscode`).

**Calls** — Immutable audit record of each completed call. Stores a JSON snapshot of the
`Meeting` at the time the call was made, plus start/end timestamps. Written when `/Call/end`
is invoked.

**RelayConfigs** — SNMP relay device configuration. `DigitalPorts` is a JSON column mapping
port numbers to device identifiers, so one relay can control multiple room PCs.

**StreamingEngines** — Wowza media server instances. Credentials stored in plain text in
the database (access restricted to Management server only).

**SystemConfigs** — Key/value configuration store. Values serialised as JSON to support any
primitive or complex type.

---

## Meeting Lifecycle and State Machines

### CallStatus State Machine

`CallStatus` represents the current state of a call on a device, tracked in `DeviceInfo` in
memory and reflected in MQTT `meeting/status` publishes.

```
              ┌─────────┐
         ┌───►│  Idle   │◄──────────────────────────────────────┐
         │    └────┬────┘                                        │
         │         │ Schedule                                    │
         │         ▼                                             │
         │    ┌──────────┐                                       │
         │    │Scheduled │                                       │
         │    └────┬─────┘                                       │
         │         │ Start                                       │
         │         ▼                                             │
  Cancel │    ┌─────────┐      Pause      ┌─────────┐    End    │
  or End │    │ Started │────────────────►│ Paused  │───────────┘
         │    └────┬────┘                 └────┬────┘
         │         │ End                       │ Resume
         └─────────┘                           │
                                               └──────────────► Started
```

### CallCommand State Machine

`CallCommand` represents the most recent command sent to a device. Used by SmartClient to
decide what action to take when a new `meeting/call` message arrives.

```
None ──Schedule──► Schedule ──Start──► Start ──Pause──► Pause ──Resume──► Start
  ▲                   │                  │                 │
  └───────────────────┴──────────────────┘                 │
              (Cancel/None at any point)                   │
                                                           └──Pause──► Pause
```

### End-to-End Meeting Lifecycle

1. **Create** — Operator or external system calls `POST /api/Meetings`. A `Meeting` row is
   created with no `DeviceId`.
2. **Schedule** — Operator calls `POST /Call/schedule`. Management validates that the target
   device is in `Auto` mode and not already active. Sets `CallStatus = Scheduled`, publishes
   retained `meeting/call/{deviceId}` with `CallCommand.Schedule`. SmartClient receives the
   message and prepares.
3. **Start** — Operator calls `PUT /Call/start`. Management validates the device is `Online`
   and in `Auto` mode. Sets `CallStatus = Started`, publishes `CallCommand.Start`. SmartClient
   calls `MeetingController.JoinMeeting()` → Zoom SDK joins the meeting room.
4. **In progress** — SmartClient publishes periodic `meeting/elapsed` ticks. CCM displays
   elapsed time. Operator may send PTZ/volume/mic/video commands via `device/control`. Breakout
   rooms and interpretation features can be activated.
5. **Pause / Resume** — Operator calls `PUT /Call/pause` / `PUT /Call/resume`. Management
   publishes the new `CallCommand`. SmartClient puts Zoom on hold or resumes.
6. **End** — Operator calls `PUT /Call/end`. Management sets `CallStatus = Idle`, publishes
   `CallCommand.None`, and writes a `Call` record to the database with the snapshot of the
   meeting and timestamps.
7. **Failed / Waiting** — If SmartClient fails to join Zoom or is waiting for the host,
   it publishes `CallStatus.Failed` or `CallStatus.Waiting`. Management and CCM display
   these states. No `Call` record is written until the call is formally ended.

---

## Device Management

### Device Modes

Each device operates in one of two modes:

| Mode | Description |
|---|---|
| **Auto** | Calls can be scheduled and started by the Management server automatically. Default operating mode. |
| **Manual** | Device is under direct operator control. Automated call scheduling and starting are blocked. Used for maintenance, testing, or manual Zoom sessions. |

Mode is set by publishing a retained `device/mode/{deviceId}` MQTT message with `DeviceModeRequest`.
SmartClient, CCM, and RAD all subscribe and update their local state.

### Connection Tracking

SmartClient publishes a retained `device/connection/{deviceId}` message (`DeviceConnectionRequest`)
whenever it connects or disconnects from the MQTT broker. Management and CCM subscribe to track
`ConnectionStatus.Online` / `ConnectionStatus.Offline` per device.

The Management server's `DeviceManager` holds a `ConcurrentDictionary<string, DeviceInfo>` keyed
by device ID. Each `DeviceInfo` holds the current `CallStatus`, `CallCommand`, `ConnectionStatus`,
`Mode`, and the currently scheduled `Meeting`.

### SemaphoreSlim Locking

`DeviceInfo` uses a per-device `SemaphoreSlim(1,1)` to serialise concurrent call lifecycle
requests. This prevents race conditions when multiple CCM operators or external integrations
attempt to modify the same device state simultaneously.

### Mode Synchronisation

If a SmartClient comes online and its local mode does not match the Management server's
last-published `device/mode` retained message, it publishes a `device/syncmode/{deviceId}`
message to inform Management. Management reconciles by re-publishing the authoritative mode.

---

## External Integrations

### Zoom SDK (C++/CLI Interop)

SmartClient uses the Zoom Windows SDK via `CourtLink2.MeetingSDK`, a C++/CLI mixed-mode DLL.
The managed `MeetingController` calls into `MeetingSDK` to:

- Authenticate with the Zoom API using a JWT token (generated by `JWTHelper.cs` using `jose-jwt`).
- Join a meeting by meeting ID and passcode.
- Monitor meeting events (participant joined/left, meeting ended by host).
- Control in-meeting features (breakout rooms, sign interpretation, language interpretation).

The Zoom SDK runs on the room PC in the same process as the WPF `SmartClient` application.
Each room PC has a unique Zoom client ID stored in DPAPI-encrypted `ClientID.dat`.

### SNMP Relay Power Control

`CourtLink2.Devices` uses `SharpSnmpLib` to send SNMP SET commands to relay hardware.
Management exposes `POST /api/DevicePower` which maps a device's `RelayDeviceId` to a
`RelayConfig` row, resolves the correct SNMP OID from `DigitalPorts`, and sends the
`PowerStatus` (On/Off/Reboot) command.

This allows operators to remotely power-cycle room PCs without physical access.

### Wowza RTMP Live Streaming

Each room PC runs `CourtLink2.ScreenCaster` alongside SmartClient. ScreenCaster uses FFmpeg
to capture the screen and push an RTMP stream to the `StreamingEngine` configured for that
device. CMM uses `LibVLC` to pull RTSP streams from Wowza and display them on the video wall.

Management publishes retained `livestreamstatus` MQTT messages containing `LiveStreamStatus[]`
so CMM knows which streams are active and where to find them.

### DirectShow PTZ Camera Control

`CourtLink2.CameraControl` uses `DirectShowLib` COM interop to send PTZ (Pan/Tilt/Zoom)
commands to USB or capture-card connected cameras. Both CCM and SmartClient reference this
library. CCM can send pan/tilt/zoom commands via `device/control/{deviceId}` MQTT messages;
SmartClient receives them and forwards to `CameraControl`.

### FFmpeg Screen Capture

ScreenCaster spawns FFmpeg as a child process with a configured output URL and codec settings.
It monitors the process and restarts it if it exits unexpectedly. Configuration (RTMP URL,
stream key, FFmpeg path) is read from the shared `AppSettings` via `Infrastructure`.

---

## Security Architecture

### Mutual TLS (mTLS)

Every HTTP connection to Management and every MQTT connection to the broker requires a client
certificate. The Management server uses `CertificateAuthenticationDefaults` middleware.
`CertificateValidationService` validates the client certificate against a configured thumbprint
whitelist loaded from `SystemConfigs`.

```
Client (CCM/CMM/RAD/SmartClient)
       │
       │  TLS ClientHello + Client Certificate
       ▼
Management Server
  ├─ Validate server cert (standard TLS)
  ├─ Validate client cert thumbprint (whitelist)
  └─ Derive role from cert CN:
       CN contains "CCM" → Role: Monitor (full control)
       CN does not contain "CCM" → Role: Viewer (read-only)
```

### Certificate Roles

| Role | Certificate CN pattern | Permissions |
|---|---|---|
| Monitor | Contains `CCM` | All REST endpoints; can schedule, start, end, pause, resume calls; SNMP power control |
| Viewer | Any other CN | Read-only endpoints: list meetings, list devices, get config |

### MQTT TLS

MQTT clients load their certificate from the Windows certificate store using
`Infrastructure`'s MQTT client factory. The broker validates the client certificate.
Topic-level access control is enforced by broker configuration (not shown in source).

### DPAPI Encryption

SmartClient reads `DeviceID.dat` and `ClientID.dat` from disk. These files contain the
device ID and Zoom client ID encrypted using Windows DPAPI (`ProtectedData.Unprotect`,
`LocalMachine` scope). This ensures the credentials can only be decrypted on the specific
machine they were provisioned on.

### AES Encryption

`AesEncryptionHelper` in `Infrastructure` provides AES-256 encryption for any string value.
Used for secrets that must be portable across machines (unlike DPAPI) but still stored
encrypted at rest.

### JWT for Zoom Authentication

`JWTHelper.cs` in SmartClient generates a short-lived JWT signed with the Zoom SDK secret,
used to authenticate the Zoom SDK when joining a meeting. The signing key comes from the
AES-decrypted application configuration.

---

## Testing and Simulation

### CourtLink2.CCMAutoTest

MSTest-based UI automation suite using Appium with WinAppDriver as the backend.
Tests drive the CCM WinUI 3 application through its real UI, verifying that scheduling a
call, starting it, and ending it produces the correct on-screen state changes.

Requires:
- WinAppDriver running on the test machine.
- A running Management server (or mock).
- A valid Monitor-role mTLS certificate installed.

### CourtLink2.Simulators.SCM (Device Simulator)

WPF application that simulates one or more SmartClient instances using `Stateless` state
machines. Useful for load testing without physical room hardware.

The simulator subscribes to the same MQTT topics as a real SmartClient and publishes
`meeting/status` and `device/connection` messages with configurable delay and failure injection.
`DeviceCallState.cs` and `DeviceCommandState.cs` mirror the real state machine transitions.

### CourtLink2.Simulators.CCM (Load Test Client)

WinUI 3 application that simulates CCM operator actions at volume. Sends REST API calls to
Management to schedule, start, end, and cancel calls across many devices simultaneously.
Used to verify Management's concurrency handling and MQTT broker throughput under full load.

### RelayDeviceTest

WinForms utility for manually sending SNMP relay commands to a relay device. Used during
hardware commissioning to verify that relay wiring and IP configuration are correct before
deploying the full system.

### WinForms.EncryptionTools

WinForms utility for provisioning room PCs. Generates DPAPI-encrypted `DeviceID.dat` and
`ClientID.dat` files with the correct device ID and Zoom client ID for a given machine.
Must be run on the target room PC so DPAPI uses the correct machine scope.

---

## Configuration and Deployment

### AppSettings Structure

All applications read configuration from `appsettings.json` (and
`appsettings.{Environment}.json`) via `Infrastructure`'s `AppSettings` binding. Key sections:

- **Mqtt**: broker hostname, port, TLS settings, certificate thumbprint.
- **Management**: base URL (`https://server:5055`), client certificate thumbprint.
- **Zoom**: SDK key, SDK secret (AES-encrypted), meeting role.
- **Streaming**: RTMP push URL, RTSP pull base URL.
- **Relay**: SNMP community string override (if not stored in DB).

### Provisioning a New Room PC

1. Install Windows, join facility network.
2. Install room PC certificates in the Windows cert store (MQTT TLS client cert).
3. Run `WinForms.EncryptionTools` to generate `DeviceID.dat` and `ClientID.dat`.
4. Copy `SmartClient` and `ScreenCaster` binaries; configure `appsettings.json`.
5. Add the device to the Management database (`Devices` table) with the same device ID.
6. Set up the relay port mapping in `RelayConfigs` if power management is needed.
7. Launch SmartClient — it will connect to MQTT, publish `device/connection` (Online),
   and appear in CCM's device list.

### Management Server Deployment

Deployed as a Windows Service (`UseWindowsService()` in `Program.cs`). SQL Server connection
string, mTLS certificate path, and MQTT broker address are configured in `appsettings.json`.
EF Core migrations are applied automatically on startup.

---
