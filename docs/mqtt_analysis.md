User: # MQTT Distributed Messaging Architecture Analysis

## Objective

Conduct a comprehensive analysis of the MQTT-based distributed messaging architecture across the CourtLink2 solution, with focus on state consistency risks in an eventually-consistent messaging system.

---

## System Architecture Context

The CourtLink2 platform implements a distributed control system for Zoom meeting management using MQTT as the primary state synchronization and command transport layer:

| Component                                   | Role                                                                                                                  | MQTT Behavior                                                                                             |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| **CourtLink2.Management**             | Central orchestration service; command authority for SmartClient fleet                                                | Publishes commands (`CallRequest`, `ControlRequest`); Subscribes to all device/meeting state topics   |
| **CourtLink2.SmartClient**            | Zoom SDK wrapper with dual-mode operation:**Auto** (Management-controlled) / **Manual** (user-controlled) | Publishes state (`MeetingStatus`, `DeviceStatus`, `DeviceConnection`); Subscribes to command topics |
| **CCM (Control Client)**              | Officer control interface for meeting/device management                                                               | Publishes control commands; Subscribes to state topics for UI binding                                     |
| **CMM (Client Monitor)**              | Real-time desktop screen capture streaming monitor                                                                    | Subscribes to stream status topics; Publishes capture requests                                            |
| **RAD (Resource Allocation Display)** | Dashboard displaying room/meeting allocation across SmartClient fleet                                                 | Read-only subscriber to meeting status, connection, and call topics                                       |

---

## Technical Analysis Requirements

### 1. Topic Ownership & Data Flow Mapping

- Document all MQTT topic patterns, retention policies, and QoS levels
- Map publisher→subscriber relationships with message schemas
- Identify shared-write topics (multiple publishers to same topic pattern)

### 2. State Consistency Risk Analysis

| Risk Category                        | Description                                                                                                   |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| **Race Conditions**            | Concurrent message publication/subscription handlers modifying shared state                                   |
| **Ordering Violations**        | Message arrival order divergence across subscribers (MQTT QoS 1 provides at-least-once, not ordered delivery) |
| **Retained Message Staleness** | Stale retained messages delivered to new subscribers before live updates                                      |
| **WILL Message Latency**       | Delayed offline detection (keep-alive timeout window)                                                         |
| **Split-Brain Scenarios**      | Network partitions causing divergent state views                                                              |

### 3. Transactional Integrity Gaps

- HTTP→MQTT command chains without distributed transaction guarantees
- Multi-topic state updates lacking atomicity (e.g., `MeetingStatus` + `DeviceStatus` published independently)
- Acknowledgment patterns without idempotency keys

### 4. Synchronization Mechanism Audit

- Session-based command validation (`SyncMode` with `SessionId`)
- Reconnection state recovery patterns
- Locking primitives in message handlers (`SemaphoreSlim` usage)

---

## Constraints

MQTT is an eventually-consistent pub/sub protocol and does not provide ACID guarantees:

| ACID Property         | MQTT Limitation                                              |
| --------------------- | ------------------------------------------------------------ |
| **Atomicity**   | Multi-topic updates are non-atomic                           |
| **Consistency** | No schema enforcement or referential integrity               |
| **Isolation**   | Concurrent subscribers see intermediate states               |
| **Durability**  | Retained messages lost on broker failure without persistence |

---

## Deliverable

Identify specific code paths and message flows where state inconsistency may occur, with severity assessment and mitigation recommendations.

GitHub Copilot: Research MQTT messaging architecture

Searched codebase for "MQTT topic patterns AppTopics subscription publish message broker connection", no results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Messaging)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/AppTopics.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Messaging/MessageBus.cs#1-1), lines 1 to 200

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Messaging/MqttCommonExtensions.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Messaging/AppMessage.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Messaging/MessageBus.cs#200-200), lines 200 to 240

Searched for regex `SyncMode|SessionId`, 20 results

Searched for regex `EnqueueMessageAsync|PublishMessageAsync`, 20 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/Services)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/Services/MqttMessagePubSub.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Services/MessagingService.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Models/DeviceManager.cs#1-1), lines 1 to 150

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Models/DeviceManager.cs#150-150), lines 150 to 198

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/MeetingStatus.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/CallRequest.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/ControlRequest.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/DeviceSyncModeRequest.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/DeviceConnectionRequest.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/DeviceStatusRequest.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/MeetingEvent.cs)

Searched for regex `SemaphoreSlim|lock\s*\(|Mutex|Monitor\.|ReaderWriterLock`, 20 results

Searched for regex `Subscribe\(|SubscribeTopics|AppMessageReceived`, 20 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Models/DeviceInfo.cs#1-1), lines 1 to 250

