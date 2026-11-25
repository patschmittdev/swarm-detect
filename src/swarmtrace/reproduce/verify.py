"""Read-only artifact verification and portable checkout provenance."""

import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath

SHARING_HASH_START = "```swarmtrace-sharing-sha256"
SHARING_HASH_HEADER = "path | sha256"
SHARING_PATHS = tuple(f"sharing-sweep/rate-{rate}/runs.csv.gz" for rate in (0, 5, 10, 30))
EVASION_HASH_START = "```swarmtrace-evasion-sha256"
EVASION_PATHS = ("evasion/runs.csv.gz",)
EXPERIMENT_REPORTS = (
    ("sharing-sweep.md", "sharing-sweep", SHARING_HASH_START, SHARING_PATHS),
    ("evasion.md", "evasion", EVASION_HASH_START, None),
    ("scope.md", "scope", None, None),
    ("containment.md", "containment", None, None),
)
"""A None path tuple allows raw rows; a None fence selects the sha256sum parser."""


def find_checkout_root() -> Path | None:
    """Accept only the checkout whose src/swarmtrace is the running package directory."""
    package = Path(__file__).resolve().parents[1]
    root = package.parent.parent
    if package.is_dir() and (root / "src" / "swarmtrace").resolve() == package:
        return root
    return None


def lock_digest(root: Path) -> str:
    """Hash uv.lock with checkout line endings normalized to LF."""
    content = (root / "uv.lock").read_bytes()
    return hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


