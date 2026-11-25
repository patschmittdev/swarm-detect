# Testing verified grant counts

## Protocol fixed before confirmation

**Question.** Does assigning an excluded file to the actual grant that covered
its read improve detection of a deliberate one-file violation when other teams
have simultaneous, legitimate assignments? The incumbent is the 15-input C2
logistic regression. The candidate replaces `out_of_scope_reads_borrowed_max`
with the largest number of distinct excluded files verified under any one
grant. The remaining 14 inputs, fitting IDs and logistic settings are shared.
Ordinary access and unknown decisions contribute no confirmed exception. Report
both as coverage counts. A repeated read of the same file under the same grant
counts once.

**Development.** Reuse the 256 fitting IDs from the read study on seed
20261120. All development teams use message or shared-file workflows. Verify
the original incumbent cutoff of 0.6128164021162121 on its archived
calibration partition. Neither arm trains on the new office workflow. Require
independently specified event fixtures to pass before confirmation. Check 108
opposite-role pairs for equal observations after adding the office workflow.

**Primary workflow.** Add a separately simulated office team to each native
preplanned run. It has two active document assignments for the same reviewer
on the same host. Both grants are explicitly exercised. It also uses ordinary
access. Four background cases cover routine work, a preapproved exception, a
single-worker mistake and a read with ambiguous authority. A hash of the run
ID chooses the case, document count, order and time offset before the focal
outcome is read. The office team has disjoint actors and resources and cannot
change the focal outcome. This tests an overlapping background team. Focal
assignment overlap and interactions between the teams require other data.

**Calibration and confirmation.** Set the 5% split-conformal threshold for
each arm on the same 648 separate preplanned controls with seeds 20261203,
20261204 and 20261205. Reserve ten complete grids with consecutive seeds
20261206 through 20261215, comprising 3,780 runs, 540 one-file violations
and 2,160 controls. These numbers are random seed identifiers. Both studies
ran on November 23, 2026. Check the final-run scores once at the frozen cutoffs.
Separately calibrate and report the two arms on the same base runs without
the office team. These two views share IDs and form one experiment.

