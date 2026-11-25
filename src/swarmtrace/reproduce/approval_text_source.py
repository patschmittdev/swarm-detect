"""Rebuild the MCPHunt text comparison from pinned task strings and independent reviews."""

import argparse
import ast
import csv
import hashlib
import inspect
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen

from swarmtrace.eval import approval_text
from swarmtrace.eval.approval_text import (
    Ticket,
    digest,
    parse_ticket,
    partition,
    read_csv,
    read_entailment,
    sentences,
    write_csv,
    write_json,
)

CODE = "48e0f42f0820f15c9e88edb0ba461c615b908ecb"
DATA = "8f05fed6face78aa48b10edcf3357c9aadfe71f5"
MODEL_REV = "cf44676c28ba7312e5c5f8f8d2c22b3e0c9cdae2"
MAX_SOURCE_BYTES = 5_000_000
REPO = f"https://raw.githubusercontent.com/lihaonan0716/MCPHunt/{CODE}/src/mcphunt/"
AUDIT = f"https://huggingface.co/datasets/lihaonan0716/mcphunt-agent-traces/resolve/{DATA}/crs_audit/"
SOURCES = {
    "prompts.py": (REPO, "a95c314413ace7013268f176f372ba90621fead3fa7e31903474145999d9c6ff"),
    "taxonomy.py": (REPO, "a85d29237d27fad239737c0fae1efa719e2efc38a04e5f68b418c46773a456f2"),
    "annotation_1.csv": (AUDIT, "284f2fc5999fee845db1d00d7301e71d5add0ca5840561014a9fce88abd046cd"),
    "annotation_2.csv": (AUDIT, "5c044d611e8e06320b6fd1f26bc4089b039500bbe131ddf7a52959ca87e59b30"),
}
MODEL_FILES = {
    "added_tokens.json": "dc046d04c9b0ada7ae6f1dc89c465801799acdf0c9a6aab8c15a1b2d5ca4e91f",
    "config.json": "3b0a2a3fb311037ba72670d87cbd16f920581985178547a76936dfdb292e5271",
    "model.safetensors": "2031ec34340911b2cecf4f95f5e24db91b2a5d7ea0fa1e704e9cd6d61585e477",
    "special_tokens_map.json": "b2f1b2f15f29a6b6d9d6ea4eca1675d2c231a71477f151d48f79cc83a625ba21",
    "spm.model": "c679fbf93643d19aab7ee10c0b99e460bdbc02fedf34b92b05af343b4af586fd",
    "tokenizer.json": "05402ffae6dd382a8491b1d29bfc139bec5d332662e86a026f433ce54c25c202",
    "tokenizer_config.json": "f5a1a74a632c0e9225e09a21ddf60c2e70ef5d3bfc1f261a24fd8ddab27254d2",
}


def sources(directory: Path, fetch: bool) -> None:
    if fetch:
        directory.mkdir(parents=True, exist_ok=True)
    for name, (base, expected) in SOURCES.items():
        path = directory / name
        if fetch and not path.exists():
            with urlopen(base + name, timeout=45) as response:
                data = response.read(MAX_SOURCE_BYTES + 1)
            if len(data) > MAX_SOURCE_BYTES:
                raise ValueError(f"source download exceeds the size limit for {name}")
            if digest(data) != expected:
                raise ValueError(f"source hash mismatch on download of {name}")
            with path.open("xb") as f:
                f.write(data)
        if digest(path.read_bytes()) != expected:
            raise ValueError(f"source hash mismatch for {name}")


def literal(node) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(literal(piece) for piece in node.values)
    if isinstance(node, ast.FormattedValue) and isinstance(node.value, ast.Name):
        if node.value.id in ("W", "base") and node.conversion == -1 and node.format_spec is None:
            return {"W": "[workspace]", "base": "[local service]"}[node.value.id]
    raise ValueError("unexpected expression in pinned ticket template")


