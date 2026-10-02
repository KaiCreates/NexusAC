"""The wire contract between server/sv_web.lua and this website.

Anything the bridge sends is untrusted input from a machine the website does not
control, so every field is bounded here before it reaches the database.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, BeforeValidator, model_validator

MAX_SNAPSHOT_BYTES = 3_000_000
MAX_MEDIA_BYTES = 1_450_000
MAX_STREAM_FRAME_BYTES = 400_000


def _as_list(value: Any) -> Any:
    """FiveM's JSON encoder writes an empty Lua list as `{}`, not `[]`."""
    if isinstance(value, dict) and not value:
        return []
    return value


Rows = Annotated[list[dict[str, Any]], BeforeValidator(_as_list), Field(max_length=512)]
Text = Annotated[str, Field(min_length=1, max_length=200)]
Reason = Annotated[str, Field(min_length=3, max_length=200)]


class Overview(BaseModel):
    model_config = ConfigDict(extra="allow")
    mode: Literal["observe", "enforce"]
    version: Annotated[str, Field(max_length=80)]
    uptime: Annotated[float, Field(ge=0)]
    online: Annotated[int, Field(ge=0)]
    clientless: Annotated[float, Field(ge=0)] | None = None


class Setting(BaseModel):
    model_config = ConfigDict(extra="allow")
    value: Union[bool, float, str]
    kind: str
    live: bool = False


class ConfigBlock(BaseModel):
    model_config = ConfigDict(extra="allow")
    settings: dict[str, Setting] = Field(default_factory=dict)
    profile: str | None = None


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: Text
    at: float
    detection: str = ""


# --------------------------------------------------------------------------- #
# Identities
#
# Mirrored up in batches rather than in full: the resource sends only identities
# touched since the cursor the website last acknowledged. `kind` is restricted to
# a known set so a compromised or buggy server cannot seed the marks table with
# arbitrary key names that the link query would then have to reckon with.
# --------------------------------------------------------------------------- #

IdentityKind = Literal[
    "license2", "license", "discord", "fivem", "steam",
    "live", "xbl", "ip", "token", "device", "name",
]