def source_digest(root: Path) -> str:
    """Hash sorted POSIX paths, NUL, 8-byte big-endian length, and LF-normalized bytes."""
    source = root / "src" / "swarmtrace"
    paths = sorted(
        (path for path in source.rglob("*.py", case_sensitive=True) if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    if not paths:
        raise FileNotFoundError("no Python source files found in src/swarmtrace")
    digest = hashlib.sha256()
    for path in paths:
        content = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def provenance_digests(root: Path | None = None) -> dict[str, str]:
    """Record both digests, warning once if expected missing or unreadable inputs prevent it."""
    root = find_checkout_root() if root is None else root
    if root is None:
        reason = "no checkout found"
    else:
        try:
            lock = lock_digest(root)
        except FileNotFoundError:
            reason = "uv.lock missing"
        except PermissionError:
            reason = "uv.lock unreadable"
        else:
            try:
                source = source_digest(root)
            except (FileNotFoundError, PermissionError):
                reason = "source unreadable"
            else:
                return {"uv_lock_sha256": lock, "source_sha256": source}
    print(f"warning: experiment provenance omitted: {reason}", file=sys.stderr)
    return {}


def _is_digest(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(character in "0123456789abcdef" for character in value))


def _valid_artifact_path(data: Path, name: str) -> bool:
    relative = PurePosixPath(name)
    return bool(name and not relative.is_absolute() and ".." not in relative.parts
                and "\\" not in name and ":" not in name
                and (data / name).resolve().is_relative_to(data.resolve()))


def _sha256sum_hashes(data: Path, report_name: str, lines: list[str]) -> dict[str, str]:
    fences = [index for index, line in enumerate(lines)
              if line.lstrip().startswith(("```", "~~~"))]
    if (len(fences) != 2 or lines[fences[0]] not in {"```", "```text"}
            or fences[1] != len(lines) - 1 or lines[fences[1]] != "```"
            or fences[1] <= fences[0] + 1):
        raise ValueError(f"malformed {report_name}: expected one final sha256sum block")
    hashes = {}
    for line in lines[fences[0] + 1:fences[1]]:
        match = re.fullmatch(r"([0-9a-f]{64})  (\S(?:.*\S)?)", line)
        if match is None:
            raise ValueError(f"malformed {report_name}: expected SHA-256, two spaces and path")
        digest, name = match.groups()
        if not _valid_artifact_path(data, name):
            raise ValueError(f"invalid artifact path in {report_name}: {name}")
        if name in hashes:
            raise ValueError(f"malformed {report_name}: duplicate artifact path: {name}")
        hashes[name] = digest
    return hashes


def _variable_table_hashes(
    data: Path, report_name: str, directory: str, block: list[str],
) -> dict[str, str]:
    if len(block) < 4 or block[1] != SHARING_HASH_HEADER or block[-1] != "```":
        raise ValueError(f"malformed {report_name}: expected final path | sha256 block")
    hashes = {}
    for row in block[2:-1]:
        name, separator, digest = row.partition(" | ")
        if not separator or not _is_digest(digest):
            raise ValueError(f"malformed {report_name}: expected SHA-256 row")
        if not _valid_artifact_path(data, name) or PurePosixPath(name).as_posix() != name:
            raise ValueError(f"invalid artifact path in {report_name}: {name}")
        if name in hashes:
            raise ValueError(f"malformed {report_name}: duplicate artifact path: {name}")
        hashes[name] = digest
    names = list(hashes)
    raw = names[1:]
    if (names[0] != f"{directory}/runs.csv.gz" or raw != sorted(raw)
            or any(not name.startswith(f"{directory}/raw/") for name in raw)):
        raise ValueError(f"malformed {report_name}: expected runs table then sorted raw paths")
    return hashes


def _experiment_hashes(
    data: Path, report_name: str, directory: str, fence: str | None,
    paths: tuple[str, ...] | None,
) -> dict[str, str]:
    """Read one report's declared hash format; absent reports require absent artifacts."""
    report = data / report_name
    if not report.exists():
        sweep = data / directory
        if sweep.exists() and (not sweep.is_dir() or any(path.is_file()
                                                       for path in sweep.rglob("*"))):
            raise ValueError(f"missing {report_name} for {directory} artifacts")
        return {}
    try:
        lines = report.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ValueError(f"cannot read {report_name}: {error}") from error
    if fence is None:
        return _sha256sum_hashes(data, report_name, lines)
    if lines.count(fence) != 1:
        raise ValueError(f"malformed {report_name}: expected one sweep hash block")
    block = lines[lines.index(fence):]
    if paths is None:
        if sum(line.lstrip().startswith(("```", "~~~")) for line in lines) != 2:
            raise ValueError(f"malformed {report_name}: expected one final hash block")
        return _variable_table_hashes(data, report_name, directory, block)
    if (len(block) != len(paths) + 3 or block[1] != SHARING_HASH_HEADER
            or block[-1] != "```"):
        raise ValueError(f"malformed {report_name}: expected final path | sha256 block")
    hashes = {}
    for expected, row in zip(paths, block[2:-1], strict=True):
        prefix = expected + " | "
        if not row.startswith(prefix) or not _is_digest(row[len(prefix):]):
            raise ValueError(f"malformed {report_name}: expected SHA-256 row for {expected}")
        hashes[expected] = row[len(prefix):]
    return hashes


def verify(data: str | Path, *, root: Path | None = None) -> None:
    """Check all listed artifact bytes; source drift and absent provenance only warn.

    Lockfile drift and artifact failures raise ValueError for the CLI's exit-1
    handling. Diagnostics are printed, rather than emitted as Python warnings, so
    informational provenance differences remain non-fatal under -W error.

    Each experiment report's final hash block lists separately verified artifacts,
    without adding them to experiment.json. Only report files are excluded from the
    unlisted-file warning; raw samples must be listed too.
    """
    data = Path(data)
    root = find_checkout_root() if root is None else root
    try:
        manifest = json.loads((data / "experiment.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read experiment.json: {error}") from error
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("artifacts_sha256"), dict)
            or not manifest["artifacts_sha256"]):
        raise ValueError("experiment.json must contain a non-empty artifacts_sha256 mapping")
    artifacts = dict(manifest["artifacts_sha256"])
    if any(not isinstance(name, str) or not _is_digest(digest)
           for name, digest in artifacts.items()):
        raise ValueError("experiment.json artifacts_sha256 must map paths to SHA-256 digests")
    failures, warnings = [], []
    reports_by_artifact = {}
    for report_name, directory, fence, paths in EXPERIMENT_REPORTS:
        try:
            hashes = _experiment_hashes(data, report_name, directory, fence, paths)
        except ValueError as error:
            if (data / report_name).exists():
                raise
            # Keep the missing-report failure, but also emit unlisted-file warnings below.
            failures.append(str(error))
            continue
        for name, digest in hashes.items():
            if name in artifacts and artifacts[name] != digest:
                raise ValueError(f"conflicting artifact hashes in {report_name}: {name}")
            artifacts[name] = digest
            if paths is None:
                reports_by_artifact[name] = report_name

    listed = set()
    matched = 0
    for name, expected in sorted(artifacts.items()):
        relative = PurePosixPath(name)
        path = data / name
        origin = f" (listed in {reports_by_artifact[name]})" if name in reports_by_artifact else ""
        if not _valid_artifact_path(data, name):
            failures.append(f"invalid artifact path: {name}")
            continue
        listed.add(relative.as_posix())
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except FileNotFoundError:
            failures.append(f"missing artifact: {name}{origin}")
        except OSError as error:
            failures.append(f"cannot read artifact: {name}: {error}{origin}")
        else:
            if actual != expected:
                failures.append(f"artifact hash mismatch: {name} "
                                f"(expected {expected}, got {actual}){origin}")
            else:
                matched += 1

    excluded = {report[0] for report in EXPERIMENT_REPORTS} | {
        "experiment.json", "README.md", "split-stability.md", "scope-identical.md",
    }
    for path in sorted(data.rglob("*")):
        if path.is_file():
            name = path.relative_to(data).as_posix()
            if name in excluded:
                continue
            if name not in listed:
                warnings.append(f"unlisted artifact: {name}")

    checks = (("uv_lock_sha256", "lockfile", lock_digest),
              ("source_sha256", "source", source_digest))
    missing = [field for field, _, _ in checks if field not in manifest]
    if missing:
        warnings.append("experiment.json missing provenance fields: " + ", ".join(missing)
                        + "; their provenance cannot be checked")
    for field, label, compute in checks:
        if field in missing:
            continue
        messages = warnings if field == "source_sha256" else failures
        if not _is_digest(manifest[field]):
            failures.append(f"experiment.json has invalid SHA-256 field: {field}")
            continue
        if root is None:
            warnings.append(f"{label} digest {field} cannot be checked: no checkout")
            continue
        try:
            actual = compute(root)
        except (FileNotFoundError, PermissionError) as error:
            messages.append(f"{label} digest unavailable: {field}: {error}")
        else:
            if actual != manifest[field]:
                messages.append(f"{label} digest mismatch: {field} "
                                f"(expected {manifest[field]}, got {actual})")
    print(f"Artifact hashes: {matched} of {len(artifacts)} match.")
    for message in warnings:
        print(f"warning: {message}", file=sys.stderr)
    if failures:
        raise ValueError("verification failed:\n" + "\n".join(failures))
