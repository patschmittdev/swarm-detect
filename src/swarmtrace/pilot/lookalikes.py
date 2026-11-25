"""Scripted clients whose traffic resembles coordinated agents without being one.

Each client takes a base URL, a numpy Generator and a stop time on the `time.monotonic()` clock,
and returns the number of requests it made. Rates are parameters; all clients check the stop time
before every request and between pauses, so they end within one request of it.
"""

import json
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np

from swarmtrace.pilot.service import COLLECTIONS, DOCS_PER_COLLECTION

USER_AGENT = "docstore-client/1.0"
USER_AGENTS = (USER_AGENT, *(f"{USER_AGENT} {kind}"
                             for kind in ("fleet", "crawler", "retry", "sessions", "browser")))


class _Client:
    def __init__(self, base_url: str, user_agent: str = USER_AGENT):
        self.base_url, self.user_agent, self.token, self.count = base_url, user_agent, None, 0

    def call(self, method: str, path: str, body: bytes | None = None):
        headers = {"User-Agent": self.user_agent}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(self.base_url + path, data=body, method=method, headers=headers)
        self.count += 1
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read() or b"null")
        except HTTPError as error:
            error.read()
            return error.code, None
        except (URLError, OSError, ValueError):
            return None, None

    def login(self) -> None:
        self.token = None
        status, payload = self.call("POST", "/session")
        self.token = payload["token"] if status == 200 else None


def _sleep_until(deadline: float, stop_at: float) -> bool:
    """Sleep until deadline; False if the stop time comes first."""
    while True:
        now = time.monotonic()
        if now >= stop_at:
            return False
        if now >= deadline:
            return True
        time.sleep(min(0.05, min(deadline, stop_at) - now))


def _all_doc_ids() -> list[str]:
    return [f"{c}-{i + 1:02d}" for c in COLLECTIONS for i in range(DOCS_PER_COLLECTION)]


def scheduled_fleet(base_url: str, rng: np.random.Generator, stop_at: float, fleet: int = 4,
                    period: float = 5.0, docs: int = 3, skew: float = 0.05) -> int:
    """`fleet` independent tokens fetch the same documents at each tick of a shared schedule."""
    ids = _all_doc_ids()
    chosen = [ids[int(k)] for k in rng.choice(len(ids), size=docs, replace=False)]
    offsets = rng.uniform(0, skew, size=fleet)
    start = time.monotonic()
    counts = [0] * fleet

    def member(k: int) -> None:
        client = _Client(base_url, f"{USER_AGENT} fleet")
        tick = 0
        while _sleep_until(start + tick * period + offsets[k], stop_at):
            if client.token is None:
                client.login()
            for doc_id in chosen:
                if time.monotonic() >= stop_at:
                    break
                client.call("GET", f"/docs/{doc_id}")
            tick += 1
        counts[k] = client.count

    threads = [threading.Thread(target=member, args=(k,), daemon=True) for k in range(fleet)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sum(counts)


def crawler(base_url: str, rng: np.random.Generator, stop_at: float, delay: float = 0.2) -> int:
    """One token walking every collection and document in order, then starting over."""
    client = _Client(base_url, f"{USER_AGENT} crawler")
    client.login()
    while time.monotonic() < stop_at:
        for collection in COLLECTIONS:
            if not _sleep_until(time.monotonic() + delay, stop_at):
                return client.count
            status, payload = client.call("GET", f"/collections/{collection}")
            for doc in (payload or {}).get("documents", []):
                if not _sleep_until(time.monotonic() + delay * rng.uniform(0.8, 1.2), stop_at):
                    return client.count
                client.call("GET", f"/docs/{doc['id']}")
    return client.count


def retry_storm(base_url: str, rng: np.random.Generator, stop_at: float, burst: int = 5,
                base_delay: float = 0.05, max_delay: float = 2.0, rest: float = 3.0) -> int:
    """One token repeating a failing request in bursts, doubling its backoff each retry."""
    client = _Client(base_url, f"{USER_AGENT} retry")
    client.login()
    target = f"/docs/archived-{int(rng.integers(100, 999))}"
    while time.monotonic() < stop_at:
        delay = base_delay
        for _ in range(burst):
            if time.monotonic() >= stop_at:
                break
            client.call("GET", target)
            if not _sleep_until(time.monotonic() + delay, stop_at):
                break
            delay = min(delay * 2, max_delay)
        if not _sleep_until(time.monotonic() + rest * rng.uniform(0.5, 1.5), stop_at):
            break
    return client.count


def many_sessions(base_url: str, rng: np.random.Generator, stop_at: float,
                  per_session: int = 3, delay: float = 0.3) -> int:
    """One client that opens a new session every few requests."""
    client = _Client(base_url, f"{USER_AGENT} sessions")
    ids = _all_doc_ids()
    while time.monotonic() < stop_at:
        client.login()
        for _ in range(per_session):
            if not _sleep_until(time.monotonic() + delay * rng.uniform(0.5, 1.5), stop_at):
                return client.count
            client.call("GET", f"/docs/{ids[int(rng.integers(len(ids)))]}")
    return client.count


def browsing_users(base_url: str, rng: np.random.Generator, stop_at: float, users: int = 3,
                   reads: int = 4, pause: float = 4.0) -> int:
    """`users` independent tokens each reading a few documents with long, irregular pauses."""
    ids = _all_doc_ids()
    seeds = rng.integers(0, 2**31, size=users)
    counts = [0] * users

    def user(k: int) -> None:
        client = _Client(base_url, f"{USER_AGENT} browser")
        try:
            _browse(client, np.random.default_rng(int(seeds[k])))
        finally:
            counts[k] = client.count

    def _browse(client: _Client, own: np.random.Generator) -> None:
        if not _sleep_until(time.monotonic() + own.exponential(pause / 2), stop_at):
            return
        while time.monotonic() < stop_at:
            client.login()
            client.call("GET", f"/collections/{COLLECTIONS[int(own.integers(len(COLLECTIONS)))]}")
            for _ in range(reads):
                if not _sleep_until(time.monotonic() + own.exponential(pause), stop_at):
                    break
                client.call("GET", f"/docs/{ids[int(own.integers(len(ids)))]}")
            if not _sleep_until(time.monotonic() + own.exponential(pause * 3), stop_at):
                break

    threads = [threading.Thread(target=user, args=(k,), daemon=True) for k in range(users)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sum(counts)


CLIENTS = {
    "scheduled_fleet": scheduled_fleet, "crawler": crawler, "retry_storm": retry_storm,
    "many_sessions": many_sessions, "browsing_users": browsing_users,
}
