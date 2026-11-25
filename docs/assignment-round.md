# Assignment-level scoring

In ten fresh grids, assignment scoring caught 519 of 540 one-file scope
violations. Whole-run logistic, evaluated with unrounded log odds, caught
37. Assignment scoring also reduced false alerts from 94 to 74 per 2,160
controls. In two earlier office layouts, accidental appendix reads alone
put the same score above a 23% false swarm-alert rate. Use it to inspect
individual grants. The evidence supports the gain on the two tested workflows
and rules out using this cutoff for general swarm escalation.
[Fresh scorecard](../benchmarks/assignment-margin/workflow/scorecard.csv)
and [earlier office controls](../benchmarks/assignment-transfer/office-controls.csv)

## Protocol fixed before testing

The primary question is whether requiring evidence to come from the same
exercised assignment catches more deliberate one-file violations than the
existing 15-input logistic detector at a 5% run-level false-alert budget.
The earlier experiment showed a loss of 254 one-file detections when unrelated
work was added to identical focal runs at a common false-alert ceiling.
[Earlier experiment](grant-scope-round.md#first-confirmation-results)

Each selected grant supplies five inputs. Count distinct excluded files and
distinct approved files read, compute the excluded fraction of distinct files,
the fraction of excluded reads that are repeats, and the fraction of the
approved list seen before the first exclusion. Use zero for a fraction with
an empty denominator or with no exclusion. Match the actual read decision
to its C2 approval. Preserve ordinary access, unknown authority and missing
capture as coverage fields. IDs never enter the fit. An empty set of exercised
grants supplies no assignment alert and stays in the evaluation denominator.

Fit one logistic score on the message and shared-file development workflows
using the original 256 run IDs. Standardize the assignment inputs with equal
total weight per nonempty run. Fit one outcome per nonempty run, using a
smooth maximum of its assignment log odds (log-mean-exp, temperature 0.25),
unit L2 weight penalty, unpenalized intercept and zero initialization. Score
new runs by the exact maximum over their actual assignments. Development and
evaluation report any empty runs. Three secondary comparisons use the
original 15-input verified-grant fit, a logistic fit on the five run-wide
column maxima, and the candidate's own weights applied to the strongest
signed contribution for each input across assignments. The last comparison
matches the candidate's raw score whenever all the strongest contributions
occur on one ticket. Its ranking at a common budget isolates the change in
grouping. Its frozen cutoff is calibrated separately. Only the comparison
with the incumbent determines the round.
[Multiple-instance logistic classification and pooled baselines](https://icml.cc/Conferences/2005/proceedings/papers/088_Supervised_RayCraven.pdf)

Hold out two office workflows, record checking and a clerical handoff, both
sharing a reviewer or document with the native work where the observations
allow. Vary the number of legitimate tickets independently of labels.
Include every run and report actual linkage, timing and fallback coverage.
Both views retain the native one-file and in-scope relay labels. Repeat the
native view on the same IDs to measure performance without extra work.
The primary positive label designates a scripted violation. As a separate
check, record how many of the designated files the focal worker actually
read according to the simulator's outcome log. Only the evaluation uses it.
These views describe one experiment. Check the augmented observations on
the 108 historical role-flipped pairs before independent evaluation.

Each workflow uses fresh office credentials. For each connected component of
registered native assignments, prefer a document whose final visible version
was read under a matching approval. A new clerk can inspect that document
while the native work continues. The native reviewer joins the new assignment
after their last original action. Record checking uses two to four reviewer
tickets for the same cover and separate worksheets. In the clerical handoff,
the clerk writes a new memo and sends its reference. The native reviewer
receives it and verifies it alongside the cover under two or three tickets.
The office reads a copy with the witnessed byte length when the native
payload is redacted. It assigns and reads these records through the actual
tool gateway. This is a full-run comparison with benign work sharing actors
and resources. It cannot establish an improvement in time to first alert.

Use eight new calibration grids (random seed identifiers 20270101 through
20270108), alternating families in the listed order. Pool their 1,728
whole-run controls for one threshold per detector across both families.
Choose the one-based order statistic with upper-tail probability at most
0.025 per primary arm under Binomial(1,728, 0.95). This gives rank 1,660.
Score strictly above the cutoff. Use the same calibration procedure on the separate native view.
Then open ten new complete grids (20270111 through 20270120), alternating
families, for 540 one-file violations, 2,160 controls and 1,620 total
violations. Each underlying ID occurs in just one confirmation family.
Comparisons between detectors within a family use the same runs. Comparisons
between the two families also reflect their different seeds. The confidence
intervals describe this fixed simulated task mix. The order-statistic error
bound assumes exchangeable independent controls. Whole-score ties stay
together in every retrospective ranking.

Require at least a one-percentage-point gain in one-file recall, a positive
paired 95% lower bound, better ranking at a common 5% false-alert ceiling,
and no net increase in the number of in-scope relay alerts. Both newly
flagged and newly cleared controls are reported. A candidate for local use also
needs a one-sided 95% upper false-alert limit at most 5%, no family with a
net one-file loss or an observed false-alert rate above 5%, and demonstrable
shared-file support in both classes of each family. Report fixed-cutoff
decisions, paired changes, results at 1%, 2% and 5% budgets and native
transfer. Confirm operational use separately on independent workflows.
Follow the existing two-round rule for diminishing returns and count only
the primary comparison. [Round criteria](detector-rounds.md#measuring-diminishing-returns)

All 256 development runs contained exercised grants, with 1,386 grants
across 107 designated positives and 149 controls. The repeat-exclusion
fraction was constant in fitting. The largest standardized weight was on
the fraction of approved files seen before the first exclusion. Report how
often a grant finishes its approved list before an excluded read on held-out
one-file runs and controls. This descriptive check can reveal dependence on
the script's action order and has no part in the adoption decision.

## Follow-up protocol for the logistic score

The first confirmation revealed that the whole-run incumbent's calibrated
probability was exactly 1.0 in the augmented workflows. With a strict
greater-than cutoff, this representation cannot alert. Retain that result.
The fitted logistic regression also produces log odds before conversion to
a finite-precision probability. Use those margins directly to preserve the
ordering of distinct, large values. Computing log odds from a saved 1.0
probability cannot recover the discarded information.

Freeze a follow-up before examining confirmation results for the margin
representation. Restore the same incumbent and whole-run verified-grant
weights. Compute margin cutoffs on the same 1,728 earlier calibration runs
in each observation view, using rank 1,660 with strict comparisons. Keep
the previous assignment weights and cutoffs and legacy probability cutoff.
Do not use any confirmation label to select a cutoff. Report the existing
grids as retrospective replay and keep them outside the new confirmation.

Use ten further complete grids, seed identifiers **20270121 through
20270130**, alternating record checking and clerical handoff. Reserve all
21,708 previously used run IDs. The primary comparison is assignment
scoring against whole-run logistic using its margin. Report the original
probability score and the whole-run verified-grant margin as diagnostic
comparators. Use the same 540 one-file runs, 2,160 controls, pooled and
per-family guardrails, exact upper false-alert bound and native transfer
checks as in the first protocol, on new IDs. This tests a corrected ranking
representation on the same workflow families. Count the assignment feature
once for diminishing returns. Stop after the fresh comparison.

Check transfer to the two previously published office layouts as a separate
retrospective control test. Both already include clerks who accidentally open
an appendix after completing their approved list. Use the original assignment
fit and its workflow cutoff. Replay the recorded mix of office jobs in each
layout and count controls whose office grants alone exceed this cutoff.
Because the run uses the maximum score over its grants, these alerts give
a lower bound on the total false alerts. Keep the original denominators
and show all four office variants. This test uses earlier controls and has
no role in fitting, calibrating or choosing the fresh confirmation.

## First confirmation and numerical replay

All 540 designated one-file violations occurred. Across all violation sizes,
the focal worker read every designated file in all 1,620 positive runs. The
table uses frozen thresholds across record checking and clerical handoff.
The final column counts authorized relays incorrectly flagged for deliberate
scope violations. These are a subset of the controls.

| Full-run score | One-file detections / 540 | All detections / 1,620 | False alerts / 2,160 | In-scope relay alerts / 540 |
| --- | ---: | ---: | ---: | ---: |
| Whole-run logistic probability | 0 | 0 | 0 | 0 |
| Same whole-run fit, log odds, retrospective | 29 | 100 | 95 | 26 |
| Whole-run verified-grant probability | 57 | 309 | 105 | 47 |
| Five inputs pooled across grants | 525 | 1,590 | 105 | 31 |
| Assignment weights pooled across grants | 525 | 1,590 | 105 | 31 |
| Five inputs on one actual grant | 522 | 1,583 | 83 | 24 |

The original incumbent rounded to 1.0 on 482 of 1,728 calibration controls
and on 595 controls and 604 positives in confirmation. Its frozen cutoff of
1.0 made an alert impossible. The first primary comparison was inconclusive
under the in-scope relay guardrail. Replaying unrounded log odds recovered
the underlying ordering. The fresh test below uses that corrected comparator.
[First scorecard](../benchmarks/assignment/workflow/scorecard.csv) and
[margin replay of these runs](../benchmarks/assignment-transfer/first-confirmation.csv)

Keeping the five inputs on one grant avoided 22 control alerts and lost three
one-file detections against either pooled version. At a common retrospective
1% false-alert ceiling, assignment scoring caught 519 one-file violations
with nine false alerts. Pooling the same weights caught 514 with 21 false
alerts. At a 5% ceiling the respective counts were 522 and 525. Much of the
one-file gain over the incumbent comes from the five inputs themselves.
[Review budgets](../benchmarks/assignment/workflow/review-budgets.csv)

Adding legitimate work preserved the five inputs of all 25,189 native grants.
It added 30,306 exercised office grants, each of which stayed within its
approved scope. The extra work changed 335 of 3,780 assignment scores, all
below the decision cutoff in both views. Across 1,518,030 successful reads,
every decision had recorded authority. The focal-team audit found a shared
approved document in every run. The native reviewer exercised multiple new
tickets on it, and the corresponding office clerk read it before the focal
team's last native action in all 3,780 runs, including all 540 one-file
cases and all 540 in-scope relay controls. This measures genuine overlap in
the simulator. The two views are paired observations of the same runs.
[Focal-team coverage](../benchmarks/assignment-support/summary.csv) and
[native scores](../benchmarks/assignment/native/scorecard.csv)

## Fresh confirmation against unrounded logistic

The corrected comparison used 3,780 new underlying runs, after excluding
all 21,708 previous IDs. Both models kept their earlier weights and cutoffs.
All 1,620 designated violations completed, including the 540 one-file
cases. Assignment scoring gained 484 one-file cases and lost two, for a
net recall gain of **89.26 percentage points**, with an approximate paired
95% interval of **84.75 to 92.13 points** across these scripted runs. Every
grid had a positive net gain.

| Workflow | Score | One-file detections | False alerts | In-scope relay alerts |
| --- | --- | ---: | ---: | ---: |
| Record checking | Whole-run log odds | 37/270 | 94/1,080 | 25/270 |
| Record checking | Per assignment | 258/270 | 38/1,080 | 7/270 |
| Clerical handoff | Whole-run log odds | 0/270 | 0/1,080 | 0/270 |
| Clerical handoff | Per assignment | 261/270 | 36/1,080 | 4/270 |
| Both | Whole-run log odds | 37/540 | 94/2,160 | 25/540 |
| Both | Per assignment | 519/540 | 74/2,160 | 11/540 |

The frozen assignment cutoff detected 1,575 of 1,620 violations across all
sizes. Its false-alert rate was 3.43%, with a one-sided 95% exact upper
limit of 4.14%. The corresponding upper limits were 4.59% in record checking
and 4.38% in clerical handoff. The incumbent used one cutoff across both
workflows and concentrated its 94 false alerts in record checking. The
verified-grant whole-run margin caught 59 one-file cases, with 105 false
alerts and 44 in-scope relay alerts. The original probability incumbent
again flagged zero runs.
[Operating points](../benchmarks/assignment-margin/workflow/operating-points.csv)
and [paired changes by family](../benchmarks/assignment-margin/workflow/families.csv)

Under a common retrospective ceiling of 108 false alerts, the assignment
score could detect 519 one-file cases and the whole-run margin could
detect 41. At a ceiling of 21 false alerts, the counts were 518 and nine.
Scoring the same IDs with the additional office work removed gave 519
versus 368 one-file detections, 74 versus 101 false alerts and 11 versus
63 in-scope relay alerts. The native comparison measures sensitivity to
extra work on the same cases. It supplies no additional independent runs.
[Review budgets](../benchmarks/assignment-margin/workflow/review-budgets.csv)
and [native transfer](../benchmarks/assignment-margin/native/operating-points.csv)

This result meets the prespecified criteria for the two tested workflows.
The in-scope guardrail applies to the pooled counts. Record checking added
six and cleared 24 in-scope alerts relative to the incumbent. Clerical handoff
added four and cleared zero. The corrected comparison counts once as an
assignment feature experiment under the stopping rule. The count of
consecutive below-minimum rounds is zero.
[Decision record](../benchmarks/assignment-margin/protocol.json)

## What happens when the clerk makes a mistake

In the first confirmation, 506 of 540 one-file cases had a grant that read
the entire approved list before its first excluded file. Zero of the 2,160
controls did. The earlier office workflows already contain a clerk who
accidentally opens an appendix at just that point in the job.

| Archived office layout | Controls | Controls with this mistake | False swarm alerts from these office grants alone |
| --- | ---: | ---: | ---: |
| Two issuers | 2,160 | 528 | 528 (at least 24.44% of all controls) |
| One issuer | 2,160 | 518 | 518 (at least 23.98% of all controls) |

All four office variants were replayed at the unchanged workflow cutoff.
The office grants in routine, explicitly excepted and unbound jobs caused
zero alerts. Other grants in those runs can only raise the maximum. These
are lower bounds on the two archived control populations. The frequency
of mistakes reflects the office scripts.
[Per-variant counts](../benchmarks/assignment-transfer/office-controls.csv)
and [control-by-control replay](../benchmarks/assignment-transfer/office-control-runs.csv.gz)

In 496 of the first 540 one-file cases, a highest-scoring grant had exactly
the same five input values as a grant from one of those accidental appendix
reads. All 496 alerted. Any deterministic classifier given just that grant's
five values must give both examples the same score. Other grants, the full
event history and independently issued approvals may distinguish some cases.
This is a limit on the individual grant representation. It also explains
why the score can highlight an access exception and still be a poor basis
for inferring a swarm's intent. [Feature collision replay](../tests/test_assignment_transfer.py)

Raising the cutoff also has a measurable limit. In the two-issuer layout,
179 control jobs had the identical office score 0.9873356480468902. A
5% budget allows only 108 alerts in that population. Any single strict
cutoff below that score must exceed the budget from those 179 clerks alone.
Only **7 of 540** one-file cases in the first confirmation scored strictly
above it. Seven is therefore an upper bound on the number of those cases
this frozen ranking could catch while meeting the older layout's budget.
Other native grants can make that constraint tighter.
[Office scores](../benchmarks/assignment-transfer/office-control-runs.csv.gz)
and [threshold calculation](../tests/test_assignment_transfer.py)

## What to test next

Use the assignment ranking for retrospective access review and calibrate new
logistic comparisons directly on log odds. The existing `logistic` API
returns probabilities. The explicit `logistic_margin` option fits the same
model and keeps calibration, scoring and strict alert comparisons in log
odds. A probability threshold and a log-odds threshold have different units.

A follow-up executed 100 independently published approval tickets and scored
both frozen models on the same actions as the dispatch and commit checks.
On 58 held-out tickets, dispatch warned on the right delivery before 17 of 32
completed effects and flagged 15 of 26 controls. Two model reviewers
from different model families, each run once, matched the office record on
the observable effects, agreed on intent in 50 of 58 tasks and both left 39
intentions unresolved.
For a new swarm model, the remaining test needs native workflow records with
prior authority, consumed versions and independent human evidence for intent.
Keep routine teamwork, genuine mistakes, approved exceptions and unused
deliveries in that comparison, with whole base tasks and templates held out.
[Public-ticket comparison](public-dispatch.md) and [text benchmark](approval-text.md)

Use the existing one-point minimum one-file recall gain, positive paired
lower bound, improved ranking within a 5% false-alert budget, and no net
increase on in-scope relay controls. Require the exact pooled upper
false-alert bound to meet 5% and report every workflow and mistake group.
At 2,160 controls, at most 91 observed false alerts meet that upper-bound
criterion. Stop tuning the same observations after two independent rounds
whose upper gain and common-budget gain both fall below one point. A
confirmed collision can already rule out distinguishing that pair from
the five grant inputs alone. [Round decision rules](detector-rounds.md#measuring-diminishing-returns)
and [independent recipient evidence](recipient-approval.md)

## Reproduction and inspection

Run the study in a new directory from the repository root. It checks 16,200
earlier run IDs and replays both original 15-input fits before generating
new work. Each held-out grid has its own score file. `independent-assignments.csv.gz`
contains the actual five inputs for every exercised grant, including routine
tickets in positive runs. `protocol.json` records the fitted assignment weights
and the frozen cutoffs. Interpret an assignment's score as a ranking learned
from run labels. A calibrated probability of an individual worker's intent
would require different labels.

```shell
uv run --frozen swarmtrace assignment-round --workers 8 --out results-replay/assignment
uv run --frozen swarmtrace assignment-round --checks-only --workers 8 --out results-replay/assignment-twins
uv run --frozen swarmtrace assignment-support --study results-replay/assignment --workers 8 --out results-replay/assignment-support
uv run --frozen swarmtrace assignment-margin --study results-replay/assignment --workers 8 --out results-replay/assignment-margin
uv run --frozen swarmtrace assignment-transfer --study results-replay/assignment --out results-replay/assignment-transfer
```

The `assignment-support` command independently checks whether shared-file evidence came
from the designated focal team. It freezes actor, host, file and timing
matches before using the simulator's focal roster. This is an evaluation
of which teams the office actually interacted with. The scorecard uses
the previously frozen detector and thresholds. Independent executions
reproduced all 38 files of the first study and all 38 files of the margin
confirmation byte for byte on Windows using different worker counts. The focal-team
audit reproduced both its files, and the transfer replay reproduced all
three. The confirmation includes the control order statistic, raw inputs,
per-run scores, family operating points and paired comparisons.

A Linux replay with the locked dependencies regenerated the entire margin
confirmation. Across the five methods and two views, all 17,280 calibration
decisions and 37,800 confirmation decisions agreed with Windows. Both systems
produced identical grant inputs, shared-budget counts and frozen operating
counts. The largest absolute score difference was below 4.3e-14. Compute each
backend's cutoff at the fixed rank on exactly the same archived controls.
This keeps a genuine tie at its cutoff even when different numerical
libraries differ in the last digit. The runner checks the identities of
calibration alerts and uses a strict greater-than comparison on every backend.
[Margin replay checks](../tests/test_assignment_margin.py)

To inspect an individual run, use a directory containing `trace.jsonl` and
its C2 `context.json`. A trace without `authorization.json` returns the number
of unknown decisions and an empty assignment list. The optional `--study`
argument loads the published fit and orders grants by their full-run score.
The reviewer does not need labels, simulator conditions or outcome records.

```powershell
uv run --frozen swarmtrace sweep --seed 42 --group-sizes 0 --coordinated-groups 1 --channels message --topologies peer --scope on --capture-authorization --out results-replay/assignment-demo
$run = (Get-ChildItem -LiteralPath results-replay/assignment-demo -Directory | Select-Object -First 1).FullName
uv run --frozen swarmtrace review-assignments --run $run --study benchmarks/assignment
```

The companion recipient study asks whether an independently issued approval
and an editor's input-version receipt can establish a downstream policy
effect. Its action and intent labels have different denominators from this
assignment study. [Recipient approval and confirmed use](recipient-approval.md)