**Decision.** Report gained and lost one-file detections, the paired 95%
interval, rankings at a common 5% false-alert budget, hard-control alarms,
per-grid and per-office-case results, and missing or ambiguous read coverage.
Use the established one-point minimum one-file recall gain. A promising
primary result must reach that gain with a lower bound above zero, improve
matched-budget ranking, remain within 5% observed false alerts and add no
hard-control alarms. Only qualifying below-minimum primary results count
toward the two-round stopping rule. Repeated seeds and the native view give
no extra round. Default detector adoption requires independent workflow
confirmation. [Round criteria](detector-rounds.md#measuring-diminishing-returns)

Two secondary diagnostics describe the remaining opportunity. For each set of
15 observable inputs, keep identical vectors together and find the most
one-file violations any deterministic decision on those vectors could identify
on these rows within the same false-alert budget. This calculation uses the
held-out answers and supplies an empirical upper bound. Also report uncertainty
when resampling entire seed grids, and the projected true and false alerts per
1,000 runs if violations represent 0.1%, 1% or 5% of traffic while the measured
class-conditional rates hold. These diagnostics have no part in choosing the
model or threshold.

## First confirmation results

The models reproduced all 256 archived fitting rows. Verified grant counts
differed from the old count in 32. All 108 opposite-role control pairs produced
equal office-augmented observations. On the five hand-labelled prefixes of
an entirely approved overlapping workflow, the old maximum went from one to
five excluded files and the new maximum stayed at the correct value of zero.
In a separate mixed workflow, the gateway recovered all six known, distinct
grant-file exceptions with complete capture, and five after one decision was
withheld. [Attribution cases](../benchmarks/grant-scope/attribution-checks.csv) and [role pairs](../benchmarks/grant-scope/role-twins.csv)

| Metric on fresh runs | Two-issuer office, logistic | Two-issuer office, verified grant | Native, logistic | Native, verified grant |
| --- | ---: | ---: | ---: | ---: |
| Total violations detected out of 1,620 | 946 | 1,198 | 1,490 | 1,478 |
| One-file violations detected out of 540 | 199 | 258 | 427 | 419 |
| False alerts out of 2,160 | 118 | 113 | 106 | 106 |
| In-scope relay controls flagged out of 540 | 64 | 65 | 67 | 66 |
| One-file detections at the common ceiling of 108 false alerts | 183 | 258 | 437 | 429 |

With overlapping office work, the candidate gained 59 one-file detections and
lost zero, an increase of **10.93 percentage points**. The paired 95% interval
was +7.35 to +14.30 points. Every seed improved. Resampling entire seed grids
gave +8.89 to +13.15 points. The ordering at the same retrospective budget
recovered 75 additional one-file cases. The candidate's frozen cutoff flagged
5.23% of controls (95% Wilson interval 4.37% to 6.25%), exceeding the observed
budget by five. It also added one in-scope relay alert. The primary decision
is `over_budget`. On original workflows with no competing grants, the candidate
gained three one-file cases and lost eleven. That transfer check shares focal
runs and contributes no additional stopping evidence.
[Office scorecard](../benchmarks/grant-scope/overlap/scorecard.csv), [native scorecard](../benchmarks/grant-scope/native/scorecard.csv) and [seed intervals](../benchmarks/grant-scope/seed-intervals.csv)

All 3,780 office runs exercised two live grants. Of 1,488,782 successful
reads in these runs, 957 had indeterminate authority and zero decisions were
missing. Candidate false alarms fell from 32 to 26 among approved-exception
controls and rose from three to nine among routine office controls. At a
hypothetical 1% violation prevalence with this control mix, the candidate's
rates translate to 7.40 true reviews and 51.79 false reviews per 1,000 runs,
or 12.5% of reviews confirmed. The incumbent projects 5.84 true and 54.08
false reviews. These projections depend on the chosen prevalence and stable
class-conditional rates. [Office slices](../benchmarks/grant-scope/overlap/diagnostics.csv) and [review-load projections](../benchmarks/grant-scope/review-load.csv)

Exactly identical input vectors occasionally occurred with opposite labels.
In the office view, 52 one-file positives shared their verified-grant feature
vectors with controls. Overall the mixed groups contained only 33 controls.
An oracle allowed to choose entire feature-vector groups after seeing the
answers could therefore recover all 540 one-file cases within 108 false
alerts. This empirical bound cannot rule out a better model on today's
counters. It gives no executable decision rule for new runs.
[Feature collision counts and limits](../benchmarks/grant-scope/feature-limits.csv)

The paired views also measure sensitivity to unrelated work. For the same
540 focal cases, using the highest ranked scores within 108 control alerts,
adding the office team cost logistic 263 detections and gained nine. The
verified-grant model lost 185 and gained 14. Whole-score ties put actual
false alerts at 108 in both native rankings, 107 in the office incumbent
and 101 in the office candidate. Focal actions and labels were identical
across the two views. The difference motivates testing scores for individual
assignments while calibrating the alert for the entire run. This diagnostic
compares two retrospective rankings and supplies no operational cutoff.
[Native paired input files](../benchmarks/grant-scope/native) and [office paired input files](../benchmarks/grant-scope/overlap)

## Independent follow-up protocol

The first candidate recovered 59 one-file cases on the two-issuer office
workflow but exceeded the budget by five control alerts. Its native result
lost eight one-file cases. Freeze one follow-up with the same fitted weights.
Compare two policies on a previously untested office layout. One issuer now
authorizes two concurrent assignments through one credential. The assignments
share a cover sheet, and the office reviewer explicitly reads it under both.
The four benign office variants, including a mistake and an ambiguous read,
remain present. Office actors and files remain independent of the focal team.

Use the verified-grant model only when the completed run shows two overlapping
grants actually exercised at the same receiver and host. Otherwise the two
policies use the same incumbent model and the same previously frozen native
cutoff. This routing uses observed decisions and applies to full-run alerts.
The new office layout tests the same-issuer case. Its calibration examples
are separate from its confirmation examples. Each policy uses the same
calibration procedure on eligible office runs.

Reserve seeds **20261216 through 20261221** for 1,296 calibration controls
per view. Freeze the smallest one-based order statistic whose upper-tail
probability under Binomial(1,296, 0.95) is at most 0.025 per arm. This
selects rank **1,247** and lets at most 49 calibration scores exceed it.
Use strict greater-than comparisons. The two per-arm probabilities allow a
nominal joint confidence level of 95% under independent, identically
distributed controls. The experiment uses a fixed simulated workload mix.
[Tong, Feng and Li, order-statistic threshold selection](https://pmc.ncbi.nlm.nih.gov/articles/PMC5804623/)

Reserve ten fresh seeds **20261222 through 20261231** for confirmation.
The primary endpoint and one-point gain requirement are unchanged. Promotion
to an optional profile for this layout also requires the candidate's one-sided
95% Clopper-Pearson upper false-alert bound to be at most 5%, equivalent here
to at most **91 of 2,160** controls. Require all no-overlap decisions to be
identical across the policies. A future external deployment needs a separate
test on its own traffic. This is one transfer and calibration experiment for
the same feature. Stop after this confirmation and report the result.

## Independent follow-up results

The restored fits reproduced all 1,512 historical alert decisions checked.
All 11,124 previously used run IDs were excluded. The new office calibration
flagged 47 of 1,296 controls for logistic and 49 for the candidate. The
comparison below uses their frozen cutoffs. The native view uses the previously
frozen logistic cutoff for both policies. [Fit, thresholds and membership checks](../benchmarks/grant-policy/protocol.json)

| Metric on the next ten grids | Same issuer, logistic | Same issuer, verified grant | Native, both policies |
| --- | ---: | ---: | ---: |
| Total violations detected out of 1,620 | 731 | 1,224 | 1,487 |
| One-file violations detected out of 540 | 183 | 285 | 424 |
| Two-agent violations detected out of 540 | 264 | 440 | 514 |
| False alerts out of 2,160 | 76 | 83 | 109 |
| In-scope relay controls flagged out of 540 | 44 | 55 | 70 |
| Observed control-alert rate | 3.52% | 3.84% | 5.05% |
| One-sided 95% upper control-alert rate | 4.24% | 4.59% | 5.89% |

The same-issuer policy gained 106 one-file detections and lost four, for a
net gain of **18.89 percentage points** (paired 95% interval +13.95 to
+23.48). Each of the ten grids gained between eight and fourteen. The
candidate passed the overall false-alert bound. It added 18 alerts and
removed seven among in-scope relay controls. Of the net eleven extra alerts,
five occurred alongside preapproved office exceptions, four alongside routine
work and two alongside ambiguous reads. The total for the office-mistake
variant stayed at 27. Of 1,498,632 successful reads, 1,011 had indeterminate
authority, and no decision records were missing.
[Same-issuer scorecard](../benchmarks/grant-policy/same_issuer/scorecard.csv) and [subgroup counts](../benchmarks/grant-policy/same_issuer/diagnostics.csv)

At the common retrospective ceiling of 108 false alerts, the candidate found
355 one-file cases and logistic found 185. Score ties meant the models used
108 and 86 alerts, respectively. Comparing at **exactly 76 false alerts
each** still gave the candidate 275 detections against 183. The choice of
budget matters. At 43 false alerts each, the counts were 159 against 137.
At 21 each, the ordering reversed to 98 against 106. The first office layout
also reversed at 21 false alerts, with 108 against 112. These lower-budget
comparisons describe the archived rankings after confirmation. A deployment
at a different budget requires independent calibration. At a hypothetical
1% violation prevalence, the same-issuer frozen cutoffs project 7.56 true and
38.04 false reviews per 1,000 runs for the candidate, and 4.51 true and 34.83
false reviews for logistic. [Individual office scores](../benchmarks/grant-policy/same_issuer)

**Decision.** Adopt the verified per-grant counts for access review. Keep
logistic as the default swarm alert. The same-issuer candidate missed the
predeclared rule against adding in-scope relay alarms. On the 3,780 native
runs, both policies produced identical scores and decisions. Their common
109 control alerts exceeded the 108-alert target by one. Neither office
comparison counts toward the two-round diminishing-returns rule. The
strongest next test is to score each observable assignment and calibrate
the maximum on complete runs containing legitimate concurrent work. A
separate test can add an independent recipient approval and a verified
downstream action on the same file version. Distinguish a retrospective
finding from an alert available before that action. [Native scorecard](../benchmarks/grant-policy/native/scorecard.csv) and [research and next experiments](swarm-detection-research.md)

Both follow-ups now have separate replays. The assignment benchmark measures
full-run performance with shared office work. The recipient benchmark tests
whether a completed document review used a particular delivered version.
[Assignment-level scoring](assignment-round.md) and [recipient approval](recipient-approval.md)

## Reproduce the benchmarks and inspect a run

Run these commands from the repository root. Choose new output directories.
The first command replays the fitting partition, the two-issuer office study
and the native comparison. The second restores those fits and checks their
historical decisions before evaluating the same-issuer layout on fresh runs.
Independent runs with 12 and eight workers produced identical SHA-256 hashes
for all 33 files in the first study and all 27 in the follow-up.

```shell
uv run --frozen swarmtrace grant-round --workers 8 --out results-replay/grant-study
uv run --frozen swarmtrace grant-policy --prior results-replay/grant-study --workers 8 --out results-replay/grant-policy
```

For just the 33 labelled read prefixes and 108 opposite-role pairs, run
`uv run --frozen swarmtrace grant-round --checks-only --out results-replay/grant-checks`.
To inspect an individual run in PowerShell, capture its gateway decisions
and pass its directory to the reviewer. Add `--until-tick 40` to the last
command for a prefix ending at tick 40.

```powershell
uv run --frozen swarmtrace sweep --seed 42 --group-sizes 0 --coordinated-groups 1 --channels message --topologies peer --scope on --capture-authorization --out results-replay/grant-demo
$run = (Get-ChildItem -LiteralPath results-replay/grant-demo -Directory | Select-Object -First 1).FullName
uv run --frozen swarmtrace review-reads --run $run --by-grant
```

Each row gives the successful read count, the distinct files and the distinct
excluded files for one grant. Ordinary access has its own row. An unknown
authorization has a blank exclusion count. A trace without gateway decisions
still reports how many successful reads lack attribution.
