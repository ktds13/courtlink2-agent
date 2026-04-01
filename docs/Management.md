# CourtLink2.Management

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Configuration](#4-configuration)
5. [REST API Reference](#5-rest-api-reference)
   - [Meetings](#51-meetings)
   - [Devices](#52-devices)
   - [Call Lifecycle](#53-call-lifecycle)
   - [System Configs](#54-system-configs)
   - [Device Power](#55-device-power)
6. [Authentication](#6-authentication)
7. [MQTT Topics](#7-mqtt-topics)
8. [Service Reference](#8-service-reference)
   - [DeviceManager](#81-devicemanager)
   - [DeviceInfo](#82-deviceinfo)
   - [StreamingService](#83-streamingservice)
   - [PowerControlService](#84-powercontrolservice)
9. [Database Schema](#9-database-schema)
10. [Operator Guide](#10-operator-guide)

---

## 1. Overview

**CourtLink2.Management** is the central backend of the CourtLink2 video visitation system. It runs as both an **ASP.NET Core Kestrel HTTPS server** and a **Windows Service**, providing:

- A **REST API** consumed by CCM for meeting management and call lifecycle control.
- An **MQTT hub** that coordinates SmartClient devices in every courtroom.
- A **SQL Server** database for persistent storage of meetings, calls, devices, and system configuration.
- **Wowza streaming** integration for live video feed management.
- **SNMP relay** control for room PC power management.

### Role in the System

```
CCM ──HTTPS (mTLS, port 5055)──► Management REST API
SmartClient ──MQTT──► Management (reports status)
Management ──MQTT──► SmartClient (issues commands)
Management ──MQTT──► CCM (stream status, meeting announcements)
```

---

## 2. Architecture

```
CourtLink2.Management (ASP.NET Core Web API + Windows Service)
├── Program.cs              Top-level bootstrap: host config, mTLS, DI, Kestrel
│
├── Controllers/            REST API controllers
│   ├── MeetingsController      CRUD + bulk import for meetings
│   ├── DevicesController       Read-only device list
│   ├── CallController          Call lifecycle (schedule/start/end/pause/resume/cancel)
│   ├── SystemConfigsController System configuration read
│   └── DevicePowerController   SNMP relay power control
│
├── Models/                 Domain models and in-memory state
│   ├── DeviceManager           Central in-memory device registry (ConcurrentDictionary)
│   ├── DeviceInfo              Per-device async state machine (SemaphoreSlim mutex)
│   ├── DeviceInfoFactory       Factory for DeviceInfo construction
│   └── RelayDeviceFactory      Factory for SNMP relay device instances
│
├── Services/               Background and infrastructure services
│   ├── MessagingService        IHostedService: MQTT lifecycle
│   ├── StreamingService        IHostedService: Wowza API polling + token generation
│   ├── PowerControlService     IHostedService: batched SNMP relay commands
│   ├── DeviceRepository        Lazy-loaded device list from SQL
│   ├── MeetingRepository       Meeting existence checks in SQL
│   └── CertificateValidationService  mTLS thumbprint whitelist validation
│
└── (Shared projects referenced)
    ├── CourtLink2.API          Request/response models, AppTopics
    ├── CourtLink2.Infrastructure  EF Core DbContext, AppSettings
    ├── CourtLink2.Models          SQL entities
    ├── CourtLink2.Messaging       MessageBus (MQTT)
    └── CourtLink2.Devices         IRelayDevice (SNMP)
```

### Startup Sequence

1. `WebApplication.CreateBuilder(args)` + `builder.Host.UseWindowsService()` — enables running as a Windows Service.
2. Certificate authentication middleware is configured: client certificates are validated against the `WhitelistClients` thumbprint list, then assigned the `Monitor` or `Viewer` role.
3. `CourtLink2DBContext` (SQL Server via EF Core) is registered as scoped.
4. `MessageBus` singleton is created with an MQTT will message (`ServerStatus=Offline`) to announce server downtime.
5. Hosted services registered: `MessagingService`, `StreamingService`, `PowerControlService`.
6. Singletons registered: `DeviceManager`, `PowerControlService`, `DeviceRepository`.
7. Scoped services registered: `MeetingRepository`, `DeviceInfoFactory`.
8. `app.RunAsync()` — starts Kestrel on HTTPS port 5055.

---

## 3. Technology Stack

| Category | Library / Version |
|---|---|
| Framework | .NET 8 ASP.NET Core (`net8.0`) |
| Web Server | Kestrel (self-hosted HTTPS, port 5055) |
| Windows Service | `Microsoft.Extensions.Hosting.WindowsServices` |
| Authentication | Mutual TLS — `Microsoft.AspNetCore.Authentication.Certificate` |
| Database ORM | Entity Framework Core (`CourtLink2DBContext`) |
| Database | SQL Server (`Microsoft.Data.SqlClient`) |
| Messaging | MQTT via `CourtLink2.Messaging` (`MQTTnet`) |
| Power Control | SNMP relay via `CourtLink2.Devices` |
| Logging | NLog 5.4 (file, Windows Event Log source `MGT1` ID 510, console) |
| Serialization | Newtonsoft.Json |

---

## 4. Configuration

Configuration is loaded from layered `appsettings.*.json` files. The active environment is controlled by the `ASPNETCORE_ENVIRONMENT` environment variable.

### Configuration Files

| File | Purpose |
|---|---|
| `appsettings.json` | Log levels only (base) |
| `appsettings.Development.json` | Full development config |
| `appsettings.Production.json` | Production overrides |
| `appsettings.CI.json` | CI pipeline overrides |
| `Properties/launchSettings.json` | Dev launch profile (`ASPNETCORE_ENVIRONMENT=Development`, HTTPS localhost:5055) |

### Key Settings

#### Kestrel HTTPS

```json
"Kestrel": {
  "Endpoints": {
    "Https": {
      "Url": "https://0.0.0.0:5055",
      "Certificate": {
        "Path": "mgt.cl2.sps.pfx",
        "Password": "<password>"
      }
    }
  }
}
```

| Key | Description |
|---|---|
| `Url` | Listening address and port |
| `Certificate.Path` | Path to the server PFX certificate |
| `Certificate.Password` | PFX password |

#### Database

```json
"ConnectionStrings": {
  "CourtLinkDB": "Server=<host>;Database=CourtLink2;..."
}
```

#### MQTT

| Key | Description |
|---|---|
| `MQTT.ServerAddress` | MQTT broker address (e.g. `127.0.0.1`) |
| `MQTT.Port` | Broker port (e.g. `5883`) |
| `MQTT.ClientId` | Broker client identifier (e.g. `mgt1`) |
| `MQTT.WillRetain` | Retain the will message (`true`) |
| `MQTT.WillDelay` | Seconds before the broker publishes the will on disconnect |

#### Relay / Power Control

| Key | Description |
|---|---|
| `RelaySetting.UseFakeRelay` | `true` to use a simulated relay (dev/test only) |
| `RelaySetting.RelayStatusPollingInterval` | Seconds between relay status polls |
| `RelaySetting.PowerCycleDelay` | Seconds between power-off and power-on during reboot |
| `RelaySetting.BatchSize` | Max simultaneous SNMP commands per batch |
| `RelaySetting.BatchDelay` | Milliseconds between batches |

#### Streaming

| Key | Description |
|---|---|
| `LiveStreamsApiURL` | Wowza REST API URL template (`{EngineIP}` placeholder) |
| `PlaybackMaterial` | Wowza application name for playback token generation |
| `TokenLifetimeInMinute` | Duration of generated Wowza playback tokens |

#### Certificate Whitelist

```json
"WhitelistClients": [
  "<SHA1 thumbprint of CCM cert>",
  "<SHA1 thumbprint of SmartClient cert>"
]
```

Each connecting client's certificate thumbprint is validated against this list. Unknown thumbprints are rejected with `403 Forbidden`.

---

## 5. REST API Reference

All endpoints require a valid mTLS client certificate. The `[Authorize]` attribute enforces role-based access:

| Role | Who Has It | Access |
|---|---|---|
| `Monitor` | CCM clients | Full read/write access |
| `Viewer` | SmartClient clients | Read-only (device list) |

Base URL: `https://<host>:5055`

---

### 5.1 Meetings

**Controller:** `MeetingsController`  
**Route prefix:** `/api/meetings`  
**Required role:** `Monitor`

#### `GET /api/meetings`

Returns all meetings for today.

**Response:** `200 OK` — array of `MeetingInfo`

```json
[
  {
    "id": 1,
    "inmateId": "123456",
    "inmateName": "John Doe",
    "displayName": "John Doe",
    "zoomMeetingId": "12345678901",
    "meetingPasscode": "abc123",
    "deviceId": "VC01",
    "startTime": "2026-03-24T09:00:00",
    "endTime": "2026-03-24T09:30:00"
  }
]
```

---

#### `POST /api/meetings`

Creates a single meeting.

**Request body:** `MeetingInfo` (without `id`)

**Response:** `201 Created` — created `MeetingInfo` with assigned `id`

---

#### `PUT /api/meetings/{id}`

Updates an existing meeting.

**Path parameter:** `id` — meeting database ID

**Request body:** `MeetingInfo`

**Response:** `200 OK` — updated `MeetingInfo`

---

#### `PUT /api/meetings/upsert/{inmateId}`

Creates or updates a meeting matched by `inmateId`.

**Path parameter:** `inmateId` — inmate identifier string

**Request body:** `MeetingInfo`

**Response:** `200 OK` — resulting `MeetingInfo`

---

#### `DELETE /api/meetings/{id}`

Deletes a meeting.

**Path parameter:** `id` — meeting database ID

**Response:** `204 No Content`

---

#### `POST /api/meetings/bulk`

Bulk-creates or updates multiple meetings in a single request.

**Request body:** array of `MeetingInfo`

**Response:** `200 OK` — array of results (success/failure per row)

---

### 5.2 Devices

**Controller:** `DevicesController`  
**Route prefix:** `/api/devices`  
**Required role:** `Viewer` or `Monitor`

#### `GET /api/devices`

Returns all configured devices.

**Response:** `200 OK` — array of `DeviceItemDto`

```json
[
  {
    "id": "VC01",
    "name": "Courtroom 1",
    "zoneId": "Zone A"
  }
]
```

---

### 5.3 Call Lifecycle

**Controller:** `CallController`  
**Route prefix:** `/call`  
**Required role:** `Monitor`

All call operations accept a request body containing at minimum `DeviceId`. The server dispatches the appropriate MQTT `CallRequest` command to the target SmartClient.

#### `POST /call/schedule`

Schedules a meeting on a device. Validates that the device is idle and the meeting is not already assigned elsewhere.

**Request body:**

```json
{
  "deviceId": "VC01",
  "meetingInfo": { ... }
}
```

**Response:** `200 OK`

**Error responses:**

| Status | Reason |
|---|---|
| `409 Conflict` | Device already has a scheduled/active call |
| `409 Conflict` | Same inmate/meeting already scheduled on another device |
| `404 Not Found` | Device not found |

---

#### `PUT /call/start`

Starts the Zoom meeting on the target device (transitions `Scheduled` → `Started`).

**Request body:** `{ "deviceId": "VC01", "sessionId": "<id>" }`

**Response:** `200 OK`

---

#### `PUT /call/end`

Ends the active or paused Zoom meeting (`Started`/`Paused` → `Ended`). The completed call record is persisted to SQL.

**Request body:** `{ "deviceId": "VC01", "sessionId": "<id>" }`

**Response:** `200 OK`

---

#### `PUT /call/pause`

Pauses the active meeting (`Started` → `Paused`).

**Request body:** `{ "deviceId": "VC01", "sessionId": "<id>" }`

**Response:** `200 OK`

---

#### `PUT /call/resume`

Resumes a paused meeting (`Paused` → `Started`).

**Request body:** `{ "deviceId": "VC01", "sessionId": "<id>" }`

**Response:** `200 OK`

---

#### `PUT /call/cancel`

Cancels a scheduled call (`Scheduled` → `Idle`).

**Request body:** `{ "deviceId": "VC01", "sessionId": "<id>" }`

**Response:** `200 OK`

---

### 5.4 System Configs

**Controller:** `SystemConfigsController`  
**Route prefix:** `/api/systemconfigs`  
**Required role:** `Monitor`

#### `GET /api/systemconfigs`

Returns system-wide configuration records from the database.

**Response:** `200 OK` — array of `SystemConfigs`

---

### 5.5 Device Power

**Controller:** `DevicePowerController`  
**Route prefix:** `/api/devicepower`  
**Required role:** `Monitor`

#### `POST /api/devicepower`

Issues a power command to one or more room PCs via SNMP relay.

**Request body:**

```json
{
  "deviceIds": ["VC01", "VC02"],
  "command": "PowerOn"  // "PowerOn" | "PowerOff" | "Reboot"
}
```

**Response:** `200 OK`

---

## 6. Authentication

Management uses **mutual TLS (mTLS)** for all client connections. Both the server and clients present X.509 certificates.

### How It Works

1. Kestrel requires a client certificate on all HTTPS connections (`RequireCertificate`).
2. `CertificateValidationService` computes the SHA-1 thumbprint of the presented certificate and checks it against the `WhitelistClients` list in configuration.
3. If the thumbprint matches a CCM cert entry, the `Monitor` role claim is added to the principal.
4. If the thumbprint matches a SmartClient/Viewer cert entry, the `Viewer` role claim is added.
5. If the thumbprint is not in the list, authentication fails with `403 Forbidden`.

### Certificate Files

| File | Used By |
|---|---|
| `mgt.cl2.sps.pfx` | Server certificate (Kestrel) |
| `mgt1.pfx` | Management's own MQTT client certificate |

### Adding a New Client Certificate

1. Obtain the SHA-1 thumbprint of the new client certificate (e.g. from Windows Certificate Manager or `certutil`).
2. Add the thumbprint string to `WhitelistClients` in `appsettings.Production.json`.
3. Restart the Management service for the change to take effect.

---

## 7. MQTT Topics

Management connects to the MQTT broker using the `mgt1` client ID and its own mTLS certificate.

### Published by Management

| Topic | Payload | When |
|---|---|---|
| `AppTopics.ServerStatus` | `ServerStatus=Online` / `ServerStatus=Offline` (will) | On service start / on unexpected disconnect |
| `AppTopics.CallCommandTopic(deviceId)` | `CallRequest` | On schedule/start/end/pause/resume/cancel API call |
| `AppTopics.MeetingEventTopic(deviceId)` | `MeetingEvent` | On meeting lifecycle state change |
| `AppTopics.DeviceModeStatusTopic(deviceId)` | `DeviceModeStatus` | On device mode change |
| `AppTopics.LiveStreamStatus` | `LiveStreamStatus[]` | On each Wowza poll cycle (from `StreamingService`) |
| `AppTopics.MeetingAnnounceTopic()` | (trigger payload) | After any meeting create/update/delete — prompts CCM to reload |

### Subscribed by Management

| Topic | Payload | Handled By | Purpose |
|---|---|---|---|
| `AppTopics.CallSubscription` | `CallStatus` | `DeviceManager` | Device reports current call phase |
| `AppTopics.MeetingStatusSubscription` | `MeetingStatus` | `DeviceManager` | Device reports Zoom meeting state |
| `AppTopics.ConnectionStatusSubscription` | `DeviceConnectionRequest` | `DeviceManager` | Device online/offline + A/V device status |
| `AppTopics.DeviceSyncModeSubscription` | `DeviceSyncModeRequest` | `DeviceManager` | Device reports Auto/Manual mode |

---

## 8. Service Reference

### 8.1 DeviceManager

**File:** `Models/DeviceManager.cs`

The central in-memory registry of all SmartClient devices, stored as a `ConcurrentDictionary<string, DeviceInfo>`.

**Responsibilities:**

- Receives MQTT events from all SmartClient devices and routes them to the appropriate `DeviceInfo` instance.
- Enforces cross-device constraints (e.g. same meeting/inmate cannot be active on two devices simultaneously).
- Dispatches MQTT `CallRequest` commands when the Management API receives a call lifecycle request.
- Tracks device connection status and propagates it to the CCM via MQTT.

**Key Methods:**

| Method | Description |
|---|---|
| `ScheduleAsync(deviceId, meetingInfo)` | Validates and schedules a meeting on a device |
| `StartAsync(deviceId, sessionId)` | Starts the call on a scheduled device |
| `EndAsync(deviceId, sessionId)` | Ends the active/paused call |
| `PauseAsync(deviceId, sessionId)` | Pauses the active call |
| `ResumeAsync(deviceId, sessionId)` | Resumes the paused call |
| `CancelAsync(deviceId, sessionId)` | Cancels the scheduled call |
| `HandleCallStatusAsync(deviceId, status)` | Processes incoming `CallStatus` from SmartClient |
| `HandleMeetingStatusAsync(deviceId, status)` | Processes incoming `MeetingStatus` from SmartClient |
| `HandleConnectionStatusAsync(deviceId, request)` | Updates device online/offline state |
| `HandleSyncModeAsync(deviceId, request)` | Updates device Auto/Manual mode |

---

### 8.2 DeviceInfo

**File:** `Models/DeviceInfo.cs`

Represents the server-side state of a single SmartClient device. Uses a `SemaphoreSlim(1,1)` async mutex to serialise state transitions and prevent race conditions.

**State Machine:**

```
Idle ──Schedule──► Scheduled ──Start──► Started ──Pause──► Paused
                      └──Cancel──► Idle    └──End──► Ended → Idle
                                                └──Resume──► Started
```

**Key Responsibilities:**

- Validates that state transitions are legal (e.g. cannot `Start` from `Idle`).
- Publishes MQTT `CallRequest` commands to the device.
- On `End`: persists a `Call` record to SQL with duration and session details.
- Tracks `SessionId` for Manual mode locking (Management must present the matching `SessionId` to modify a device in Manual mode).

---

### 8.3 StreamingService

**File:** `Services/StreamingService.cs`

An `IHostedService` that polls the Wowza Media Server REST API on a configurable timer and broadcasts live stream status to all CCM clients.

**How It Works:**

1. On each timer tick, queries the Wowza REST API at `LiveStreamsApiURL` for each configured `StreamingEngine`.
2. Collects `LiveStreamStatus` records: stream name, engine IP, active/inactive state.
3. Generates short-lived **Wowza secure playback tokens** using SHA-256 HMAC with the configured shared secret, valid for `TokenLifetimeInMinute` minutes.
4. Publishes the `LiveStreamStatus[]` array to `AppTopics.LiveStreamStatus` via MQTT.

**Configuration Dependencies:** `LiveStreamsApiURL`, `PlaybackMaterial`, `TokenLifetimeInMinute`, `StreamingEngine` records in SQL.

---

### 8.4 PowerControlService

**File:** `Services/PowerControlService.cs`

An `IHostedService` that manages SNMP relay device control for room PC power management.

**How It Works:**

1. Loads `RelayDevice` configuration records from SQL (IP, port, SNMP community string, digital port assignments).
2. Queues power commands (On / Off / Reboot) submitted via `DevicePowerController`.
3. Executes commands in configurable batches (`BatchSize`, `BatchDelay`) to avoid overloading the relay network.
4. For Reboot: issues PowerOff, waits `PowerCycleDelay` seconds, then issues PowerOn.
5. In development (`UseFakeRelay = true`), uses a simulated relay that logs commands without sending SNMP packets.

---

## 9. Database Schema

Management uses **Entity Framework Core** with `CourtLink2DBContext` targeting a SQL Server `CourtLink2` database.

### Core Tables

#### `Meetings`

| Column | Type | Description |
|---|---|---|
| `Id` | int (PK) | Auto-increment primary key |
| `InmateId` | nvarchar | Inmate identifier |
| `InmateName` | nvarchar | Inmate full name |
| `DisplayName` | nvarchar | Name shown on device screen |
| `ZoomMeetingId` | nvarchar | 10–11 digit Zoom meeting ID |
| `MeetingPasscode` | nvarchar | Zoom meeting passcode |
| `DeviceId` | nvarchar | Assigned device (nullable) |
| `StartTime` | datetime2 | Scheduled start |
| `EndTime` | datetime2 | Scheduled end |
| `CreatedTime` | datetime2 | Record creation timestamp |
| `LastModifiedTime` | datetime2 | Last update timestamp |

#### `Calls`

| Column | Type | Description |
|---|---|---|
| `Id` | int (PK) | Auto-increment primary key |
| `SessionId` | nvarchar | Unique session identifier |
| `DeviceId` | nvarchar | Device the call ran on |
| `MeetingId` | int (FK) | Reference to `Meetings.Id` |
| `StartTime` | datetime2 | Actual call start |
| `EndTime` | datetime2 | Actual call end |
| `Duration` | int | Duration in seconds |

#### `Devices`

| Column | Type | Description |
|---|---|---|
| `Id` | nvarchar (PK) | Device identifier (e.g. `VC01`) |
| `Name` | nvarchar | Display name |
| `ZoneId` | nvarchar | Zone/area grouping |
| `StreamName` | nvarchar | Wowza stream name |
| `StreamingEngineId` | int (FK) | Reference to `StreamingEngines.Id` |

#### `StreamingEngines`

| Column | Type | Description |
|---|---|---|
| `Id` | int (PK) | Auto-increment primary key |
| `IPAddress` | nvarchar | Wowza engine IP |
| `UserName` | nvarchar | Wowza admin username |
| `Password` | nvarchar | Wowza admin password |

#### `RelayDevices`

| Column | Type | Description |
|---|---|---|
| `Id` | int (PK) | Auto-increment primary key |
| `IP` | nvarchar | SNMP relay device IP |
| `Port` | int | SNMP port |
| `Community` | nvarchar | SNMP community string |
| `DigitalPorts` | nvarchar | JSON array of port-to-device mappings |

#### `SystemConfigs`

| Column | Type | Description |
|---|---|---|
| `Key` | nvarchar (PK) | Configuration key |
| `Value` | nvarchar | Configuration value |

---

## 10. Operator Guide

### Prerequisites

- Windows Server 2019 or later (or Windows 10+)
- SQL Server instance with an empty `CourtLink2` database
- MQTT broker running (e.g. Mosquitto) accessible at the configured address and port
- Wowza Media Server (if live streaming is required)
- Server TLS certificate (`mgt.cl2.sps.pfx`) and MQTT client certificate (`mgt1.pfx`)

### Installation as a Windows Service

1. Publish the Management application to a folder (e.g. `C:\CourtLink2\Management`).
2. Open an elevated Command Prompt and run:
   ```
   sc create CourtLink2.Management binPath="C:\CourtLink2\Management\CourtLink2.Management.exe" start=auto
   sc description CourtLink2.Management "CourtLink2 Management Server"
   ```
3. Set the service account to one with access to the certificate store and SQL Server.
4. Start the service:
   ```
   sc start CourtLink2.Management
   ```

### Configuring SSL Certificates

1. Place `mgt.cl2.sps.pfx` (server cert) and `mgt1.pfx` (MQTT client cert) in the application folder (or a path referenced in `appsettings.Production.json`).
2. Update `Kestrel.Endpoints.Https.Certificate.Path` and `Certificate.Password` in `appsettings.Production.json`.

### Configuring SQL Server

1. Create a database named `CourtLink2` on your SQL Server instance.
2. Run the EF Core migrations:
   ```
   dotnet ef database update --project CourtLink2.Infrastructure
   ```
3. Update the `ConnectionStrings.CourtLinkDB` connection string in `appsettings.Production.json`.

### Adding Client Certificates (CCM or SmartClient)

1. Obtain the SHA-1 thumbprint of the new client certificate.
   - Using Windows: `certutil -dump <cert.pfx>` — look for `Cert Hash(sha1)`.
   - Using OpenSSL: `openssl x509 -fingerprint -sha1 -noout -in cert.pem`.
2. Add the thumbprint (uppercase, no spaces) to the `WhitelistClients` array in `appsettings.Production.json`.
3. Restart the service:
   ```
   sc stop CourtLink2.Management
   sc start CourtLink2.Management
   ```

### Checking Service Health

- **Windows Event Log:** Events are written to the Application log under source `MGT1`, Event ID `510`.
- **Log file:** NLog writes to the configured log file (check `appsettings.json` NLog target path).
- **MQTT will message:** If the service stops unexpectedly, the broker publishes `ServerStatus=Offline` on the retained will topic. CCM will show a disconnected server icon.

### Stopping the Service

```
sc stop CourtLink2.Management
```

The service publishes `ServerStatus=Offline` before shutting down gracefully.

### Troubleshooting

| Symptom | Likely Cause | Resolution |
|---|---|---|
| Service fails to start | Invalid PFX certificate or wrong password | Verify certificate path and password in config |
| `403 Forbidden` from CCM | Client cert thumbprint not in whitelist | Add thumbprint to `WhitelistClients` and restart |
| Meetings not persisted | SQL connection string wrong or DB not migrated | Check connection string; run EF migrations |
| No live stream status in CCM | Wowza unreachable or `LiveStreamsApiURL` wrong | Verify Wowza is running; check URL and engine credentials in DB |
| Relay commands not working | `UseFakeRelay=true` in production | Set `UseFakeRelay=false` in `appsettings.Production.json` |
| MQTT will not connect | Broker address/port wrong or cert mismatch | Verify `MQTT` settings and that `mgt1.pfx` is trusted by the broker |
