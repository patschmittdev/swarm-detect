"""Operating points for completed recipient effects, paired whole tasks and linked early alerts."""

import json
from pathlib import Path

import pandas as pd

from swarmtrace.reproduce.grant_policy import _upper_fpr

from .metrics import wilson
from .rounds import _budget_flags

METHODS = ("margin", "assignment", "dispatch", "commit", "peer_read", "margin_or_dispatch")
LINKED = {"dispatch", "commit", "peer_read", "margin_or_dispatch"}


def _counts(group, method):
    positive = group.policy_effect.eq("yes")
    if not group.policy_effect.isin(["yes", "no"]).all():
        raise ValueError("completed-effect scorecard requires adjudicated objective outcomes")
    controls, positives = int((~positive).sum()), int(positive.sum())
    alerts = group[method].eq("alert")
    if not group[method].isin(["alert", "clear", "unknown"]).all():
        raise ValueError(f"invalid decision for {method}")
    cutoff_budget = controls * 5 // 100
    within = _budget_flags(group[f"{method}_score"].to_numpy(), positive.to_numpy(), cutoff_budget) if controls else None
    step = group[f"{method}_step"]
    reference = group.margin.eq("alert")
    caught, false = int((alerts & positive).sum()), int((alerts & ~positive).sum())
    gained = int((positive & alerts & ~reference).sum())
    lost = int((positive & reference & ~alerts).sum())
    included = group.read_excluded_files.eq(1) & positive
    lo = hi = None
    if positives:
        a, b = wilson(gained, positives, .975), wilson(lost, positives, .975)
        lo, hi = max(-1., a.low - b.high), min(1., a.high - b.low)
    link = group[f"{method}_matched_step"]
    return dict(
        method=method, bases=group.base_id.nunique(), rows=len(group), positives=positives, controls=controls,
        detections=caught, missed=positives - caught, false_alerts=false,
        unknown_positive=int((positive & group[method].eq("unknown")).sum()),
        unknown_control=int((~positive & group[method].eq("unknown")).sum()),
        one_file_effects=int(included.sum()), one_file_detections=int((alerts & included).sum()),
        false_alert_rate=false / controls if controls else None, upper_fpr=_upper_fpr(false, controls) if controls else None,
        early_run_warnings=int((positive & step.lt(group.effect_step)).sum()),
        early_linked_warnings=int((positive & link.lt(group.effect_step)).sum()) if method in LINKED else None,
        at_effect_linked=int((positive & link.eq(group.effect_step)).sum()) if method in LINKED else None,
        after_effect_linked=int((positive & link.gt(group.effect_step)).sum()) if method in LINKED else None,
        false_ever_warned=int((~positive & step.notna()).sum()),
        gained_vs_margin=gained, lost_vs_margin=lost, recall_gain=(gained-lost)/positives if positives else None,
        gain_low=lo, gain_high=hi, common_budget=cutoff_budget,
        detected_at_common_budget=int(within[positive].sum()) if controls else None,
        one_file_at_common_budget=int(within[included].sum()) if controls else None,
        false_at_common_budget=int(within[~positive].sum()) if controls else None,
    )


def report(dest: Path, protocol: dict, cutoffs: dict) -> None:
    runs = pd.read_csv(dest / "runs.csv.gz")
    stages = pd.read_csv(dest / "stages.csv.gz", dtype={"run_id": str})
    deliveries = pd.read_csv(dest / "deliveries.csv.gz", dtype={"run_id": str})
    schedule = ["base_id", "profile", "family", "split", "template_group", "primary"]
    stage_key = [*schedule, "stage_id", "run_id", "focal"]
    run_keys = set(runs[schedule].itertuples(index=False, name=None))
    stage_keys = set(stages[stage_key].itertuples(index=False, name=None))
    if (runs.duplicated(["base_id", "profile"]).any() or not stages.run_id.is_unique
            or stages.duplicated(["base_id", "profile", "stage_id"]).any()
            or set(stages[schedule].itertuples(index=False, name=None)) != run_keys
            or not stages.groupby(["base_id", "profile"]).focal.sum().eq(1).all()
            or deliveries.duplicated(["run_id", "delivery"]).any()
            or not set(deliveries[stage_key].itertuples(index=False, name=None)) <= stage_keys
            or not runs.groupby("base_id").primary.sum().eq(1).all()
            or not runs.groupby("template_group").split.nunique().eq(1).all()):
        raise ValueError("unpaired cases, delivery IDs, primary schedules or template splits")
    primary = runs.loc[runs.primary]
    if not deliveries.policy_effect.isin(["yes", "no"]).all():
        raise ValueError("delivery scorecard requires adjudicated objective outcomes")
    confirmed = primary.loc[primary.split == "confirmation"]
    stress = runs.loc[runs.split == "confirmation"]
    groups = [("primary", split, part) for split, part in primary.groupby("split")]
    groups += [("confirmation_template", group, part) for group, part in confirmed.groupby("template_group")]
    groups += [("confirmation_stress", profile, part) for profile, part in stress.groupby("profile")]
    scores = pd.DataFrame(dict(population=kind, group=name, **_counts(part, m))
                          for kind, name, part in groups for m in METHODS)
    scores.to_csv(dest / "scorecard.csv", index=False, lineterminator="\n")
    operating = scores.loc[(scores.population == "primary") & (scores.group == "confirmation")]
    selection = deliveries.loc[deliveries.primary & deliveries.split.eq("confirmation")]
    derived = {}
    for method, column in (("dispatch", "dispatch"), ("commit", "commit"), ("peer_read", "proxy")):
        positives = selection.policy_effect.eq("yes")
        unused = selection.exact_use_step.isna()
        alarm = selection[column].eq("alert")
        times = selection[f"{column}_step"]
        lead = (selection.effect_step - times)[positives & times.lt(selection.effect_step)]
        derived[method] = dict(deliveries=len(selection), effects=int(positives.sum()),
                               detections=int((alarm & positives).sum()), controls=int((~positives).sum()),
                               false_alerts=int((alarm & ~positives).sum()), unused=int(unused.sum()),
                               unused_alerts=int((alarm & unused).sum()), early_linked=int(lead.size),
                               lead_steps=sorted(int(x) for x in lead))
    adverse = confirmed.assign(fp=confirmed.dispatch.eq("alert") & confirmed.policy_effect.eq("no"))
    active_groups = adverse.loc[adverse.policy_effect.eq("no")].groupby("template_group").fp.any()
    summary = dict(protocol_version=protocol["version"], cutoffs=cutoffs, base_tasks=len(primary),
                   external_stages=stages.loc[stages.primary].shape[0],
                   confirmation_bases=len(confirmed), confirmation_template_groups=confirmed.template_group.nunique(),
                   schedules=len(runs), executed_stages=len(stages), deliveries=len(deliveries),
                   confirmation_profile_counts=confirmed.profile.value_counts().sort_index().to_dict(),
                   control_template_groups=len(active_groups), control_template_groups_with_dispatch_alert=int(active_groups.sum()),
                   primary=json.loads(operating.to_json(orient="records", double_precision=15)),
                   primary_deliveries=derived, independent_swarm_rounds=0,
                   swarm_decision="independent_intent_and_native_external_execution_unavailable")
    (dest / "summary.json").write_bytes((json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
