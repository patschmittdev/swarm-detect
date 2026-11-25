# Main result in detail

This page holds the full account of the main dataset. The README gives the
short version. Every number comes from a file under `data/`.

All numbers below are from the by-run split of the recorded dataset (32 relay
runs and 86 control runs in the test set) unless a different split is named.
The tables they come from are in the generated block at the end of this page.

**Access logs alone do not separate a relay from teamwork.** At V0, and with the
generic coordination features at any tier, every detector scores near or below
0.5 AUROC (logistic 0.440, boosted 0.418). The simulator makes relay and
delegation identical at V0 on purpose, so this is the expected result and a
check that nothing leaks the label.

**Audit logs (V1) reach AUROC 0.92, and the chosen sharing rate sets that
number.** With the aggregation features, logistic scores 0.920 [0.873, 0.961]
and boosted 0.926 [0.877, 0.967]. Over 20 split seeds the means are 0.923 (SD
0.016) and 0.924 (SD 0.020). 14 of the 86 test controls contain a benign team
that shares a credential, and such a run looks like a relay. If those runs tie
with relays at random and every other control is separated perfectly, the
expected AUROC is 1 - (14/86)/2 = 0.919. The measured values are within noise
of that. They can sit slightly above it because a relay run can also contain a
sloppy benign team among its other teams, which adds shared logins. Against
controls with no sharing team the separation is complete (AUROC 1.000), and
all 5 false positives are sharing controls. A different sharing rate would
give a different headline number.

**A sloppy benign team is the same behaviour as the offence, by construction.**
In the main dataset the relay group and a sloppy-sharing benign team run the
same code path. Team for team, they differ only in their label. The mix of
team sizes across runs differs, and the fitted logistic model gains a little
from it (see the sharing-rate experiment in the README). So the chance-level result against
the 14 sharing controls (logistic 0.511 [0.332, 0.678], boosted 0.542 [0.369,
0.719], rule 0.442 [0.300, 0.621]) is a check that the pipeline has no hidden
cue, not a discovery. The
claim it supports is narrow: a log can show that a credential was shared, and
it cannot show why. The default "10% of benign teams share" means that 53 of
288 control runs (18%) contain at least one sharing team.

**0.92 AUROC is not a 92% detection rate.** At the threshold calibrated for a 5%
false-positive rate, logistic flags 14 of 32 relay runs and boosted 13 of 32,
with 5 of 86 controls flagged. The threshold falls inside the range of
sharing-control scores, so a flag in practice means "many pairs with shared
logins": a large group, or two sharing groups in one run. Logistic flags 7 of
the 7 relay runs that also contain a sloppy benign team and 7 of the 25 that do
not.

**The obvious rule ranks runs as well as the fitted models and flags fewer.**
The rule baseline has no fitted parameters: its score is the number of agent
pairs with at least one shared-credential login. Its AUROC is 0.909 [0.851,
0.959], against 0.920 and 0.926 for the fitted detectors; over 20 split seeds
the means are 0.928 against 0.923 and 0.924. At the calibrated threshold it
flags 7 of 32 relay runs, half as many as logistic's 14, with 4 of 86 controls
flagged against logistic's 5. The reason is the integer score. The threshold
is 4 pairs, a run is flagged only above it, and 5 relay runs score exactly 4.
Logistic flags all 5 of those and 3 more with only 2 or 3 sharing pairs, and
misses one run the rule flags. Its inputs are the maximum, top-k mean and
count of shared-credential logins and of access expansion, so its scores are
continuous and not tied at 4.

**Small groups mostly pass under the threshold.** Logistic flags 2 of 13
two-member relays, 6 of 12 three-member relays and 6 of 7 five-member relays.
The rule flags 1 of 13, 3 of 12 and 3 of 7. The counts are small and the
intervals are wide.

**Attribution finds every relay member but also names benign agents.** At V1
with the aggregation features, the pair scorer on its own names 97 of 97 offensive agents in the test set, and
97 of the 176 agents it names are offensive. Gated by a detector's run-level
flag, recall and precision are both about one half (logistic: 52 of 97 and 52
of 103). Every wrongly named agent is a member of a benign team that shares a
credential: 79 of 79 for the pair scorer, 51 of 51 for logistic, 49 of 49 for
boosted and 42 of 42 for the rule. With the aggregation features at V1 and V2,
on the by-run split and every hold-out, no solo agent and no member of a
non-sharing team is named. So with these features attribution's errors are the
same sharing teams that limit detection. This does not hold with all features:
there, members of non-sharing teams are named too (V1 by run: 11 for logistic,
85 for the pair scorer). When a run is flagged, the offensive group is
recovered exactly: the pair scorer reconstructs it in 32 of 32 relay runs, and
gated by logistic in 14 of 32, which is every run logistic flags.