def tickets(directory: Path) -> list[Ticket]:
    # Inspect literal arguments; never import or execute either upstream module.
    registry = next(n.value for n in ast.parse((directory / "taxonomy.py").read_bytes()).body
                    if isinstance(n, ast.AnnAssign) and n.target.id == "TASK_REGISTRY")
    info = {}
    for key, value in zip(registry.keys, registry.values, strict=True):
        mechanism, family = (literal(x) for x in value.args[:2])
        paired = next((literal(k.value) for k in value.keywords if k.arg == "paired_risk"), "")
        info[literal(key)] = (mechanism, family, paired)
    result = []
    for node in ast.parse((directory / "prompts.py").read_bytes()).body:
        if not isinstance(node, ast.FunctionDef) or node.name not in ("_build_tasks", "_build_browser_tasks"):
            continue
        for line in node.body:
            if isinstance(line, ast.Expr) and isinstance(line.value, ast.Call):
                call = line.value
                if not isinstance(call.func, ast.Name) or call.func.id != "add" or len(call.args) != 3:
                    raise ValueError("unexpected source task record")
                key, text = map(literal, call.args[:2])
                result.append(Ticket(key, *info[key], text))
    if len(result) != 147 or set(info) != {t.task_id for t in result}:
        raise ValueError("incomplete externally authored task registry")
    return sorted(result, key=lambda t: t.task_id)


def _reviewers(directory: Path, cases: list[Ticket]) -> list[dict]:
    by_id = {t.task_id: t for t in cases}
    reviews = {key: {"task_id": key} for key in by_id}
    for number in (1, 2):
        with (directory / f"annotation_{number}.csv").open(encoding="utf-8-sig", newline="") as f:
            raw = list(csv.DictReader(f))
        if len(raw) != len(reviews) or {row["task_id"] for row in raw} != by_id.keys():
            raise ValueError("independent review lacks unique complete IDs")
        for row in raw:
            key = row["task_id"]
            if row["mechanism"] != by_id[key].mechanism:
                raise ValueError("independent review family disagrees with the registry")
            value = {"TRUE": "yes", "FALSE": "no"}.get(row["your_crs_label"].strip())
            if value is None:
                raise ValueError("unexpected public review code")
            reviews[key][f"reviewer_{number}"] = value
    return list(reviews.values())


def _probabilities(cases, hints, snapshot, threads):
    import tokenizers
    import torch
    import transformers
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    for name, expected in MODEL_FILES.items():
        with (snapshot / name).open("rb") as f:
            if hashlib.file_digest(f, "sha256").hexdigest() != expected:
                raise ValueError(f"checkpoint hash mismatch for {name}")
    torch.set_num_threads(threads)
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False)
    model = AutoModelForSequenceClassification.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=False, use_safetensors=True).float().cpu().eval()
    entail = model.config.label2id["entailment"]
    texts = sorted({s for t in cases for s in (t.text, *(t.text[a:b] for a, b in sentences(t.text)))})
    pairs = [(s, h) for s in texts for h in hints]
    values = []
    with torch.inference_mode():
        for i in range(0, len(pairs), 8):
            batch = pairs[i:i + 8]
            encoded = tokenizer([s for s, _ in batch], [h for _, h in batch], padding=True, return_tensors="pt")
            if encoded.input_ids.shape[1] > model.config.max_position_embeddings:
                raise ValueError("ticket exceeds the encoder's context window")
            values.extend(model(**encoded).logits.softmax(dim=1)[:, entail].tolist())
    env = {"torch": str(torch.__version__), "transformers": transformers.__version__,
           "tokenizers": tokenizers.__version__, "python": sys.version.split()[0],
           "device": "cpu", "dtype": "float32", "batch_size": 8, "threads": threads,
           "unique_premises": len(texts), "nli_pairs": len(pairs)}
    return dict(zip(texts, zip(values[::2], values[1::2], strict=True), strict=True)), env


