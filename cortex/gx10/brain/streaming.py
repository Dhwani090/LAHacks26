# SSE event helpers — formats payloads for sse_starlette.EventSourceResponse.
# PRD §9 (SSE event order).
# Events emitted: started, transcript, brain_frame, cold_zones, suggestions, complete, error.
# Each helper returns a dict with {"event": ..., "data": <json string>}.
# See docs/PRD.md §9.

from __future__ import annotations
import json
from typing import Any


def started(mode: str, estimated_ms: int) -> dict[str, str]:
    return {"event": "started", "data": json.dumps({"mode": mode, "estimated_ms": estimated_ms})}


def transcript(words: list[dict[str, Any]]) -> dict[str, str]:
    return {"event": "transcript", "data": json.dumps({"words": words})}


def brain_frame(t: float, activation: list[float]) -> dict[str, str]:
    return {"event": "brain_frame", "data": json.dumps({"t": t, "activation": activation})}


def cold_zones(zones: list[dict[str, Any]]) -> dict[str, str]:
    return {"event": "cold_zones", "data": json.dumps({"zones": zones})}


def suggestions(items: list[dict[str, Any]]) -> dict[str, str]:
    return {"event": "suggestions", "data": json.dumps({"suggestions": items})}


def complete(payload: dict[str, Any] | None = None) -> dict[str, str]:
    return {"event": "complete", "data": json.dumps(payload or {})}


def error(message: str) -> dict[str, str]:
    return {"event": "error", "data": json.dumps({"message": message})}
