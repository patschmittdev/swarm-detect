"""Read the independently issued EntCollabBench routing instructions and source document bytes."""

import hashlib
import json
import re
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

ROUTE = re.compile(r"\bask (\w+_approval_specialist) to perform\b")
DOCUMENT = re.compile(r"\bsubmission/[\w/-]+\.md\b")
TOPIC = re.compile(r"\btopic context: ([^.\n]+)\.", re.I)
ONLY_DESIGNATED = ("You only need to relay my approval request and all provided information or file paths "
                   "to the designated approval_specialist agent")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def key(*parts: str) -> str:
    return digest("\0".join(parts).encode())


@dataclass(frozen=True)
class Stage:
    stage_id: str
    topic: str
    author: str
    document: str
    recipients: tuple[str, ...]
    text: str
    ticket_digest: str


@dataclass(frozen=True)
class Ticket:
    base_id: str
    family: str
    stages: tuple[Stage, ...]


def _sources(cache: Path, protocol: dict, fetch: bool) -> None:
    for name, expected in protocol["assets"].items():
        if name not in {"approval_tasks_80.json", "approval_multi_task_20.json", "local_data.zip"}:
            raise ValueError("unexpected EntCollabBench asset")
        path = cache / name
        if not path.is_file():
            if not fetch:
                raise ValueError(f"missing pinned input {name}; use --fetch or supply --source-dir")
            cache.mkdir(parents=True, exist_ok=True)
            revision = protocol["revision"]
            url = f"https://huggingface.co/datasets/Kirito-Lab/EntCollabBench/resolve/{revision}/{name}"
            with urllib.request.urlopen(url, timeout=40) as response:
                content = response.read(5_000_001)
            if len(content) > 5_000_000 or digest(content) != expected:
                raise ValueError(f"unexpected download bytes for {name}")
            with NamedTemporaryFile(dir=cache, delete=False) as stream:
                tmp = Path(stream.name)
                stream.write(content)
            try:
                tmp.replace(path)
            finally:
                tmp.unlink(missing_ok=True)
        if digest(path.read_bytes()) != expected:
            raise ValueError(f"pinned source digest differs for {name}")


def _stage(row, archive: zipfile.ZipFile) -> Stage:
    prompt = row["user_prompt"]
    routes = {}
    for line in prompt.splitlines():
        match = ROUTE.search(line)
        if match:
            role = match.group(1)
            files = tuple(DOCUMENT.findall(line))
            if role in routes or not files or any(".." in p.split("/") for p in files):
                raise ValueError("invalid document routing clause")
            routes[role] = files
    topics = set(TOPIC.findall(prompt))
    if not routes or len(topics) != 1 or ONLY_DESIGNATED not in " ".join(prompt.split()):
        raise ValueError("stage needs an explicit recipient restriction, routing clause and policy topic")
    # The named recipients come from the request, never its ground-truth decisions.
    document = next(iter(routes.values()))[0]
    recipients = tuple(role for role, names in routes.items() if document in names)
    copies = set()
    for role in recipients:
        member = archive.getinfo(f"local_data/{role}/{document}")
        if member.file_size > 500_000:
            raise ValueError("source document is unexpectedly large")
        copies.add(archive.read(member))
    if len(copies) != 1:
        raise ValueError("named recipients have different input versions")
    text = copies.pop().decode("utf-8")
    return Stage(row["sub_task_id"], topics.pop().strip().lower().removesuffix(" negation"),
                 row["beginning_agent"], document, recipients, text, digest(prompt.encode()))


def read_tickets(cache: Path, protocol: dict, *, fetch: bool = False) -> list[Ticket]:
    _sources(cache, protocol, fetch)
    tickets = []
    with zipfile.ZipFile(cache / "local_data.zip") as archive:
        for name in ("approval_tasks_80.json", "approval_multi_task_20.json"):
            for row in json.loads((cache / name).read_bytes()):
                stages = tuple(_stage(s, archive) for s in row["sub_task_list"])
                match = re.match(r"^\d+-stage (\w+)", row["description"])
                family = match.group(1) if match else stages[0].topic
                tickets.append(Ticket(row["task_id"], family, stages))
    stage_ids = [s.stage_id for task in tickets for s in task.stages]
    if len(tickets) != len({t.base_id for t in tickets}) or len(stage_ids) != len(set(stage_ids)):
        raise ValueError("duplicate public ticket or stage")
    return sorted(tickets, key=lambda t: t.base_id)


def split_tickets(tickets, integration_ids):
    """Transitively keep reused policy topics, multistage pipelines and entire base tasks together."""
    groups = []
    for task in tickets:
        topics = {s.topic for s in task.stages}
        if len(task.stages) > 1:
            topics.add(f"pipeline/{task.family}")
        shared = [group for group in groups if topics & group[1]]
        groups = [group for group in groups if group not in shared]
        groups.append(({task.base_id}.union(*(g[0] for g in shared)), topics.union(*(g[1] for g in shared))))
    if not set(integration_ids) <= {t.base_id for t in tickets}:
        raise ValueError("unknown source integration task")
    return {base: ("integration" if ids & set(integration_ids) else "confirmation", key(*sorted(tags))[:12])
            for ids, tags in groups for base in ids}
