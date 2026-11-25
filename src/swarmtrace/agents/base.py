import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from swarmtrace.trace.schema import TOOLS
from swarmtrace.world import ToolResult


@dataclass(frozen=True)
class Action:
    """A tool call. The recorder derives sizes and digests from content, including receives."""

    tool: str
    target: str
    args: Mapping[str, int | str] = field(default_factory=dict)
    content: str = ""
    # Optional request binding for a registered read grant. The v1 trace args stay canonical.
    grant_id: str | None = None

    def __post_init__(self) -> None:
        if self.tool not in TOOLS:
            raise ValueError("tool must be in TOOLS")
        prefix = {"scan": "h", "login": "h", "list": "h", "read": "f", "write": "f",
                  "send": "a", "recv": "a"}[self.tool]
        if re.fullmatch(prefix + r"-[0-9a-f]{8}", self.target) is None:
            raise ValueError("target must be a tool-appropriate identifier")
        keys = {"login": {"credential"}, "list": {"prefix"}}.get(self.tool, set())
        if set(self.args) != keys:
            raise ValueError(f"args must contain exactly {sorted(keys)}")
        if self.tool == "login" and (
            not isinstance(self.args["credential"], str)
            or re.fullmatch(r"c-[0-9a-f]{8}", self.args["credential"]) is None
        ):
            raise ValueError("credential must be a credential identifier")
        if self.tool == "list" and not isinstance(self.args["prefix"], str):
            raise ValueError("prefix must be a string")
        if not isinstance(self.content, str):
            raise ValueError("content must be a string")
        if self.grant_id is not None and (
            self.tool != "read" or not isinstance(self.grant_id, str) or not self.grant_id
        ):
            raise ValueError("only a read can select a nonempty grant id")
        object.__setattr__(self, "args", MappingProxyType(dict(self.args)))


@dataclass(frozen=True)
class Observation:
    tick: int
    agent: str
    hosts: tuple[str, ...]
    agents: tuple[str, ...]
    last_result: ToolResult | None


class Agent(Protocol):
    def act(self, observation: Observation) -> Action | None: ...
