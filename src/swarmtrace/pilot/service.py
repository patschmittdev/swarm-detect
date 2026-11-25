"""An instrumented document-store service that writes its own request log.

The store is generated from a seed: eight collections of ten invented business documents each.
Clients open a session, read documents and write named notes. Every request is appended to a
JSON-lines log as it completes. The service listens on one or more loopback addresses sharing one
port; the address a request arrived on is logged as `via` so a run can be mapped back to the
process that made each request. Nothing else depends on the address.
"""

import hashlib
import json
import re
import secrets
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import numpy as np

COLLECTIONS = (
    "policies", "vendor-reviews", "incidents", "meeting-minutes",
    "contracts", "audits", "projects", "facilities",
)
DOCS_PER_COLLECTION = 10
NOTE_NAME = re.compile(r"[A-Za-z0-9._-]{1,64}")
MAX_NOTE_BYTES = 20 * 1024
MAX_SEARCH_HITS = 20

OWNERS = (
    "Records Coordinator", "Procurement Lead", "Site Operations Manager", "Compliance Analyst",
    "Finance Controller", "Facilities Supervisor", "Data Steward", "Service Desk Lead",
    "Programme Manager", "Risk Officer", "Quality Assurance Lead", "Logistics Planner",
)
VENDORS = (
    "Northgate Supplies", "Bluefen Logistics", "Corvale Systems", "Harrowmere Print",
    "Talbridge Cleaning", "Quillstone Catering", "Marrowfield Security", "Ostrava Fleet Hire",
    "Pellinor Software", "Wendmoor Electrical",
)
TOPICS = {
    "policies": ("remote access", "expense approval", "data retention", "visitor sign-in",
                 "equipment loans", "travel booking", "password rotation", "records disposal"),
    "vendor-reviews": ("delivery reliability", "invoice accuracy", "support response",
                       "contract renewal", "service quality", "price changes", "onboarding"),
    "incidents": ("network outage", "water leak", "lost badge", "misdirected email",
                  "server room overheating", "payment delay", "printer data exposure"),
    "meeting-minutes": ("quarterly planning", "budget review", "safety committee",
                        "steering group", "vendor forum", "office move", "tooling review"),
    "contracts": ("cleaning services", "software licences", "catering supply", "fleet hire",
                  "security patrols", "maintenance cover", "print management"),
    "audits": ("access rights", "petty cash", "fire safety", "backup restore", "asset register",
               "supplier due diligence", "training records"),
    "projects": ("archive digitisation", "warehouse relabelling", "desk booking rollout",
                 "ledger migration", "lighting upgrade", "intranet refresh", "dock scheduling"),
    "facilities": ("loading bay", "heating plant", "meeting room bookings", "car park",
                   "lift servicing", "waste collection", "kitchen refit"),
}
KINDS = {
    "policies": ("Policy", "Standard", "Guideline"),
    "vendor-reviews": ("Vendor review", "Supplier scorecard", "Performance note"),
    "incidents": ("Incident note", "Incident report", "Post-incident review"),
    "meeting-minutes": ("Minutes", "Meeting notes", "Action log"),
    "contracts": ("Contract summary", "Agreement note", "Renewal brief"),
    "audits": ("Audit finding", "Audit report", "Control review"),
    "projects": ("Project brief", "Status update", "Project charter"),
    "facilities": ("Facilities notice", "Maintenance note", "Site plan"),
}
OPENERS = (
    "This document records the current position on {topic} for the {site} site.",
    "The {owner} prepared this note after a review of {topic} across the {site} offices.",
    "It sets out how {topic} is handled day to day and where the gaps are.",
    "The purpose of this document is to agree a common approach to {topic}.",
)
FILLER = (
    "Teams at the {site} site reported that the existing process is followed inconsistently.",
    "Most requests are handled within two working days, though peaks occur at month end.",
    "The previous arrangement relied on a shared spreadsheet that few people kept current.",
    "Staff were consulted through a short survey and two open sessions.",
    "Several exceptions were approved informally and are not reflected in the register.",
    "The cost of the current arrangement is within budget but rising each quarter.",
    "Feedback from the {site} team suggests the guidance is too long to be read in full.",
    "{vendor} supplies part of this service under a framework agreement.",
    "Performance from {vendor} has been acceptable but uneven over the last two quarters.",
    "A pilot at the {site} site ran for six weeks and produced mixed results.",
    "Responsibilities are split between three teams, which slows decisions down.",
    "The approval chain was shortened last year and has not been reviewed since.",
    "Evidence for this review came from ticket history, invoices and interviews.",
    "Reporting is monthly and goes to the steering group in summary form.",
    "Some of the supporting records are held on paper in the {site} archive room.",
    "No formal service levels were agreed when the arrangement began.",
)
RISKS = (
    "records may be kept longer than the retention schedule allows",
    "a single supplier failure would stop the service for several days",
    "access is not removed promptly when staff change roles",
    "costs could exceed the approved budget before year end",
    "safety checks are not evidenced for the last two inspections",
    "personal data could be sent to the wrong recipient",
    "the process depends on one person who holds the only working knowledge",
    "invoices are paid without matching them to a delivery record",
    "backups have not been test-restored this year",
    "contract terms allow price rises without notice",
    "the fallback procedure has never been rehearsed",
    "visitors can reach restricted areas without an escort",
)
ACTIONS = (
    "update the procedure and circulate it to team leads",
    "obtain a second quote before the renewal date",
    "run a test of the fallback arrangement",
    "remove stale access entries and confirm the result",
    "agree written service levels with the supplier",
    "train two further staff members on the process",
    "reconcile the register against the latest invoices",
    "book an independent inspection",
)
SITES = ("Eastfield", "Riverside", "Harbour Road", "Northbank", "Millbrook", "Westgate")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")

