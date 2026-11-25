# Read attribution and a second-reader test

## Protocol

The first question is whether an auditor can link a successful file read to the
authorization that actually covered it. The second is whether knowing that two
different agents read the same excluded file improves detection of deliberate
scope violations. These questions use different ground truth.

**Read attribution.** Use hand-labelled local access cases with ordinary access,
one assignment, overlapping assignments, an explicit grant, absent records and
accidental scope breaches. Compare the recorded decision with the existing
login-based inference on the same events. Count correct links, wrong links and
unknowns. Report scope precision and recall, including breaches the auditor
cannot resolve. Replay the 108 role-flipped pairs from seed 20261120 and compare
the trace, assignment context and new authorization records byte for byte.

**Coordination candidate.** Add one count to the existing 15 scope features.
Count distinct files successfully read outside the approved scope of grants
by at least two different agents. Each agent's attribution must be independently
resolved. Repeat reads by one agent and reads by a second agent within its own
scope contribute zero. A prefix uses only events through its checkpoint.
Ground-truth roles, goals and outcome files are evaluation data.

**Fit and confirmation.** Use seed 20261120 for development. Keep runs with
message or shared-file focal workflows and exclude runs containing a preplanned
background group. Apply the existing stratified scope split within that eligible
population. Fit the incumbent and candidate on the fitting partition and
calibrate their thresholds on the separate calibration controls at a 5% target.
A feature constant throughout fitting supplies no learned coefficient. Keep
the fitting procedure and feature availability fixed across both test grids.

Reserve the preplanned focal workflow, both topologies and seeds **20261126 and
20261127** for confirmation. Retain legitimate sharing and mistake-enabled
controls. The incumbent is refitted on the same restricted development set as
the candidate. The earlier all-workflow fit was exposed to this workflow. Use
the existing labels for deliberate scope violations and an independently
recorded objective tick for timing.

**Decision.** The primary endpoint is recall on one-file violations. Report
the frozen-threshold results and the ranking at a common 5% control-alert
ceiling. The minimum worthwhile gain is one percentage point. Also report
false alerts on legitimate groups, detection of two-agent violations, and
strictly early detections at ticks 0, 8, ..., 152 and 159. Report any-checkpoint
control alerts separately from final-run control alerts. The two test grids
constitute one confirmation round. A grid with no examples of the candidate
behavior cannot establish its value on workflows where that behavior occurs.
If the added feature is constant throughout fitting or absent from every
confirmation run, record insufficient feature support and leave the
diminishing-returns count untouched.
[Round decision criteria](detector-rounds.md)

## Follow-up protocol for the alert budget

The first confirmation exceeded the 5% control-alert budget. Use its original
15-feature logistic model for one calibration experiment. Rebuild the fit from
the recorded development IDs and check its original cutoff against the frozen
value. Keep the fitted weights and feature order fixed. Use all 648 preplanned
controls on seeds **20261128, 20261129 and 20261130** to set one split-conformal
cutoff at 5%. Include both legitimate groups and in-scope relays. The cutoff
applies to a full run.

Before examining any new confirmation outcomes, reserve **20261201 and
20261202** as two complete preplanned grids. Apply both the original and new
cutoffs to the same scores. Report the per-grid and pooled control-alert rates
and Wilson intervals, total and one-file detections, two-agent detections and
hard-control alerts. Accept the operating point for this simulated workload if
the pooled observed control-alert rate is at most 5%. Report the recall cost
and the result of each grid even when the pooled rate qualifies. Keep this
calibration comparison outside the diminishing-returns count. The experiment
tests a threshold change with a fixed ranking.

