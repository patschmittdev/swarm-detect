import errno
import hashlib
import json
from pathlib import Path

import pytest

from swarmtrace.cli import main
from swarmtrace.reproduce.pipeline import _write_experiment
from swarmtrace.reproduce.verify import (
    EXPERIMENT_REPORTS,
    _experiment_hashes,
    find_checkout_root,
    lock_digest,
    provenance_digests,
    source_digest,
    verify,
)
from swarmtrace.sim.runner import Condition, run_one

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIGEST_FIELDS = ("uv_lock_sha256", "source_sha256")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def _read_manifest(data: Path) -> dict:
    return json.loads((data / "experiment.json").read_text(encoding="utf-8"))


def _save_manifest(data: Path, manifest: dict) -> None:
    (data / "experiment.json").write_text(json.dumps(manifest), encoding="utf-8", newline="\n")


@pytest.fixture
def source_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "checkout"
    source = root / "src" / "swarmtrace"
    (source / "a").mkdir(parents=True)
    # Creation order differs from case-sensitive POSIX path order on both platforms.
    (source / "a" / "nested.py").write_bytes(b"nested = 3\n")
    (source / "a.py").write_bytes(b"value = 2\n")
    (source / "Z.py").write_bytes(b"value = 1\n")
    (root / "uv.lock").write_bytes(b"version = 1\nrevision = 3\n")
    monkeypatch.setattr("swarmtrace.reproduce.verify.__file__",
                        str(source / "reproduce" / "verify.py"))
    monkeypatch.chdir(tmp_path)
    return root


@pytest.fixture
def generated_data(tmp_path: Path, source_tree: Path) -> Path:
    data = tmp_path / "recorded"
    run_one(Condition("message", "peer", 0, 1, 8), 20261120, data / "raw" / "sample")
    (data / "artifact.bin").write_bytes(b"\x00\xff\r\n\x80")
    _write_experiment(data, {"format": "swarmtrace-experiment-v1", "config": {"seed": 20261120}})
    return data


@pytest.mark.parametrize("relative", ["src/swarmtrace", "src/unused/../swarmtrace"])
def test_checkout_discovery_accepts_the_resolved_in_tree_package(
    source_tree: Path, monkeypatch: pytest.MonkeyPatch, relative: str,
) -> None:
    monkeypatch.setattr("swarmtrace.reproduce.verify.__file__",
                        str(source_tree / relative / "reproduce" / "verify.py"))
    assert find_checkout_root() == source_tree
    assert provenance_digests() == provenance_digests(source_tree)


@pytest.mark.parametrize("location", ["outside", "venv"])
def test_checkout_discovery_rejects_installed_package_even_when_cwd_is_a_checkout(
    source_tree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], location: str,
) -> None:
    installed = tmp_path / "installed" if location == "outside" else source_tree / ".venv"
    package = installed / "lib" / "site-packages" / "swarmtrace"
    package.mkdir(parents=True)
    (installed / "uv.lock").write_bytes(b"unrelated lockfile\n")
    monkeypatch.setattr("swarmtrace.reproduce.verify.__file__",
                        str(package / "reproduce" / "verify.py"))
    monkeypatch.chdir(source_tree / "src" / "swarmtrace" / "a")
    assert find_checkout_root() is None
    assert provenance_digests() == {}
    assert capsys.readouterr().err == "warning: experiment provenance omitted: no checkout found\n"


