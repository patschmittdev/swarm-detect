import bz2
import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from swarmtrace.study import folding, transfer
from swarmtrace.study.fleet_api import Fleet


@dataclass
class StubResult:
    score: float
    alert: bool
    groups: list = field(default_factory=list)

    def to_dict(self):
        return {"score": self.score}


def _assess(events):
    names = {e["token_id"] for e in events if e["token_id"]}
    return StubResult(float(len(names)), len(names) >= 6)


def _baselines(events, identity_removed=False):
    return {"requests": float(len(events)), "sessions": None, "concurrency": 1.0,
            "template_multiplicity": None}


STUB = Fleet(None, list, _assess, _baselines)
SECRET_NAMES = [f"SecretAgentName{i}" for i in range(8)]


def test_fold_and_keys():
    assert folding.fold("Hello, WORLD!! 2026 see https://x.example/a") == "hello world 0 see u"
    text = "alpha beta gamma delta epsilon"
    assert folding.keys(text) == [text]
    assert folding.keys("too few words") == []
    long = " ".join("w" + chr(97 + i % 26) * (1 + i // 26) for i in range(100))
    prefix, suffix = folding.keys(long)
    assert prefix.split()[0] == "wa" and len(prefix.split()) == 12
    assert len(suffix.split()) == 12
    assert folding.sanitise("a\x07b " + "A" * 250) == "ab [BLOB]"
    assert folding.changed_text("abc", "abXc") == "X"
    assert folding.changed_text("abc", "ab") == "ab"


def test_sequential_recurrence_by_hand():
    import numpy as np

    u = float(np.random.default_rng(0).random())
    c = [0.0] * 48 + [1.0, 0.0]
    bins = folding.Bins(0, [1] * 50, [0] * 50, c, [5.0, 0.0] * 25)
    log_s, alarms = folding.sequential(bins, 0)
    assert log_s[:48] == [0.0] * 48
    # bin 48: 48 past zeros, none greater or tied with 1.0, so p = u / 49
    p48 = u / 49
    e48 = sum(eps * p48 ** (eps - 1) for eps in folding.EPSILONS) / 5
    assert 10 ** log_s[48] == pytest.approx(e48)
    # bin 49: C = 0 ties the 48 zeros and is below 1.0: p = (1 + U * 49) / 50, S = e * S_prev
    u2 = float(np.random.default_rng(0).random(2)[1])
    p49 = (1 + u2 * 49) / 50
    e49 = sum(eps * p49 ** (eps - 1) for eps in folding.EPSILONS) / 5
    assert 10 ** log_s[49] == pytest.approx(e49 * max(e48, 1.0))
    assert not any(alarms)


def test_sequential_alarm_gate_and_reset():
    c = [0.0] * 48 + [1.0] * 6
    gated = folding.Bins(0, [1] * 54, [0] * 54, c, [0.0] * 54)
    _, alarms = folding.sequential(gated, 0)
    assert not any(alarms)
    open_gate = folding.Bins(0, [1] * 54, [0] * 54, c, [5.0] * 54)
    log_s, alarms = folding.sequential(open_gate, 0)
    first = alarms.index(True)
    assert log_s[first] >= 2.0 and log_s[first + 1] < log_s[first]


def test_sequential_warmup_and_alarm():
    quiet = folding.Bins(0, [1] * 60, [0] * 60, [0.0] * 60, [0.0] * 60)
    log_s, alarms = folding.sequential(quiet, 0)
    assert log_s[:48] == [0.0] * 48 and not any(alarms)
    burst = folding.Bins(0, [1] * 60, [0] * 60, [0.0] * 50 + [1.0] * 10, [0.0] * 50 + [5.0] * 10)
    _, alarms = folding.sequential(burst, 0)
    assert any(alarms)
    assert folding.e_value(1.0) == pytest.approx(sum(folding.EPSILONS) / 5)


def test_bin_series_counts_distinct_actors():
    keys = ["one two three four"]
    events = [(3600 * 10 + i, f"a{i}", keys) for i in range(5)] + [(3600 * 12, None, keys)]
    bins = folding.bin_series(events)
    assert bins.n == [5, 0, 1] and bins.coordinated == [5, 0, 1]
    assert bins.C == [1.0, 0.0, 1.0] and bins.M[0] == 5.0


def _incident(tmp_path):
    rows, start = [], datetime(2026, 5, 24, 6, tzinfo=UTC)
    for day in range(3):
        for i in range(25 if day != 1 else 10):
            t = start + timedelta(days=day, minutes=i)
            name = SECRET_NAMES[i % (8 if day == 2 else 2)] if i % 7 else ""
            rows.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "label": name,
                         "page_key": f"SecretPage{i % 3}", "body_sha256": f"{i:064x}",
                         "body_len": 10, "body": f"SecretBody hello all agents please join {i}"})
    data = "".join(json.dumps(r) + "\n" for r in rows).encode()
    path = tmp_path / "revisions.jsonl"
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def _control(tmp_path):
    lines = []
    for day in range(2):
        for i in range(22):
            cols = [""] * 78
            cols[2], cols[3] = "revision", "create"
            cols[4] = f"2025-03-0{day + 1} 10:{i:02d}:00.0"
            cols[9] = SECRET_NAMES[i % 3]
            cols[15] = "name" if i == 0 else ("SENTINELbotflag" if i == 1 else "")
            cols[28], cols[65], cols[67] = str(i), "100", f"sha{i}"
            lines.append("\t".join(cols))
    cols[4] = "2024-12-31 10:00:00.0"
    lines.append("\t".join(cols))
    path = tmp_path / "control.tsv.bz2"
    path.write_bytes(bz2.compress(("\n".join(lines) + "\n").encode()))
    return path, _pin(path)