**The result rests on one feature.** `shared_credential_logins` carries the
signal. `access_expansion_after_receipt` is a V0 feature and adds no ranking
power, but the fitted logistic model gives it weight, which moves individual
runs across the threshold. No
feature reads content and there is no V2 aggregation feature, so V2 aggregation
results equal V1. V2 adds one generic feature, `provenance_links`, which does
not change the conclusion.

**Detection does not transfer reliably when the relay group's condition is
held out.** The hold-outs apply to the relay (focal) group's channel or
topology only. Other teams in the training runs draw their own channel and
topology, so the held-out value is not strictly unseen. AUROC stays between
0.75 and 0.97 (0.90 to 0.96 for the rule), but the calibrated threshold does
not carry over. Boosted flags
0 of 54 relay runs with hub held out. Online, with peer held out, it flags 35
of 54 relay runs and also 26 of 144 controls. Part of this is a calibration
artefact: the topology hold-outs have 43 calibration controls, so the threshold
is the second-highest calibration score, and in the hub and boosted cell the
top two tie, which puts the threshold at the calibration maximum.

**Online detection is weak and mostly late.** On the by-run split, 13 of 32
relay runs cross the logistic online threshold at some checkpoint, at 5 of 86
controls. Only 7 of 32 cross strictly before the relay completes and 2 more
cross at the completion tick; the mean first crossing is at 1.02 times the
completion tick. Boosted crosses strictly before completion in 11 of 32, at
0.82 times the completion tick on average. The rule crosses strictly before
completion in 3 of 32, and 1 more crosses at the completion tick.

**Scores below 0.5 are a property of the run pool, not a signal.** Detectors
using only generic features average 0.45 to 0.47 over 20 split seeds (generic
logistic 0.450, SD 0.041), while the volume baseline averages 0.502. With
labels shuffled, every detector averages 0.48 to 0.52. The runs come from a
small grid of conditions with a fixed class ratio, and a fitted model with no
signal ranks slightly backwards inside that pool. Read these values as "no
detection", not as an inverted signal.

**Controls.** Three deliberately loud relays are flagged by both fitted V1
aggregation detectors, and logistic scores them above every calibration control. Boosted
does not: one benign control with a sharing team scores 0.8842, above the
lowest loud run at 0.8800. The boosted model is not monotone in shared-login
counts and is flat beyond its fitting range, where the largest count is 2, so
no amount of re-use can meet that bar. It is reported as not met and is not
gated. Boosted's two gated bars would also be met by a relay with no extra
re-use, so only the logistic strict bar tests loudness. This rule was revised
after the fact: the original rule required both detectors to meet the strict
bar, boosted failed it, and the rule was then split by detector. The rule
baseline is reported beside them and never gated: it flags the 3 loud runs,
and its strict bar is not met, because extra re-use of one credential does not
add pairs (lowest loud run 5, highest calibration control 5). On 18 all-benign
runs logistic and boosted each flag 1, a run that contains a sharing team, and
the rule flags none.

## Generated tables

The block below is pasted by `swarmtrace reproduce --readme RESULTS.md` from
`data/headline.md`. Full tables: [V0](data/results-V0.md),
[V1](data/results-V1.md), [V2](data/results-V2.md),
[controls](data/controls.md), [shuffled labels](data/negative-control.md),
[split stability](data/split-stability.md).

## Simulator details

- The three `xcorr_lag*_n_above` generic features are constant across all 396
  recorded main runs.
- Every agent's mistakes target one fixed host per run, and with fewer than 15
  agents team sizes are anti-correlated.

<!-- BEGIN GENERATED RESULTS -->