def rebuild(protocol_path: Path, source: Path, snapshot: Path, out: Path, threads: int) -> None:
    if out.exists() or threads < 1:
        raise ValueError("rebuild requires a new output directory and positive thread count")
    sources(source, False)
    protocol = json.loads(protocol_path.read_bytes())
    if (protocol["source_code_revision"], protocol["source_audit_revision"], protocol["model_revision"]) != (
            CODE, DATA, MODEL_REV) or len(protocol["hypotheses"]) != 2 or (
            protocol["implementation_sha256"] != implementation_hash()):
        raise ValueError("unexpected external protocol or checkpoint")
    cases = tickets(source)
    groups = partition(cases, protocol["quarantine_published_examples"])
    probs, env = _probabilities(cases, protocol["hypotheses"], snapshot, threads)
    rows = []
    for t in cases:
        group, split = groups[t.task_id]
        model = read_entailment(t.text, probs)
        req, derived = probs[t.text]
        rows.append(dict(task_id=t.task_id, mechanism=t.mechanism, family=t.family, paired=t.paired,
                         group=group, split=split, text_length=len(t.text), text_sha256=digest(t.text.encode()),
                         **parse_ticket(t.text).fields(t.text, "parser"),
                         **model.fields(t.text, "deberta"), deberta_full_required=req, deberta_full_redactable=derived))
    # The external reviewer labels are interpreted only after all text predictions exist.
    reviewers = _reviewers(source, cases)
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as tmp:
        stage = Path(tmp) / "study"
        stage.mkdir()
        (stage / "protocol.json").write_bytes(protocol_path.read_bytes())
        write_csv(stage / "predictions.csv", rows)
        write_csv(stage / "reviewers.csv", reviewers)
        inputs = {p.name: digest(p.read_bytes()) for p in sorted(stage.iterdir())}
        write_json(stage / "manifest.json", {"sha256": inputs, "inference": env,
                   "source_sha256": {k: v[1] for k, v in SOURCES.items()}, "checkpoint_sha256": MODEL_FILES})
        stage.rename(out)


def implementation_hash() -> str:
    """Fingerprint the frozen text, split, scoring and calibration rules."""
    funcs = (literal, tickets, partition, approval_text.template, sentences, parse_ticket, read_entailment,
             _probabilities, approval_text.decision, approval_text._calibrate)
    material = [approval_text._TRANSFER.pattern, approval_text._DERIVED.pattern, str(approval_text.FLOOR)]
    material.extend(inspect.getsource(f).replace("\r\n", "\n") for f in funcs)
    return digest("\0".join(material).encode())


def quote(study: Path, source: Path, task_id: str, method: str) -> str:
    sources(source, False)
    lookup = {c.task_id: c.text for c in tickets(source)}
    predictions = study / "predictions.csv"
    manifest = json.loads((study / "manifest.json").read_bytes())
    if digest(predictions.read_bytes()) != manifest["sha256"]["predictions.csv"]:
        raise ValueError("unexpected approval-text predictions")
    rows = read_csv(predictions)
    row = next((r for r in rows if r["task_id"] == task_id), None)
    if row is None or method not in ("parser", "deberta") or task_id not in lookup:
        raise ValueError("unknown task or reader")
    text = lookup[task_id]
    if digest(text.encode()) != row["text_sha256"]:
        raise ValueError("ticket hash mismatch")
    snippet = text[int(row[f"{method}_start"]):int(row[f"{method}_end"])]
    if (digest(snippet.encode()) if snippet else "") != row[f"{method}_quote_sha256"]:
        raise ValueError("supporting quote hash mismatch")
    return snippet


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cmd = cli.add_subparsers(dest="command", required=True)
    rebuild_cli = cmd.add_parser("rebuild")
    rebuild_cli.add_argument("--snapshot", type=Path, required=True)
    rebuild_cli.add_argument("--out", type=Path, required=True)
    rebuild_cli.add_argument("--threads", type=int, default=8)
    quotes = cmd.add_parser("quote")
    quotes.add_argument("--task", required=True)
    quotes.add_argument("--method", required=True, choices=("parser", "deberta"))
    for sub in (rebuild_cli, quotes):
        sub.add_argument("--study", type=Path, default=Path("benchmarks/approval-text"))
        sub.add_argument("--source", type=Path, required=True)
        sub.add_argument("--fetch", action="store_true", help="Fetch four pinned public text and review files")
    args = cli.parse_args()
    sources(args.source, args.fetch)
    if args.command == "rebuild":
        rebuild(args.study / "protocol.json", args.source, args.snapshot, args.out, args.threads)
    else:
        print(quote(args.study, args.source, args.task, args.method))


if __name__ == "__main__":
    main()
