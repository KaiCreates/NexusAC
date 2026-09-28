"""Server-only Cloudflare Realtime SFU adapter.

The browser/NUI owns RTCPeerConnection and sends SDP through application
signaling endpoints. This module is the only place that speaks to Cloudflare;
the App Secret must never be returned to a caller or written to logs.
"""
from __future__ import annotations

from typing import Any

import httpx

from . import config

_BASE = "https://rtc.live.cloudflare.com/v1"
_TIMEOUT = httpx.Timeout(10.0, connect=4.0)


class SfuUnavailable(RuntimeError):
    """SFU credentials are not configured on this website deployment."""


class SfuError(RuntimeError):
    """The provider rejected or failed a signaling operation."""


def configured() -> bool:
    return bool(config.CLOUDFLARE_REALTIME_APP_ID and
                config.CLOUDFLARE_REALTIME_APP_SECRET)


class CloudflareSfu:
    """Small async API client; deliberately contains no browser-facing secret."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        if not configured():
            raise SfuUnavailable("WebRTC streaming is not configured on the website.")
        self._client = client
        self._owns_client = client is None
        self._root = f"{_BASE}/apps/{config.CLOUDFLARE_REALTIME_APP_ID}"
        self._headers = {
            "Authorization": f"Bearer {config.CLOUDFLARE_REALTIME_APP_SECRET}",
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("POST", path, body)

    async def _put(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", path, body)

    async def _request(self, method: str, path: str,
                       body: dict[str, Any] | None = None) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=_TIMEOUT)
        try:
            response = await client.request(
                method, f"{self._root}/{path.lstrip('/')}",
                headers=self._headers, json=body,
            )
            data = response.json()
            if response.is_error or not isinstance(data, dict) or data.get("errorCode"):
                # Provider bodies may include request details; do not log SDP,
                # credentials, or raw response contents.
                raise SfuError("Cloudflare Realtime signaling request failed.")
            return data
        except (httpx.HTTPError, ValueError) as exc:
            raise SfuError("Cloudflare Realtime is temporarily unavailable.") from exc
        finally:
            if self._owns_client:
                await client.aclose()

    async def create_session(self) -> str:
        result = await self._post("sessions/new")
        session_id = result.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise SfuError("Cloudflare did not return a session identifier.")
        return session_id

    async def publish_video(self, session_id: str, offer: dict[str, str], mid: str,
                            track_name: str) -> dict[str, Any]:
        if offer.get("type") != "offer" or not offer.get("sdp"):
            raise ValueError("A complete WebRTC offer is required.")
        result = await self._post(
            f"sessions/{session_id}/tracks/new",
            {"sessionDescription": offer,
             "tracks": [{"location": "local", "mid": mid,
                         "trackName": track_name}]},
        )
        description = result.get("sessionDescription")
        if not isinstance(description, dict) or description.get("type") != "answer":
            raise SfuError("Cloudflare returned an invalid publisher answer.")
        return {"sessionDescription": description}

    async def subscribe_video(self, publisher_session: str,
                              track_name: str = "screen") -> dict[str, Any]:
        session_id = await self.create_session()
        result = await self._post(
            f"sessions/{session_id}/tracks/new",
            {"tracks": [{"location": "remote", "sessionId": publisher_session,
                         "trackName": track_name}]},
        )
        description = result.get("sessionDescription")
        if not isinstance(description, dict) or description.get("type") != "offer":
            raise SfuError("Cloudflare returned an invalid subscriber offer.")
        return {"sessionId": session_id, "sessionDescription": description,
                "tracks": result.get("tracks", [])}

    async def answer_subscription(self, session_id: str,
                                  answer: dict[str, str]) -> dict[str, Any]:
        if answer.get("type") != "answer" or not answer.get("sdp"):
            raise ValueError("A complete WebRTC answer is required.")
        return await self._put(f"sessions/{session_id}/renegotiate",
                               {"sessionDescription": answer})

    async def close(self, session_id: str, tracks: list[dict[str, str]]) -> dict[str, Any]:
        if not tracks:
            return {"ok": True}
        return await self._put(f"sessions/{session_id}/tracks/close", {"tracks": tracks})