Read [](file:///d%3A/dev/courtlink2/CourtLink2.CCM/Services)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.CMM/Services)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Models/DeviceInfo.cs#250-250), lines 250 to 429

Read [](file:///d%3A/dev/courtlink2/CourtLink2.CCM/Services/MessagingService.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.CMM/Services/MessagingService.cs)

Searched for regex `appsettings.*\.json|Broker|ServerAddress|ServerPort` (`**/*.json`), 20 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/appsettings.json)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/appsettings.json)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/appsettings.Development.json#1-1), lines 1 to 100

Read [](file:///d%3A/dev/courtlink2/CourtLink2.RAD)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/appsettings.Development.json#1-1), lines 1 to 50

Read [](file:///d%3A/dev/courtlink2/CourtLink2.RAD/Services)

Searched for regex `MeetingEvent|MeetingEventTopic|DeviceCaptureTopic|ElapsedStatusTopic`, 20 results

Searched for regex `BreakoutRoomControlTopic|SignInterpretationControlTopic|LanguageInterpretationControlTopic`, 10 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.RAD/Services/MessagingService.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/Services)

Searched for regex `ConcurrentDictionary|concurrent|race|atomic`, 20 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/Services/MeetingCommandObserver.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/Services/DeviceControlService.cs#1-1), lines 1 to 100

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/Services/MeetingEventPublisher.cs)

Searched for regex `reconnect|retry|recovery|reconnection`, 20 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/Services/DeviceStatusPublisher.cs#1-1), lines 1 to 100

Searched for regex `LiveStreamStatus|StreamingService`, 20 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Services/StreamingService.cs#1-1), lines 1 to 120

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/UserControls/TaskBar.xaml.cs#35-35), lines 35 to 74

Searched for regex `\.Where\(.+IsMatchTopic`, 20 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.RAD/ViewModel/RoomAllocationDisplayViewModel.cs#1-1), lines 1 to 150

Read [](file:///d%3A/dev/courtlink2/CourtLink2.CCM/ViewModel/LanguageInterpretationViewModel.cs#100-100), lines 100 to 250

Read [](file:///d%3A/dev/courtlink2/CourtLink2.CCM/Services/ObservableProvider.cs#1-1), lines 1 to 100

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/ServerStatusRequest.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/Constants.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.CCM/Services/ObservableProvider.cs#100-100), lines 100 to 128

Searched for regex `QualityOfServiceLevel|AtLeastOnce|AtMostOnce|ExactlyOnce`, 20 results

Searched for regex `async.*Subscribe|await.*Subscribe`, 20 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/BreakoutRoomRequest.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/LanguageInterpretationRequest.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Messaging/ClientCertificate.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Guard)

Searched for regex `WillPayload|WillTopic|WillMessage|LastWill`, 20 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/AppSetup.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Infrastructure/CourtLinkMessageBusFactory.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Guard/Form1.cs#1-1), lines 1 to 100

Read [](file:///d%3A/dev/courtlink2/CourtLink2.CCM/Services/MeetingManager.cs)

Searched for regex `Retain|retain\s*=\s*true`, 20 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.CCM/ViewModel/LanguageInterpretationViewModel.cs#250-250), lines 250 to 300

Searched for regex `DeviceCapture|ElapsedStatus`, 10 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/DeviceCaptureRequest.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/ElapsedRequest.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/DeviceModeRequest.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Simulators.SCM/Device.cs#100-100), lines 100 to 180

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Simulators.CCM/MQTTSubscriber.cs)

Searched for regex `try\s*\{.*catch|OnError|errorHandler`, 12 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/UserControls/SettingWindow.xaml.cs#70-70), lines 70 to 200

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Models/Constants.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Controllers)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Controllers/CallController.cs)

Based on the comprehensive research, I can now present a detailed plan for the MQTT distributed messaging architecture analysis.

---

## Plan: MQTT State Consistency Risk Assessment

This analysis identifies critical state consistency risks in the CourtLink2 MQTT-based distributed architecture. The system uses MQTTnet with QoS 1 (at-least-once) delivery across 5 components, with **6 high-severity bugs** and **4 architectural gaps** requiring mitigation.

### Steps

1. **Fix critical semaphore bug in `DeviceInfo.GetName()`** at DeviceInfo.cs — `Release()` called without prior `WaitAsync()` corrupts semaphore count, causing deadlocks or uncontrolled concurrent access.
2. **Atomize multi-property state updates** in DeviceManager.HandleDeviceSyncMode — wrap sequential `SetDeviceMode`, `SetCallMode`, `SetStatus` calls in single lock acquisition to prevent intermediate state visibility.
3. **Replace fire-and-forget publishes** (`_ = EnqueueMessageAsync(...)`) in MqttMessagePubSub.cs with awaited calls + exception handling to detect publish failures.
4. **Add transaction boundary** for DB+MQTT operations in CallController.cs — implement Outbox pattern or compensating transaction for `SaveCompletedCall()` → `PublishCallCommand()` sequences.
5. **Implement subscription disposal** in ObservableProvider.cs — track `IDisposable` from `.Subscribe()` calls and dispose on component shutdown to prevent memory leaks.
6. **Add read-side locking** in `DeviceInfo.ValidateMeetingStatus()` — reads `Command` and `Status` without lock while concurrent handlers may modify them.