@pytest.mark.parametrize(("unavailable", "reason"), [
    ("no-checkout", "no checkout found"),
    ("uv.lock", "uv.lock missing"),
    ("src/swarmtrace/a.py", "source unreadable"),
])
def test_writer_omits_unavailable_provenance_and_verify_still_checks_artifacts(
    generated_data: Path, source_tree: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], unavailable: str, reason: str,
) -> None:
    expected = _read_manifest(generated_data)
    for field in DIGEST_FIELDS:
        expected.pop(field)
    (generated_data / "experiment.json").unlink()
    artifacts = _snapshot(generated_data)
    if unavailable == "no-checkout":
        monkeypatch.setattr("swarmtrace.reproduce.verify.find_checkout_root", lambda: None)
    elif unavailable == "uv.lock":
        (source_tree / "uv.lock").unlink()
        assert find_checkout_root() == source_tree
    else:
        original = Path.read_bytes

        def unreadable_provenance(path: Path) -> bytes:
            if path == source_tree / unavailable:
                raise PermissionError("provenance unavailable")
            return original(path)

        monkeypatch.setattr(Path, "read_bytes", unreadable_provenance)

    _write_experiment(generated_data,
                      {"format": "swarmtrace-experiment-v1", "config": {"seed": 20261120}})
    output = capsys.readouterr()
    assert output.err == f"warning: experiment provenance omitted: {reason}\n"
    assert not output.out
    assert _read_manifest(generated_data) == expected
    after = _snapshot(generated_data)
    after.pop("experiment.json")
    assert after == artifacts
    main(["verify", "--data", str(generated_data)])
    output = capsys.readouterr()
    assert "warning: experiment.json missing provenance fields:" in output.err
    assert all(field in output.err for field in DIGEST_FIELDS)
    assert "Artifact hashes: 4 of 4 match" in output.out
    assert "mismatch" not in output.err


@pytest.mark.parametrize("unreadable", ["uv.lock", "src/swarmtrace/a.py"])
@pytest.mark.parametrize("failure", [OSError(errno.EIO, "unexpected read failure"),
                                    ValueError("unexpected digest bug")])
def test_writer_propagates_unexpected_provenance_errors(
    generated_data: Path, source_tree: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], unreadable: str, failure: Exception,
) -> None:
    (generated_data / "experiment.json").unlink()
    before = _snapshot(generated_data)
    original = Path.read_bytes

    def broken_read(path: Path) -> bytes:
        if path == source_tree / unreadable:
            raise failure
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", broken_read)
    with pytest.raises(type(failure)) as error:
        _write_experiment(generated_data, {"format": "swarmtrace-experiment-v1"})
    assert error.value is failure
    assert not capsys.readouterr().err
    assert _snapshot(generated_data) == before


def test_source_digest_uses_sorted_posix_paths_and_file_bytes(source_tree: Path) -> None:
    expected = hashlib.sha256()
    for name, content in (
        ("src/swarmtrace/Z.py", b"value = 1\n"),
        ("src/swarmtrace/a.py", b"value = 2\n"),
        ("src/swarmtrace/a/nested.py", b"nested = 3\n"),
    ):
        expected.update(name.encode("utf-8") + b"\0")
        expected.update(len(content).to_bytes(8, "big"))
        expected.update(content)
    assert source_digest(source_tree) == expected.hexdigest()
    original = source_digest(source_tree)
    source = source_tree / "src" / "swarmtrace"
    (source / "a.py").rename(source / "renamed.py")
    assert source_digest(source_tree) != original


def test_provenance_normalizes_crlf_and_ignores_non_source_files(source_tree: Path) -> None:
    expected = provenance_digests(source_tree)
    assert expected["uv_lock_sha256"] == hashlib.sha256(
        b"version = 1\nrevision = 3\n").hexdigest()
    for path in [source_tree / "uv.lock", *source_tree.rglob("*.py")]:
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    source = source_tree / "src" / "swarmtrace"
    (source / "notes.txt").write_bytes(b"not Python source\n")
    (source / "ignored.PY").write_bytes(b"outside_lowercase_glob = True\n")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "a.pyc").write_bytes(b"bytecode")
    (source_tree / "unrelated.py").write_bytes(b"outside = True\n")
    assert provenance_digests(source_tree) == expected
    assert lock_digest(source_tree) == expected["uv_lock_sha256"]


