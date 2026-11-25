"""Check the cited draft's approval consumption identities on selected, independently labelled data."""

import argparse
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

DRAFT = "draft-gruszka-audit-decision-receipts-10"
ARCHIVE_SHA256 = "9f3aa3711b3b332e009dc7edf6e276c866f3cd638b2a10670668fb7793790e43"
ARCHIVE_BYTES = 361812
REVISION = "984dc3e1a1b4bdac9542c6f02fb7648e6bba0560"
URL = (
    f"https://raw.githubusercontent.com/b7n0de/proofbundle/{REVISION}/drafts/"
    f"draft-gruszka-audit-decision-receipts/{DRAFT}-test-vectors.tar.gz"
)
# Each suffix identifies paired inputs and expected manifests. The base manifest holds four cases.
CASES = {
    ".json": ("F10", "F13", "F71", "F77"),
    "-08/60-v1-accept.json": ("V1-accept",),
    "-10/013-g14a.json": ("G14a",),
    "-10/014-g14b.json": ("G14b",),
    "-10/017-g16c.json": ("G16c",),
    "-10/343-cs1.json": ("CS1",),
    "-10/344-cs2.json": ("CS2",),
    "-10/345-cs3.json": ("CS3",),
    "-10/346-cs4.json": ("CS4",),
}


def _identity(entry):
    if not isinstance(entry, dict):
        return None
    approval_id, session, digest = (entry.get(key) for key in ("approvalId", "session", "actionDigest"))
    if not isinstance(approval_id, str) or not approval_id or not isinstance(session, str) or not session:
        return None
    if not isinstance(digest, dict) or digest.keys() != {"sha256"}:
        return None
    sha = digest["sha256"]
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        return None
    return approval_id, sha, session


def consumption_status(approval: dict, state_bytes: bytes) -> tuple[str, str | None]:
    """Compare the full identity and ID-only baseline after validating the supplied generations."""
    requested = _identity(approval)
    if requested is None:
        raise ValueError("the approval input must have a valid identity")
    try:
        state = json.loads(state_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return "unusable_view", None
    if isinstance(state, list):
        generations = [state]
    elif isinstance(state, dict) and state:
        generations = state.values()
    else:
        return "unusable_view", None

    spent = id_seen = False
    for entries in generations:
        if not isinstance(entries, list):
            return "unusable_view", None
        for entry in entries:
            key = _identity(entry)
            if key is None:
                return "unusable_view", None
            # A malformed entry in a later generation still makes the entire view unusable.
            spent |= key == requested
            id_seen |= key[0] == requested[0]
    return ("already_spent" if spent else "no_match", "already_spent" if id_seen else "no_match")


def _member(archive: tarfile.TarFile, relative: str) -> bytes:
    member = archive.getmember(f"{DRAFT}-test-vectors/{relative}")
    if not relative.endswith(".json") or not member.isfile():
        raise ValueError(f"expected a regular JSON member at {relative}")
    with archive.extractfile(member) as reader:
        return reader.read()


def _manifest(archive, prefix, suffix, names):
    rows = json.loads(_member(archive, prefix + suffix))["vectors"]
    selected = {row["name"]: row for row in rows if row["name"] in names}
    if len(selected) != len(names):
        raise ValueError(f"incomplete vector manifest {prefix}{suffix}")
    return selected


def _reference(row):
    if row["expected"] == "pass" and row["text_result"] == "pass, not refused under Section 4":
        return "no_match"
    if row["expected"] == "refuse":
        item = re.search(r"Section 4,? item ([145])\b", row["text_result"])
        if item:
            return "unusable_view" if item[1] == "5" else "already_spent"
    raise ValueError(f"unexpected Section 4 reference for {row['name']}")


def check_vectors(payload: bytes) -> dict:
    """Read selected JSON in memory. The publisher's expected labels enter only after prediction."""
    if len(payload) != ARCHIVE_BYTES or hashlib.sha256(payload).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("archive size or SHA-256 differs from the pinned draft package")
    cases = []
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for suffix, names in CASES.items():
            inputs = _manifest(archive, "inputs", suffix, names)
            references = _manifest(archive, "expected", suffix, names)
            for name in names:
                # Read only the two named JSON data files. Never run the recorded command.
                args = inputs[name]["verifier"]["argv"]
                approval_file = args[args.index("-approval") + 1]
                state_file = args[args.index("-consumed") + 1]
                approval = json.loads(_member(archive, approval_file))
                status, id_only = consumption_status(approval, _member(archive, state_file))
                cases.append({
                    "name": name, "approval_input": approval_file, "state_input": state_file,
                    "reference": _reference(references[name]), "full_identity": status,
                    "approval_id_only": id_only,
                })
    readable = [row for row in cases if row["approval_id_only"] is not None]
    return {
        "source": {"draft": DRAFT, "section": 4, "commit": REVISION, "url": URL,
                   "archive_sha256": ARCHIVE_SHA256, "archive_bytes": ARCHIVE_BYTES},
        "scope": (
            "All selected vectors pass the publisher's receipt check. This comparison covers "
            "Section 4 identity and validity of the supplied state. A no-match assumes a complete "
            "view. Authorization, durable enforcement, retention, actual effects and motive each "
            "require additional evidence. E1 to E21 concern the auditor's separate receipt check. "
            "F90 and G15a/b concern the expiry of received approval copies."
        ),
        "counts": {
            "vectors": len(cases),
            "match_publisher": sum(row["full_identity"] == row["reference"] for row in cases),
            "spent": sum(row["full_identity"] == "already_spent" for row in cases),
            "no_match": sum(row["full_identity"] == "no_match" for row in cases),
            "unusable_supplied_view": len(cases) - len(readable),
            "readable_for_id_only": len(readable),
            "id_only_matches_on_readable": sum(row["approval_id_only"] == row["reference"] for row in readable),
            "id_only_false_spent": sum(
                row["approval_id_only"] == "already_spent" and row["reference"] == "no_match"
                for row in readable
            ),
            "independent_swarm_accuracy_rounds": 0,
        },
        "vectors": cases,
    }


def _publish(path: Path, payload: bytes) -> None:
    """Publish complete bytes without replacing another file, including on concurrent retries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as writer:
        temporary = Path(writer.name)
        writer.write(payload)
    try:
        try:
            path.hardlink_to(temporary)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != payload:
                raise ValueError(f"conflicting file {path}") from None
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--archive", type=Path, help="read the pinned local .tar.gz")
    source.add_argument("--fetch", action="store_true", help="read the fixed upstream archive in memory")
    parser.add_argument("--out", type=Path, help="write the derived JSON, or print it when omitted")
    args = parser.parse_args()
    stream = urlopen(URL, timeout=45) if args.fetch else args.archive.open("rb")
    with stream:
        report = check_vectors(stream.read(ARCHIVE_BYTES + 1))
    result = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out is None:
        print(result, end="")
    else:
        _publish(args.out, result.encode("utf-8"))


if __name__ == "__main__":
    main()