The control mix matters when applying a cutoff to a new workflow. The
conformal construction assumes a comparable distribution for calibration and
future controls. The held-out counts measure the realized alert rate on the
two new grids. [Bates et al., Testing for Outliers with Conformal p-values](https://arxiv.org/abs/2104.08279)

## Read attribution results

The simulator gateway captured the basis for each successful read. It checks a
requested grant against the actor, host and active credential before recording
it. Without a selection, a single possible authority can resolve the read.
Competing authorities leave it unknown. A delegated read is outside scope if
the file is absent from the selected grant's approved list. A successful read
under ordinary access has no delegated file restriction in this check.

| Method | Correct attribution out of 13 | Wrong | Unknown | Breaches found out of 7 | False breach alerts on 6 known negatives |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gateway decision | 12 | 0 | 1 | 6 | 0 |
| Login-history inference | 5 | 1 | 7 | 5 | 2 |

One known breach had its decision deliberately withheld. The gateway reported
it as unknown. A fourteenth read had competing assignments with different
scopes and no selected grant. It has no known scope label and is excluded from
the table. All 108 pairs with identical activity but opposite role labels
produced byte-identical traces, assignment context and authorization records.
[Hand-labelled cases](../benchmarks/read-authorization/attribution-cases.csv) and [role-pair results](../benchmarks/read-authorization/role-twins.csv)

## Held-out detection results

Filtering out preplanned background groups removed 235 of the 756 otherwise
eligible development runs. Fitting used 256 runs, including two with a
second reader. Calibration used 62 controls. Both test grids contained the
held-out workflow and were scored at the frozen cutoffs.

| Full-run metric on the two grids | Logistic | Logistic with a second-reader count |
| --- | ---: | ---: |
| Violations detected | 309 / 324 | 309 / 324 |
| One-file violations detected | 94 / 108 | 94 / 108 |
| Two-agent violations detected | 107 / 108 | 107 / 108 |
| Control alerts | 33 / 432 | 33 / 432 |
| In-scope relay controls flagged | 20 / 108 | 20 / 108 |
| Benign sharing controls flagged | 13 / 71 | 13 / 71 |
| One-file detections at a common 5% control ceiling | 48 / 108 | 48 / 108 |

Three deliberate violations and one control had a second reader of the same
excluded file. Across 295,957 successful reads, the gateway confirmed 1,200
outside-grant reads. All 324 positives and 116 of 432 controls had at least
one. Every one of the 33 control alerts had a verified scope breach. Fourteen
of the 15 missed deliberate violations involved a single file. These counts
identify where additional evidence has to distinguish a mistake from deliberate
use. A read-level exception still merits an access review in either case.

The two detectors gained and lost zero one-file cases against each other.
The approximate 95% interval on the paired change ran from -4.45 to +4.45
percentage points. Each exceeded the pooled budget of 21 control alerts,
with an observed rate of 7.64% (95% Wilson interval 5.49% to 10.53%).
At eight-tick checkpoints, each flagged 263 of 324 violations strictly before
task completion and flagged 34 of 432 controls at least once. Keep the
15-feature logistic detector for escalation and use gateway records for
event review. This round contributes zero to the two-round stopping rule.
[Paired scorecard](../benchmarks/read-authorization/scorecard.csv), [workflow diagnostics](../benchmarks/read-authorization/workflow/diagnostics.csv) and [round decision](../benchmarks/read-authorization/decision.json)

## Fresh calibration results

The archived data reproduced the incumbent cutoff of `0.6128164021162121`
exactly. The 617th smallest score among 648 fresh preplanned controls set
the new cutoff at `0.8900233023199413`. Thirty-one calibration controls scored
strictly above it. Both operating points used identical scores in confirmation.

| Metric | Original cutoff | Workflow-calibrated cutoff |
| --- | ---: | ---: |
| Control alerts, grid 20261201 | 11 / 216 | 8 / 216 |
| Control alerts, grid 20261202 | 13 / 216 | 8 / 216 |
| Pooled control-alert rate, 95% Wilson interval | 5.56% (3.76% to 8.13%) | 3.70% (2.29% to 5.93%) |
| Total violations detected | 314 / 324 | 271 / 324 |
| One-file violations detected | 98 / 108 | 64 / 108 |
| Two-agent violations detected | 108 / 108 | 99 / 108 |
| In-scope relays flagged | 18 / 108 | 11 / 108 |
| Benign sharing controls flagged | 6 / 43 | 5 / 43 |
| Runs sent for review | 338 / 756 | 287 / 756 |

The new cutoff met the preregistered observed 5% requirement on both fresh
grids. It avoided eight false alerts at a cost of 43 additional missed
violations, including 34 one-file cases. Use it as an opt-in benchmark for
preplanned, full-run alerts when that budget takes priority. The pooled
interval still extends above 5%, and this experiment covers a single workflow
family. In a retrospective check, the highest-recall threshold on this same
ranking within 21 control alerts detected 78 of 108 one-file cases. A live,
repeatedly checked alert would need its own calibration.
[Confirmation results](../benchmarks/read-calibration/diagnostics.csv), [calibration control scores](../benchmarks/read-calibration/calibration-controls.csv.gz) and [fit and cutoff provenance](../benchmarks/read-calibration/protocol.json)

## Follow-up experiments

The second-reader experiment kept the original scope counts in both models.
The follow-up replaced the login-based count with the number of distinct
excluded files attributed to the same grant. On 540 held-out one-file cases,
that change gained 59 detections with an overlapping office team and lost
eight without that team. A second confirmation tested whether to use the
verified count only when two competing assignments were actually exercised.
[Grant-count study](grant-scope-round.md)

For a separate candidate, collect task authorizations written before activity
and reviewed independently of the outcome. Start with a structured list of
expected actions and recipients.
Pair legitimate exceptions and single-worker mistakes with deliberate one-file
violations in previously untested workflows. Freeze a comparison of the
existing logistic model with one additional feature indicating whether a
subsequent use of the file matches an independently approved recipient or
purpose. Missing approval records should remain unknown. Use only information
available at the time of the alert. If tickets contain free text, compare a
simple parser against a classifier that selects a supporting passage and can
return unclear. A trial of Jev, the commercial classification model named in
the detector rounds, could supply numbered candidate passages as choices.
[Earlier zero-shot benchmark](detector-rounds.md#starting-measurements) and [TypeSafe's documented question types](https://docs.typesafe.ai/introduction)

The later comparison tested DeBERTa against a parser on the same public
recipient instructions and separately on human-rated transfer requirements.
[Recipient routing](dispatch-role-text.md) and [transfer necessity](approval-text.md)

Keep the one-point minimum gain for one-file recall and the 5% control-alert
ceiling. Plan at least 498 independent one-file cases across held-out workflows.
With zero gained or lost cases, 498 is the first sample size for which the
existing paired interval puts its upper bound below one point. More cases may
be needed when decisions differ or workflows are correlated. The unchanged
stopping rule requires two consecutive eligible rounds before shifting the
focus to profiling runtime at identical detection decisions and alert ticks.

## Reproduce and review

Run the studies from the repository root. Both commands write to a new
directory. The second reads the frozen model specification produced by the
first. The repository includes all paired scores for offline review.
Replaying with five and eight workers produced identical bytes in all nine
read-study files and all five calibration files.

```shell
uv run --frozen swarmtrace read-round --workers 4 --out results-replay/read-round
uv run --frozen swarmtrace calibrate-read-alerts --study results-replay/read-round --data data --workers 4 --out results-replay/read-calibration
```

For the event fixtures and the 108 byte comparisons alone, add
`--attribution-only` to `read-round`. For a single run, collect authorization
records with `sweep --scope on --capture-authorization`. The following
PowerShell example exports the read review. Add `--breaches-only` for verified
scope breaches or `--until-tick 40` for the inclusive prefix.

```powershell
uv run --frozen swarmtrace sweep --seed 42 --group-sizes 0 --coordinated-groups 1 --channels message --topologies peer --scope on --capture-authorization --out results-replay/read-demo
$run = (Get-ChildItem results-replay/read-demo -Directory | Select-Object -First 1).FullName
uv run --frozen swarmtrace review-reads --run $run --out results-replay/review.csv
```

The review uses `trace.jsonl` and, when present, `authorization.json`. Each
decision uses the run ID and event sequence to identify the read. Older traces
and partial records return unknown for reads without a gateway decision.