### Further Considerations

1. **Retained message staleness** — Should we implement message timestamps with TTL validation so new subscribers reject stale retained messages older than N seconds? *Recommended: Add `Timestamp` to all DTOs with 30s staleness threshold.*
2. **WILL message latency** — Current 60s keep-alive timeout means offline detection can be delayed up to 90s (1.5× keep-alive). Reduce to 15s for faster failover, or accept latency for network stability?
3. **Split-brain recovery** — When network partitions heal, should Management service request full state resync from SmartClients, or trust retained messages? *Recommended: Add `serverstatus` subscription handler in SCM to trigger state republish on Management reconnect.*

User: Also analyze more detail analysis of the followings:

- Audit synchronization mechanisms - Review SyncMode session-based locking, reconnection recovery patterns, and the 5-second WILL message delay implications.
- Identify cross-component consistency risks - Map message flows where HTTP→MQTT or multi-step MQTT chains could leave the system in partial states.
- Event Acknowledgment Race Condition: Multiple CCM clients updating AckedBy[] simultaneously may overwrite each other — should we implement optimistic concurrency or a dedicated aggregation service? Option A: Aggregation in SmartClient / Option B: CRDT-style merge / Option C: Accept eventual consistency
- No Distributed Transaction Protection: HTTP success followed by MQTT failure leaves inconsistent state — should we implement saga pattern, or is the current try-catch with logging acceptable for this real-time control scenario?

GitHub Copilot: Deep-dive MQTT sync mechanisms

Searched for text `SyncMode`, 20 results

Searched for text `SessionId`, 20 results

Searched for text `AckedBy`, 20 results

Searched for text `MeetingEventAck`, 20 results

Searched for regex `WillMessage|LastWill|LWT`, 2 results

Searched for regex `Reconnect|ConnectionStatusChanged|Disconnected`, 20 results

Searched for text `PublishCallCommand`, 7 results

Searched for text `EnqueueMessageAsync`, 20 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/MQZoomer/MeetingController.cs#1-1), lines 1 to 100

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Messaging/MessageBus.cs#90-90), lines 90 to 200

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/MeetingEvent.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/DeviceSyncModeRequest.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/MQZoomer/MeetingController.cs#200-200), lines 200 to 400

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/MQZoomer/MeetingController.cs#700-700), lines 700 to 800

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Messaging/MessageBus.cs#1-1), lines 1 to 90

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Models/DeviceInfo.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/Services/MqttMessagePubSub.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/Services/MeetingEventPublisher.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/Extensions/MeetingEventExtensions.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/UserControls/TaskBar.xaml.cs#35-35), lines 35 to 74

Searched for files matching `**/CourtLink2.Management/Controllers/*.cs`, 5 matches

Searched for text `DeviceManager` (`**/CourtLink2.Management/**`), 16 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Controllers/CallController.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Models/DeviceManager.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Messaging/MessageBus.cs#200-200), lines 200 to 240

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Simulators.SCM/Device.cs#100-100), lines 100 to 250

Searched for text `WillPayload`, 12 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/AppSetup.cs#30-30), lines 30 to 77

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Infrastructure/CourtLinkMessageBusFactory.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.CCM/ViewModel/DeviceItemViewModel.cs#1-1), lines 1 to 100

Read [](file:///d%3A/dev/courtlink2/CourtLink2.CCM/ViewModel/DeviceItemViewModel.cs#130-130), lines 130 to 377

Read [](file:///d%3A/dev/courtlink2/CourtLink2.CCM/Services/ObservableProvider.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.CCM/ViewModel/LanguageInterpretationViewModel.cs#100-100), lines 100 to 200

Searched for text `WillDelay`, 4 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Controllers/MeetingsController.cs#1-1), lines 1 to 150

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Controllers/MeetingsController.cs#150-150), lines 150 to 177

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Infrastructure/AppSettings/MqttSettings.cs)

Searched for regex `PublishMessageAsync|EnqueueMessageAsync` (`**/CourtLink2.Management/Controllers/**`), 1 result

Searched for regex `SaveChangesAsync.*Publish|SaveChangesAsync.*Enqueue`, no results

Searched for text `_messageBus.PublishMessageAsync`, 2 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Services/MessagingService.cs)

