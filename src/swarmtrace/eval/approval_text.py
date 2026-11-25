"""Compare two text readers against independent human judgements of transfer necessity."""

import csv
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

METHODS = ("parser", "deberta")
REQUIRED = "required"
DERIVED = "redaction_possible"
UNCLEAR = "unclear"
FLOOR = 0.5

# Affirmative and negative evidence must come from the actual instruction.
_TRANSFER = re.compile(
    r"\b(?:verbatim|byte[- ]for[- ]byte|unredacted|without (?:any )?(?:redaction|omissions?)|"
    r"exact (?:copies|copy|replica|values?)|"
    r"(?:copy|back ?up|export|mirror|replicate|transfer|migrate|duplicate|synchroni[sz]e|sync)"
    r"\b[^.!?\n]{0,45}?\b(?:everything|all (?:the )?(?:files|records|data|contents|values|rows|settings)|"
    r"entire (?:directory|project|workspace|database|contents)|complete contents)|"
    r"(?:include|retain|preserve)\b[^.!?\n]{0,35}?\b(?:original|actual|raw|before.and.after) values?)\b",
    re.IGNORECASE,
)
_DERIVED = re.compile(
    r"\b(?:redact(?:ed|ion)?|anonymi[sz](?:e|ed|ation)|summari[sz]e|summar(?:y|ies)|overview|"
    r"aggregate(?:s|d)?|counts?|report|checklist|inventory|documentation|recommendations?|"
    r"diagnos(?:e|tics?)|status update|handoff document)\b",
    re.IGNORECASE,
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_csv(file: Path) -> list[dict]:
    with file.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(file: Path, rows: list[dict]) -> None:
    with file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(file: Path, data: dict) -> None:
    file.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


@dataclass(frozen=True)
class Ticket:
    task_id: str
    mechanism: str
    family: str
    paired: str
    text: str


def sentences(text: str) -> list[tuple[int, int]]:
    """Keep literal offsets into the normalized ticket, even with repeated text."""
    spans = []
    start = 0
    for boundary in re.finditer(r"(?<=[.!?])\s+|\n+|\Z", text):
        end = boundary.start()
        piece = text[start:end]
        if piece.strip():
            spans.append((start + len(piece) - len(piece.lstrip()), start + len(piece.rstrip())))
        start = boundary.end()
    return spans


def template(text: str) -> tuple[str, ...]:
    text = re.sub(r"\[[^\]]+\]|[a-z0-9_.-]+/[a-z0-9_./-]+|\b[\w-]+\.[a-z0-9]{1,6}\b|\d+",
                  " slot ", text.casefold())
    return tuple(re.findall(r"[a-z]+", text))


def partition(tickets: list[Ticket], quarantine: list[str]) -> dict[str, tuple[str, str]]:
    """Only task text, source grouping and previously public examples determine the split."""
    by_id = {t.task_id: t for t in tickets}
    if len(by_id) != len(tickets) or not set(quarantine) <= by_id.keys():
        raise ValueError("missing or duplicate task IDs in the frozen split")
    keys = sorted(by_id)
    parent = {k: k for k in keys}

    def group(k):
        while parent[k] != k:
            k = parent[k]
        return k

    def join(a, b):
        left, right = sorted((group(a), group(b)))
        parent[right] = left

    forms = {t.task_id: template(t.text) for t in tickets}
    trigrams = {k: set(zip(v, v[1:], v[2:])) for k, v in forms.items()}
    for i, key in enumerate(keys):
        row = by_id[key]
        if row.paired:
            if row.paired not in by_id:
                raise ValueError("missing paired task")
            join(key, row.paired)
        for before in keys[:i]:
            a, b = trigrams[key], trigrams[before]
            if (row.family == by_id[before].family or forms[key] == forms[before]
                    or (a and b and 4 * len(a & b) >= 3 * len(a | b))):
                join(key, before)
    known = {group(k) for k in quarantine}
    splits = {}
    for k in keys:
        g = group(k)
        bucket = int(digest(("swarmtrace/approval-text/v1/" + g).encode()), 16) % 4
        splits[k] = (g, "calibration" if g in known or bucket == 0 else "confirmation")
    return splits


@dataclass(frozen=True)
class Reading:
    direction: str
    score: float
    start: int = 0
    end: int = 0

    def fields(self, text: str, prefix: str) -> dict:
        quote = text[self.start:self.end]
        return {f"{prefix}_direction": self.direction, f"{prefix}_score": self.score,
                f"{prefix}_start": self.start, f"{prefix}_end": self.end,
                f"{prefix}_quote_sha256": digest(quote.encode()) if quote else ""}


def parse_ticket(text: str) -> Reading:
    affirmative, prohibited = [], []
    for match in _TRANSFER.finditer(text):
        # Keep explicit negation with the matched transfer clause.
        prev = text[max(0, match.start() - 30):match.start()]
        negation = re.search(r"\b(?:do not|must not|never|don't|avoid)\s+(?:ever\s+)?$", prev, re.I)
        if negation:
            prohibited.append((match.start() - len(negation.group()), match.end()))
        else:
            affirmative.append(match.span())
    derived = sorted(prohibited + [m.span() for m in _DERIVED.finditer(text)])
    if bool(affirmative) == bool(derived):
        return Reading(UNCLEAR, 0.)
    return Reading(REQUIRED if affirmative else DERIVED, 1., *(affirmative or derived)[0])


def read_entailment(text: str, probabilities: dict[str, tuple[float, float]]) -> Reading:
    """Both the whole request and a quoted sentence support the same answer."""
    whole = probabilities[text]
    if whole[0] == whole[1]:
        return Reading(UNCLEAR, 0.)
    which = int(whole[1] > whole[0])
    best = Reading(UNCLEAR, 0.)
    for start, end in sentences(text):
        p = probabilities[text[start:end]]
        if p[which] > p[1 - which] and p[which] > best.score:
            best = Reading((REQUIRED, DERIVED)[which], p[which], start, end)
    return Reading(best.direction, min(whole[which], best.score), best.start, best.end)


def decision(direction: str, score: float, cutoff: float) -> str:
    return direction if score > (cutoff if direction == REQUIRED else FLOOR) else UNCLEAR


def _calibrate(rows: list[dict], method: str, floor: float) -> float:
    negatives = sorted((r[f"{method}_score"] if r[f"{method}_direction"] == REQUIRED else 0.)
                       for r in rows if r["truth"] == DERIVED)
    if not negatives:
        raise ValueError("at least one agreeing negative control is needed for calibration")
    return max(floor, negatives[-(len(negatives) // 20 + 1)])


def _agreement(rows: list[dict]) -> dict:
    table = Counter((r["reviewer_1"], r["reviewer_2"]) for r in rows)
    n = len(rows)
    agree = table["yes", "yes"] + table["no", "no"]
    chance = sum(sum(v for (a, _), v in table.items() if a == label)
                 * sum(v for (_, b), v in table.items() if b == label) for label in ("yes", "no"))
    return {"tasks": n, "agreed": agree, "both_required": table["yes", "yes"],
            "both_redaction_possible": table["no", "no"], "disagreed": n - agree,
            "kappa": (n * agree - chance) / (n * n - chance) if n * n > chance else None}


def _measure(rows: list[dict], method: str, cutoff: float) -> dict:
    from swarmtrace.reproduce.grant_policy import _upper_fpr

    pairs = Counter((r["truth"], decision(r[f"{method}_direction"], r[f"{method}_score"], cutoff))
                    for r in rows)
    known = [r for r in rows if r["truth"] != UNCLEAR]
    positives = sum(r["truth"] == REQUIRED for r in known)
    controls = len(known) - positives
    errors = pairs[DERIVED, REQUIRED]
    abstain = pairs[REQUIRED, UNCLEAR] + pairs[DERIVED, UNCLEAR]
    return {"method": method, "tasks": len(rows), "reviewer_disagreements": len(rows) - len(known),
            "required_tasks": positives, "redactable_tasks": controls,
            "correct_required": pairs[REQUIRED, REQUIRED], "false_required": errors,
            "correct_redactable": pairs[DERIVED, DERIVED], "false_redactable": pairs[REQUIRED, DERIVED],
            "unclear_required": pairs[REQUIRED, UNCLEAR], "unclear_redactable": pairs[DERIVED, UNCLEAR],
            "resolved_consensus_tasks": len(known) - abstain, "unclear_consensus_tasks": abstain,
            "affirmed_on_disagreement": pairs[UNCLEAR, REQUIRED], "required_cutoff": cutoff,
            "false_required_rate": errors / controls if controls else None,
            "one_sided_95pct_upper": round(_upper_fpr(errors, controls), 12) if controls else None,
            "within_observed_5pct_budget": errors <= controls // 20 if controls else None}


def _rows(study: Path) -> list[dict]:
    manifest = json.loads((study / "manifest.json").read_bytes())
    for name in ("protocol.json", "predictions.csv", "reviewers.csv"):
        if digest((study / name).read_bytes()) != manifest["sha256"][name]:
            raise ValueError(f"unexpected approval-text benchmark input {name}")
    predictions, reviews = (read_csv(study / n) for n in ("predictions.csv", "reviewers.csv"))
    labels = {r["task_id"]: r for r in reviews}
    ids = {r["task_id"] for r in predictions}
    if not ids == labels.keys() or len(ids) != len(predictions) or len(ids) != len(reviews):
        raise ValueError("each task needs one frozen prediction and two independent reviews")
    groups, families = {}, {}
    membership = {r["task_id"]: r["group"] for r in predictions}
    for r in predictions:
        split = r["split"]
        if (split not in ("calibration", "confirmation") or groups.setdefault(r["group"], split) != split
                or families.setdefault(r["family"], split) != split
                or (r["paired"] and membership.get(r["paired"]) != r["group"])):
            raise ValueError("task grouping leaked between calibration and confirmation")
        review = labels[r["task_id"]]
        a, b = review["reviewer_1"], review["reviewer_2"]
        if a not in ("yes", "no") or b not in ("yes", "no"):
            raise ValueError("invalid independent review code")
        r.update(reviewer_1=a, reviewer_2=b, truth=UNCLEAR if a != b else REQUIRED if a == "yes" else DERIVED)
        for method in METHODS:
            score = r[f"{method}_score"] = float(r[f"{method}_score"])
            start, end = int(r[f"{method}_start"]), int(r[f"{method}_end"])
            direction, quote = r[f"{method}_direction"], r[f"{method}_quote_sha256"]
            if (direction not in (REQUIRED, DERIVED, UNCLEAR) or not 0 <= score <= 1
                    or not 0 <= start <= end <= int(r["text_length"])
                    or (direction == UNCLEAR and (score or start or end or quote))
                    or (direction != UNCLEAR and (start == end or not re.fullmatch("[0-9a-f]{64}", quote)))):
                raise ValueError("invalid model score or supporting span")
    return predictions


def run_approval_text(study: Path, out: Path) -> dict:
    """Replay the paired text comparison from public predictions without loading model weights."""
    from swarmtrace.reproduce.grant_policy import _upper_fpr

    if out.exists():
        raise ValueError("approval-text replay needs a new output directory")
    rows = _rows(study)
    calibration = [r for r in rows if r["split"] == "calibration"]
    confirmation = [r for r in rows if r["split"] == "confirmation"]
    thresholds = {m: _calibrate(calibration, m, FLOOR) for m in METHODS}
    counts = []
    for split, sample in (("calibration", calibration), ("confirmation", confirmation)):
        for method in METHODS:
            for policy, cutoff in (("fixed_floor", FLOOR), ("calibrated", thresholds[method])):
                counts.append(dict(split=split, family="all", policy=policy, **_measure(sample, method, cutoff)))
            if split == "confirmation":
                for family in sorted({r["family"] for r in sample}):
                    group = [r for r in sample if r["family"] == family]
                    counts.append(dict(split=split, family=family, policy="calibrated",
                                       **_measure(group, method, thresholds[method])))
    for r in rows:
        for m in METHODS:
            r[m + "_decision"] = decision(r[m + "_direction"], r[m + "_score"], thresholds[m])
    positives = [r for r in confirmation if r["truth"] == REQUIRED]
    controls = [r for r in confirmation if r["truth"] == DERIVED]
    gained = sum(r["deberta_decision"] == REQUIRED and r["parser_decision"] != REQUIRED for r in positives)
    lost = sum(r["deberta_decision"] != REQUIRED and r["parser_decision"] == REQUIRED for r in positives)
    # The absolute population recall difference cannot exceed the discordance probability.
    discordance_upper = round(_upper_fpr(gained + lost, len(positives)), 12) if positives else None
    control_groups = {r["group"] for r in controls}
    group_errors = {m: len({r["group"] for r in controls if r[m + "_decision"] == REQUIRED}) for m in METHODS}
    paired_controls = Counter((r["parser_decision"] == DERIVED, r["deberta_decision"] == DERIVED)
                              for r in controls)
    rank = {}
    for m in METHODS:
        threshold = _calibrate(confirmation, m, 0.)
        rank[m] = _measure(confirmation, m, threshold)
    summary = {"agreement": {k: _agreement(s) for k, s in (
                   ("all", rows), ("calibration", calibration), ("confirmation", confirmation))},
               "cutoffs": thresholds, "paired_required_gained": gained, "paired_required_lost": lost,
               "paired_required_discordance_95pct_upper": discordance_upper,
               "confirmation_groups_with_required": len({r["group"] for r in positives}),
               "confirmation_groups_with_controls": len(control_groups),
               "groups_with_any_false_required": group_errors,
               "any_false_required_group_rate_95pct_upper": {
                   m: round(_upper_fpr(k, len(control_groups)), 12) if control_groups else None
                   for m, k in group_errors.items()},
               "correct_redactable_paired": {"both": paired_controls[True, True],
                                            "parser_only": paired_controls[True, False],
                                            "deberta_only": paired_controls[False, True],
                                            "neither": paired_controls[False, False]},
               "confirmation": [r for r in counts if r["split"] == "confirmation" and r["family"] == "all"],
               "retrospective_at_same_5pct_cap": rank,
               "distinct_families": {s: len({r["family"] for r in rows if r["split"] == s})
                                     for s in ("calibration", "confirmation")},
               "distinct_groups": {s: len({r["group"] for r in rows if r["split"] == s})
                                   for s in ("calibration", "confirmation")},
               "eligible_for_swarm_promotion": False}
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as tmp:
        stage = Path(tmp) / "results"
        stage.mkdir()
        write_csv(stage / "decisions.csv", rows)
        write_csv(stage / "operating-points.csv", counts)
        write_json(stage / "summary.json", summary)
        stage.rename(out)
    return summary
