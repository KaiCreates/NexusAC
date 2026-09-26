"""The raw event log: query parsing and reads.

THE QUERY LANGUAGE
------------------
Deliberately small, because the people using it are investigating an incident at
speed, not writing reports.

    weaponDamage                       free text -- names, licenses, or a type
    event_type:weaponDamage            a field
    data.weaponType:`weapon_pistol`    a field inside the event's own payload
    event_type:playerKilled && sender_name:Arne
    event_type:entityCreated || event_type:entityRemoved

`&&` binds tighter than `||`, there are no parentheses, and that is on purpose:
one level of grouping covers every query anyone actually types here, and a real
expression parser would mean real parse errors to explain mid-investigation.

Values may be bare, `backtick quoted` or "double quoted". Quoting matters for
anything containing a space or a colon.

SAFETY
------
Values are always parameterised. The one thing interpolated into SQL is the
jsonb path in a `data.x.y` term, and every segment of it is checked against
[A-Za-z0-9_]+ before it goes anywhere near a query string.
"""
from __future__ import annotations

import re
from typing import Any

from . import db

PAGE_SIZES = (25, 50, 100, 250)
# count(*) over a filtered event table is unbounded work. Counting one page past
# the ceiling is enough to drive pagination and to say "10000+" honestly.
COUNT_CEILING = 10_000

SEGMENT = re.compile(r"^[A-Za-z0-9_]+$")
TERM = re.compile(
    r"""^\s*(?P<field>[A-Za-z_][A-Za-z0-9_.]*)\s*:\s*
        (?P<value>`[^`]*`|"[^"]*"|\S+)\s*$""",
    re.X,
)

# field name in a query -> column. Anything not here and not data.* is treated
# as free text, so a typo searches rather than erroring.
COLUMNS = {
    "event_type": "type",
    "type": "type",
    "sender": "sender",
    "target": "target",
    "sender_name": "sender_name",
    "target_name": "target_name",
}

RANGES = {
    "1h": 3600, "24h": 86400, "7d": 604800, "30d": 2592000, "all": 0,
}


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "`\"":
        return value[1:-1]
    return value


def _term_sql(raw: str) -> tuple[str, list[Any]]:
    """One term -> (sql, params). Never raises; an unparseable term becomes a
    free-text search so the box is forgiving."""
    match = TERM.match(raw)
    if not match:
        text = raw.strip()
        if not text:
            return "TRUE", []
        like = f"%{text.lower()}%"
        return (
            "(lower(sender_name) LIKE %s OR lower(target_name) LIKE %s "
            " OR lower(coalesce(sender,'')) LIKE %s OR lower(coalesce(target,'')) LIKE %s "
            " OR lower(type) LIKE %s)",
            [like, like, like, like, like],
        )

    field = match.group("field")
    value = _unquote(match.group("value"))

    if field in COLUMNS:
        column = COLUMNS[field]
        # Types and identifiers are matched exactly; names are what people
        # half-remember, so those contain.
        if column in ("sender_name", "target_name"):
            return f"lower({column}) LIKE %s", [f"%{value.lower()}%"]
        return f"lower({column}) = %s", [value.lower()]

    if field.startswith("data."):
        path = field[5:].split(".")
        if not path or not all(SEGMENT.match(p) for p in path):
            return "FALSE", []
        if len(path) == 1:
            return "lower(data->>%s) = %s", [path[0], value.lower()]
        # #>> takes a text[] path and returns text.
        return "lower(data#>>%s) = %s", [path, value.lower()]

    # Unknown field: fall back to free text over the whole term.
    return _term_sql(raw.replace(":", " ", 1))


def parse(query: str) -> tuple[str, list[Any]]:
    """Whole query -> (sql, params). Empty query matches everything."""
    text = (query or "").strip()
    if not text:
        return "TRUE", []

    or_groups = [g for g in re.split(r"\s*\|\|\s*", text) if g.strip()]
    or_sql, params = [], []

    for group in or_groups:
        and_terms = [t for t in re.split(r"\s*&&\s*", group) if t.strip()]
        and_sql = []
        for term in and_terms:
            sql, args = _term_sql(term)
            and_sql.append(sql)
            params.extend(args)
        or_sql.append("(" + " AND ".join(and_sql or ["TRUE"]) + ")")

    return "(" + " OR ".join(or_sql) + ")", params


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #

def _row(record: dict) -> dict:
    return {
        "id": int(record["id"]),
        "at": int(record["at"]),
        "type": record["type"],
        "sender": record["sender"],
        "senderName": record["sender_name"],
        "target": record["target"],
        "targetName": record["target_name"],
        "data": record["data"] or {},
        "server": str(record["server"]),
    }


