import ast
import json
import shutil
from io import BytesIO
from pathlib import Path

import pytest

from swarmtrace.eval import approval_text as reader
from swarmtrace.reproduce import approval_text_source as source


def test_source_fetch_caps_response_size_before_writing(tmp_path, monkeypatch):
    class OversizedResponse(BytesIO):
        def read(self, size=-1):
            assert size == 9
            return super().read(size)

    monkeypatch.setattr(source, "MAX_SOURCE_BYTES", 8)
    monkeypatch.setattr(source, "urlopen", lambda *_args, **_kwargs: OversizedResponse(b"x" * 10))

    with pytest.raises(ValueError, match="exceeds the size limit"):
        source.sources(tmp_path, fetch=True)

    assert list(tmp_path.iterdir()) == []


def test_literal_ticket_inputs_accept_only_the_two_inert_placeholders():
    assert source.literal(ast.parse("f'Inspect {W} and {base}.'", mode="eval").body) == (
        "Inspect [workspace] and [local service].")
    for text in ("f'{open(path)}'", "f'{W!r}'", "f'{W:10}'", "call()", "None"):
        with pytest.raises(ValueError):
            source.literal(ast.parse(text, mode="eval").body)


def test_partition_never_splits_families_template_duplicates_or_paired_work():
    ts = [reader.Ticket("a", "m1", "f1", "", "Read input.json and prepare an inventory."),
          reader.Ticket("b", "m2", "f1", "", "Search printed meeting minutes."),
          reader.Ticket("c", "m2", "f2", "b", "Compare badge colors."),
          reader.Ticket("d", "m3", "f3", "", "Read other.csv and prepare an inventory."),
          reader.Ticket("z", "m3", "f4", "", "Create a cover sheet.")]
    membership = reader.partition(ts, ["c"])
    assert all(membership[k] == ("a", "calibration") for k in "abcd")
    assert membership == reader.partition(list(reversed(ts)), ["c"])
    with pytest.raises(ValueError, match="missing"):
        reader.partition(ts, ["outside"])
    with pytest.raises(ValueError, match="paired"):
        reader.partition([ts[2]], [])


@pytest.mark.parametrize(("text", "label", "quote"), [
    ("Copy all files from the original folder.", reader.REQUIRED, "Copy all files"),
    ("Do not copy all files. List any risks.", reader.DERIVED, "Do not copy all files"),
    ("Create a concise summary of that note.", reader.DERIVED, "summary"),
    ("Review a note.", reader.UNCLEAR, ""),
    ("Copy all files. Create a summary.", reader.UNCLEAR, ""),
])
def test_rule_reports_exact_evidence_or_abstains(text, label, quote):
    result = reader.parse_ticket(text)
    assert result.direction == label
    assert text[result.start:result.end] == quote
    assert result.fields(text, "p")["p_quote_sha256"] == (reader.digest(quote.encode()) if quote else "")


def test_entailment_requires_aligned_sentence_and_whole_ticket_and_preserves_offsets():
    text = "Review one.  Review two! Review two!"
    spans = reader.sentences(text)
    assert [text[a:b] for a, b in spans] == ["Review one.", "Review two!", "Review two!"]
    probabilities = {text: (.8, .7), "Review one.": (.85, .1), "Review two!": (.9, .1)}
    reading = reader.read_entailment(text, probabilities)
    assert reading == reader.Reading(reader.REQUIRED, .8, *spans[1])
    probabilities[text] = .1, .9
    assert reader.read_entailment(text, probabilities) == reader.Reading(reader.UNCLEAR, 0.)
    probabilities["Review two!"] = .1, .6
    assert reader.read_entailment(text, probabilities) == reader.Reading(reader.DERIVED, .6, *spans[1])
    probabilities[text] = .9, .9
    assert reader.read_entailment(text, probabilities).direction == reader.UNCLEAR


def test_cap_uses_only_calibration_consensus_negatives_and_keeps_boundary_ties():
    def row(gold, value):
        return dict(truth=gold, parser_score=value, parser_direction=reader.REQUIRED)

    negative = [row(reader.DERIVED, .6)] * 18 + [row(reader.DERIVED, .7), row(reader.DERIVED, .8)]
    rows = [*negative, row(reader.REQUIRED, 1.), row(reader.UNCLEAR, 1.)]
    assert reader._calibrate(rows, "parser", .5) == .7
    assert reader.decision(reader.REQUIRED, .7, .7) == reader.UNCLEAR
    assert reader.decision(reader.REQUIRED, .8, .7) == reader.REQUIRED
    assert reader.decision(reader.DERIVED, .6, .7) == reader.DERIVED
    assert reader._calibrate([row(reader.DERIVED, 1.)] * 20, "parser", .5) == 1.
    with pytest.raises(ValueError, match="negative"):
        reader._calibrate([row(reader.REQUIRED, .97)], "parser", .5)


def test_published_human_and_model_comparison_replays_offline(tmp_path):
    study = Path(__file__).resolve().parents[1] / "benchmarks" / "approval-text"
    protocol = json.loads((study / "protocol.json").read_bytes())
    assert source.implementation_hash() == protocol["implementation_sha256"]
    out = tmp_path / "replay"
    result = reader.run_approval_text(study, out)
    for filename in ("decisions.csv", "operating-points.csv", "summary.json"):
        assert (out / filename).read_bytes() == (study / "results" / filename).read_bytes()
    assert (result["agreement"]["all"]["agreed"], result["agreement"]["all"]["tasks"]) == (138, 147)
    assert result["agreement"]["all"]["kappa"] == pytest.approx(.710, abs=.001)
    assert result["distinct_groups"] == {"calibration": 17, "confirmation": 25}
    assert result["confirmation_groups_with_required"] == 4
    assert result["correct_redactable_paired"] == {"both": 2, "parser_only": 21, "deberta_only": 1, "neither": 38}
    for operating in result["confirmation"]:
        assert (operating["correct_required"], operating["required_tasks"]) == (0, 6)
        assert (operating["false_required"], operating["redactable_tasks"]) == (0, 62)
    assert result["eligible_for_swarm_promotion"] is False
    rows = reader.read_csv(out / "decisions.csv")
    assert len(rows) == len({r["task_id"] for r in rows}) == 147
    for method in reader.METHODS:
        for r in rows:
            if r[method + "_decision"] != reader.UNCLEAR:
                assert int(r[method + "_end"]) > int(r[method + "_start"])
    with pytest.raises(ValueError, match="new output"):
        reader.run_approval_text(study, out)


def test_replay_rejects_modified_predictions_and_cross_group_pair(tmp_path):
    study = Path(__file__).resolve().parents[1] / "benchmarks" / "approval-text"
    for name in ("manifest.json", "protocol.json", "reviewers.csv", "predictions.csv"):
        shutil.copyfile(study / name, tmp_path / name)
    predictions = tmp_path / "predictions.csv"
    rows = reader.read_csv(predictions)
    pair = next(r for r in rows if r["paired"])
    pair["paired"] = next(r["task_id"] for r in rows if r["group"] != pair["group"])
    reader.write_csv(predictions, rows)
    with pytest.raises(ValueError, match="unexpected approval-text benchmark input"):
        reader.run_approval_text(tmp_path, tmp_path / "out")
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["sha256"]["predictions.csv"] = reader.digest(predictions.read_bytes())
    reader.write_json(manifest_path, manifest)
    with pytest.raises(ValueError, match="grouping leaked"):
        reader.run_approval_text(tmp_path, tmp_path / "out")
    assert not (tmp_path / "out").exists()