Read [](file:///d%3A/dev/courtlink2/CourtLink2.API/AppTopics.cs)

Searched for text `KeepAlive`, no results

Searched for regex `reInitializeOnMqttReconnect`, 6 results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.SmartClient/UserControls/TaskBar.xaml.cs#1-1), lines 1 to 70

Searched for regex `Subscribe.*\.Subscribe\(` (`**/CourtLink2.SmartClient/Services/**`), no results

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Simulators.SCM/Device.cs#1-1), lines 1 to 50

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Simulators.SCM/Device.cs#50-50), lines 50 to 100

Read [](file:///d%3A/dev/courtlink2/CourtLink2.Management/Models/DeviceInfoFactory.cs#1-1), lines 1 to 110

Searched for regex `Subscribe.*Publish|Subscribe.*Enqueue`, no results

Searched for regex `\.Subscribe\(.*async`, 12 results

Searched for text `lock(`, 2 results

Searched for text `SemaphoreSlim`, 1 result

Based on this comprehensive deep-dive, here is the refined plan:

---

## Plan: Deep MQTT Synchronization Risk Mitigation

A detailed analysis of SyncMode locking, WILL message timing, HTTP→MQTT chains, and event acknowledgment races reveals **4 critical architectural gaps** requiring decisions between consistency vs. complexity trade-offs.

### Steps

1. **Strengthen SessionId-based locking** in MeetingController.cs — current validation at `IsValidSession()` happens per-message but command execution isn't atomic with session ownership; add session lease expiry and command-under-session atomicity.
2. **Reduce WILL delay from 5s→1s** in MqttMessageBus.cs at `WillDelay` property, and add explicit `KeepAlive` interval (currently unset, relying on TCP timeout) to detect offline devices faster.
3. **Atomize reconnection republish** in MqttSubscriptionManager.cs — currently publishes `SyncMode`, `MeetingStatus`, `DeviceConnection` as 3 separate messages; bundle into single compound message or add sequence numbers so subscribers can detect/reassemble.
4. **Implement Outbox pattern** for HTTP→MQTT in DeviceInfo.cs `EndMeeting()` — wrap `SaveCompletedCall()` + `PublishCallCommand()` in transactional outbox to ensure atomicity between DB and MQTT.
5. **Add optimistic concurrency to AckedBy[]** in MeetingManager.cs — use `lock(_meetingEventLock)` pattern from SCMMeetingController.cs (simulator) that production code lacks; add version field to detect stale updates.
6. **Document partial-state windows** for multi-step chains — in SCMMeetingController.cs the `Subscribe→Transform→Publish` pattern creates observable intermediate states; add state machine guards or compensating messages.

### Further Considerations

1. **Event Acknowledgment Race Condition** — Multiple CCMs updating `AckedBy[]` simultaneously may overwrite each other's acks. Which approach?

   - **Option A: Aggregation in SmartClient** — SCM serializes acks with `lock()` (as simulator does, but production MeetingManager.cs lacks this). *Low complexity, single point of aggregation.*
   - **Option B: CRDT-style merge** — Each ack message carries full `AckedBy[]` array; receivers union-merge arrays. *Tolerant to message reordering, higher message size.*
   - **Option C: Accept eventual consistency** — Allow temporary overwrites; final state converges as SCM republishes on each ack. *Simplest, acceptable if UI can tolerate flicker.*
   - **Recommendation**: Option A with production lock — minimal change, matches simulator pattern.
2. **No Distributed Transaction Protection** — `SaveCompletedCall()` commits to SQL, then `PublishCallCommand()` may fail, leaving DB/MQTT inconsistent. Which approach?

   - **Option A: Saga pattern** — Add compensating action (delete DB record) if MQTT fails. *Complex, requires idempotent operations.*
   - **Option B: Outbox pattern** — Write MQTT message to DB outbox table in same transaction; background worker publishes. *Guaranteed delivery, adds latency.*
   - **Option C: Current try-catch + logging** — Log failures, rely on manual reconciliation. *Acceptable for real-time control where retry is operator-driven.*
   - **Recommendation**: Option B (Outbox) for `EndMeeting` critical path; Option C acceptable for non-critical status updates.
3. **WILL Message 5-Second Delay vs. Quick Reconnect** — If SCM reconnects within 5 seconds, WILL is cancelled but state may be stale (published before crash). Should we:

   - Force full state republish on every reconnect (current behavior) — may cause UI flicker
   - Add `ReconnectSequence` counter so subscribers detect/discard pre-crash messages
   - Reduce delay to 1s and accept more frequent false-offline during network blips
4. **SessionId Lease Expiry** — Currently sessions never expire; orphan sessions from crashed CCM clients block Auto mode permanently. Add TTL (e.g., 5 minutes) with heartbeat refresh?
