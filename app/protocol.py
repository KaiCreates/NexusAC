"""The wire contract between server/sv_web.lua and this website.

Anything the bridge sends is untrusted input from a machine the website does not
control, so every field is bounded here before it reaches the database.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, BeforeValidator

MAX_SNAPSHOT_BYTES = 3_000_000
MAX_MEDIA_BYTES = 1_450_000


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
    data: dict[str, Any] = Field(default_factory=dict)


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
    bans: Rows = Field(default_factory=list)
    feed: Rows = Field(default_factory=list)
    logs: Rows = Field(default_factory=list)
    config: ConfigBlock = Field(default_factory=ConfigBlock)
    events: Any = None
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


class UnbanCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["unban"]
    identifier: Text
    reason: Reason


class SettingCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["setting"]
    path: Text
    value: Union[bool, float, Annotated[str, Field(max_length=300)]]
    expected: Union[bool, float, Annotated[str, Field(max_length=300)]]


class DetectorCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["detector"]
    detector: Text
    mode: Literal["disabled", "observe", "enforce"]
    expected: Literal["disabled", "observe", "enforce"]


class PunishCommand(BaseModel):
    """What ONE detection of a signal kind does on its own.

    'risk' is the default and hands the finding to the correlation engine.
    Anything else is an immediate verdict on a single detection, which is why
    the resource ships almost everything on 'risk'.
    """
    model_config = ConfigDict(extra="forbid")
    type: Literal["punish"]
    signal: Annotated[str, Field(min_length=1, max_length=60)]
    action: Literal["none", "log", "risk", "kick", "ban"]
    expected: Literal["none", "log", "risk", "kick", "ban"]


Command = Annotated[
    Union[
        WarnCommand, KickCommand, BanCommand, FreezeCommand, ScreenshotCommand,
        UnbanCommand, SettingCommand, DetectorCommand, PunishCommand,
    ],
    Field(discriminator="type"),
]


class CommandEnvelope(BaseModel):
    command: Command


def parse_command(payload: dict) -> BaseModel:
    return CommandEnvelope(command=payload).command


def issues(error: ValidationError) -> list[str]:
    return [f"{'.'.join(str(p) for p in i['loc'])}: {i['msg']}" for i in error.errors()[:8]]
