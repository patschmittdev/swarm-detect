import json
import time
from collections import Counter

import numpy as np
import pytest

from swarmtrace.pilot import lookalikes
from swarmtrace.pilot.service import COLLECTIONS, Service


@pytest.fixture
def svc(tmp_path):
    with Service(seed=3, addresses=["127.0.0.1"], log_path=tmp_path / "log.jsonl") as s:
        yield s


def run_client(svc, tmp_path, fn, seconds, **kw):
    start = time.monotonic()
    count = fn(svc.base_urls[0], np.random.default_rng(0), start + seconds, **kw)
    elapsed = time.monotonic() - start
    svc.stop()
    log = [json.loads(x) for x in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert count == len(log)
    assert elapsed < seconds + 1.0
    return log


def test_scheduled_fleet_bursts_on_shared_ticks(svc, tmp_path):
    log = run_client(svc, tmp_path, lookalikes.scheduled_fleet, 1.7, fleet=3, period=0.5, docs=2)
    docs = [e for e in log if e["path"].startswith("/docs/")]
    assert len({e["token_id"] for e in docs}) == 3
    assert len({e["path"] for e in docs}) == 2
    ticks = Counter(round(e["t_start"] / 0.5) for e in docs)
    assert len(ticks) >= 3 and all(n == 6 for n in list(ticks.values())[:3])


def test_crawler_walks_in_order(svc, tmp_path):
    log = run_client(svc, tmp_path, lookalikes.crawler, 1.5, delay=0.01)
    assert len({e["token_id"] for e in log if e["token_id"]}) == 1
    walk = [e["path"] for e in log[1:]]
    assert walk[0] == f"/collections/{COLLECTIONS[0]}"
    assert walk[1:11] == [f"/docs/{COLLECTIONS[0]}-{i:02d}" for i in range(1, 11)]
    assert walk[11] == f"/collections/{COLLECTIONS[1]}"


def test_retry_storm_repeats_failure_with_backoff(svc, tmp_path):
    log = run_client(svc, tmp_path, lookalikes.retry_storm, 1.5, burst=4, base_delay=0.05,
                     rest=0.4)
    fails = [e for e in log if e["path"] != "/session"]
    assert len({e["path"] for e in fails}) == 1 and all(e["status"] == 404 for e in fails)
    gaps = np.diff([e["t_start"] for e in fails[:4]])
    assert np.all(np.diff(gaps) > 0)


def test_many_sessions_churns_tokens(svc, tmp_path):
    log = run_client(svc, tmp_path, lookalikes.many_sessions, 1.5, per_session=2, delay=0.05)
    sessions = sum(e["path"] == "/session" for e in log)
    tokens = {e["token_id"] for e in log if e["token_id"]}
    assert sessions >= 3 and len(tokens) >= sessions - 1
    assert max(Counter(e["token_id"] for e in log if e["token_id"]).values()) <= 2


def test_browsing_users_are_independent_and_sparse(svc, tmp_path):
    log = run_client(svc, tmp_path, lookalikes.browsing_users, 2.0, users=3, reads=3, pause=0.1)
    assert len({e["token_id"] for e in log if e["token_id"]}) >= 3
    assert all(e["status"] == 200 for e in log)


def test_clients_stop_promptly_with_long_pauses(svc, tmp_path):
    start = time.monotonic()
    lookalikes.browsing_users(svc.base_urls[0], np.random.default_rng(1), start + 0.5, pause=60)
    lookalikes.retry_storm(svc.base_urls[0], np.random.default_rng(1), start + 0.8, rest=60)
    assert time.monotonic() - start < 1.8
