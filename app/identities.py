"""Identity search and account linking.

Two identities are linked when they share an identifier. That relationship is
derived from nx_identity_marks at query time rather than stored as edges,
because an edge table is wrong the moment it falls behind the marks feeding it.

Two judgements are baked in here, and both matter more than they look:

* **Hub values do not link.** An IP behind CGNAT, or a shared VPN exit, can be
  carried by hundreds of unrelated players. Treating that as evidence of an
  alias produces a graph where everyone is related to everyone. A value carried
  by more than MAX_SHARE identities is reported as suppressed rather than used,
  so the investigator can see it was considered and why it was dropped.

* **The link kinds travel with the edge.** "These two accounts share a Discord
  ID and nothing else" and "these two share a hardware token" are very different
  claims. The API never flattens that to a boolean, because the person acting on
  it has to be able to tell them apart.
"""
from __future__ import annotations

import re
from typing import Any

from . import db
from .security import require

# The spec's own performance note draws the line at 500 linked accounts.
MAX_NODES = 500
# Above this many holders, a value is a hub and stops being evidence.
MAX_SHARE = 40
MAX_DEPTH = 4
PAGE_SIZES = (25, 50, 100)

LICENSE = re.compile(r"^[0-9a-f]{40}$", re.I)
DISCORD = re.compile(r"^\d{17,20}$")
# SteamID64 in hex is always 15 digits beginning 110000; the seventh digit is
# not always 1 (110000 5 ... exists), so it is not pinned.
STEAM_HEX = re.compile(r"^(?:steam:)?(110000[0-9a-f]{9})$", re.I)
STEAM_64 = re.compile(r"^(7656119\d{10})$")
IPV4 = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")
HEX_TOKEN = re.compile(r"^[0-9a-f]{32,}$", re.I)
PREFIXED = re.compile(
    r"^(license2|license|discord|fivem|steam|live|xbl|ip|token|device|name):(.+)$", re.I
)

# Which kinds a bare value could plausibly be, most specific first.
def classify(raw: str) -> tuple[list[tuple[str, str]], str | None]:
    """Return the (kind, value) pairs to look for, and a name fragment if the
    query does not look like an identifier at all."""
    q = (raw or "").strip()
    if not q:
        return [], None

    prefixed = PREFIXED.match(q)
    if prefixed:
        return [(prefixed.group(1).lower(), prefixed.group(2).strip())], None

    if LICENSE.match(q):
        # license and license2 are the same 40 hex characters from different
        # sources, so a bare one has to be looked for as either.
        return [("license", q.lower()), ("license2", q.lower())], None

    steam = STEAM_HEX.match(q)
    if steam:
        return [("steam", steam.group(1).lower())], None

    # SteamID64 is checked before Discord, and deliberately does not win
    # outright. A 17-digit SteamID64 (76561198...) and a mid-2015 Discord
    # snowflake occupy the same numeric range, so a value that could be either
    # is looked up as both rather than one being silently picked. The page says
    # which readings were used.
    if STEAM_64.match(q):
        pairs = [("steam", format(int(q), "x"))]
        if DISCORD.match(q):
            pairs.append(("discord", q))
        return pairs, None

    if DISCORD.match(q):
        return [("discord", q)], None

    ip = IPV4.match(q)
    if ip and all(int(part) <= 255 for part in ip.groups()):
        return [("ip", q)], None

    if HEX_TOKEN.match(q):
        return [("token", q.lower()), ("device", q.lower())], None

    return [], q


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #

def _rows_for(workspace: str, uids: list[str]) -> list[dict]:
    if not uids:
        return []
    return db.query(
        """SELECT uid, first_seen, last_seen, sessions, last_name, banned, ban_reason, banned_at
             FROM nx_identities WHERE workspace=%s AND uid = ANY(%s)""",
        (workspace, uids),
    )


def _marks_for(workspace: str, uids: list[str]) -> dict[str, list[dict]]:
    if not uids:
        return {}
    rows = db.query(
        """SELECT uid, kind, value, first_seen, last_seen, times_seen
             FROM nx_identity_marks WHERE workspace=%s AND uid = ANY(%s)
            ORDER BY kind, value""",
        (workspace, uids),
    )
    out: dict[str, list[dict]] = {}
    for row in rows:
        out.setdefault(row["uid"], []).append(row)
    return out


def _present(row: dict, marks: list[dict]) -> dict:
    """One identity as the page draws it: the card, plus the platform badges."""
    kinds: dict[str, list[str]] = {}
    for mark in marks:
        kinds.setdefault(mark["kind"], []).append(mark["value"])
    return {
        "uid": row["uid"],
        "name": row["last_name"] or "(no name)",
        "firstSeen": int(row["first_seen"]),
        "lastSeen": int(row["last_seen"]),
        "sessions": int(row["sessions"]),
        "banned": bool(row["banned"]),
        "reason": row["ban_reason"],
        "bannedAt": row["banned_at"],
        "kinds": kinds,
        "markCount": len(marks),
    }


