"""Why players left: the Disconnects page.

Every drop reaches nx_events as a `playerDropped` row. The game server's
reason text is the only thing older rows carry; rows recorded since the
resource's departure snapshot (server/sv_events.lua) also carry what was true
at that moment -- time in city, position, health, vehicle, ping, recent
detections, and whether NexusAC itself kicked or banned them.

Classification happens here, not in the resource, so every row -- old or new
-- is read the same way, and improving a pattern re-reads history for free.

Three views on top of the rows:
  * crash signatures   the same crash text across several players is a bug or
                       an attack; one player's odd crash is usually their PC
  * mass disconnects   several players leaving inside CLUSTER_SECONDS. Crashes
                       and timeouts clustered NEAR EACH OTHER are the shape of
                       a crash attack; a server restart looks like one too,
                       which is why it is labelled separately
  * repeat crashers    one player crashing again and again
"""
from __future__ import annotations

import math
import re
from typing import Any

from . import db

WINDOWS = {"1h": 3600, "24h": 86400, "7d": 7 * 86400}
MAX_ROWS = 2000
CLUSTER_SECONDS = 20
CLUSTER_MIN = 3
NEAR_METRES = 250.0

CATEGORIES = {
    "crash":    "Crashed",
    "timeout":  "Timed out",
    "network":  "Network error",
    "quit":     "Quit",
    "kick":     "Kicked",
    "ban":      "Banned",
    "server":   "Server restart / stop",
    "resource": "Download / resource error",
    "other":    "Other",
}

# Order matters: the first match wins.
_RULES: list[tuple[str, re.Pattern]] = [
    ("ban",      re.compile(r"\bbann?ed\b|ban id|ban-id|\bNX-B-", re.I)),
    ("crash",    re.compile(r"crash|unhandled exception|\.exe\s*[+!]|\.dll\s*[+!]|\bERR_[A-Z_]+|access violation", re.I)),
    ("timeout",  re.compile(r"timed out|time[- ]?out", re.I)),
    ("network",  re.compile(r"overflow|reliable (network|state)|packet|connection (was )?(lost|closed|reset)|enet", re.I)),
    ("server",   re.compile(r"server (is )?(shutting down|restarting|closed|stopp)|scheduled restart|txadmin.*restart", re.I)),
    ("kick",     re.compile(r"kick|dropped by|removed from the server|\[txadmin\]", re.I)),
    ("resource", re.compile(r"download|failed to (load|verify|fetch)|could(n't| not) load|resource .* (failed|error)|missing (asset|file)", re.I)),
    ("quit",     re.compile(r"^\s*(exiting|exited|quit|disconnected|left)\b|disconnected by (user|client)|client quit", re.I)),
]

_SIG = re.compile(r"(?:game crashed:?\s*)?(.+)", re.I)


def classify(reason: str, data: dict | None = None) -> dict:
    """category, label, who ('nexus'/'txadmin'/None), and a crash signature."""
    data = data or {}
    text = (reason or "").strip()
    who = None

    if data.get("by") == "nexus":
        category = "ban" if data.get("action") == "ban" else "kick"
        who = "nexus"
    else:
        category = "other"
        for name, pattern in _RULES:
            if pattern.search(text):
                category = name
                break
        if category in ("kick", "ban", "server") and "txadmin" in text.lower():
            who = "txadmin"

    signature = None
    if category == "crash":
        m = _SIG.match(text)
        # Keep the part that identifies WHERE it crashed; drop any trailing
        # free text so the same crash groups together.
        signature = (m.group(1) if m else text).strip()
        signature = re.split(r"\s{2,}|\n", signature)[0][:120]

    return {"category": category, "label": CATEGORIES[category], "by": who, "signature": signature}


def _distance(a: dict, b: dict) -> float | None:
    try:
        return math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))
    except (KeyError, TypeError, ValueError):
        return None