class IdentityMark(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: IdentityKind
    value: Annotated[str, Field(min_length=1, max_length=160)]
    first: Annotated[int, Field(ge=0)] = 0
    last: Annotated[int, Field(ge=0)] = 0
    seen: Annotated[int, Field(ge=0)] = 1


class IdentityRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    uid: Annotated[str, Field(min_length=1, max_length=80)]
    first: Annotated[int, Field(ge=0)] = 0
    last: Annotated[int, Field(ge=0)] = 0
    sessions: Annotated[int, Field(ge=0)] = 1
    name: Annotated[str, Field(max_length=100)] = ""
    banned: bool = False
    reason: Annotated[str, Field(max_length=255)] | None = None
    bannedAt: Annotated[int, Field(ge=0)] | None = None
    marks: Annotated[
        list[IdentityMark], BeforeValidator(_as_list), Field(max_length=64)
    ] = Field(default_factory=list)


class IdentityBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # Highest `last_seen` in this batch. The website stores it and hands it back
    # so the resource knows where to resume.
    cursor: Annotated[int, Field(ge=0)] = 0
    rows: Annotated[
        list[IdentityRow], BeforeValidator(_as_list), Field(max_length=100)
    ] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Event log
#
# `eventLog`, not `events` -- `events` on the snapshot is already the Event
# Protection rule set, and the two are unrelated.
# --------------------------------------------------------------------------- #

class EventRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    seq: Annotated[int, Field(ge=0)]
    at: Annotated[int, Field(ge=0)]
    type: Annotated[str, Field(min_length=1, max_length=40)]
    sender: Annotated[str, Field(max_length=80)] | None = None
    senderName: Annotated[str, Field(max_length=100)] | None = None
    target: Annotated[str, Field(max_length=80)] | None = None
    targetName: Annotated[str, Field(max_length=100)] | None = None
    # Left loose on purpose: the useful fields differ per event type and the
    # page queries them by path. Bounded by the snapshot size limit instead.
    # FiveM's json.encode turns an empty Lua table into [] rather than {}.
    # Treat only that empty representation as an empty object; a populated
    # array is still malformed event metadata and must be rejected.
    data: Annotated[dict[str, Any], BeforeValidator(
        lambda value: {} if value == [] else value
    )] = Field(default_factory=dict)


class EventBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")
    boot: Annotated[str, Field(min_length=1, max_length=200)]
    cursor: Annotated[int, Field(ge=0)] = 0
    rows: Annotated[
        list[EventRow], BeforeValidator(_as_list), Field(max_length=200)
    ] = Field(default_factory=list)


class PunishmentRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    seq: Annotated[int, Field(ge=0)]
    at: Annotated[int, Field(ge=0)]
    kind: Literal["ban", "kick", "warn", "unban", "unwarn"]
    identifier: Annotated[str, Field(max_length=80)] | None = None
    name: Annotated[str, Field(max_length=100)] | None = None
    reason: Annotated[str, Field(max_length=500)] | None = None
    by: Annotated[str, Field(max_length=100)] | None = None
    auto: bool = False
    days: Annotated[int, Field(ge=0, le=3650)] | None = None
    detector: Annotated[str, Field(max_length=60)] | None = None
    evidence: Annotated[str, Field(max_length=200)] | None = None


class PunishmentBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")
    boot: Annotated[str, Field(min_length=1, max_length=200)]
    cursor: Annotated[int, Field(ge=0)] = 0
    rows: Annotated[
        list[PunishmentRow], BeforeValidator(_as_list), Field(max_length=200)
    ] = Field(default_factory=list)


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overview: Overview
    identities: IdentityBlock | None = None
    eventLog: EventBlock | None = None
    punishments: PunishmentBlock | None = None
    players: Rows = Field(default_factory=list)
    detectors: Rows = Field(default_factory=list)
    protections: Rows = Field(default_factory=list)
    cleanup: dict[str, Annotated[int, Field(ge=0)]] = Field(default_factory=dict)
    bans: Rows = Field(default_factory=list)
    feed: Rows = Field(default_factory=list)
    logs: Rows = Field(default_factory=list)
    # Bounded server resource inventory and source-scanned event declarations.
    # These are metadata, not a trace of every runtime event invocation.
    resources: dict[str, Any] = Field(default_factory=dict)
    config: ConfigBlock = Field(default_factory=ConfigBlock)
    events: Any = None
    eventRules: Rows = Field(default_factory=list)
    integrations: Any = None
    evidence: Annotated[
        list[EvidenceItem], BeforeValidator(_as_list), Field(max_length=200)
    ] = Field(default_factory=list)


class Acknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Annotated[str, Field(min_length=36, max_length=36)]
    ok: bool
    message: Annotated[str, Field(max_length=1000)] = ""
    uncertain: bool = False


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol: Literal[1]
    boot: Text
    sequence: Annotated[int, Field(gt=0)]
    sentAt: int
    snapshot: Snapshot
    acknowledgements: Annotated[
        list[Acknowledgement], BeforeValidator(_as_list), Field(max_length=50)
    ] = Field(default_factory=list)


class MediaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidenceId: Annotated[str, Field(min_length=1, max_length=200)]
    slot: Annotated[int, Field(ge=0, le=2)]
    data: Annotated[str, Field(max_length=MAX_MEDIA_BYTES, pattern=r"^data:image/jpeg;base64,[A-Za-z0-9+/]+={0,2}$")]


class StreamStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Annotated[int, Field(gt=0, le=1024)]
    playerSession: Annotated[str, Field(min_length=1, max_length=100)]
    captureSession: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]


class StreamFrameRequest(StreamStartRequest):
    sequence: Annotated[int, Field(gt=0)]
    data: Annotated[str, Field(max_length=MAX_STREAM_FRAME_BYTES,
                               pattern=r"^data:image/(?:jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$")]


