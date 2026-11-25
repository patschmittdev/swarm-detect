"""Read an ordered JSONL capture of native provider hooks without retaining the payloads."""

import json
from pathlib import Path

from .claude_hooks import review_claude_hooks
from .grok_hooks import review_grok_hooks


def _events(stream, provider: str, discriminator: str):
    seen = False
    for line_number, line in enumerate(stream, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError(f"expected one JSON hook object on line {line_number}") from None
        if not isinstance(event, dict) or not isinstance(event.get(discriminator), str) or not event[discriminator].strip():
            raise ValueError(f"line {line_number} has no native {discriminator} event name")
        # Grok emits Claude-style aliases alongside its own camel-case fields.
        if provider == "claude" and "hookEventName" in event:
            raise ValueError(f"line {line_number} uses the Grok hook format")
        if provider == "grok" and any(
            alias in event and event[alias] != event.get(native)
            for alias, native in (("hook_event_name", "hookEventName"), ("session_id", "sessionId"))
        ):
            raise ValueError(f"line {line_number} has conflicting native Grok fields")
        seen = True
        yield event
    if not seen:
        raise ValueError("the hook capture contains no events")


def review_hook_file(path: Path, provider: str, *, show_links: bool = False) -> dict:
    """Review one capture. Independent files must be reviewed separately."""
    formats = {"claude": ("hook_event_name", review_claude_hooks), "grok": ("hookEventName", review_grok_hooks)}
    if provider not in formats:
        raise ValueError("choose claude or grok for the native hook format")
    discriminator, review = formats[provider]
    links = [] if show_links else None
    try:
        with path.open(encoding="utf-8-sig") as stream:
            counts = review(_events(stream, provider, discriminator), links=links)
    except (OSError, UnicodeError):
        raise ValueError("the hook capture could not be read as a UTF-8 file") from None
    result = {"provider": provider, "counts": counts}
    if show_links:
        result["links"] = links
    return result