def search(workspace: str, raw: str, page: int, size: int) -> dict:
    """Find identities by identifier or by name."""
    size = size if size in PAGE_SIZES else PAGE_SIZES[0]
    page = max(1, page)
    offset = (page - 1) * size

    pairs, name = classify(raw)

    if pairs:
        kinds = [k for k, _ in pairs]
        values = [v for _, v in pairs]
        where = (
            "uid IN (SELECT uid FROM nx_identity_marks "
            "WHERE workspace=%s AND (kind, value) IN "
            "(SELECT * FROM unnest(%s::text[], %s::text[])))"
        )
        args: tuple[Any, ...] = (workspace, kinds, values)
    elif name:
        where = "lower(last_name) LIKE %s"
        args = (f"%{name.lower()}%",)
    else:
        # No query: the most recently seen identities, which is a useful landing
        # state rather than an empty page.
        where = "TRUE"
        args = ()

    total = db.one(
        f"SELECT count(*) AS n FROM nx_identities WHERE workspace=%s AND {where}",
        (workspace, *args),
    )
    rows = db.query(
        f"""SELECT uid, first_seen, last_seen, sessions, last_name, banned, ban_reason, banned_at
              FROM nx_identities WHERE workspace=%s AND {where}
             ORDER BY last_seen DESC, uid LIMIT %s OFFSET %s""",
        (workspace, *args, size, offset),
    )

    marks = _marks_for(workspace, [r["uid"] for r in rows])
    return {
        "query": raw,
        "matched": "identifier" if pairs else ("name" if name else "recent"),
        "kinds": [k for k, _ in pairs],
        "total": int(total["n"]) if total else 0,
        "page": page,
        "size": size,
        "results": [_present(r, marks.get(r["uid"], [])) for r in rows],
    }


def detail(workspace: str, uid: str) -> dict:
    row = db.one(
        """SELECT uid, first_seen, last_seen, sessions, last_name, banned, ban_reason, banned_at
             FROM nx_identities WHERE workspace=%s AND uid=%s""",
        (workspace, uid),
    )
    require(row, 404, "No identity with that id has connected to this workspace.")
    marks = _marks_for(workspace, [uid]).get(uid, [])
    out = _present(row, marks)
    out["marks"] = [
        {
            "kind": m["kind"], "value": m["value"],
            "firstSeen": int(m["first_seen"]), "lastSeen": int(m["last_seen"]),
            "seen": int(m["times_seen"]),
        }
        for m in marks
    ]
    return out


# --------------------------------------------------------------------------- #
# Alias traversal
# --------------------------------------------------------------------------- #

def aliases(workspace: str, uid: str, depth: int = MAX_DEPTH) -> dict:
    """Every identity reachable from `uid` through shared identifiers.

    Breadth-first, one indexed round trip per level, stopping at MAX_NODES.
    Hub values are dropped before they can pull half the workspace in.
    """
    require(
        db.one("SELECT 1 AS ok FROM nx_identities WHERE workspace=%s AND uid=%s", (workspace, uid)),
        404,
        "No identity with that id has connected to this workspace.",
    )

    depth = max(1, min(depth, MAX_DEPTH))
    found: set[str] = {uid}
    frontier: list[str] = [uid]
    # (kind, value) -> set of uids carrying it, for the values we actually used
    shared: dict[tuple[str, str], set[str]] = {}
    suppressed: dict[tuple[str, str], int] = {}
    truncated = False

    for _ in range(depth):
        if not frontier or len(found) >= MAX_NODES:
            break

        # Values carried by the frontier.
        values = db.query(
            """SELECT DISTINCT kind, value FROM nx_identity_marks
                WHERE workspace=%s AND uid = ANY(%s)""",
            (workspace, frontier),
        )
        pending = [(v["kind"], v["value"]) for v in values if (v["kind"], v["value"]) not in shared
                   and (v["kind"], v["value"]) not in suppressed]
        if not pending:
            break

        # Who else carries them.
        holders = db.query(
            """SELECT kind, value, uid FROM nx_identity_marks
                WHERE workspace=%s AND (kind, value) IN
                      (SELECT * FROM unnest(%s::text[], %s::text[]))""",
            (workspace, [k for k, _ in pending], [v for _, v in pending]),
        )

        grouped: dict[tuple[str, str], set[str]] = {}
        for row in holders:
            grouped.setdefault((row["kind"], row["value"]), set()).add(row["uid"])

        nxt: set[str] = set()
        for key, uids in grouped.items():
            if len(uids) > MAX_SHARE:
                # A value this widely shared says nothing about any one pair.
                suppressed[key] = len(uids)
                continue
            if len(uids) < 2:
                continue
            shared[key] = uids
            nxt |= uids - found

        for candidate in sorted(nxt):
            if len(found) >= MAX_NODES:
                truncated = True
                break
            found.add(candidate)

        frontier = [u for u in sorted(nxt) if u in found]

    rows = _rows_for(workspace, sorted(found))
    marks = _marks_for(workspace, sorted(found))

    # Edges, with the kinds that justify each one. Only pairs that both survived
    # into the node set are emitted, so the graph never references a node the
    # caller was not given.
    edges: dict[tuple[str, str], set[str]] = {}
    for (kind, _value), uids in shared.items():
        members = sorted(u for u in uids if u in found)
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                edges.setdefault((members[i], members[j]), set()).add(kind)

    return {
        "root": uid,
        "truncated": truncated or len(found) >= MAX_NODES,
        "limit": MAX_NODES,
        "nodes": [_present(r, marks.get(r["uid"], [])) for r in rows],
        "edges": [
            {"a": a, "b": b, "kinds": sorted(kinds)} for (a, b), kinds in edges.items()
        ],
        "suppressed": [
            {"kind": k, "value": v if k != "ip" else _mask_ip(v), "holders": n}
            for (k, v), n in sorted(suppressed.items(), key=lambda kv: -kv[1])[:20]
        ],
    }


def _mask_ip(value: str) -> str:
    """A suppressed IP is shown as a /24 -- enough to recognise the hub without
    printing a specific household's address next to a list of strangers."""
    parts = value.split(".")
    return ".".join(parts[:3] + ["x"]) if len(parts) == 4 else value
