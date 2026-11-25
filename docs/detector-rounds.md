# Detector improvement rounds

Keep logistic as the incumbent for swarm escalation. The zero-shot experiment gave
DeBERTa English descriptions of the six audit counters or fifteen scope counters
already available to logistic. The model had no independent account of what
the team was asked to do. Revision `cf44676c28ba7312e5c5f8f8d2c22b3e0c9cdae2`
scored entailment of one fixed statement per task. The audit statement was
“The agents deliberately pooled their access to carry out an unauthorized
operation.” The scope statement was “Agents deliberately used a borrowed
credential to read files beyond the approved scope of a handoff.” [DeBERTa model card](https://huggingface.co/MoritzLaurer/deberta-v3-large-zeroshot-v2.0)

## Starting measurements

The three simulation grids contain 324 audit relays and 864 controls, plus 1,458
deliberate scope violations and 1,944 controls. The archive fit and calibration
seed is 20261120. At the frozen thresholds, adding the zero-shot score moved audit
detections from 115 to 148 and control alerts from 41 to 57. For scope, detections
moved from 1,435 to 1,436 and control alerts from 107 to 109. Both scope
configurations exceeded the observed 5% budget. If 5% is an operational
requirement, calibrate a new cutoff on reserved controls and verify the
resulting alert rate on a fresh population.

The table compares ranking at the same review workload. It counts the most
positive runs a single threshold could detect on the pooled grids within 43 audit
or 97 scope control alerts. Equal scores stay together. This is a retrospective
diagnostic. The frozen thresholds above determine alerts on future runs.

| Detector | Audit relays out of 324 | Scope violations out of 1,458 | One-file violations out of 486 |
| --- | ---: | ---: | ---: |
| Logistic | 115 | 1,417 | 445 |
| Zero-shot alone | 99 | 191 | 67 |
| Logistic plus zero-shot | 97 | 1,418 | 446 |

At the frozen thresholds the added score recovered two one-file cases and lost
one. The net gain was 0.21 percentage points, with an approximate paired 95%
interval from -1.30 to +1.71 points. The data support keeping the simpler model.
The interval still admits a useful small gain on this simulation distribution.
The replay uses saved DeBERTa predictions. We subsequently tested the same
open-weight model on public task text. Jev, TypeSafe's commercial
classification model, which answers typed questions about a text without
generating any, has no measurement here: only the open-weight DeBERTa model
was run.
[Frozen score files](../benchmarks/zero-shot), [public text results](approval-text.md) and [independent Jev benchmark](https://arxiv.org/abs/2609.37647)

## Next experiments

| Round | Change to test | What would justify continuing |
| --- | --- | --- |
| 1. Attribute each read | Give every read a trusted authorization decision that identifies its grant, its own ordinary permissions, or an unknown basis. Compare the existing inference with this record on the same traces. Include two simultaneous assignments to one agent, ordinary access and missing records. | Against independently recorded event truth, report correctly linked reads, wrong grants and unknowns separately. Require correct attribution on unambiguous fixtures and an unknown result on ambiguous ones. Measure event-level precision and recall for scope breaches, including accidental reads. |
| 2. Corroborate coordination | Test one additional signal alongside logistic, such as a second agent subsequently using the same excluded resource outside its own approved task. Include ordinary handoffs and single-worker mistakes. | Evaluate the paired recall gain and false alerts on untouched workflow families. Also report alerts on legitimate collaboration, two-agent relay recall and detections strictly before task completion. |
| 3. Optimize cost after accuracy flattens | Profile feature extraction and scoring on the same recorded traces. Optimize the measured bottleneck. Revisit language models if independently approved task tickets supply new free-text evidence. | For speed, compare median and p95 end-to-end latency at fixed concurrency on the same hardware, with identical decisions and first-alert ticks. For text, compare a parser with a classifier that quotes the ticket passage and can return unclear. Use the same alert and accuracy criteria. |

Rounds 1 and 2 are complete. Recording the gateway decision improved read
attribution. Adding the second reader changed zero one-file detections on
the held-out preplanned workflow. Both models exceeded the 5% alert budget.
Calibrating the incumbent once on fresh controls from that workflow lowered
false alerts from 24 to 16 per 432 controls on two more grids. It cost 43 of
the 314 violations detected at the original cutoff.
[Read authorization study and scorecards](read-authorization-round.md)

Replacing one login-inferred scope count with a verified per-grant count
improved one-file recall on ten grids with concurrent office assignments.
The first frozen cutoff exceeded the false-alert budget. Ten further grids
tested using the grant count only when assignments competed. On a new
same-issuer layout it detected 285 of 540 one-file cases, up from 183, and
flagged 83 of 2,160 controls. In-scope relay alerts rose from 44 to 55,
which missed the adoption rule. Native fallback decisions were identical.
[Grant-count study](grant-scope-round.md) and [November 2026 research review](swarm-detection-research.md)

Scoring the five read-scope inputs on each individual assignment met the
local criteria on two scripted workflows. On ten fresh grids it caught 519
of 540 one-file violations, versus 37 for the incumbent scored in log odds.
Control alerts fell from 94 to 74 per 2,160. A replay of two earlier layouts
then showed why this cutoff cannot support general escalation. It flagged
all 1,046 clerks who accidentally read the appendix across 4,320 controls.
Keep the score available for assignment review. The assignment experiment
counts once, and the consecutive below-minimum count remains zero.
[Assignment confirmation](assignment-round.md#fresh-confirmation-against-unrounded-logistic)
and [mistake controls](assignment-round.md#what-happens-when-the-clerk-makes-a-mistake)

In a separate replay of 24 document-office cases, version-level recipient
receipts detected 7 of 10 known unapproved uses and alerted on zero of 13
known negatives. All seven first alerts were at or after the effect. Two
accidents also triggered the rule. One accidental and one deliberate use
had identical observations and receipts. This is a conformance
result. A follow-up paired both classifiers and the two receipt checks on
public tickets run in the document office. The dispatch check flagged 15 of
26 control tasks. Neither it nor the text reader qualified for deployment.
The consecutive below-minimum count remains zero because the public rounds
lack independent intent outcomes on the executed actions.
[Recipient replay](recipient-approval.md), [public dispatch](public-dispatch.md),
[same-ticket recipient text](dispatch-role-text.md) and [independent human transfer judgments](approval-text.md)

The original grids gave each worker at most one inbound handoff. They cannot
measure the value of resolving competing grants. They also include controls
that made actual out-of-scope reads. Of 107 scope controls flagged by logistic,
106 had a simulator-confirmed read outside the handoff. Score the scope-review
queue against access events and the swarm-escalation queue against coordinated
behavior. Keep role labels and simulated outcomes on the evaluation side. Preserve equality on the
108 role-flipped pairs with identical observed traces and context. [Scope estimator](../src/swarmtrace/features/scope.py) and [identical-policy control](../data/scope-identical.md)

## Measuring diminishing returns

Before opening a confirmation set, record the candidate, incumbent, data and
model versions, available evidence, primary metric, minimum gain and frozen
cutoffs. Use separate fitting and calibration runs. The three published grids
are now regression data. Reserve disjoint workflow families and fresh runs for
confirmation. Changing a seed within the same scripted workflow tests a narrower
kind of generalization.

The proposed minimum worthwhile gains are **3 percentage points of recall on
audit relays** and **1 point on one-file scope violations**, at an observed
control-alert rate of at most **5%**. These amount to about ten audit relays or
five one-file violations on the current pooled sample. Choose a different
minimum with `--min-gain` before inspecting new results if review costs change.

| Pooled evidence | Round decision |
| --- | --- |
| `promising` | The frozen-threshold gain reaches the minimum, its lower bound exceeds zero, ranking improves within the shared budget, and hard-control alerts do not increase. Confirm on unseen workflows before promoting. |
| `below_minimum` | The candidate is within budget, the upper bound on the frozen-threshold gain is below the minimum, and the shared-budget ranking gain also falls short. After two consecutive, independently confirmed rounds of this kind against the same incumbent using the same evidence, redirect effort to better observations or runtime. |
| `over_budget` | The candidate exceeds the observed control-alert ceiling. Examine calibration on separate data. |
| `inconclusive` or `insufficient_data` | The comparison cannot settle the decision. Collect the missing controls or more independent runs when the interval still admits a worthwhile gain. |

Count one predeclared candidate and one confirmation result per round. The
per-grid rows, the pooled row and repeated scores on a published grid all
describe the same experiment. Only consecutive qualifying rounds count toward
the stopping rule. Record each round's held-out workflows, gained and lost
detections, interval, control alerts and decision beside its scorecard.

For example, the boosted scope detector flagged 97 of the 1,944 controls,
within budget. Against logistic it recovered 19 one-file violations and lost
43. Even the upper bound on its net recall gain was only +0.03 points, below
the 1-point minimum. This historical replay illustrates `below_minimum`.
Future rounds need fresh confirmation sets to start a stopping streak.

The primary gain is the fraction of eligible runs detected only by the candidate
minus the fraction detected only by the incumbent. The interval subtracts the
endpoints of two 97.5% Wilson intervals for those discordant fractions, yielding
approximate simultaneous 95% bounds. It retains uncertainty when zero cases
switch. It describes run sampling conditional on the fits and workload mix.
Per-grid rows expose variation, and the pooled row weights each run equally.
The card gives 95% Wilson intervals for each observed control-alert rate. A
round needs finite calibrated cutoffs, primary positives, hard controls, and
enough controls for one false alert to fit within 5%. Inspect each held-out
workflow for regressions before promoting a candidate.
[NIST on Wilson intervals](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm) and [simultaneous intervals](https://www.itl.nist.gov/div898/handbook/prc/section4/prc473.htm)

## Replay a round

From the repository root, these commands replay the zero-shot comparison
without model inference.

```shell
uv run --frozen swarmtrace benchmark-round --task main --candidate logistic+zero-shot --scores benchmarks/zero-shot/20261123.csv.gz benchmarks/zero-shot/20261124.csv.gz benchmarks/zero-shot/20261125.csv.gz
uv run --frozen swarmtrace benchmark-round --task scope --candidate logistic+zero-shot --scores benchmarks/zero-shot/20261123.csv.gz benchmarks/zero-shot/20261124.csv.gz benchmarks/zero-shot/20261125.csv.gz
```

For the built-in detectors, export scores once per independent grid. The example
uses the first grid from the [accuracy study](detector-accuracy.md#reproduce).

```shell
uv run --frozen swarmtrace compare-detectors --data data --seed 20261120 --test-tables results-replay/fresh --scores-out results-replay/round-scores.csv --out results-replay/round-summary.csv
uv run --frozen swarmtrace benchmark-round --task scope --reference logistic --candidate boosted --scores results-replay/round-scores.csv --out results-replay/round-scorecard.csv
```

An external scorer can use the same CSV schema. Supply one row per task, run
and detector with `run_id`, `task`, `test_set` set to `independent`, `split_seed`,
`detector`, `score`, `threshold`, `positive`, `small_positive` and `hard_control`.
Higher scores indicate stronger evidence. Alert when the score strictly exceeds
the calibration threshold. For audit, small positives are two-agent relays and
hard controls have a benign sharing team. For scope, small positives are one-file
violations and hard controls are in-scope relays. The benchmark checks pairing,
labels, disjoint run IDs and consistent cutoffs. The person preparing the
experiment records checkpoint identity and keeps confirmation workflows unseen.