# --------------------------------------------------------------------------- #
# Commands sent from the website down to the anti-cheat
# --------------------------------------------------------------------------- #

class _Targeted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Annotated[int, Field(gt=0)]
    session: Text
    reason: Reason


class WarnCommand(_Targeted):
    """Recorded against the player's identity and shown to them. Counted, and
    escalates only if the server configured it to."""
    type: Literal["warn"]


class KickCommand(_Targeted):
    type: Literal["kick"]


class BanCommand(_Targeted):
    type: Literal["ban"]
    days: Annotated[int, Field(ge=0, le=3650)]


class FreezeCommand(_Targeted):
    type: Literal["freeze"]
    on: bool


class ScreenshotCommand(_Targeted):
    type: Literal["screenshot"]


class VehicleExemptCommand(BaseModel):
    """Exempt one player (the car developer) from the city speed limiter and
    the vehicle boost checks. Stored by licence on the game server."""
    model_config = ConfigDict(extra="forbid")
    type: Literal["vehicleExempt"]
    target: Annotated[int, Field(gt=0)]
    session: Text
    enabled: bool


class UnbanCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["unban"]
    identifier: Text
    reason: Reason


class SettingCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["setting"]
    path: Text
    # List-backed settings (OCR phrases and vehicle model tiers) use the same
    # audited scalar command path as every other setting. The request endpoint
    # is capped at 16 KiB, so 6 KiB per side leaves room for both value and the
    # optimistic-concurrency `expected` value in one command.
    value: Union[bool, float, Annotated[str, Field(max_length=6000)]]
    expected: Union[bool, float, Annotated[str, Field(max_length=6000)]]


class EntityCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["entity"]
    model: Annotated[str, Field(min_length=1, max_length=80)]
    policy: Literal["allow", "block", "ban"]
    risk: Annotated[int, Field(ge=0, le=200)] = 0


class DetectorCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["detector"]
    detector: Text
    mode: Literal["disabled", "observe", "enforce"]
    expected: Literal["disabled", "observe", "enforce"]


class WebhookCommand(BaseModel):
    """Set or clear one Discord webhook channel.

    Write only, and it carries no `expected`: the resource never hands a webhook
    URL back out, so there is nothing to compare against. An empty url clears
    the channel.
    """
    model_config = ConfigDict(extra="forbid")
    type: Literal["webhook"]
    category: Literal["main", "bans", "kicks", "detections", "movement", "combat",
                      "entities", "economy", "resources", "admin", "errors", "screenshots", "aim"]
    url: Annotated[str, Field(max_length=250)] = ""


class PunishCommand(BaseModel):
    """Override one 2.0 signal's module action without bypassing confidence.

    'risk' uses the module's configured action and confidence policy; it no
    longer means cross-family risk correlation. Observe/Disabled still win.
    """
    model_config = ConfigDict(extra="forbid")
    type: Literal["punish"]
    signal: Annotated[str, Field(min_length=1, max_length=60)]
    action: Literal["none", "log", "risk", "kick", "ban"]
    expected: Literal["none", "log", "risk", "kick", "ban"]


class ProtectionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["protection"]
    id: Text
    enabled: bool
    profile: Literal["relaxed", "balanced", "strict"]
    action: Literal["log", "kick", "ban"]
    minConfidence: Annotated[int, Field(ge=50, le=100)]
    screenshot: bool
    discord: bool
    expected: dict[str, Any]


EventName = Annotated[str, Field(min_length=3, max_length=96, pattern=r"^[A-Za-z0-9_:.-]+$")]


class EventRuleItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: EventName
    mode: Literal["watch", "ignore"] = "watch"
    perMinute: Annotated[int, Field(ge=1, le=1000)] = 30