def test_writer_adds_provenance_without_changing_artifacts(
    generated_data: Path, source_tree: Path,
) -> None:
    manifest = _read_manifest(generated_data)
    assert {field: manifest[field] for field in DIGEST_FIELDS} == provenance_digests(source_tree)
    artifacts = _snapshot(generated_data)
    artifacts.pop("experiment.json")
    assert manifest["artifacts_sha256"] == {
        name: hashlib.sha256(content).hexdigest() for name, content in artifacts.items()
    }
    assert not set(DIGEST_FIELDS) & json.loads(artifacts["raw/sample/manifest.json"]).keys()

    # Re-record identical artifacts after a source revision, without running the simulator again.
    (source_tree / "src" / "swarmtrace" / "a.py").write_bytes(b"value = 99\n")
    (generated_data / "experiment.json").unlink()
    _write_experiment(generated_data,
                      {"format": "swarmtrace-experiment-v1", "config": {"seed": 20261120}})
    revised = _read_manifest(generated_data)
    assert revised.pop("source_sha256") != manifest.pop("source_sha256")
    assert revised == manifest
    after = _snapshot(generated_data)
    after.pop("experiment.json")
    assert after == artifacts


def test_verify_generated_data_is_read_only(
    generated_data: Path, source_tree: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    before = _snapshot(generated_data), _snapshot(source_tree)
    verify(generated_data)
    output = capsys.readouterr()
    count = len(_read_manifest(generated_data)["artifacts_sha256"])
    assert f"Artifact hashes: {count} of {count} match" in output.out
    assert not output.err
    assert (_snapshot(generated_data), _snapshot(source_tree)) == before


def test_verify_flipped_byte_exits_one_without_usage(
    generated_data: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    artifact = generated_data / "artifact.bin"
    content = bytearray(artifact.read_bytes())
    content[0] ^= 1
    artifact.write_bytes(content)
    before = _snapshot(generated_data)
    with pytest.raises(SystemExit) as error:
        main(["verify", "--data", str(generated_data)])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "verification failed:" in output.err
    assert "artifact hash mismatch: artifact.bin" in output.err
    assert "usage:" not in output.err
    assert "warning:" not in output.err
    assert _snapshot(generated_data) == before


def test_verify_names_all_failed_artifacts(
    generated_data: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    (generated_data / "artifact.bin").write_bytes(b"changed")
    (generated_data / "raw" / "sample" / "trace.jsonl").unlink()
    with pytest.raises(SystemExit) as error:
        main(["verify", "--data", str(generated_data)])
    assert error.value.code == 1
    message = capsys.readouterr().err
    assert "artifact hash mismatch: artifact.bin" in message
    assert "missing artifact: raw/sample/trace.jsonl" in message
    assert "usage:" not in message


def test_verify_does_not_normalize_artifact_bytes(generated_data: Path) -> None:
    artifact = generated_data / "artifact.bin"
    artifact.write_bytes(artifact.read_bytes().replace(b"\r\n", b"\n"))
    with pytest.raises(ValueError, match="artifact hash mismatch: artifact.bin"):
        verify(generated_data)


def test_source_mismatch_is_only_a_warning(
    generated_data: Path, source_tree: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    (source_tree / "src" / "swarmtrace" / "a.py").write_bytes(b"value = 99\n")
    assert main(["verify", "--data", str(generated_data)]) is None
    output = capsys.readouterr()
    assert "warning: source digest mismatch: source_sha256" in output.err
    assert "artifact hash mismatch" not in output.err
    assert "Artifact hashes: 4 of 4 match" in output.out


def test_source_warning_does_not_hide_artifact_failure(
    generated_data: Path, source_tree: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    (source_tree / "src" / "swarmtrace" / "a.py").write_bytes(b"value = 99\n")
    (generated_data / "artifact.bin").unlink()
    with pytest.raises(SystemExit) as error:
        main(["verify", "--data", str(generated_data)])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "warning: source digest mismatch: source_sha256" in output.err
    assert "missing artifact: artifact.bin" in output.err
    assert "usage:" not in output.err


def test_lock_mismatch_exits_one_without_usage(
    generated_data: Path, source_tree: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    (source_tree / "uv.lock").write_bytes(b"version = 2\n")
    with pytest.raises(SystemExit) as error:
        main(["verify", "--data", str(generated_data)])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "lockfile digest mismatch: uv_lock_sha256" in output.err
    assert "usage:" not in output.err


def test_recorded_digests_without_checkout_only_warn(
    generated_data: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("swarmtrace.reproduce.verify.find_checkout_root", lambda: None)
    before = _snapshot(generated_data)
    assert main(["verify", "--data", str(generated_data)]) is None
    output = capsys.readouterr()
    assert output.err.splitlines() == [
        "warning: lockfile digest uv_lock_sha256 cannot be checked: no checkout",
        "warning: source digest source_sha256 cannot be checked: no checkout",
    ]
    assert "Artifact hashes: 4 of 4 match" in output.out
    assert _snapshot(generated_data) == before
    (generated_data / "artifact.bin").write_bytes(b"changed")
    with pytest.raises(SystemExit) as error:
        main(["verify", "--data", str(generated_data)])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "artifact hash mismatch: artifact.bin" in output.err
    assert "usage:" not in output.err


@pytest.mark.parametrize("missing", [("source_sha256",), ("uv_lock_sha256",), DIGEST_FIELDS])
def test_missing_digests_warn_and_still_check_artifacts(
    generated_data: Path, capsys: pytest.CaptureFixture[str], missing: tuple[str, ...],
) -> None:
    manifest = _read_manifest(generated_data)
    for field in missing:
        manifest.pop(field)
    _save_manifest(generated_data, manifest)
    main(["verify", "--data", str(generated_data)])
    output = capsys.readouterr()
    assert "warning: experiment.json missing provenance fields:" in output.err
    assert all(field in output.err for field in missing)
    assert "Artifact hashes: 4 of 4 match" in output.out
    (generated_data / "artifact.bin").write_bytes(b"changed")
    with pytest.raises(SystemExit) as error:
        main(["verify", "--data", str(generated_data)])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "artifact hash mismatch: artifact.bin" in output.err
    assert all(field in output.err for field in missing)
    assert "usage:" not in output.err


@pytest.mark.parametrize("name", ["../x", r"..\x", "/x", r"C:\x", "C:/x", "C:x"])
def test_verify_rejects_paths_outside_data_without_reading_them(
    generated_data: Path, source_tree: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], name: str,
) -> None:
    manifest = _read_manifest(generated_data)
    manifest["artifacts_sha256"][name] = "0" * 64
    _save_manifest(generated_data, manifest)
    original = Path.read_bytes

    def confined_read(path: Path) -> bytes:
        resolved = path.resolve()
        assert (resolved.is_relative_to(generated_data.resolve())
                or resolved.is_relative_to(source_tree.resolve())), (
            f"verification tried to read outside its data and checkout: {path}"
        )
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", confined_read)
    with pytest.raises(SystemExit) as error:
        main(["verify", "--data", str(generated_data)])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert f"invalid artifact path: {name}" in output.err
    assert "usage:" not in output.err


def test_unlisted_files_warn_and_verification_still_exits_zero(
    generated_data: Path, source_tree: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    for name in ("extra.bin", "nested/extra.txt", "README.md", "split-stability.md"):
        path = generated_data / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"unlisted\n")
    before = _snapshot(generated_data), _snapshot(source_tree)
    assert main(["verify", "--data", str(generated_data)]) is None
    output = capsys.readouterr()
    assert output.err.splitlines() == [
        "warning: unlisted artifact: extra.bin",
        "warning: unlisted artifact: nested/extra.txt",
    ]
    assert "Artifact hashes: 4 of 4 match" in output.out
    assert (_snapshot(generated_data), _snapshot(source_tree)) == before


def test_verify_committed_data_matches_every_artifact(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = PROJECT_ROOT / "data"
    manifest = _read_manifest(data)
    expected = {data / name for name in manifest["artifacts_sha256"]}
    assert expected
    for report_name, directory, fence, paths in EXPERIMENT_REPORTS:
        if (data / report_name).exists():
            expected.update(data / name for name in
                            _experiment_hashes(data, report_name, directory, fence, paths))
    assert all(field in manifest for field in DIGEST_FIELDS)
    before = _snapshot(data)
    read: set[Path] = set()
    original = Path.read_bytes

    def track_read(path: Path) -> bytes:
        read.add(path)
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", track_read)
    main(["verify", "--data", str(data)])
    assert expected <= read
    output = capsys.readouterr()
    assert f"Artifact hashes: {len(expected)} of {len(expected)} match" in output.out
    assert "warning: experiment.json missing provenance fields:" not in output.err
    assert "artifact hash mismatch:" not in output.err
    # Source edits after regeneration may warn; all other verification checks stay strict.
    source_warning = (
        "warning: source digest mismatch: source_sha256 "
        f"(expected {manifest['source_sha256']}, got {source_digest(PROJECT_ROOT)})"
    )
    assert output.err.splitlines() in ([], [source_warning])
    assert _snapshot(data) == before


@pytest.mark.parametrize("content", [None, "{", "[]", "{}", '{"artifacts_sha256": []}',
                                     '{"artifacts_sha256": {}}'])
def test_invalid_or_empty_experiment_exits_one_without_usage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str | None,
) -> None:
    if content is not None:
        (tmp_path / "experiment.json").write_text(content, encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        main(["verify", "--data", str(tmp_path)])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "experiment.json" in output.err
    assert "usage:" not in output.err
    assert "0 of 0 match" not in output.out


@pytest.mark.parametrize("arguments", [["verify"], ["verify", "--data"],
                                       ["verify", "--data", "data", "--unknown"]])
def test_verify_argument_errors_still_exit_two_with_usage(
    capsys: pytest.CaptureFixture[str], arguments: list[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2
    output = capsys.readouterr()
    assert "usage:" in output.err
    assert "error:" in output.err


@pytest.fixture
def evasion_data(generated_data: Path) -> Path:
    path = generated_data / "evasion/runs.csv.gz"
    path.parent.mkdir()
    path.write_bytes(b"recorded evasion table\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (generated_data / "evasion.md").write_text(
        "# Evasion\n\n```swarmtrace-evasion-sha256\npath | sha256\n"
        f"evasion/runs.csv.gz | {digest}\n```\n", encoding="utf-8",
    )
    return generated_data


def test_verify_accepts_evasion_hashes_and_listed_raw_samples(
    evasion_data: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    raw = evasion_data / "evasion/raw/standard/sample/trace.jsonl"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"sample\n")
    _write_evasion_hash_block(evasion_data)
    before = _snapshot(evasion_data)
    verify(evasion_data)
    output = capsys.readouterr()
    assert "6 of 6 match" in output.out
    assert "unlisted artifact: evasion/raw/standard/sample/trace.jsonl" not in output.err
    assert "unlisted artifact: evasion.md" not in output.err
    assert "unlisted artifact: evasion/runs.csv.gz" not in output.err
    assert _snapshot(evasion_data) == before


@pytest.mark.parametrize("mutation", ("mismatch", "missing"))
def test_verify_rejects_changed_or_missing_evasion_table(evasion_data: Path, mutation: str) -> None:
    path = evasion_data / "evasion/runs.csv.gz"
    if mutation == "missing":
        path.unlink()
    else:
        path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="evasion/runs.csv.gz"):
        verify(evasion_data)


@pytest.mark.parametrize("mutation", (
    "no-block", "duplicate-block", "wrong-header", "wrong-path", "bad-digest",
    "missing-row", "extra-row", "no-end", "trailing-text", "missing-report",
))
def test_verify_rejects_malformed_evasion_block(evasion_data: Path, mutation: str) -> None:
    report = evasion_data / "evasion.md"
    text = report.read_text(encoding="utf-8")
    lines = text.splitlines()
    if mutation == "missing-report":
        report.unlink()
    else:
        if mutation == "no-block":
            text = "# Evasion\n"
        elif mutation == "duplicate-block":
            text += "\n".join(lines[2:]) + "\n"
        elif mutation == "wrong-header":
            text = text.replace("path | sha256", "file | hash")
        elif mutation == "wrong-path":
            text = text.replace("evasion/runs.csv.gz", "../runs.csv.gz")
        elif mutation == "bad-digest":
            text = text.replace(lines[-2].split(" | ")[1], "x" * 64)
        elif mutation == "missing-row":
            text = text.replace(lines[-2] + "\n", "")
        elif mutation == "extra-row":
            text = text.replace("\n```\n", f"\n{lines[-2]}\n```\n")
        elif mutation == "no-end":
            text = text.removesuffix("```\n")
        else:
            text += "trailing text\n"
        report.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="evasion.md"):
        verify(evasion_data)


def test_verify_accepts_absent_evasion_experiment(generated_data: Path) -> None:
    (generated_data / "evasion/raw").mkdir(parents=True)
    verify(generated_data)


def test_verify_requires_evasion_report_even_for_raw_only_artifacts(generated_data: Path) -> None:
    raw = generated_data / "evasion/raw/standard/sample/trace.jsonl"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"sample")
    with pytest.raises(ValueError, match="missing evasion.md"):
        verify(generated_data)


def test_verify_accepts_both_experiment_reports_together(
    evasion_data: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    lines = ["# Sharing sweep", "", "```swarmtrace-sharing-sha256", "path | sha256"]
    for rate in (0, 5, 10, 30):
        name = f"sharing-sweep/rate-{rate}/runs.csv.gz"
        path = evasion_data / name
        path.parent.mkdir(parents=True)
        path.write_bytes(f"rate {rate}".encode())
        lines.append(f"{name} | {hashlib.sha256(path.read_bytes()).hexdigest()}")
    (evasion_data / "sharing-sweep.md").write_text(
        "\n".join([*lines, "```", ""]), encoding="utf-8",
    )
    verify(evasion_data)
    output = capsys.readouterr()
    assert "9 of 9 match" in output.out
    assert "unlisted artifact" not in output.err


def test_verify_rejects_conflicting_evasion_hash_in_main_manifest(evasion_data: Path) -> None:
    manifest = _read_manifest(evasion_data)
    manifest["artifacts_sha256"]["evasion/runs.csv.gz"] = "0" * 64
    _save_manifest(evasion_data, manifest)
    with pytest.raises(ValueError, match="conflicting artifact hashes in evasion.md"):
        verify(evasion_data)


@pytest.mark.parametrize("report_exists", (True, False))
def test_verify_unlisted_raw_samples_warn_with_or_without_report(
    evasion_data: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    report_exists: bool,
) -> None:
    samples = []
    for style in ("standard", "owner_silent"):
        for filename in ("trace.jsonl", "labels.json", "manifest.json"):
            path = evasion_data / "evasion/raw" / style / "sample" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"unlisted sample, not hash-verified\n")
            samples.append(path)
    if not report_exists:
        (evasion_data / "evasion.md").unlink()
        (evasion_data / "evasion/runs.csv.gz").unlink()
    before = _snapshot(evasion_data)
    original = Path.read_bytes

    def guarded_read(path: Path) -> bytes:
        assert path not in samples, "unlisted raw samples must not be hash-verified"
        return original(path)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", guarded_read)
        if report_exists:
            verify(evasion_data)
        else:
            with pytest.raises(ValueError, match="missing evasion.md"):
                verify(evasion_data)
    output = capsys.readouterr()
    expected = [
        f"warning: unlisted artifact: {path.relative_to(evasion_data).as_posix()}"
        for path in sorted(samples)
    ]
    assert output.err.splitlines() == expected
    assert _snapshot(evasion_data) == before


@pytest.mark.parametrize("relative", ("evasion/extra.bin", "evasion/raw-extra/sample.bin"))
def test_verify_still_warns_for_evasion_files_outside_raw(
    evasion_data: Path, capsys: pytest.CaptureFixture[str], relative: str,
) -> None:
    path = evasion_data / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"unlisted\n")
    before = _snapshot(evasion_data)
    verify(evasion_data)
    output = capsys.readouterr()
    assert output.err.splitlines() == [f"warning: unlisted artifact: {relative}"]
    assert "5 of 5 match" in output.out
    assert _snapshot(evasion_data) == before


def _write_evasion_hash_block(data: Path) -> None:
    paths = [data / "evasion/runs.csv.gz", *sorted(
        (path for path in (data / "evasion/raw").rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(data).as_posix(),
    )]
    rows = [f"{path.relative_to(data).as_posix()} | {hashlib.sha256(path.read_bytes()).hexdigest()}"
            for path in paths]
    (data / "evasion.md").write_text(
        "# Evasion\n\n```swarmtrace-evasion-sha256\npath | sha256\n"
        + "\n".join(rows) + "\n```\n", encoding="utf-8",
    )


@pytest.mark.parametrize("mutation", ("tampered", "missing", "extra"))
def test_verify_hash_checks_listed_evasion_raw_and_warns_for_extras(
    evasion_data: Path, capsys: pytest.CaptureFixture[str], mutation: str,
) -> None:
    raw = evasion_data / "evasion/raw/standard/sample/trace.jsonl"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"sample\n")
    _write_evasion_hash_block(evasion_data)
    if mutation == "extra":
        extra = raw.with_name("README.md")
        extra.write_bytes(b"unlisted")
        verify(evasion_data)
        assert capsys.readouterr().err.splitlines() == [
            "warning: unlisted artifact: evasion/raw/standard/sample/README.md",
        ]
    else:
        if mutation == "missing":
            raw.unlink()
        else:
            raw.write_bytes(b"changed")
        with pytest.raises(ValueError, match="evasion.md") as error:
            verify(evasion_data)
        assert "evasion/raw/standard/sample/trace.jsonl" in str(error.value)
        expected = "missing artifact" if mutation == "missing" else "hash mismatch"
        assert expected in str(error.value)


@pytest.mark.parametrize("mutation", (
    "order", "table-last", "duplicate", "outside-raw", "traversal",
))
def test_verify_rejects_invalid_evasion_raw_hash_rows(evasion_data: Path, mutation: str) -> None:
    for name in ("a", "b"):
        path = evasion_data / f"evasion/raw/{name}/trace.jsonl"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"sample")
    _write_evasion_hash_block(evasion_data)
    report = evasion_data / "evasion.md"
    lines = report.read_text(encoding="utf-8").splitlines()
    if mutation == "order":
        lines[-3], lines[-2] = lines[-2], lines[-3]
    elif mutation == "table-last":
        lines[-4], lines[-2] = lines[-2], lines[-4]
    elif mutation == "duplicate":
        lines[-2] = lines[-3]
    else:
        replacement = "evasion/extra.bin" if mutation == "outside-raw" else "evasion/raw/../bad"
        lines[-2] = lines[-2].replace("evasion/raw/b/trace.jsonl", replacement)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="evasion.md"):
        verify(evasion_data)


@pytest.fixture(params=("scope", "containment"))
def sha256sum_report(generated_data: Path, request: pytest.FixtureRequest) -> tuple[Path, str]:
    directory = request.param
    names = (f"{directory}/runs.csv.gz", f"{directory}/raw/sample/context.json")
    rows = []
    for name in names:
        path = generated_data / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode("utf-8"))
        rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {name}")
    (generated_data / f"{directory}.md").write_text(
        "# Report\n\n```text\n" + "\n".join(rows) + "\n```\n", encoding="utf-8",
    )
    return generated_data, directory


@pytest.mark.parametrize("opening", ("```", "```text"))
def test_verify_accepts_sha256sum_report_and_only_excludes_report_files(
    sha256sum_report: tuple[Path, str], capsys: pytest.CaptureFixture[str], opening: str,
) -> None:
    data, directory = sha256sum_report
    report = data / f"{directory}.md"
    report.write_text(report.read_text(encoding="utf-8").replace("```text", opening),
                      encoding="utf-8")
    (data / "scope-identical.md").write_text("illustration", encoding="utf-8")
    extra = data / directory / "raw/extra.bin"
    extra.write_bytes(b"unlisted")
    extra.with_name("README.md").write_bytes(b"also unlisted")
    before = _snapshot(data)
    verify(data)
    output = capsys.readouterr()
    assert "6 of 6 match" in output.out
    assert set(output.err.splitlines()) == {
        f"warning: unlisted artifact: {directory}/raw/extra.bin",
        f"warning: unlisted artifact: {directory}/raw/README.md",
    }
    assert _snapshot(data) == before


@pytest.mark.parametrize("mutation", ("tampered", "missing"))
def test_verify_rejects_changed_sha256sum_artifacts(
    sha256sum_report: tuple[Path, str], mutation: str,
) -> None:
    data, directory = sha256sum_report
    path = data / directory / "raw/sample/context.json"
    if mutation == "missing":
        path.unlink()
    else:
        path.write_bytes(b"changed")
    with pytest.raises(ValueError, match=f"{directory}.md") as error:
        verify(data)
    assert ("missing artifact" if mutation == "missing" else "hash mismatch") in str(error.value)


@pytest.mark.parametrize("mutation", (
    "no-block", "two-blocks", "tilde-block", "trailing-text", "blank-after", "bad-digest",
    "one-space",
    "three-spaces",
    "bad-fence", "empty", "duplicate-row", "unclosed", "malformed-row",
))
def test_verify_rejects_malformed_sha256sum_blocks(
    sha256sum_report: tuple[Path, str], mutation: str,
) -> None:
    data, directory = sha256sum_report
    report = data / f"{directory}.md"
    text = report.read_text(encoding="utf-8")
    lines = text.splitlines()
    if mutation == "no-block":
        text = "# Report\n"
    elif mutation == "two-blocks":
        text = "```\nother block\n```\n" + text
    elif mutation == "tilde-block":
        text = "~~~\nother block\n~~~\n" + text
    elif mutation == "trailing-text":
        text += "after\n"
    elif mutation == "blank-after":
        text += "\n"
    elif mutation == "bad-digest":
        text = text.replace(lines[-2][:64], "X" * 64)
    elif mutation == "one-space":
        text = text.replace("  ", " ")
    elif mutation == "three-spaces":
        text = text.replace("  ", "   ")
    elif mutation == "bad-fence":
        text = text.replace("```text", "```python")
    elif mutation == "empty":
        text = "# Report\n\n```\n```\n"
    elif mutation == "duplicate-row":
        text = text.replace(lines[-2], lines[-3])
    elif mutation == "unclosed":
        text = text.removesuffix("```\n")
    else:
        text = text.replace(lines[-2], "not a hash row")
    report.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=f"{directory}.md"):
        verify(data)


@pytest.mark.parametrize("name", ("../outside", "/outside", "C:/outside", "raw\\file"))
def test_verify_rejects_sha256sum_paths_outside_data(
    sha256sum_report: tuple[Path, str], name: str,
) -> None:
    data, directory = sha256sum_report
    (data / f"{directory}.md").write_text(
        "# Report\n\n```\n" + "0" * 64 + f"  {name}\n```\n", encoding="utf-8",
    )
    with pytest.raises(ValueError, match=f"invalid artifact path in {directory}.md"):
        verify(data)


def test_verify_requires_sha256sum_report_for_present_artifacts(
    sha256sum_report: tuple[Path, str],
) -> None:
    data, directory = sha256sum_report
    (data / f"{directory}.md").unlink()
    with pytest.raises(ValueError, match=f"missing {directory}.md"):
        verify(data)


def test_verify_accepts_absent_scope_and_containment(generated_data: Path) -> None:
    verify(generated_data)
