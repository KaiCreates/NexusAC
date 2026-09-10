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


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overview: Overview
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


Command = Annotated[
    Union[
        KickCommand, BanCommand, FreezeCommand, ScreenshotCommand,
        UnbanCommand, SettingCommand, DetectorCommand,
    ],
    Field(discriminator="type"),
]


class CommandEnvelope(BaseModel):
    command: Command


def parse_command(payload: dict) -> BaseModel:
    return CommandEnvelope(command=payload).command


def issues(error: ValidationError) -> list[str]:
    return [f"{'.'.join(str(p) for p in i['loc'])}: {i['msg']}" for i in error.errors()[:8]]