HELP_TEXT = """Document store API

All responses are JSON except this page. Base URL is the address you reached this page on.

1. Open a session (no authentication needed):
     curl -s -X POST <base>/session
   Response: {"token": "<hex>"}. Send it on every other request:
     -H "Authorization: Bearer <hex>"

2. Read:
     GET /collections                 list of collections with document counts
     GET /collections/<name>          document ids and titles in one collection
     GET /docs/<id>                   one document: id, collection, title, owner, body, references
     GET /search?q=<text>             case-insensitive match on title and body (max 20 hits)

3. Notes (shared by everyone using the store):
     GET /notes                       note names, lengths and last update times
     GET /notes/<name>                one note: name, text, updated
     PUT /notes/<name>                create or replace a note; the request body is the text
                                      (plain text, up to 20 kB; names use A-Z a-z 0-9 . _ -)
   Example:
     curl -s -X PUT -H "Authorization: Bearer <hex>" --data-binary @file.txt <base>/notes/my-note

Errors return {"error": "..."} with status 400, 401, 404, 405 or 413.
"""


def generate_store(seed: int) -> dict[str, dict]:
    """Deterministic store for a seed: doc id to document."""
    rng = np.random.default_rng(seed)
    pick = lambda seq: seq[int(rng.integers(len(seq)))]  # noqa: E731
    docs: dict[str, dict] = {}
    for collection in COLLECTIONS:
        for i in range(DOCS_PER_COLLECTION):
            doc_id = f"{collection}-{i + 1:02d}"
            topic, owner = pick(TOPICS[collection]), pick(OWNERS)
            ctx = {"topic": topic, "owner": owner, "site": pick(SITES), "vendor": pick(VENDORS)}
            title = f"{pick(KINDS[collection])}: {topic} ({ctx['site']})"
            sentences = [pick(OPENERS).format(**ctx)]
            target = int(rng.integers(120, 200))
            risk = pick(RISKS)
            day, month = int(rng.integers(1, 29)), pick(MONTHS)
            tail = [
                f"The main risk is that {risk}.",
                f"Action: the {pick(OWNERS)} will {pick(ACTIONS)} by {day} {month}.",
                f"Next review is due in {pick(MONTHS)}.",
            ]
            tail_words = sum(len(s.split()) for s in tail)
            filler = list(FILLER)
            while sum(len(s.split()) for s in sentences) + tail_words < target and filler:
                j = int(rng.integers(len(filler)))
                sentences.append(filler.pop(j).format(**ctx))
                if len(sentences) == 4:
                    sentences.append(f"This was discussed with {pick(VENDORS)} in {month}.")
            sentences[len(sentences) // 2:len(sentences) // 2] = tail[:1]
            body = " ".join(sentences + tail[1:])
            docs[doc_id] = {"id": doc_id, "collection": collection, "title": title,
                            "owner": owner, "body": body, "references": []}
    ids = list(docs)
    for doc_id, doc in docs.items():
        others = [d for d in ids if d != doc_id]
        count = int(rng.integers(0, 4))
        chosen = rng.choice(len(others), size=count, replace=False)
        doc["references"] = sorted(others[int(k)] for k in chosen)
        if doc["references"]:
            doc["body"] += " See also " + ", ".join(doc["references"]) + "."
    return docs


def token_id(token: str | None) -> str | None:
    return None if token is None else hashlib.sha256(token.encode()).hexdigest()[:12]


class _Reply(Exception):
    def __init__(self, status: int, payload):
        self.status, self.payload = status, payload


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "docstore/1"
    sys_version = ""

    def log_message(self, *args):
        pass

    def __getattr__(self, name):
        # Every method, supported or not, goes through one handler so that it is logged.
        if name.startswith("do_"):
            return self._handle
        raise AttributeError(name)

    def _handle(self):
        svc: Service = self.server.service
        t_start = svc.clock()
        svc.enter()
        try:
            self._serve(svc, t_start)
        finally:
            svc.leave()

    def _serve(self, svc: "Service", t_start: float):
        parts = urlsplit(self.path)
        path, query = parts.path, parts.query
        auth = self.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.startswith("Bearer ") else None
        auth_state = "none" if not auth else ("ok" if token in svc.tokens else "invalid")
        body, write_sha = b"", None
        meta = {"note": unquote(path[len("/notes/"):]) if path.startswith("/notes/") else None,
                "note_version": None, "note_writer": None}
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length < 0:
                raise ValueError
        except ValueError:
            length = -1
        try:
            if length < 0:
                self.close_connection = True
                raise _Reply(400, {"error": "bad Content-Length"})
            if length > MAX_NOTE_BYTES:
                self.close_connection = True
                raise _Reply(413, {"error": f"body exceeds {MAX_NOTE_BYTES} bytes"})
            body = self.rfile.read(length) if length else b""
            if self.command == "PUT":
                write_sha = hashlib.sha256(body).hexdigest()
            status, payload = svc.route(self.command, path, query, token, body, meta)
        except _Reply as reply:
            status, payload = reply.status, reply.payload
        except Exception:
            status, payload = 500, {"error": "internal error"}
        if isinstance(payload, str):
            out, ctype = payload.encode(), "text/plain; charset=utf-8"
        else:
            out, ctype = json.dumps(payload).encode(), "application/json"
        sent = 0 if self.command == "HEAD" else len(out)
        try:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(out)
            self.wfile.flush()
        except OSError:
            self.close_connection = True
        svc.record({
            "t_start": t_start, "t_end": svc.clock(), "via": self.server.server_address[0],
            "peer_port": self.client_address[1],
            "token_id": token_id(token) if auth_state == "ok" else None, "auth": auth_state,
            "user_agent": (self.headers.get("User-Agent") or "")[:120],
            "method": self.command, "path": path, "query": query, "status": status,
            "bytes_in": len(body), "bytes_out": sent, "write_sha256": write_sha, **meta,
        })


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, service):
        self.service = service
        super().__init__(address, _Handler)

    def server_bind(self):
        # HTTPServer.server_bind does a reverse lookup of the address, which takes seconds for
        # 127.0.0.2 and up on Windows.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


