import hashlib
import json
import socket
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from swarmtrace.pilot.service import COLLECTIONS, Service, generate_store, token_id

FIELDS = ["seq", "t_start", "t_end", "via", "peer_port", "token_id", "auth", "user_agent", "method",
          "path", "query", "status", "bytes_in", "bytes_out", "write_sha256",
          "note", "note_version", "note_writer"]


def call(base, method, path, token=None, body=None, headers=None):
    h = {"User-Agent": "test-client", **(headers or {})}
    if token:
        h["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(base + path, data=body, method=method, headers=h), timeout=5) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if "json" in r.headers["Content-Type"] else raw)
    except HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def read_log(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture
def svc(tmp_path):
    with Service(seed=7, addresses=["127.0.0.1"], log_path=tmp_path / "log.jsonl") as s:
        s.base = s.base_urls[0]
        s.token = call(s.base, "POST", "/session")[1]["token"]
        yield s


def test_store_is_deterministic_per_seed():
    a, b, c = generate_store(1), generate_store(1), generate_store(2)
    assert a == b and a != c
    assert len(a) == 80 and {d["collection"] for d in a.values()} == set(COLLECTIONS)
    for doc in a.values():
        assert 120 <= len(doc["body"].split()) <= 220
        assert 0 <= len(doc["references"]) <= 3 and doc["id"] not in doc["references"]
        assert all(r in a for r in doc["references"])
        assert set(doc) == {"id", "collection", "title", "owner", "body", "references"}


def test_help_and_session(svc):
    status, text = call(svc.base, "GET", "/help")
    assert status == 200 and b"/session" in text and b"Bearer" in text
    assert len(svc.token) == 32 and int(svc.token, 16) >= 0
    assert call(svc.base, "GET", "/session")[0] == 405


def test_auth_required(svc):
    for path in ("/collections", "/docs/policies-01", "/notes", "/search?q=a"):
        status, body = call(svc.base, "GET", path)
        assert status == 401 and "/session" in body["hint"] and "/help" in body["hint"]
    assert call(svc.base, "GET", "/collections", token="0" * 32)[0] == 401


def test_read_endpoints(svc):
    b, t = svc.base, svc.token
    status, body = call(b, "GET", "/collections", t)
    assert status == 200 and [c["name"] for c in body["collections"]] == list(COLLECTIONS)
    status, body = call(b, "GET", "/collections/audits", t)
    assert status == 200 and len(body["documents"]) == 10
    doc_id = body["documents"][0]["id"]
    status, doc = call(b, "GET", f"/docs/{doc_id}", t)
    assert status == 200 and doc == svc.docs[doc_id]
    word = doc["title"].split()[0].upper()
    status, body = call(b, "GET", f"/search?q={word}", t)
    assert status == 200 and 0 < len(body["results"]) <= 20
    assert all(word.lower() in (svc.docs[r["id"]]["title"] + svc.docs[r["id"]]["body"]).lower()
               for r in body["results"])
    assert call(b, "GET", "/search?q=", t)[0] == 400
    assert call(b, "GET", "/collections/nope", t)[0] == 404
    assert call(b, "GET", "/docs/nope", t)[0] == 404
    assert call(b, "GET", "/elsewhere", t)[0] == 404
    assert call(b, "POST", "/collections", t)[0] == 405


def test_notes(svc):
    b, t = svc.base, svc.token
    assert call(b, "GET", "/notes", t)[1] == {"notes": []}
    assert call(b, "PUT", "/notes/a-1.txt", t, b"hello")[0] == 201
    other = call(b, "POST", "/session")[1]["token"]
    assert call(b, "PUT", "/notes/a-1.txt", other, b"hello again")[0] == 200
    status, note = call(b, "GET", "/notes/a-1.txt", t)
    assert status == 200 and note["text"] == "hello again"
    listing = call(b, "GET", "/notes", t)[1]["notes"]
    assert listing[0]["name"] == "a-1.txt" and listing[0]["length"] == 11
    assert set(listing[0]) == {"name", "length", "updated"}
    assert call(b, "GET", "/notes/missing", t)[0] == 404
    assert call(b, "PUT", "/notes/bad%20name", t, b"x")[0] == 400
    assert call(b, "PUT", "/notes/" + "x" * 65, t, b"x")[0] == 400
    assert call(b, "PUT", "/notes/big", t, b"x" * (20 * 1024 + 1))[0] == 413
    assert call(b, "PUT", "/notes/bin", t, b"\xff\xfe")[0] == 400
    snap = svc.snapshot()
    assert snap == [{"name": "a-1.txt", "length": 11,
                     "sha256": hashlib.sha256(b"hello again").hexdigest(),
                     "created_by": token_id(t), "last_written_by": token_id(other),
                     "updates": 2}]


def test_log_fields_and_order(svc, tmp_path):
    call(svc.base, "PUT", "/notes/n", svc.token, b"abc")
    call(svc.base, "GET", "/search?q=risk&x=1", svc.token)
    call(svc.base, "GET", "/docs/x", headers={"User-Agent": "u" * 300})
    svc.stop()
    log = read_log(tmp_path / "log.jsonl")
    assert [e["seq"] for e in log] == list(range(1, len(log) + 1))
    for e in log:
        assert list(e) == FIELDS
        assert e["t_start"] <= e["t_end"] and e["via"] == "127.0.0.1"
        assert round(e["t_end"], 6) == e["t_end"]
    session, put, search, unauth = log
    assert session["token_id"] is None and session["path"] == "/session"
    assert session["auth"] == "none" and put["auth"] == "ok"
    assert put["token_id"] == token_id(svc.token) and put["bytes_in"] == 3
    assert put["write_sha256"] == hashlib.sha256(b"abc").hexdigest() and put["status"] == 201
    assert search["query"] == "q=risk&x=1" and search["path"] == "/search"
    assert search["write_sha256"] is None and search["bytes_out"] > 0
    assert unauth["status"] == 401 and len(unauth["user_agent"]) == 120


def test_concurrent_requests_logged_once(svc, tmp_path):
    def worker(k):
        for i in range(10):
            call(svc.base, "GET", f"/docs/policies-0{i % 9 + 1}?w={k}&i={i}", svc.token)

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    svc.stop()
    log = read_log(tmp_path / "log.jsonl")[1:]
    assert len(log) == 80 and len({e["query"] for e in log}) == 80
    assert sorted(e["seq"] for e in log) == list(range(2, 82))


def test_via_records_listener_address(tmp_path):
    log_path = tmp_path / "log.jsonl"
    with Service(seed=1, addresses=["127.0.0.1", "127.0.0.2"], log_path=log_path) as s:
        assert len({u.rsplit(":", 1)[1] for u in s.base_urls}) == 1
        for base in s.base_urls:
            call(base, "GET", "/help")
    vias = [e["via"] for e in read_log(log_path)]
    assert vias == ["127.0.0.1", "127.0.0.2"]


def test_malformed_requests_do_not_break_server(svc):
    import socket
    host, port = "127.0.0.1", svc.port
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.sendall(b"PUT /notes/x HTTP/1.1\r\nHost: a\r\nContent-Length: abc\r\n\r\n")
        assert b" 400 " in sock.recv(4096).split(b"\r\n")[0]
    assert call(svc.base, "GET", "/help")[0] == 200


def slow_put(port, token, delay_event, done):
    """PUT whose body arrives only after delay_event is set; returns via done."""
    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    head = f"PUT /notes/slow HTTP/1.1|Host: a|Authorization: Bearer {token}|"
    head += "Content-Length: 4|Connection: close||"
    sock.sendall(head.replace("|", chr(13) + chr(10)).encode())
    delay_event.wait(5)
    try:
        sock.sendall(b"body")
        done.append(sock.recv(4096))
    except OSError as error:
        done.append(error)
    sock.close()


def test_overlapping_requests_have_overlapping_intervals(svc, tmp_path):
    release, done = threading.Event(), []
    thread = threading.Thread(target=slow_put, args=(svc.port, svc.token, release, done))
    thread.start()
    time.sleep(0.2)
    assert call(svc.base, "GET", "/collections", svc.token)[0] == 200
    release.set()
    thread.join()
    svc.stop()
    log = read_log(tmp_path / "log.jsonl")
    get = next(e for e in log if e["path"] == "/collections")
    put = next(e for e in log if e["path"] == "/notes/slow")
    assert done[0].startswith(b"HTTP/1.1 201")
    assert put["status"] == 201 and put["t_start"] < get["t_start"] <= get["t_end"] < put["t_end"]


def test_sequential_requests_do_not_overlap(svc, tmp_path):
    for _ in range(5):
        call(svc.base, "GET", "/docs/policies-01", svc.token)
    svc.stop()
    log = read_log(tmp_path / "log.jsonl")
    assert all(e["t_end"] > e["t_start"] for e in log)
    assert all(a["t_end"] <= b["t_start"] for a, b in zip(log, log[1:]))


def test_invalid_token_is_not_identified(svc, tmp_path):
    assert call(svc.base, "GET", "/collections", token="f" * 32)[0] == 401
    assert call(svc.base, "GET", "/collections", headers={"Authorization": "Basic x"})[0] == 401
    svc.stop()
    bad, basic = read_log(tmp_path / "log.jsonl")[1:]
    assert bad["token_id"] is None and bad["auth"] == "invalid"
    assert basic["token_id"] is None and basic["auth"] == "invalid"


def test_unsupported_methods_are_logged(svc, tmp_path):
    for method in ("HEAD", "DELETE", "OPTIONS"):
        assert call(svc.base, method, "/help")[0] == 405
    svc.stop()
    log = read_log(tmp_path / "log.jsonl")[1:]
    assert [(e["method"], e["status"]) for e in log] == [
        ("HEAD", 405), ("DELETE", 405), ("OPTIONS", 405)]


def test_stop_waits_for_in_flight_request(svc, tmp_path):
    release, done = threading.Event(), []
    thread = threading.Thread(target=slow_put, args=(svc.port, svc.token, release, done))
    thread.start()
    time.sleep(0.2)
    threading.Timer(0.5, release.set).start()
    svc.stop()
    thread.join()
    assert [e["path"] for e in read_log(tmp_path / "log.jsonl")] == ["/session", "/notes/slow"]
    assert [n["name"] for n in svc.snapshot()] == ["slow"]