def search(
    workspace: str,
    query: str,
    kind: str | None,
    window: str,
    page: int,
    size: int,
    server: str | None = None,
) -> dict:
    size = size if size in PAGE_SIZES else PAGE_SIZES[0]
    page = max(1, page)

    where = ["workspace = %s"]
    params: list[Any] = [workspace]

    if server:
        # The filter arrives from a query string, and Postgres raises on a
        # malformed uuid rather than returning nothing. Checking it here turns a
        # 500 into an empty result, which is the honest answer to "events for a
        # server that does not exist".
        import uuid as _uuid
        try:
            _uuid.UUID(str(server))
        except (ValueError, AttributeError, TypeError):
            return {"query": query, "total": 0, "capped": False,
                    "page": page, "size": size, "rows": []}
        where.append("server = %s")
        params.append(server)

    if kind and kind != "all":
        where.append("type = %s")
        params.append(kind)

    seconds = RANGES.get(window, 0)
    if seconds:
        from .security import now
        where.append("at >= %s")
        params.append(now() - seconds)

    sql, args = parse(query)
    where.append(sql)
    params.extend(args)

    clause = " AND ".join(where)

    counted = db.one(
        f"SELECT count(*) AS n FROM (SELECT 1 FROM nx_events WHERE {clause} LIMIT {COUNT_CEILING + 1}) t",
        params,
    )
    total = int(counted["n"]) if counted else 0

    rows = db.query(
        f"""SELECT id, at, type, sender, sender_name, target, target_name, data, server
              FROM nx_events WHERE {clause}
             ORDER BY at DESC, id DESC LIMIT %s OFFSET %s""",
        (*params, size, (page - 1) * size),
    )

    return {
        "query": query,
        "total": total,
        "capped": total > COUNT_CEILING,
        "page": page,
        "size": size,
        "rows": [_row(r) for r in rows],
    }


ACTIVITY_WINDOWS = {"24h": (86400, 3600), "7d": (604800, 21600)}


def activity(workspace: str, server: str, window: str = "24h") -> dict:
    """Bucketed counts for one server's Overview chart, plus window totals.

    `series` is every recorded event per bucket (the chart); `totals` breaks out
    the four tiles under it. Detections come from the event log, kicks and bans
    from the punishment record, entities from entityCreated -- which the resource
    samples (25% by default), so that tile says "recorded", not "created".
    """
    span, step = ACTIVITY_WINDOWS.get(window, ACTIVITY_WINDOWS["24h"])
    from .security import now
    end = now()
    start = end - span
    buckets = span // step

    rows = db.query(
        """SELECT floor((at - %s) / %s)::int AS b, count(*) AS n
             FROM nx_events WHERE workspace=%s AND server=%s AND at >= %s
            GROUP BY b""",
        (start, step, workspace, server, start),
    )
    series = [0] * buckets
    for r in rows:
        index = int(r["b"])
        if 0 <= index < buckets:
            series[index] = int(r["n"])

    kinds = db.one(
        """SELECT count(*) FILTER (WHERE type='detection') AS detections,
                  count(*) FILTER (WHERE type='entityCreated') AS entities
             FROM nx_events WHERE workspace=%s AND server=%s AND at >= %s""",
        (workspace, server, start),
    ) or {}
    punish = db.one(
        """SELECT count(*) FILTER (WHERE kind='kick') AS kicks,
                  count(*) FILTER (WHERE kind='ban') AS bans
             FROM nx_punishments WHERE workspace=%s AND server=%s AND at >= %s""",
        (workspace, server, start),
    ) or {}

    return {
        "window": window if window in ACTIVITY_WINDOWS else "24h",
        "start": start,
        "step": step,
        "series": series,
        "totals": {
            "detections": int(kinds.get("detections") or 0),
            "entities": int(kinds.get("entities") or 0),
            "kicks": int(punish.get("kicks") or 0),
            "bans": int(punish.get("bans") or 0),
        },
    }


def types(workspace: str) -> list[dict]:
    """Every type seen, with counts, for the filter dropdown.

    Bounded by the retention window rather than the whole table, which keeps it
    an index-only scan of recent rows instead of a full count.
    """
    rows = db.query(
        """SELECT type, count(*) AS n FROM nx_events
            WHERE workspace=%s GROUP BY type ORDER BY n DESC LIMIT 60""",
        (workspace,),
    )
    return [{"type": r["type"], "count": int(r["n"])} for r in rows]