def _pin(path):
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def test_transfer_end_to_end(tmp_path, capsys):
    incident, digest = _incident(tmp_path)
    control, pin = _control(tmp_path)
    with pytest.raises(ValueError, match="SHA-256"):
        transfer.read_control(control)
    with pytest.raises(ValueError, match="SHA-256"):
        transfer.read_incident(incident)
    out = tmp_path / "out"
    report = transfer.run_transfer(incident, control, out, fleet=STUB, root=tmp_path,
                                   _test_expected_sha256=digest, _test_control=pin,
                                   official={"set": "transfer"})
    assert json.loads((out / "OFFICIAL.json").read_text()) == {"set": "transfer"}
    assert "by construction" in report["rules"]["note"]
    printed = capsys.readouterr()
    assert "SENTINEL" not in printed.out + printed.err
    assert report["control"]["by_bot_flag"]["other"] == 2
    seeds = report["rules"]["template_folding"]["incident"]["per_seed"]
    assert len(seeds) == 20 and all("eligible_days_with_alarm" in s for s in seeds)
    assert report["incident"]["rows"] == 60 and report["incident"]["eligible_days"] == 2
    assert report["control"]["rows"] == 44 and report["control"]["by_bot_flag"]["name"] == 2
    assert report["rules"]["edits"]["control_max"] == 22
    assert report["rules"]["edits"]["incident"]["flagged"] == 2
    assert report["rules"]["names"]["incident"]["flagged"] == 1
    det = report["detector"]["identity"]["incident"]
    assert det["flagged"] == 1 and det["first"]["window"] == "2026-05-26"
    assert det["first"]["edits_through_window"] == 60
    assert report["detector"]["no_identity"]["incident"]["flagged"] == 0
    assert report["rules"]["template_folding"]["control"] == "not applicable (no text)"
    with open(out / "windows.csv", encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 8
    written = (out / "windows.csv").read_text() + (out / "summary.json").read_text()
    assert "Secret" not in written and "SENTINEL" not in written
    with pytest.raises(FileExistsError):
        transfer.run_transfer(incident, control, out, fleet=STUB, _test_expected_sha256=digest,
                              _test_control=pin)


def test_bot_labels_and_empty_control(tmp_path):
    assert [transfer.bot_label(v) for v in ("", "name", "group", "group,name", "x")] == [
        "none", "name", "group", "name+group", "other"]
    incident, digest = _incident(tmp_path)
    cols = [""] * 78
    cols[2], cols[3], cols[4] = "revision", "create", "2025-03-01 10:00:00.0"
    control = tmp_path / "small.tsv.bz2"
    control.write_bytes(bz2.compress(("\t".join(cols) + "\n").encode()))
    with pytest.raises(ValueError, match="no eligible day"):
        transfer.run_transfer(incident, control, tmp_path / "o", fleet=STUB,
                              _test_expected_sha256=digest, _test_control=_pin(control))
    bad = tmp_path / "bad.tsv.bz2"
    cols[65] = "SENTINELsize"
    bad.write_bytes(bz2.compress(("\t".join(cols) + "\n").encode()))
    with pytest.raises(ValueError) as info:
        transfer.read_control(bad, _test_expected_sha256=_pin(bad)[0])
    assert str(info.value) == "control row 1: column 65 unreadable"


def test_incident_body_type_checked(tmp_path):
    row = {"time": "2026-05-24T00:00:00Z", "label": "x", "page_key": "p", "body_sha256": "h",
           "body_len": 1, "body": 5}
    path = tmp_path / "r.jsonl"
    path.write_bytes((json.dumps(row) + "\n").encode() + b"\xff\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="incident row 1: TypeError"):
        transfer.read_incident(path, _test_expected_sha256=digest)
    path.write_bytes(b"\xff\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="incident row 1: UnicodeDecodeError"):
        transfer.read_incident(path, _test_expected_sha256=digest)


def test_eligible_day_alarm_counts(monkeypatch):
    day0 = datetime(2026, 5, 24, tzinfo=UTC)
    events = [((day0 + timedelta(hours=h)).timestamp(), "a", []) for h in range(72)]
    edits = [transfer.Edit(day0 + timedelta(hours=h), "a", "p", None, None) for h in range(72)]
    # alarms at hours 5 and 6 (day 0), 30 (day 1) and 60 (day 2)
    alarm_hours = {5, 6, 30, 60}
    monkeypatch.setattr(folding, "sequential", lambda bins, seed: (
        [0.0] * len(bins.n), [b in alarm_hours for b in range(len(bins.n))]))
    eligible = {day0.date(), (day0 + timedelta(days=2)).date()}
    rule = transfer.folding_rule(events, edits, eligible, seeds=range(3))
    assert [s["alarm_bins"] for s in rule["per_seed"]] == [4, 4, 4]
    assert [s["eligible_days_with_alarm"] for s in rule["per_seed"]] == [2, 2, 2]
    first = rule["per_seed"][0]["first_alarm"]
    assert first["edits_through_window"] == 6 and first["days_after_first_edit"] == 0.25


def test_detector_rows_mapping():
    t0 = datetime(2026, 5, 24, tzinfo=UTC)
    edits = [transfer.Edit(t0 + timedelta(seconds=s), n, "P", "h", None)
             for s, n in ((0, "A"), (30, None))]
    opaque = transfer.Opaque(b"fixed")
    rows = transfer.detector_rows(edits, opaque, identity=True)
    assert [r["t_start"] for r in rows] == [0.0, 30.0] and rows[1]["token_id"] is None
    assert rows[0]["path"].startswith("/notes/") and "P" not in rows[0]["path"][7:]
    assert rows[0]["bytes_in"] == 0 and rows[0]["method"] == "PUT" and rows[0]["seq"] == 1
    assert all(r["token_id"] is None for r in transfer.detector_rows(edits, opaque, False))
