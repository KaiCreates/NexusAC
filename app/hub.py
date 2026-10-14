"""The live link to each game server, entirely in memory.

The game server keeps ONE request open (POST /api/bridge). It carries the
answers to the previous jobs up, and is held here until there is new work or
HOLD_SECONDS pass. A browser request becomes a job, is handed to that waiting
request at once, and the browser's call returns the moment the answer comes
back on the game server's next request -- typically a few hundred ms.

Identical section requests that are already in flight are merged, so ten staff
watching the same page cost the game server one answer, not ten.
"""
import asyncio
import json
import secrets
import time

HOLD_SECONDS = 20.0
ANSWER_TIMEOUT = 15.0
OFFLINE_AFTER = HOLD_SECONDS + 15.0


class Link:
    def __init__(self) -> None:
        self.jobs: list[dict] = []
        self.wake = asyncio.Event()
        self.pending: dict[str, asyncio.Future] = {}
        self.merged: dict[str, str] = {}  # merge key -> job id in flight
        self.last_seen = 0.0
        self.info: dict = {}

    @property
    def online(self) -> bool:
        return time.monotonic() - self.last_seen < OFFLINE_AFTER


links: dict[str, Link] = {}


def link(server_id: str) -> Link:
    lk = links.get(server_id)
    if lk is None:
        lk = links[server_id] = Link()
    return lk


async def ask(server_id: str, job: dict) -> dict:
    """Send one job to the game server and wait for its answer."""
    lk = link(server_id)
    if not lk.online:
        return {"ok": False, "offline": True, "msg": "The game server is not connected to the website."}

    merge = None
    if job["kind"] in ("section", "open"):
        merge = json.dumps([job["kind"], job.get("section"), job.get("arg"), job["role"]], sort_keys=True, default=str)
        same = lk.merged.get(merge)
        if same and same in lk.pending:
            return await _wait(lk, same)

    job_id = secrets.token_hex(8)
    job["id"] = job_id
    lk.pending[job_id] = asyncio.get_running_loop().create_future()
    if merge:
        lk.merged[merge] = job_id
    lk.jobs.append(job)
    lk.wake.set()
    try:
        return await _wait(lk, job_id)
    finally:
        lk.pending.pop(job_id, None)
        if merge and lk.merged.get(merge) == job_id:
            del lk.merged[merge]


async def _wait(lk: Link, job_id: str) -> dict:
    fut = lk.pending.get(job_id)
    if fut is None:
        return {"ok": False, "msg": "That request expired."}
    try:
        return await asyncio.wait_for(asyncio.shield(fut), ANSWER_TIMEOUT)
    except asyncio.TimeoutError:
        return {"ok": False, "msg": "The game server did not answer in time."}


async def bridge(server_id: str, body: dict) -> list[dict]:
    """One game-server request: take its answers, hold until there are jobs."""
    lk = link(server_id)
    lk.last_seen = time.monotonic()
    lk.info = {k: body.get(k) for k in ("server", "version", "players", "mode")}
    for reply in body.get("replies") or []:
        if isinstance(reply, dict):
            fut = lk.pending.get(str(reply.get("id")))
            if fut and not fut.done():
                fut.set_result(reply)
    if not lk.jobs:
        lk.wake.clear()
        try:
            await asyncio.wait_for(lk.wake.wait(), HOLD_SECONDS)
        except asyncio.TimeoutError:
            pass
    lk.last_seen = time.monotonic()
    jobs, lk.jobs = lk.jobs, []
    return jobs
