from dataclasses import dataclass

import numpy as np

from .base import Action, Observation


@dataclass(frozen=True)
class Workspace:
    """An assigned workspace, containing identifiers rather than live world objects."""

    host: str
    credential: str
    source: str
    output: str
    shared_host: str
    mistake_host: str | None = None
    mistake_file: str | None = None


class MaintenanceAgent:
    """Maintain a private workspace and inspect the common work area between jobs.

    Activity draws are independent of work state, including waits and failures.
    """

    def __init__(
        self, workspace: Workspace, mode: str, *, activity_rate: float = 0.75,
        activity_seed: int = 0,
        mistake_rate: float = 0.02, mistake_seed: int = 0,
    ) -> None:
        if mode not in ("patrol", "backup", "audit"):
            raise ValueError("unknown maintenance mode")
        if not 0.0 <= activity_rate <= 1.0:
            raise ValueError("activity_rate must be between 0 and 1")
        if type(activity_seed) is not int or activity_seed < 0:
            raise ValueError("activity_seed must be a non-negative integer")
        if not 0.0 <= mistake_rate <= 1.0:
            raise ValueError("mistake_rate must be between 0 and 1")
        if type(mistake_seed) is not int or mistake_seed < 0:
            raise ValueError("mistake_seed must be a non-negative integer")
        self.workspace = workspace
        self.activity_rate = activity_rate
        activity_stream = np.random.SeedSequence(activity_seed).spawn(1)[0]
        self._activity_rng = np.random.default_rng(activity_stream)
        self.mistake_rate = mistake_rate
        self._mistake_rng = np.random.default_rng(np.random.SeedSequence(mistake_seed).spawn(1)[0])
        self._mode = mode
        self._logged_in = False
        self._pending: str | None = None
        self._backup_content: str | None = None
        self._visits = 0

    def _emit(self, action: Action, pending: str) -> Action:
        self._pending = pending
        return action

    def _active(self) -> bool:
        return bool(self._activity_rng.random() < self.activity_rate)

    def _mistake(self) -> Action | None:
        if self._mistake_rng.random() >= self.mistake_rate:
            return None
        if self.workspace.mistake_host is None or self.workspace.mistake_file is None:
            return None
        if int(self._mistake_rng.integers(2)):
            action = Action("login", self.workspace.mistake_host,
                            {"credential": self.workspace.credential})
        else:
            action = Action("read", self.workspace.mistake_file)
        return self._emit(action, "mistake")

    def _observe(self, observation: Observation) -> None:
        pending, self._pending = self._pending, None
        result = observation.last_result
        if pending is None or result is None or result.status != "ok":
            return
        if pending == "login":
            self._logged_in = True
        elif pending == "backup_read":
            self._backup_content = result.content
        elif pending == "backup_write":
            self._backup_content = None

    def _login(self) -> Action:
        return self._emit(Action("login", self.workspace.host,
                                 {"credential": self.workspace.credential}), "login")

    def _maintenance(self) -> Action:
        self._visits += 1
        host = self.workspace.host if self._visits % 2 else self.workspace.shared_host
        if self._mode == "patrol":
            return self._emit(Action("scan", host), "maintenance")
        if self._mode == "audit":
            return self._emit(Action("list", host, {"prefix": "/data/"}), "maintenance")
        if self._backup_content is None:
            return self._emit(Action("read", self.workspace.source), "backup_read")
        return self._emit(Action("write", self.workspace.output, content=self._backup_content),
                          "backup_write")

    def act(self, observation: Observation) -> Action | None:
        self._observe(observation)
        if not self._active():
            return None
        mistake = self._mistake()
        if mistake is not None:
            return mistake
        if not self._logged_in:
            return self._login()
        return self._maintenance()


class PatrolAgent(MaintenanceAgent):
    def __init__(
        self, workspace: Workspace, *, activity_rate: float = 0.75, activity_seed: int = 0,
        mistake_rate: float = 0.02, mistake_seed: int = 0,
    ) -> None:
        super().__init__(workspace, "patrol",
                         activity_rate=activity_rate, activity_seed=activity_seed,
                         mistake_rate=mistake_rate, mistake_seed=mistake_seed)


class BackupAgent(MaintenanceAgent):
    def __init__(
        self, workspace: Workspace, *, activity_rate: float = 0.75, activity_seed: int = 0,
        mistake_rate: float = 0.02, mistake_seed: int = 0,
    ) -> None:
        super().__init__(workspace, "backup",
                         activity_rate=activity_rate, activity_seed=activity_seed,
                         mistake_rate=mistake_rate, mistake_seed=mistake_seed)


class AuditAgent(MaintenanceAgent):
    def __init__(
        self, workspace: Workspace, *, activity_rate: float = 0.75, activity_seed: int = 0,
        mistake_rate: float = 0.02, mistake_seed: int = 0,
    ) -> None:
        super().__init__(workspace, "audit",
                         activity_rate=activity_rate, activity_seed=activity_seed,
                         mistake_rate=mistake_rate, mistake_seed=mistake_seed)
