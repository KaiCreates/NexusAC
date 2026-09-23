"""The punishment record: bans, kicks, warnings and reversals.

Simpler than the event log on purpose. Events needed a query language because
their payloads are free-form; a punishment has a fixed shape, so filters on
kind, actor and player cover it and there is nothing to parse.
"""
from __future__ import annotations

from typing import Any

from . import db
from .security import now

PAGE_SIZES = (25, 50, 100)
KINDS = ("ban", "kick", "warn", "unban", "unwarn")
RANGES = {"24h": 86400, "7d": 604800, "30d": 2592000, "90d": 7776000, "all": 0}


def _row(record: dict) -> dict:
    return {
        "id": int(record["id"]),
        "at": int(record["at"]),
        "kind": record["kind"],
        "identifier": record["identifier"],
        "name": record["name"] or "Unknown",
        "reason": record["reason"],
        "by": record["by_actor"] or "NexusAC",
        "auto": bool(record["auto"]),
        "days": record["days"],
        "detector": record["detector"],
        "evidence": record["evidence"],
    }


def search(
    workspace: str,
    query: str,
    kind: str | None,
    window: str,
    actor: str | None,
    page: int,
    size: int,
) -> dict:
    size = size if size in PAGE_SIZES else PAGE_SIZES[0]
    page = max(1, page)

    where = ["workspace = %s"]
    params: list[Any] = [workspace]

    if kind and kind in KINDS:
        where.append("kind = %s")
        params.append(kind)

    if actor == "auto":
        where.append("auto = true")
    elif actor == "staff":
        where.append("auto = false")

    seconds = RANGES.get(window, 0)
    if seconds:
        where.append("at >= %s")
        params.append(now() - seconds)

    text = (query or "").strip()
    if text:
        # One box for the three things anybody pastes in: a player name, an
        # identifier, or the name of the staff member who did it.
        like = f"%{text.lower()}%"
        where.append(
            "(lower(coalesce(name,'')) LIKE %s OR lower(coalesce(identifier,'')) LIKE %s "
            " OR lower(coalesce(by_actor,'')) LIKE %s OR lower(coalesce(reason,'')) LIKE %s)"
        )
        params.extend([like, like, like, like])

    clause = " AND ".join(where)

    counted = db.one(
        f"SELECT count(*) AS n FROM nx_punishments WHERE {clause}", params
    )
    rows = db.query(
        f"""SELECT id, at, kind, identifier, name, reason, by_actor, auto, days,
                   detector, evidence
              FROM nx_punishments WHERE {clause}
             ORDER BY at DESC, id DESC LIMIT %s OFFSET %s""",
        (*params, size, (page - 1) * size),
    )

    return {
        "query": query,
        "total": int(counted["n"]) if counted else 0,
        "page": page,
        "size": size,
        "rows": [_row(r) for r in rows],
    }


def summary(workspace: str) -> dict:
    """Counts by kind over the last 30 days, for the header tiles."""
    rows = db.query(
        """SELECT kind, count(*) AS n FROM nx_punishments
            WHERE workspace=%s AND at >= %s GROUP BY kind""",
        (workspace, now() - 2592000),
    )
    counts = {r["kind"]: int(r["n"]) for r in rows}

    staff = db.one(
        """SELECT count(*) FILTER (WHERE auto) AS automatic,
                  count(*) FILTER (WHERE NOT auto) AS by_staff
             FROM nx_punishments WHERE workspace=%s AND at >= %s""",
        (workspace, now() - 2592000),
    )

    return {
        "window": "30d",
        "counts": {k: counts.get(k, 0) for k in KINDS},
        "automatic": int((staff or {}).get("automatic") or 0),
        "byStaff": int((staff or {}).get("by_staff") or 0),
    }


def for_identity(workspace: str, identifier: str, limit: int = 50) -> list[dict]:
    """Everything on file for one account. Used by the Identities drawer."""
    rows = db.query(
        """SELECT id, at, kind, identifier, name, reason, by_actor, auto, days,
                  detector, evidence
             FROM nx_punishments WHERE workspace=%s AND identifier=%s
            ORDER BY at DESC LIMIT %s""",
        (workspace, identifier, min(limit, 200)),
    )
    return [_row(r) for r in rows]
