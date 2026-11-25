"""SHA-256 records of the protocol and the scoring code, and the check against a freeze file."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
FREEZE_PACKAGES = ("fleet", "study", "pilot")
SCORING_PACKAGES = ("fleet", "study")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_source(path: Path) -> str:
    """SHA-256 of a source file with CRLF line endings read as LF.

    A checkout may convert line endings; the freeze must not depend on that.
    """
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def source_hashes(packages=SCORING_PACKAGES, root: Path = PACKAGE_ROOT) -> dict[str, str]:
    """SHA-256 of every .py file under root/<package>, keyed by 'package/relative/path'."""
    hashes = {}
    for package in packages:
        base = Path(root) / package
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            hashes[f"{package}/{path.relative_to(base).as_posix()}"] = sha256_source(path)
    return hashes


def write_freeze(protocol: Path, out: Path, root: Path = PACKAGE_ROOT) -> dict:
    """Write the freeze record; refuses to overwrite."""
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"{out} already exists")
    record = {
        "frozen_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "protocol": {"file": Path(protocol).name, "sha256": sha256_source(Path(protocol))},
        "sources": source_hashes(FREEZE_PACKAGES, root),
    }
    with open(out, "x", encoding="utf-8") as handle:
        handle.write(json.dumps(record, indent=2) + "\n")
    return record


def check_freeze(freeze: Path, protocol: Path | None = None, root: Path = PACKAGE_ROOT) -> None:
    """Raise ValueError if the protocol or any frozen package's .py files differ from the record.

    Added and removed files count as differences.
    """
    record = json.loads(Path(freeze).read_text(encoding="utf-8"))
    problems = []
    if protocol is not None and sha256_source(Path(protocol)) != record["protocol"]["sha256"]:
        problems.append("protocol")
    now = source_hashes(FREEZE_PACKAGES, root)
    frozen = record["sources"]
    for name in sorted(set(now) | set(frozen)):
        if now.get(name) != frozen.get(name):
            problems.append(name)
    if problems:
        raise ValueError(f"differs from freeze {freeze}: {', '.join(problems)}")