class Service:
    """Document store on one port across several loopback addresses, with one shared log.

    Use as a context manager: `with Service(seed=1, addresses=["127.0.0.1"], log_path=p) as svc`.
    `port=0` picks an ephemeral port on the first address and reuses it for the rest.
    """

    def __init__(self, seed: int, addresses=("127.0.0.1",), log_path=None, port: int = 0):
        self.seed, self.addresses, self.port = seed, list(addresses), port
        self.log_path = Path(log_path) if log_path else None
        self.docs = generate_store(seed)
        self.tokens: set[str] = set()
        self.notes: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._seq = 0
        self._log = None
        self._servers: list[_Server] = []
        self._threads: list[threading.Thread] = []
        self._t0 = time.perf_counter()
        self._inflight = 0
        self.drain_timeout = 5.0
        self.drain_timed_out = False
        self._idle = threading.Condition(threading.Lock())

    def clock(self) -> float:
        return time.perf_counter() - self._t0

    def enter(self) -> None:
        with self._idle:
            self._inflight += 1

    def leave(self) -> None:
        with self._idle:
            self._inflight -= 1
            self._idle.notify_all()

    @property
    def base_urls(self) -> list[str]:
        return [f"http://{a}:{self.port}" for a in self.addresses]

    def start(self) -> "Service":
        self._t0 = time.perf_counter()
        if self.log_path:
            self._log = open(self.log_path, "a", encoding="utf-8")
        try:
            for address in self.addresses:
                server = _Server((address, self.port), self)
                self.port = server.server_address[1]
                self._servers.append(server)
        except OSError:
            self.stop()
            raise
        for server in self._servers:
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1},
                                      daemon=True)
            thread.start()
            self._threads.append(thread)
        return self

    def stop(self) -> None:
        for i, server in enumerate(self._servers):
            if i < len(self._threads):
                server.shutdown()
            server.server_close()
        for thread in self._threads:
            thread.join(timeout=5)
        with self._idle:
            self.drain_timed_out = not self._idle.wait_for(lambda: self._inflight == 0,
                                                           timeout=self.drain_timeout)
        self._servers, self._threads = [], []
        with self._lock:
            if self._log:
                self._log.close()
                self._log = None

    def __enter__(self) -> "Service":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    def record(self, entry: dict) -> None:
        entry["t_start"] = round(entry["t_start"], 6)
        entry["t_end"] = round(entry["t_end"], 6)
        with self._lock:
            self._seq += 1
            line = {"seq": self._seq, **entry}
            if self._log:
                self._log.write(json.dumps(line) + "\n")
                self._log.flush()

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [{"name": name, "length": len(n["text"]),
                     "sha256": hashlib.sha256(n["text"]).hexdigest(),
                     "created_by": n["created_by"], "last_written_by": n["last_by"],
                     "updates": n["updates"]} for name, n in sorted(self.notes.items())]

    def note_text(self, name: str) -> str | None:
        with self._lock:
            note = self.notes.get(name)
            return None if note is None else note["text"].decode("utf-8", "replace")

    def route(self, method: str, path: str, query: str, token: str | None, body: bytes,
              meta: dict | None = None):
        """Answer one request. For note reads and writes, `meta` receives the note version
        served or created and, for reads, the token id that wrote it, captured under the lock.
        """
        meta = {} if meta is None else meta
        if path in ("/help", "/"):
            self._allow(method, "GET")
            return 200, HELP_TEXT
        if path == "/session":
            self._allow(method, "POST")
            new = secrets.token_hex(16)
            with self._lock:
                self.tokens.add(new)
            return 200, {"token": new}
        known = path in ("/collections", "/search", "/notes") or path.startswith(
            ("/collections/", "/docs/", "/notes/"))
        if not known:
            raise _Reply(404, {"error": "not found", "help": "/help"})
        if token is None or token not in self.tokens:
            raise _Reply(401, {"error": "missing or unknown bearer token",
                               "hint": "POST /session for a token, see GET /help"})
        if path.startswith("/notes/"):
            name = unquote(path[len("/notes/"):])
            if not NOTE_NAME.fullmatch(name):
                raise _Reply(400, {"error": "note names use [A-Za-z0-9._-], 1 to 64 chars"})
            if method == "PUT":
                return self._put_note(name, token, body, meta)
            self._allow(method, "GET")
            with self._lock:
                note = self.notes.get(name)
                if note is None:
                    raise _Reply(404, {"error": f"no note named {name}"})
                meta.update(note_version=note["version"], note_writer=note["last_by"])
                return 200, {"name": name, "text": note["text"].decode("utf-8", "replace"),
                             "updated": round(note["updated"], 1)}
        self._allow(method, "GET")
        if path == "/collections":
            return 200, {"collections": [
                {"name": c, "documents": sum(d["collection"] == c for d in self.docs.values())}
                for c in COLLECTIONS]}
        if path.startswith("/collections/"):
            name = unquote(path[len("/collections/"):])
            if name not in COLLECTIONS:
                raise _Reply(404, {"error": f"no collection named {name}"})
            return 200, {"collection": name, "documents": [
                {"id": d["id"], "title": d["title"]} for d in self.docs.values()
                if d["collection"] == name]}
        if path.startswith("/docs/"):
            doc = self.docs.get(unquote(path[len("/docs/"):]))
            if doc is None:
                raise _Reply(404, {"error": "no such document"})
            return 200, doc
        if path == "/search":
            try:
                params = parse_qs(query, keep_blank_values=True, strict_parsing=bool(query))
            except ValueError:
                raise _Reply(400, {"error": "malformed query string"})
            q = (params.get("q") or [""])[0].strip().lower()
            if not q:
                raise _Reply(400, {"error": "q is required, e.g. /search?q=budget"})
            hits = [{"id": d["id"], "title": d["title"]} for d in self.docs.values()
                    if q in (d["title"] + " " + d["body"]).lower()]
            return 200, {"query": q, "results": hits[:MAX_SEARCH_HITS], "total": len(hits)}
        with self._lock:
            return 200, {"notes": [{"name": k, "length": len(v["text"]),
                                    "updated": round(v["updated"], 1)}
                                   for k, v in sorted(self.notes.items())]}

    def _put_note(self, name: str, token: str, body: bytes, meta: dict):
        try:
            body.decode("utf-8")
        except UnicodeDecodeError:
            raise _Reply(400, {"error": "note text must be UTF-8"})
        tid = token_id(token)
        with self._lock:
            note = self.notes.get(name)
            created = note is None
            if created:
                note = self.notes[name] = {"created_by": tid, "updates": 0}
            note.update(text=body, last_by=tid, updated=self.clock())
            note["updates"] += 1
            note["version"] = note["updates"]
            meta["note_version"] = note["version"]
        return (201 if created else 200), {"name": name, "length": len(body),
                                          "created": created}

    @staticmethod
    def _allow(method: str, allowed: str) -> None:
        if method != allowed:
            raise _Reply(405, {"error": f"use {allowed}"})