## By-run split

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Tier | Family | Detector | AUROC | Detection rate at calibrated threshold | FPR | Online coverage | Online FPR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| by run | V0 | generic | volume (family-independent) | 0.525 [0.413, 0.648] | 0 of 32; 0.000 [0.000, 0.107] | 3 of 86; 0.035 [0.012, 0.098] | 3 of 32; 0.094 [0.032, 0.242] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V0 | generic | logistic | 0.440 [0.308, 0.550] | 4 of 32; 0.125 [0.050, 0.281] | 4 of 86; 0.047 [0.018, 0.114] | 2 of 32; 0.062 [0.017, 0.201] | 11 of 86; 0.128 [0.073, 0.215] |
| by run | V0 | generic | boosted | 0.418 [0.303, 0.529] | 4 of 32; 0.125 [0.050, 0.281] | 12 of 86; 0.140 [0.082, 0.228] | 1 of 32; 0.031 [0.006, 0.157] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V0 | generic | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| by run | V1 | aggregation | volume (family-independent) | 0.525 [0.413, 0.648] | 0 of 32; 0.000 [0.000, 0.107] | 3 of 86; 0.035 [0.012, 0.098] | 3 of 32; 0.094 [0.032, 0.242] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V1 | aggregation | logistic | 0.920 [0.873, 0.961] | 14 of 32; 0.438 [0.282, 0.607] | 5 of 86; 0.058 [0.025, 0.129] | 13 of 32; 0.406 [0.255, 0.577] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V1 | aggregation | boosted | 0.926 [0.877, 0.967] | 13 of 32; 0.406 [0.255, 0.577] | 5 of 86; 0.058 [0.025, 0.129] | 12 of 32; 0.375 [0.229, 0.547] | 6 of 86; 0.070 [0.032, 0.144] |
| by run | V1 | aggregation | rule | 0.909 [0.851, 0.959] | 7 of 32; 0.219 [0.110, 0.388] | 4 of 86; 0.047 [0.018, 0.114] | 7 of 32; 0.219 [0.110, 0.388] | 4 of 86; 0.047 [0.018, 0.114] |
| by run | V2 | all | volume (family-independent) | 0.525 [0.413, 0.648] | 0 of 32; 0.000 [0.000, 0.107] | 3 of 86; 0.035 [0.012, 0.098] | 3 of 32; 0.094 [0.032, 0.242] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V2 | all | logistic | 0.913 [0.860, 0.955] | 15 of 32; 0.469 [0.309, 0.636] | 8 of 86; 0.093 [0.048, 0.173] | 10 of 32; 0.312 [0.180, 0.486] | 4 of 86; 0.047 [0.018, 0.114] |
| by run | V2 | all | boosted | 0.903 [0.848, 0.953] | 18 of 32; 0.562 [0.393, 0.718] | 9 of 86; 0.105 [0.056, 0.187] | 6 of 32; 0.188 [0.089, 0.353] | 4 of 86; 0.047 [0.018, 0.114] |
| by run | V2 | all | rule | 0.909 [0.851, 0.959] | 7 of 32; 0.219 [0.110, 0.388] | 4 of 86; 0.047 [0.018, 0.114] | 7 of 32; 0.219 [0.110, 0.388] | 4 of 86; 0.047 [0.018, 0.114] |

## V1 aggregation: offensive group size

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Detector | Size 2 | Size 3 | Size 5 |
| --- | --- | --- | --- |
| volume (family-independent) | 0 of 13; 0.000 [0.000, 0.228] | 0 of 12; 0.000 [0.000, 0.242] | 0 of 7; 0.000 [0.000, 0.354] |
| logistic | 2 of 13; 0.154 [0.043, 0.422] | 6 of 12; 0.500 [0.254, 0.746] | 6 of 7; 0.857 [0.487, 0.974] |
| boosted | 1 of 13; 0.077 [0.014, 0.333] | 6 of 12; 0.500 [0.254, 0.746] | 6 of 7; 0.857 [0.487, 0.974] |
| rule | 1 of 13; 0.077 [0.014, 0.333] | 3 of 12; 0.250 [0.089, 0.532] | 3 of 7; 0.429 [0.158, 0.750] |

## V1 aggregation: positives versus sharing controls

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Detector | Positive test runs | Sharing controls | All test controls | Restricted AUROC |
| --- | --- | --- | --- | --- |
| volume (family-independent) | 32 | 14 | 86 | 0.504 [0.346, 0.661] |
| logistic | 32 | 14 | 86 | 0.511 [0.332, 0.678] |
| boosted | 32 | 14 | 86 | 0.542 [0.369, 0.719] |
| rule | 32 | 14 | 86 | 0.442 [0.300, 0.621] |

Independent benign test: 18 control / 0 positive; independent loud test: 0 control / 3 positive.
Binding loud gate: passed.
Full headline and held-out tables: [headline](data/headline.md). Full reports: [V0](data/results-V0.md), [V1](data/results-V1.md), [V2](data/results-V2.md), [controls](data/controls.md), [shuffled labels](data/negative-control.md).

<!-- END GENERATED RESULTS -->