class EventRuleCommand(BaseModel):
    """Manage dashboard-side watch/ignore overrides for named server events.

    `import` carries a whole .txt import as one command, so the resource can
    validate it and save it in a single all-or-nothing write."""
    model_config = ConfigDict(extra="forbid")
    type: Literal["eventRule"]
    operation: Literal["save", "delete", "import"]
    name: EventName | None = None
    mode: Literal["watch", "ignore"] = "watch"
    perMinute: Annotated[int, Field(ge=1, le=1000)] = 30
    rules: Annotated[list[EventRuleItem], Field(max_length=128)] | None = None

    @model_validator(mode="after")
    def _shape(self) -> "EventRuleCommand":
        if self.operation == "import":
            if not self.rules:
                raise ValueError("an import needs at least one rule")
        elif self.name is None:
            raise ValueError("save and delete need an event name")
        return self


class StreamCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["stream"]
    operation: Literal["start", "stop"]
    target: Annotated[int, Field(gt=0, le=1024)]
    session: Text
    viewerId: Annotated[str, Field(pattern=r"^[0-9a-fA-F-]{36}$")]


class StreamViewer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    viewerId: Annotated[str, Field(pattern=r"^[0-9a-fA-F-]{36}$")]
    target: Annotated[int, Field(gt=0, le=1024)]
    session: Text
    afterSequence: Annotated[int, Field(ge=0)] = 0


class StreamFramesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    streams: Annotated[list[StreamViewer], BeforeValidator(_as_list), Field(max_length=4)]


class CleanupCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["cleanup"]
    category: Literal["vehicles", "peds", "objects"]
    scope: Literal["server", "client"]
    expected: Annotated[int, Field(ge=0)]



class InventoryCommand(BaseModel):
    """Read-only inventory lookup, answered through /bridge/inventory.

    search  characters matching `query` (online first; offline from the DB)
    view    one character by ESX identifier: pockets, money, owned vehicles'
            trunks and gloveboxes, stashes
    player  the same for an online player, by server id + session
    """
    model_config = ConfigDict(extra="forbid")
    type: Literal["inventory"]
    operation: Literal["search", "view", "player"]
    query: Annotated[str, Field(max_length=60)] = ""
    identifier: Annotated[str, Field(max_length=80, pattern=r"^[A-Za-z0-9:_-]*$")] = ""
    target: Annotated[int, Field(ge=0, le=1024)] = 0
    session: Annotated[str, Field(max_length=100)] = ""

    @model_validator(mode="after")
    def _shape(self) -> "InventoryCommand":
        if self.operation == "view" and not self.identifier:
            raise ValueError("view needs an identifier")
        if self.operation == "player" and (self.target < 1 or not self.session):
            raise ValueError("player needs a target and session")
        return self


MAX_INVENTORY_BYTES = 900_000


class InventoryUpload(BaseModel):
    """The game server's answer to one InventoryCommand, keyed by command id."""
    model_config = ConfigDict(extra="forbid")
    commandId: Annotated[str, Field(pattern=r"^[0-9a-fA-F-]{36}$")]
    operation: Literal["search", "view", "player"]
    ok: bool = True
    message: Annotated[str, Field(max_length=500)] = ""
    body: dict[str, Any] = Field(default_factory=dict)


Command = Annotated[
    Union[
        WarnCommand, KickCommand, BanCommand, FreezeCommand, ScreenshotCommand,
        UnbanCommand, SettingCommand, EntityCommand, DetectorCommand, PunishCommand,
        WebhookCommand, ProtectionCommand, EventRuleCommand, StreamCommand, CleanupCommand,
        VehicleExemptCommand, InventoryCommand,
    ],
    Field(discriminator="type"),
]


class CommandEnvelope(BaseModel):
    command: Command


def parse_command(payload: dict) -> BaseModel:
    return CommandEnvelope(command=payload).command


def issues(error: ValidationError) -> list[str]:
    return [f"{'.'.join(str(p) for p in i['loc'])}: {i['msg']}" for i in error.errors()[:8]]