def _clusters(rows: list[dict]) -> list[dict]:
    """Groups of CLUSTER_MIN+ disconnects inside CLUSTER_SECONDS of each other."""
    ordered = sorted(rows, key=lambda r: r["at"])
    out, current = [], []
    for row in ordered:
        if current and row["at"] - current[0]["at"] > CLUSTER_SECONDS:
            if len(current) >= CLUSTER_MIN:
                out.append(current)
            current = []
        current.append(row)
    if len(current) >= CLUSTER_MIN:
        out.append(current)

    result = []
    for group in out:
        cats: dict[str, int] = {}
        for r in group:
            cats[r["category"]] = cats.get(r["category"], 0) + 1
        bad = cats.get("crash", 0) + cats.get("timeout", 0) + cats.get("network", 0)
        placed = [r for r in group if r["data"].get("x") is not None]
        near = False
        if len(placed) >= 2:
            spread = max((_distance(a, b) or 0.0) for a in placed for b in placed)
            near = spread <= NEAR_METRES
        if cats.get("server", 0) >= len(group) / 2:
            verdict = "server restart"
        elif bad >= CLUSTER_MIN and near:
            verdict = "possible crash attack"
        elif bad >= CLUSTER_MIN:
            verdict = "mass crash / timeout"
        else:
            verdict = "busy moment"
        result.append({
            "start": group[0]["at"], "end": group[-1]["at"], "count": len(group),
            "categories": cats, "near": near, "verdict": verdict,
            "players": [r["senderName"] or r["sender"] or "?" for r in group][:12],
        })
    result.sort(key=lambda c: c["start"], reverse=True)
    return result[:10]


def summary(workspace: str, server: str, window: str = "24h") -> dict:
    from .security import now
    span = WINDOWS.get(window, WINDOWS["24h"])
    end = now()
    records = db.query(
        """SELECT id, at, sender, sender_name, data FROM nx_events
            WHERE workspace=%s AND server=%s AND type='playerDropped' AND at >= %s
            ORDER BY at DESC, id DESC LIMIT %s""",
        (workspace, server, end - span, MAX_ROWS),
    )

    rows: list[dict] = []
    totals = {k: 0 for k in CATEGORIES}
    signatures: dict[str, dict] = {}
    crashers: dict[str, dict] = {}

    for rec in records:
        data = rec["data"] or {}
        c = classify(str(data.get("reason") or ""), data)
        row = {
            "id": int(rec["id"]), "at": int(rec["at"]),
            "sender": rec["sender"], "senderName": rec["sender_name"],
            "data": data, **c,
        }
        rows.append(row)
        totals[c["category"]] += 1

        if c["signature"]:
            sig = signatures.setdefault(c["signature"], {"signature": c["signature"], "count": 0, "players": set(), "last": 0})
            sig["count"] += 1
            sig["players"].add(rec["sender_name"] or rec["sender"] or "?")
            sig["last"] = max(sig["last"], int(rec["at"]))

        if c["category"] in ("crash", "timeout"):
            key = rec["sender"] or rec["sender_name"] or "?"
            p = crashers.setdefault(key, {"sender": rec["sender"], "name": rec["sender_name"], "count": 0, "last": 0})
            p["count"] += 1
            p["last"] = max(p["last"], int(rec["at"]))

    sig_list = sorted(
        ({**s, "players": sorted(s["players"])[:10], "playerCount": len(s["players"])} for s in signatures.values()),
        key=lambda s: (s["playerCount"], s["count"]), reverse=True)[:15]
    repeaters = sorted((p for p in crashers.values() if p["count"] >= 3),
                       key=lambda p: p["count"], reverse=True)[:10]

    return {
        "window": window if window in WINDOWS else "24h",
        "total": len(rows),
        "truncated": len(rows) >= MAX_ROWS,
        "totals": totals,
        "labels": CATEGORIES,
        "rows": rows[:300],
        "signatures": sig_list,
        "clusters": _clusters(rows),
        "repeaters": repeaters,
    }
