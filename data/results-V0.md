# Results, tier V0

Detection rates use 95% Wilson intervals, with k of n runs. AUROC, means and attribution use percentile bootstrap intervals over runs and show valid/requested resamples. Attribution precision and recall count agents (k of n agents), but agents in one run are not independent, so their intervals resample whole runs, not agents.

Resampling: test runs are resampled with replacement within strata, each stratum to its own size. AUROC is stratified by positive and control runs; time to detection resamples detected runs with an objective tick above 0. Bootstrap treats runs as independent even though default control conditions each have 16 replicates (2 rpc x 8 repeats). Its interval is withheld when a stratum has fewer than 2 runs or fewer than 90% of requested resamples give a defined value.

Calibration: each split's training runs are divided by run, stratified by class, into a fitting set and a calibration set (30% of each class). Every model is fitted on the fitting set, and its threshold is the split-conformal quantile of its own scores on the calibration control runs (the ceil((n + 1)(1 - alpha))-th smallest of n, alpha = 0.05; +inf, never firing, when n is too small). Run counts per split are in the Calibration table.

Full-trace detection uses a model fitted on complete fitting-set traces. Detection rate is the fraction of positive test runs scoring above its calibrated threshold; FPR is the corresponding fraction of control test runs.

Online detection uses a separate model fitted on prefix features at checkpoints (every 8 ticks plus the final tick), with a run-level threshold calibrated on each calibration control run's maximum checkpoint score. Online FPR is the fraction of control test runs crossing it at any checkpoint. Coverage is the fraction of positive test runs crossing it at any checkpoint. Among positive runs with an objective tick above 0, Detected strictly before completion is the fraction whose first crossing checkpoint is before that tick, and Detected at completion the fraction whose first crossing checkpoint is that tick; an undetected run counts in neither. Time to detection is the mean first-crossing checkpoint tick divided by the objective tick, conditional on detection; it is quantized to the checkpoint cadence.

Attribution rows: for each detector, groups proposed by the pair scorer count only in runs that detector flags; offensive agents in unflagged runs are false negatives. The pairs row is the pair scorer on every test run, a diagnostic not gated by any detector. Attribution precision and recall resample test runs within positive and control strata; group reconstruction resamples positive test runs.

Group reconstruction, per positive test run: the proposed group is the connected component of flagged pairs with the most offensive members (ties to the larger Jaccard overlap, then to the first sorted agent ids). It is empty, with Jaccard overlap 0, when the detector does not flag the run or no pair is flagged. Reconstructed exactly means the proposed group equals the offensive group.

Wrongly named agents: non-offensive agents in any proposed group, counted by role, out of all wrongly named agents (precision's denominator minus its numerator). Roles come from the labels. The labels do not say which benign team shares credentials, only how many teams in a run do (benign_sharing_teams). A team is observed sharing when two of its members have a shared-credential login (shared_credential_logins in the V1 pair table); a non-sharing team cannot produce one. This evidence is always taken at V1, whatever the tier or feature family of the table, because the role table describes ground truth, not what the defender sees; it stays on the evaluation side. A team is also sharing when every benign team in its run is declared sharing. When the sharing teams found number exactly the declared count, the run's other benign teams are non-sharing; otherwise they are counted as sharing unresolved, never guessed. No sharing metadata means the run's condition lacks benign_sharing_teams.

A degenerate bootstrap interval is one where every valid resample gave the same value, so both ends are equal; it is printed with that qualification, because it reflects the few runs that carry the count, not certainty about the population rate.

Rule: a baseline with no fitted parameters. Its score for a run is the number of agent pairs with at least one shared-credential login (shared_credential_logins_n_above, a V1 aggregation feature). Its full-trace and online thresholds are calibrated like the fitted detectors', and a run is flagged when its count is strictly above the threshold, so a control tied at the threshold is not flagged. Online, it is the same count on each prefix. Its attribution rows gate the pair scorer by its own flags. It is not available at V0 or without aggregation features.

## In-distribution

### Calibration

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Fitting runs | Calibration runs | Calibration controls | Test runs | Never fires (calibration set too small) |
| --- | --- | --- | --- | --- | --- |
| by run | 194 | 84 | 61 | 118 | none |

### Features: generic

Volume is a family-independent reference; its columns do not change.

### Full-trace detection

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Detector | AUROC | Detection rate at calibrated threshold | FPR on controls |
| --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 0.525 [0.413, 0.648] (118 of 118 runs; 200/200 resamples) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.035 [0.012, 0.098] (3 of 86 runs; Wilson) |
| by run | logistic | 0.440 [0.308, 0.550] (118 of 118 runs; 200/200 resamples) | 0.125 [0.050, 0.281] (4 of 32 runs; Wilson) | 0.047 [0.018, 0.114] (4 of 86 runs; Wilson) |
| by run | boosted | 0.418 [0.303, 0.529] (118 of 118 runs; 200/200 resamples) | 0.125 [0.050, 0.281] (4 of 32 runs; Wilson) | 0.140 [0.082, 0.228] (12 of 86 runs; Wilson) |
| by run | rule | not available at this tier | not available at this tier | not available at this tier |

### Online detection

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Detector | Online FPR on controls | Detection coverage | Detected strictly before completion | Detected at completion | Time to detection (conditional on detection) |
| --- | --- | --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 0.058 [0.025, 0.129] (5 of 86 runs; Wilson) | 0.094 [0.032, 0.242] (3 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 2.422 [1.571, 4.077] (3 of 32 runs; 200/200 resamples) |
| by run | logistic | 0.128 [0.073, 0.215] (11 of 86 runs; Wilson) | 0.062 [0.017, 0.201] (2 of 32 runs; Wilson) | 0.062 [0.017, 0.201] (2 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.764 [0.622, 0.907] (2 of 32 runs; 200/200 resamples) |
| by run | boosted | 0.058 [0.025, 0.129] (5 of 86 runs; Wilson) | 0.031 [0.006, 0.157] (1 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.031 [0.006, 0.157] (1 of 32 runs; Wilson) | 1.000 [no interval: fewer than 2 runs in a resampling stratum] (1 of 32 runs; 0/200 resamples) |
| by run | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |

### Attribution

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Precision | Recall |
| --- | --- | --- | --- |
| by run | volume (family-independent) | 0.000 (0 of 22 agents; 190/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population precision) | 0.000 (0 of 97 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| by run | logistic | 0.226 [0.081, 0.465] (14 of 62 agents; 200/200 resamples) | 0.144 [0.000, 0.307] (14 of 97 agents; 200/200 resamples) |
| by run | boosted | 0.133 [0.027, 0.239] (16 of 120 agents; 200/200 resamples) | 0.165 [0.031, 0.346] (16 of 97 agents; 200/200 resamples) |
| by run | rule | not available at this tier | not available at this tier |
| by run | pairs | 0.119 [0.100, 0.136] (89 of 751 agents; 200/200 resamples) | 0.918 [0.844, 0.979] (89 of 97 agents; 200/200 resamples) |

### Group reconstruction

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Mean Jaccard overlap of proposed group | Reconstructed exactly |
| --- | --- | --- | --- |
| by run | volume (family-independent) | 0.000 (32 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| by run | logistic | 0.055 [0.012, 0.113] (32 of 32 runs; 200/200 resamples) | 0.000 (0 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| by run | boosted | 0.054 [0.013, 0.109] (32 of 32 runs; 200/200 resamples) | 0.000 (0 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| by run | rule | not available at this tier | not available at this tier |
| by run | pairs | 0.584 [0.479, 0.690] (32 of 32 runs; 200/200 resamples) | 0.344 [0.188, 0.531] (11 of 32 runs; 200/200 resamples) |

### Wrongly named agents

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Wrongly named | benign_solo | benign_team, sharing team | benign_team, non-sharing team | benign_team, sharing unresolved | benign_team, no sharing metadata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 22 agents | 0 | 0 | 22 | 0 | 0 |
| by run | logistic | 48 agents | 0 | 0 | 33 | 15 | 0 |
| by run | boosted | 104 agents | 0 | 0 | 84 | 20 | 0 |
| by run | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| by run | pairs | 662 agents | 0 | 25 | 522 | 115 | 0 |

### Features: aggregation

Volume is a family-independent reference; its columns do not change.

### Full-trace detection

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Detector | AUROC | Detection rate at calibrated threshold | FPR on controls |
| --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 0.525 [0.413, 0.648] (118 of 118 runs; 200/200 resamples) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.035 [0.012, 0.098] (3 of 86 runs; Wilson) |
| by run | logistic | 0.442 [0.319, 0.552] (118 of 118 runs; 200/200 resamples) | 0.031 [0.006, 0.157] (1 of 32 runs; Wilson) | 0.035 [0.012, 0.098] (3 of 86 runs; Wilson) |
| by run | boosted | 0.488 [0.363, 0.609] (118 of 118 runs; 200/200 resamples) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.000 [0.000, 0.043] (0 of 86 runs; Wilson) |
| by run | rule | not available at this tier | not available at this tier | not available at this tier |

### Online detection

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Detector | Online FPR on controls | Detection coverage | Detected strictly before completion | Detected at completion | Time to detection (conditional on detection) |
| --- | --- | --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 0.058 [0.025, 0.129] (5 of 86 runs; Wilson) | 0.094 [0.032, 0.242] (3 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 2.422 [1.571, 4.077] (3 of 32 runs; 200/200 resamples) |
| by run | logistic | 0.023 [0.006, 0.081] (2 of 86 runs; Wilson) | 0.031 [0.006, 0.157] (1 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 1.068 [no interval: fewer than 2 runs in a resampling stratum] (1 of 32 runs; 0/200 resamples) |
| by run | boosted | 0.035 [0.012, 0.098] (3 of 86 runs; Wilson) | 0.031 [0.006, 0.157] (1 of 32 runs; Wilson) | 0.031 [0.006, 0.157] (1 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.958 [no interval: fewer than 2 runs in a resampling stratum] (1 of 32 runs; 0/200 resamples) |
| by run | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |

### Attribution

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Precision | Recall |
| --- | --- | --- | --- |
| by run | volume (family-independent) | 0.000 (0 of 22 agents; 190/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population precision) | 0.000 (0 of 97 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| by run | logistic | 0.132 [0.000, 0.500] (5 of 38 agents; 196/200 resamples) | 0.052 [0.000, 0.165] (5 of 97 agents; 200/200 resamples) |
| by run | boosted | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 97 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| by run | rule | not available at this tier | not available at this tier |
| by run | pairs | 0.117 [0.078, 0.151] (61 of 523 agents; 200/200 resamples) | 0.629 [0.444, 0.802] (61 of 97 agents; 200/200 resamples) |

### Group reconstruction

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Mean Jaccard overlap of proposed group | Reconstructed exactly |
| --- | --- | --- | --- |
| by run | volume (family-independent) | 0.000 (32 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| by run | logistic | 0.031 [0.000, 0.094] (32 of 32 runs; 200/200 resamples) | 0.031 [0.000, 0.094] (1 of 32 runs; 200/200 resamples) |
| by run | boosted | 0.000 (32 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| by run | rule | not available at this tier | not available at this tier |
| by run | pairs | 0.625 [0.438, 0.781] (32 of 32 runs; 200/200 resamples) | 0.625 [0.500, 0.781] (20 of 32 runs; 200/200 resamples) |

### Wrongly named agents

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Wrongly named | benign_solo | benign_team, sharing team | benign_team, non-sharing team | benign_team, sharing unresolved | benign_team, no sharing metadata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 22 agents | 0 | 0 | 22 | 0 | 0 |
| by run | logistic | 33 agents | 0 | 0 | 21 | 12 | 0 |
| by run | boosted | 0 agents | 0 | 0 | 0 | 0 | 0 |
| by run | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| by run | pairs | 462 agents | 0 | 11 | 362 | 89 | 0 |

### Features: all

Volume is a family-independent reference; its columns do not change.

### Full-trace detection

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Detector | AUROC | Detection rate at calibrated threshold | FPR on controls |
| --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 0.525 [0.413, 0.648] (118 of 118 runs; 200/200 resamples) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.035 [0.012, 0.098] (3 of 86 runs; Wilson) |
| by run | logistic | 0.435 [0.306, 0.542] (118 of 118 runs; 200/200 resamples) | 0.125 [0.050, 0.281] (4 of 32 runs; Wilson) | 0.047 [0.018, 0.114] (4 of 86 runs; Wilson) |
| by run | boosted | 0.407 [0.284, 0.521] (118 of 118 runs; 200/200 resamples) | 0.094 [0.032, 0.242] (3 of 32 runs; Wilson) | 0.105 [0.056, 0.187] (9 of 86 runs; Wilson) |
| by run | rule | not available at this tier | not available at this tier | not available at this tier |

### Online detection

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Detector | Online FPR on controls | Detection coverage | Detected strictly before completion | Detected at completion | Time to detection (conditional on detection) |
| --- | --- | --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 0.058 [0.025, 0.129] (5 of 86 runs; Wilson) | 0.094 [0.032, 0.242] (3 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 2.422 [1.571, 4.077] (3 of 32 runs; 200/200 resamples) |
| by run | logistic | 0.116 [0.064, 0.201] (10 of 86 runs; Wilson) | 0.094 [0.032, 0.242] (3 of 32 runs; Wilson) | 0.031 [0.006, 0.157] (1 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 1.298 [0.826, 1.766] (3 of 32 runs; 200/200 resamples) |
| by run | boosted | 0.035 [0.012, 0.098] (3 of 86 runs; Wilson) | 0.031 [0.006, 0.157] (1 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 1.348 [no interval: fewer than 2 runs in a resampling stratum] (1 of 32 runs; 0/200 resamples) |
| by run | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |

### Attribution

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Precision | Recall |
| --- | --- | --- | --- |
| by run | volume (family-independent) | 0.000 (0 of 22 agents; 190/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population precision) | 0.000 (0 of 97 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| by run | logistic | 0.192 [0.057, 0.423] (14 of 73 agents; 200/200 resamples) | 0.144 [0.000, 0.307] (14 of 97 agents; 200/200 resamples) |
| by run | boosted | 0.149 [0.000, 0.306] (13 of 87 agents; 200/200 resamples) | 0.134 [0.000, 0.280] (13 of 97 agents; 200/200 resamples) |
| by run | rule | not available at this tier | not available at this tier |
| by run | pairs | 0.119 [0.100, 0.136] (89 of 751 agents; 200/200 resamples) | 0.918 [0.844, 0.979] (89 of 97 agents; 200/200 resamples) |

### Group reconstruction

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Mean Jaccard overlap of proposed group | Reconstructed exactly |
| --- | --- | --- | --- |
| by run | volume (family-independent) | 0.000 (32 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| by run | logistic | 0.055 [0.012, 0.113] (32 of 32 runs; 200/200 resamples) | 0.000 (0 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| by run | boosted | 0.042 [0.013, 0.087] (32 of 32 runs; 200/200 resamples) | 0.000 (0 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| by run | rule | not available at this tier | not available at this tier |
| by run | pairs | 0.584 [0.479, 0.690] (32 of 32 runs; 200/200 resamples) | 0.344 [0.188, 0.531] (11 of 32 runs; 200/200 resamples) |

### Wrongly named agents

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Wrongly named | benign_solo | benign_team, sharing team | benign_team, non-sharing team | benign_team, sharing unresolved | benign_team, no sharing metadata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 22 agents | 0 | 0 | 22 | 0 | 0 |
| by run | logistic | 59 agents | 0 | 0 | 44 | 15 | 0 |
| by run | boosted | 74 agents | 0 | 0 | 63 | 11 | 0 |
| by run | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| by run | pairs | 662 agents | 0 | 25 | 522 | 115 | 0 |

## Held-out

### Calibration

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Fitting runs | Calibration runs | Calibration controls | Test runs | Never fires (calibration set too small) |
| --- | --- | --- | --- | --- | --- |
| held-out channel=message | 184 | 80 | 58 | 132 | none |
| held-out channel=preplanned | 184 | 80 | 58 | 132 | none |
| held-out channel=shared_file | 184 | 80 | 58 | 132 | none |
| held-out topology=hub | 139 | 59 | 43 | 198 | none |
| held-out topology=peer | 139 | 59 | 43 | 198 | none |

### Features: generic

Volume is a family-independent reference; its columns do not change.

### Full-trace detection

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Detector | AUROC | Detection rate at calibrated threshold | FPR on controls |
| --- | --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 0.488 [0.378, 0.596] (132 of 132 runs; 200/200 resamples) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.010 [0.002, 0.057] (1 of 96 runs; Wilson) |
| held-out channel=message | logistic | 0.494 [0.377, 0.609] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) |
| held-out channel=message | boosted | 0.527 [0.426, 0.624] (132 of 132 runs; 200/200 resamples) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) |
| held-out channel=message | rule | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=preplanned | volume (family-independent) | 0.426 [0.315, 0.545] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.031 [0.011, 0.088] (3 of 96 runs; Wilson) |
| held-out channel=preplanned | logistic | 0.568 [0.459, 0.694] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.010 [0.002, 0.057] (1 of 96 runs; Wilson) |
| held-out channel=preplanned | boosted | 0.598 [0.502, 0.697] (132 of 132 runs; 200/200 resamples) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.021 [0.006, 0.073] (2 of 96 runs; Wilson) |
| held-out channel=preplanned | rule | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=shared_file | volume (family-independent) | 0.528 [0.419, 0.651] (132 of 132 runs; 200/200 resamples) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.042 [0.016, 0.102] (4 of 96 runs; Wilson) |
| held-out channel=shared_file | logistic | 0.480 [0.371, 0.584] (132 of 132 runs; 200/200 resamples) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.021 [0.006, 0.073] (2 of 96 runs; Wilson) |
| held-out channel=shared_file | boosted | 0.486 [0.356, 0.589] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.021 [0.006, 0.073] (2 of 96 runs; Wilson) |
| held-out channel=shared_file | rule | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=hub | volume (family-independent) | 0.516 [0.416, 0.598] (198 of 198 runs; 200/200 resamples) | 0.111 [0.052, 0.222] (6 of 54 runs; Wilson) | 0.049 [0.024, 0.097] (7 of 144 runs; Wilson) |
| held-out topology=hub | logistic | 0.496 [0.418, 0.587] (198 of 198 runs; 200/200 resamples) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.014 [0.004, 0.049] (2 of 144 runs; Wilson) |
| held-out topology=hub | boosted | 0.526 [0.444, 0.615] (198 of 198 runs; 200/200 resamples) | 0.167 [0.090, 0.287] (9 of 54 runs; Wilson) | 0.194 [0.138, 0.267] (28 of 144 runs; Wilson) |
| held-out topology=hub | rule | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=peer | volume (family-independent) | 0.518 [0.416, 0.622] (198 of 198 runs; 200/200 resamples) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.014 [0.004, 0.049] (2 of 144 runs; Wilson) |
| held-out topology=peer | logistic | 0.487 [0.405, 0.590] (198 of 198 runs; 200/200 resamples) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.042 [0.019, 0.088] (6 of 144 runs; Wilson) |
| held-out topology=peer | boosted | 0.515 [0.419, 0.620] (198 of 198 runs; 200/200 resamples) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.125 [0.081, 0.189] (18 of 144 runs; Wilson) |
| held-out topology=peer | rule | not available at this tier | not available at this tier | not available at this tier |

### Online detection

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Detector | Online FPR on controls | Detection coverage | Detected strictly before completion | Detected at completion | Time to detection (conditional on detection) |
| --- | --- | --- | --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 0.021 [0.006, 0.073] (2 of 96 runs; Wilson) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 3.086 [1.560, 4.613] (2 of 36 runs; 200/200 resamples) |
| held-out channel=message | logistic | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=message | boosted | 0.010 [0.002, 0.057] (1 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=message | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=preplanned | volume (family-independent) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=preplanned | logistic | 0.042 [0.016, 0.102] (4 of 96 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 1.746 [no interval: fewer than 2 runs in a resampling stratum] (1 of 36 runs; 0/200 resamples) |
| held-out channel=preplanned | boosted | 0.031 [0.011, 0.088] (3 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=preplanned | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=shared_file | volume (family-independent) | 0.062 [0.029, 0.130] (6 of 96 runs; Wilson) | 0.194 [0.098, 0.350] (7 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 4.835 [3.761, 5.933] (7 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | logistic | 0.083 [0.043, 0.156] (8 of 96 runs; Wilson) | 0.111 [0.044, 0.253] (4 of 36 runs; Wilson) | 0.083 [0.029, 0.218] (3 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.777 [0.401, 1.172] (4 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | boosted | 0.104 [0.058, 0.181] (10 of 96 runs; Wilson) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 1.115 [0.714, 1.516] (2 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=hub | volume (family-independent) | 0.062 [0.033, 0.115] (9 of 144 runs; Wilson) | 0.111 [0.052, 0.222] (6 of 54 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.871 [0.685, 1.084] (6 of 54 runs; 200/200 resamples) |
| held-out topology=hub | logistic | 0.035 [0.015, 0.079] (5 of 144 runs; Wilson) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 2.630 [2.088, 3.171] (2 of 54 runs; 200/200 resamples) |
| held-out topology=hub | boosted | 0.042 [0.019, 0.088] (6 of 144 runs; Wilson) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 1.628 [1.348, 1.909] (2 of 54 runs; 200/200 resamples) |
| held-out topology=hub | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=peer | volume (family-independent) | 0.028 [0.011, 0.069] (4 of 144 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 3.784 [2.724, 5.087] (5 of 54 runs; 200/200 resamples) |
| held-out topology=peer | logistic | 0.042 [0.019, 0.088] (6 of 144 runs; Wilson) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.877 [0.867, 0.886] (2 of 54 runs; 200/200 resamples) |
| held-out topology=peer | boosted | 0.090 [0.054, 0.148] (13 of 144 runs; Wilson) | 0.074 [0.029, 0.176] (4 of 54 runs; Wilson) | 0.074 [0.029, 0.176] (4 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.586 [0.501, 0.685] (4 of 54 runs; 200/200 resamples) |
| held-out topology=peer | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |

### Attribution

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Method | Precision | Recall |
| --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=message | logistic | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=message | boosted | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=message | rule | not available at this tier | not available at this tier |
| held-out channel=message | pairs | 0.000 (0 of 189 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population precision) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | volume (family-independent) | 0.000 [no interval: only 130 of 200 resamples defined] (0 of 5 agents; 130/200 resamples) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | logistic | 0.000 [no interval: only 122 of 200 resamples defined] (0 of 8 agents; 122/200 resamples) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | boosted | 0.000 (0 of 12 agents; 190/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population precision) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | rule | not available at this tier | not available at this tier |
| held-out channel=preplanned | pairs | 0.009 [0.000, 0.022] (2 of 228 agents; 200/200 resamples) | 0.017 [0.000, 0.043] (2 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | volume (family-independent) | 0.195 [0.000, 0.401] (8 of 41 agents; 200/200 resamples) | 0.067 [0.000, 0.180] (8 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | logistic | 0.233 [0.000, 0.420] (10 of 43 agents; 196/200 resamples) | 0.083 [0.000, 0.197] (10 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | boosted | 0.000 [no interval: only 171 of 200 resamples defined] (0 of 16 agents; 171/200 resamples) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=shared_file | rule | not available at this tier | not available at this tier |
| held-out channel=shared_file | pairs | 0.138 [0.120, 0.156] (120 of 869 agents; 200/200 resamples) | 1.000 (120 of 120 agents; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population recall of one) |
| held-out topology=hub | volume (family-independent) | 0.246 [0.105, 0.412] (17 of 69 agents; 200/200 resamples) | 0.094 [0.030, 0.168] (17 of 180 agents; 200/200 resamples) |
| held-out topology=hub | logistic | 0.000 [no interval: only 173 of 200 resamples defined] (0 of 15 agents; 173/200 resamples) | 0.000 (0 of 180 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out topology=hub | boosted | 0.120 [0.047, 0.183] (27 of 225 agents; 200/200 resamples) | 0.150 [0.052, 0.234] (27 of 180 agents; 200/200 resamples) |
| held-out topology=hub | rule | not available at this tier | not available at this tier |
| held-out topology=hub | pairs | 0.136 [0.120, 0.153] (170 of 1247 agents; 200/200 resamples) | 0.944 [0.898, 0.989] (170 of 180 agents; 200/200 resamples) |
| held-out topology=peer | volume (family-independent) | 0.304 [0.000, 1.000] (7 of 23 agents; 196/200 resamples) | 0.039 [0.000, 0.105] (7 of 180 agents; 200/200 resamples) |
| held-out topology=peer | logistic | 0.114 [0.000, 0.242] (9 of 79 agents; 200/200 resamples) | 0.050 [0.000, 0.128] (9 of 180 agents; 200/200 resamples) |
| held-out topology=peer | boosted | 0.112 [0.028, 0.234] (20 of 178 agents; 200/200 resamples) | 0.111 [0.029, 0.207] (20 of 180 agents; 200/200 resamples) |
| held-out topology=peer | rule | not available at this tier | not available at this tier |
| held-out topology=peer | pairs | 0.136 [0.122, 0.151] (172 of 1267 agents; 200/200 resamples) | 0.956 [0.920, 0.988] (172 of 180 agents; 200/200 resamples) |

### Group reconstruction

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Method | Mean Jaccard overlap of proposed group | Reconstructed exactly |
| --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=message | logistic | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=message | boosted | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=message | rule | not available at this tier | not available at this tier |
| held-out channel=message | pairs | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | volume (family-independent) | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | logistic | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | boosted | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | rule | not available at this tier | not available at this tier |
| held-out channel=preplanned | pairs | 0.012 [0.000, 0.031] (36 of 36 runs; 200/200 resamples) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=shared_file | volume (family-independent) | 0.024 [0.000, 0.066] (36 of 36 runs; 200/200 resamples) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=shared_file | logistic | 0.024 [0.000, 0.065] (36 of 36 runs; 200/200 resamples) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=shared_file | boosted | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=shared_file | rule | not available at this tier | not available at this tier |
| held-out channel=shared_file | pairs | 0.664 [0.576, 0.771] (36 of 36 runs; 200/200 resamples) | 0.389 [0.250, 0.528] (14 of 36 runs; 200/200 resamples) |
| held-out topology=hub | volume (family-independent) | 0.065 [0.015, 0.130] (54 of 54 runs; 200/200 resamples) | 0.037 [0.000, 0.093] (2 of 54 runs; 200/200 resamples) |
| held-out topology=hub | logistic | 0.000 (54 of 54 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 54 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out topology=hub | boosted | 0.087 [0.025, 0.154] (54 of 54 runs; 200/200 resamples) | 0.056 [0.000, 0.130] (3 of 54 runs; 200/200 resamples) |
| held-out topology=hub | rule | not available at this tier | not available at this tier |
| held-out topology=hub | pairs | 0.575 [0.501, 0.655] (54 of 54 runs; 200/200 resamples) | 0.333 [0.204, 0.463] (18 of 54 runs; 200/200 resamples) |
| held-out topology=peer | volume (family-independent) | 0.031 [0.000, 0.080] (54 of 54 runs; 200/200 resamples) | 0.019 [0.000, 0.056] (1 of 54 runs; 200/200 resamples) |
| held-out topology=peer | logistic | 0.015 [0.000, 0.036] (54 of 54 runs; 200/200 resamples) | 0.000 (0 of 54 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out topology=peer | boosted | 0.082 [0.019, 0.161] (54 of 54 runs; 200/200 resamples) | 0.056 [0.000, 0.112] (3 of 54 runs; 200/200 resamples) |
| held-out topology=peer | rule | not available at this tier | not available at this tier |
| held-out topology=peer | pairs | 0.633 [0.557, 0.705] (54 of 54 runs; 200/200 resamples) | 0.370 [0.241, 0.500] (20 of 54 runs; 200/200 resamples) |

### Wrongly named agents

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Method | Wrongly named | benign_solo | benign_team, sharing team | benign_team, non-sharing team | benign_team, sharing unresolved | benign_team, no sharing metadata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out channel=message | logistic | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out channel=message | boosted | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out channel=message | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=message | pairs | 189 agents | 0 | 2 | 172 | 15 | 0 |
| held-out channel=preplanned | volume (family-independent) | 5 agents | 0 | 0 | 0 | 5 | 0 |
| held-out channel=preplanned | logistic | 8 agents | 0 | 0 | 8 | 0 | 0 |
| held-out channel=preplanned | boosted | 12 agents | 0 | 0 | 5 | 7 | 0 |
| held-out channel=preplanned | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=preplanned | pairs | 226 agents | 0 | 0 | 165 | 61 | 0 |
| held-out channel=shared_file | volume (family-independent) | 33 agents | 0 | 5 | 15 | 13 | 0 |
| held-out channel=shared_file | logistic | 33 agents | 1 | 0 | 13 | 19 | 0 |
| held-out channel=shared_file | boosted | 16 agents | 0 | 0 | 0 | 16 | 0 |
| held-out channel=shared_file | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=shared_file | pairs | 749 agents | 3 | 23 | 533 | 190 | 0 |
| held-out topology=hub | volume (family-independent) | 52 agents | 0 | 2 | 40 | 10 | 0 |
| held-out topology=hub | logistic | 15 agents | 0 | 0 | 15 | 0 | 0 |
| held-out topology=hub | boosted | 198 agents | 0 | 0 | 134 | 64 | 0 |
| held-out topology=hub | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=hub | pairs | 1077 agents | 0 | 18 | 866 | 193 | 0 |
| held-out topology=peer | volume (family-independent) | 16 agents | 0 | 0 | 16 | 0 | 0 |
| held-out topology=peer | logistic | 70 agents | 0 | 0 | 62 | 8 | 0 |
| held-out topology=peer | boosted | 158 agents | 0 | 8 | 116 | 34 | 0 |
| held-out topology=peer | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=peer | pairs | 1095 agents | 0 | 37 | 852 | 206 | 0 |

### Features: aggregation

Volume is a family-independent reference; its columns do not change.

### Full-trace detection

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Detector | AUROC | Detection rate at calibrated threshold | FPR on controls |
| --- | --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 0.488 [0.378, 0.596] (132 of 132 runs; 200/200 resamples) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.010 [0.002, 0.057] (1 of 96 runs; Wilson) |
| held-out channel=message | logistic | 0.441 [0.331, 0.544] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) |
| held-out channel=message | boosted | 0.499 [0.391, 0.618] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) |
| held-out channel=message | rule | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=preplanned | volume (family-independent) | 0.426 [0.315, 0.545] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.031 [0.011, 0.088] (3 of 96 runs; Wilson) |
| held-out channel=preplanned | logistic | 0.507 [0.419, 0.601] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) |
| held-out channel=preplanned | boosted | 0.398 [0.305, 0.498] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) |
| held-out channel=preplanned | rule | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=shared_file | volume (family-independent) | 0.528 [0.419, 0.651] (132 of 132 runs; 200/200 resamples) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.042 [0.016, 0.102] (4 of 96 runs; Wilson) |
| held-out channel=shared_file | logistic | 0.447 [0.354, 0.572] (132 of 132 runs; 200/200 resamples) | 0.083 [0.029, 0.218] (3 of 36 runs; Wilson) | 0.104 [0.058, 0.181] (10 of 96 runs; Wilson) |
| held-out channel=shared_file | boosted | 0.459 [0.353, 0.544] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) |
| held-out channel=shared_file | rule | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=hub | volume (family-independent) | 0.516 [0.416, 0.598] (198 of 198 runs; 200/200 resamples) | 0.111 [0.052, 0.222] (6 of 54 runs; Wilson) | 0.049 [0.024, 0.097] (7 of 144 runs; Wilson) |
| held-out topology=hub | logistic | 0.414 [0.311, 0.520] (198 of 198 runs; 200/200 resamples) | 0.056 [0.019, 0.151] (3 of 54 runs; Wilson) | 0.097 [0.059, 0.157] (14 of 144 runs; Wilson) |
| held-out topology=hub | boosted | 0.434 [0.355, 0.514] (198 of 198 runs; 200/200 resamples) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.026] (0 of 144 runs; Wilson) |
| held-out topology=hub | rule | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=peer | volume (family-independent) | 0.518 [0.416, 0.622] (198 of 198 runs; 200/200 resamples) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.014 [0.004, 0.049] (2 of 144 runs; Wilson) |
| held-out topology=peer | logistic | 0.491 [0.416, 0.581] (198 of 198 runs; 200/200 resamples) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.097 [0.059, 0.157] (14 of 144 runs; Wilson) |
| held-out topology=peer | boosted | 0.459 [0.372, 0.566] (198 of 198 runs; 200/200 resamples) | 0.222 [0.132, 0.349] (12 of 54 runs; Wilson) | 0.222 [0.162, 0.297] (32 of 144 runs; Wilson) |
| held-out topology=peer | rule | not available at this tier | not available at this tier | not available at this tier |

### Online detection

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Detector | Online FPR on controls | Detection coverage | Detected strictly before completion | Detected at completion | Time to detection (conditional on detection) |
| --- | --- | --- | --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 0.021 [0.006, 0.073] (2 of 96 runs; Wilson) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 3.086 [1.560, 4.613] (2 of 36 runs; 200/200 resamples) |
| held-out channel=message | logistic | 0.010 [0.002, 0.057] (1 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=message | boosted | 0.010 [0.002, 0.057] (1 of 96 runs; Wilson) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 1.070 [1.045, 1.095] (2 of 36 runs; 200/200 resamples) |
| held-out channel=message | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=preplanned | volume (family-independent) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=preplanned | logistic | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=preplanned | boosted | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=preplanned | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=shared_file | volume (family-independent) | 0.062 [0.029, 0.130] (6 of 96 runs; Wilson) | 0.194 [0.098, 0.350] (7 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 4.835 [3.761, 5.933] (7 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | logistic | 0.083 [0.043, 0.156] (8 of 96 runs; Wilson) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.850 [0.633, 1.068] (2 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | boosted | 0.042 [0.016, 0.102] (4 of 96 runs; Wilson) | 0.083 [0.029, 0.218] (3 of 36 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 1.190 [0.469, 1.808] (3 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=hub | volume (family-independent) | 0.062 [0.033, 0.115] (9 of 144 runs; Wilson) | 0.111 [0.052, 0.222] (6 of 54 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.871 [0.685, 1.084] (6 of 54 runs; 200/200 resamples) |
| held-out topology=hub | logistic | 0.069 [0.038, 0.123] (10 of 144 runs; Wilson) | 0.056 [0.019, 0.151] (3 of 54 runs; Wilson) | 0.019 [0.003, 0.098] (1 of 54 runs; Wilson) | 0.019 [0.003, 0.098] (1 of 54 runs; Wilson) | 1.018 [0.958, 1.095] (3 of 54 runs; 200/200 resamples) |
| held-out topology=hub | boosted | 0.000 [0.000, 0.026] (0 of 144 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | undefined (0 of 54 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out topology=hub | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=peer | volume (family-independent) | 0.028 [0.011, 0.069] (4 of 144 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 3.784 [2.724, 5.087] (5 of 54 runs; 200/200 resamples) |
| held-out topology=peer | logistic | 0.097 [0.059, 0.157] (14 of 144 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.056 [0.019, 0.151] (3 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.990 [0.708, 1.347] (5 of 54 runs; 200/200 resamples) |
| held-out topology=peer | boosted | 0.035 [0.015, 0.079] (5 of 144 runs; Wilson) | 0.056 [0.019, 0.151] (3 of 54 runs; Wilson) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.808 [0.469, 1.068] (3 of 54 runs; 200/200 resamples) |
| held-out topology=peer | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |

### Attribution

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Method | Precision | Recall |
| --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 0.600 [no interval: only 176 of 200 resamples defined] (3 of 5 agents; 176/200 resamples) | 0.025 [0.000, 0.079] (3 of 120 agents; 200/200 resamples) |
| held-out channel=message | logistic | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=message | boosted | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=message | rule | not available at this tier | not available at this tier |
| held-out channel=message | pairs | 0.163 [0.143, 0.188] (120 of 734 agents; 200/200 resamples) | 1.000 (120 of 120 agents; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population recall of one) |
| held-out channel=preplanned | volume (family-independent) | 0.000 [no interval: only 176 of 200 resamples defined] (0 of 9 agents; 176/200 resamples) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | logistic | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | boosted | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | rule | not available at this tier | not available at this tier |
| held-out channel=preplanned | pairs | 0.000 (0 of 261 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population precision) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=shared_file | volume (family-independent) | 0.258 [0.000, 0.539] (8 of 31 agents; 200/200 resamples) | 0.067 [0.000, 0.180] (8 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | logistic | 0.102 [0.000, 0.207] (13 of 128 agents; 200/200 resamples) | 0.108 [0.000, 0.242] (13 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | boosted | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=shared_file | rule | not available at this tier | not available at this tier |
| held-out channel=shared_file | pairs | 0.169 [0.147, 0.190] (120 of 710 agents; 200/200 resamples) | 1.000 (120 of 120 agents; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population recall of one) |
| held-out topology=hub | volume (family-independent) | 0.196 [0.000, 0.409] (9 of 46 agents; 200/200 resamples) | 0.050 [0.014, 0.106] (9 of 180 agents; 200/200 resamples) |
| held-out topology=hub | logistic | 0.075 [0.000, 0.151] (8 of 106 agents; 200/200 resamples) | 0.044 [0.000, 0.113] (8 of 180 agents; 200/200 resamples) |
| held-out topology=hub | boosted | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 180 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out topology=hub | rule | not available at this tier | not available at this tier |
| held-out topology=hub | pairs | 0.144 [0.115, 0.167] (120 of 836 agents; 200/200 resamples) | 0.667 [0.541, 0.772] (120 of 180 agents; 200/200 resamples) |
| held-out topology=peer | volume (family-independent) | 0.381 [0.000, 1.000] (8 of 21 agents; 196/200 resamples) | 0.044 [0.000, 0.121] (8 of 180 agents; 200/200 resamples) |
| held-out topology=peer | logistic | 0.122 [0.052, 0.222] (23 of 189 agents; 200/200 resamples) | 0.128 [0.029, 0.259] (23 of 180 agents; 200/200 resamples) |
| held-out topology=peer | boosted | 0.149 [0.075, 0.241] (40 of 269 agents; 200/200 resamples) | 0.222 [0.089, 0.359] (40 of 180 agents; 200/200 resamples) |
| held-out topology=peer | rule | not available at this tier | not available at this tier |
| held-out topology=peer | pairs | 0.138 [0.108, 0.173] (120 of 869 agents; 200/200 resamples) | 0.667 [0.547, 0.784] (120 of 180 agents; 200/200 resamples) |

### Group reconstruction

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Method | Mean Jaccard overlap of proposed group | Reconstructed exactly |
| --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 0.028 [0.000, 0.083] (36 of 36 runs; 200/200 resamples) | 0.028 [0.000, 0.083] (1 of 36 runs; 200/200 resamples) |
| held-out channel=message | logistic | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=message | boosted | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=message | rule | not available at this tier | not available at this tier |
| held-out channel=message | pairs | 1.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population mean Jaccard overlap of one) | 1.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population exact-reconstruction rate of one) |
| held-out channel=preplanned | volume (family-independent) | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | logistic | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | boosted | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | rule | not available at this tier | not available at this tier |
| held-out channel=preplanned | pairs | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=shared_file | volume (family-independent) | 0.056 [0.000, 0.140] (36 of 36 runs; 200/200 resamples) | 0.056 [0.000, 0.139] (2 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | logistic | 0.083 [0.000, 0.194] (36 of 36 runs; 200/200 resamples) | 0.083 [0.000, 0.194] (3 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | boosted | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=shared_file | rule | not available at this tier | not available at this tier |
| held-out channel=shared_file | pairs | 1.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population mean Jaccard overlap of one) | 1.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population exact-reconstruction rate of one) |
| held-out topology=hub | volume (family-independent) | 0.056 [0.000, 0.130] (54 of 54 runs; 200/200 resamples) | 0.056 [0.000, 0.111] (3 of 54 runs; 200/200 resamples) |
| held-out topology=hub | logistic | 0.056 [0.000, 0.111] (54 of 54 runs; 200/200 resamples) | 0.056 [0.000, 0.111] (3 of 54 runs; 200/200 resamples) |
| held-out topology=hub | boosted | 0.000 (54 of 54 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 54 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out topology=hub | rule | not available at this tier | not available at this tier |
| held-out topology=hub | pairs | 0.667 [0.537, 0.778] (54 of 54 runs; 200/200 resamples) | 0.667 [0.556, 0.778] (36 of 54 runs; 200/200 resamples) |
| held-out topology=peer | volume (family-independent) | 0.037 [0.000, 0.093] (54 of 54 runs; 200/200 resamples) | 0.037 [0.000, 0.093] (2 of 54 runs; 200/200 resamples) |
| held-out topology=peer | logistic | 0.093 [0.019, 0.148] (54 of 54 runs; 200/200 resamples) | 0.093 [0.019, 0.185] (5 of 54 runs; 200/200 resamples) |
| held-out topology=peer | boosted | 0.148 [0.056, 0.241] (54 of 54 runs; 200/200 resamples) | 0.148 [0.056, 0.241] (8 of 54 runs; 200/200 resamples) |
| held-out topology=peer | rule | not available at this tier | not available at this tier |
| held-out topology=peer | pairs | 0.667 [0.537, 0.778] (54 of 54 runs; 200/200 resamples) | 0.667 [0.556, 0.778] (36 of 54 runs; 200/200 resamples) |

### Wrongly named agents

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Method | Wrongly named | benign_solo | benign_team, sharing team | benign_team, non-sharing team | benign_team, sharing unresolved | benign_team, no sharing metadata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 2 agents | 0 | 0 | 2 | 0 | 0 |
| held-out channel=message | logistic | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out channel=message | boosted | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out channel=message | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=message | pairs | 614 agents | 0 | 17 | 551 | 46 | 0 |
| held-out channel=preplanned | volume (family-independent) | 9 agents | 0 | 0 | 2 | 7 | 0 |
| held-out channel=preplanned | logistic | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out channel=preplanned | boosted | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out channel=preplanned | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=preplanned | pairs | 261 agents | 0 | 0 | 187 | 74 | 0 |
| held-out channel=shared_file | volume (family-independent) | 23 agents | 0 | 0 | 10 | 13 | 0 |
| held-out channel=shared_file | logistic | 115 agents | 0 | 0 | 77 | 38 | 0 |
| held-out channel=shared_file | boosted | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out channel=shared_file | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=shared_file | pairs | 590 agents | 0 | 18 | 415 | 157 | 0 |
| held-out topology=hub | volume (family-independent) | 37 agents | 0 | 2 | 30 | 5 | 0 |
| held-out topology=hub | logistic | 98 agents | 0 | 0 | 80 | 18 | 0 |
| held-out topology=hub | boosted | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out topology=hub | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=hub | pairs | 716 agents | 0 | 16 | 582 | 118 | 0 |
| held-out topology=peer | volume (family-independent) | 13 agents | 0 | 0 | 13 | 0 | 0 |
| held-out topology=peer | logistic | 166 agents | 0 | 0 | 120 | 46 | 0 |
| held-out topology=peer | boosted | 229 agents | 0 | 10 | 170 | 49 | 0 |
| held-out topology=peer | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=peer | pairs | 749 agents | 0 | 19 | 571 | 159 | 0 |

### Features: all

Volume is a family-independent reference; its columns do not change.

### Full-trace detection

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Detector | AUROC | Detection rate at calibrated threshold | FPR on controls |
| --- | --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 0.488 [0.378, 0.596] (132 of 132 runs; 200/200 resamples) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.010 [0.002, 0.057] (1 of 96 runs; Wilson) |
| held-out channel=message | logistic | 0.487 [0.366, 0.604] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) |
| held-out channel=message | boosted | 0.520 [0.413, 0.621] (132 of 132 runs; 200/200 resamples) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.010 [0.002, 0.057] (1 of 96 runs; Wilson) |
| held-out channel=message | rule | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=preplanned | volume (family-independent) | 0.426 [0.315, 0.545] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.031 [0.011, 0.088] (3 of 96 runs; Wilson) |
| held-out channel=preplanned | logistic | 0.582 [0.472, 0.703] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.010 [0.002, 0.057] (1 of 96 runs; Wilson) |
| held-out channel=preplanned | boosted | 0.581 [0.475, 0.686] (132 of 132 runs; 200/200 resamples) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.052 [0.022, 0.116] (5 of 96 runs; Wilson) |
| held-out channel=preplanned | rule | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=shared_file | volume (family-independent) | 0.528 [0.419, 0.651] (132 of 132 runs; 200/200 resamples) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.042 [0.016, 0.102] (4 of 96 runs; Wilson) |
| held-out channel=shared_file | logistic | 0.479 [0.373, 0.583] (132 of 132 runs; 200/200 resamples) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.021 [0.006, 0.073] (2 of 96 runs; Wilson) |
| held-out channel=shared_file | boosted | 0.491 [0.368, 0.595] (132 of 132 runs; 200/200 resamples) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.031 [0.011, 0.088] (3 of 96 runs; Wilson) |
| held-out channel=shared_file | rule | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=hub | volume (family-independent) | 0.516 [0.416, 0.598] (198 of 198 runs; 200/200 resamples) | 0.111 [0.052, 0.222] (6 of 54 runs; Wilson) | 0.049 [0.024, 0.097] (7 of 144 runs; Wilson) |
| held-out topology=hub | logistic | 0.496 [0.415, 0.589] (198 of 198 runs; 200/200 resamples) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.014 [0.004, 0.049] (2 of 144 runs; Wilson) |
| held-out topology=hub | boosted | 0.527 [0.444, 0.601] (198 of 198 runs; 200/200 resamples) | 0.130 [0.064, 0.244] (7 of 54 runs; Wilson) | 0.146 [0.097, 0.213] (21 of 144 runs; Wilson) |
| held-out topology=hub | rule | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=peer | volume (family-independent) | 0.518 [0.416, 0.622] (198 of 198 runs; 200/200 resamples) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.014 [0.004, 0.049] (2 of 144 runs; Wilson) |
| held-out topology=peer | logistic | 0.497 [0.405, 0.596] (198 of 198 runs; 200/200 resamples) | 0.074 [0.029, 0.176] (4 of 54 runs; Wilson) | 0.090 [0.054, 0.148] (13 of 144 runs; Wilson) |
| held-out topology=peer | boosted | 0.511 [0.412, 0.604] (198 of 198 runs; 200/200 resamples) | 0.111 [0.052, 0.222] (6 of 54 runs; Wilson) | 0.118 [0.075, 0.181] (17 of 144 runs; Wilson) |
| held-out topology=peer | rule | not available at this tier | not available at this tier | not available at this tier |

### Online detection

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Detector | Online FPR on controls | Detection coverage | Detected strictly before completion | Detected at completion | Time to detection (conditional on detection) |
| --- | --- | --- | --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 0.021 [0.006, 0.073] (2 of 96 runs; Wilson) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 3.086 [1.560, 4.613] (2 of 36 runs; 200/200 resamples) |
| held-out channel=message | logistic | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=message | boosted | 0.021 [0.006, 0.073] (2 of 96 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 1.756 [no interval: fewer than 2 runs in a resampling stratum] (1 of 36 runs; 0/200 resamples) |
| held-out channel=message | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=preplanned | volume (family-independent) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=preplanned | logistic | 0.021 [0.006, 0.073] (2 of 96 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.455 [no interval: fewer than 2 runs in a resampling stratum] (1 of 36 runs; 0/200 resamples) |
| held-out channel=preplanned | boosted | 0.021 [0.006, 0.073] (2 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=preplanned | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=shared_file | volume (family-independent) | 0.062 [0.029, 0.130] (6 of 96 runs; Wilson) | 0.194 [0.098, 0.350] (7 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 4.835 [3.761, 5.933] (7 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | logistic | 0.104 [0.058, 0.181] (10 of 96 runs; Wilson) | 0.139 [0.061, 0.287] (5 of 36 runs; Wilson) | 0.111 [0.044, 0.253] (4 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.795 [0.437, 1.076] (5 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | boosted | 0.042 [0.016, 0.102] (4 of 96 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 3.065 [no interval: fewer than 2 runs in a resampling stratum] (1 of 36 runs; 0/200 resamples) |
| held-out channel=shared_file | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=hub | volume (family-independent) | 0.062 [0.033, 0.115] (9 of 144 runs; Wilson) | 0.111 [0.052, 0.222] (6 of 54 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.871 [0.685, 1.084] (6 of 54 runs; 200/200 resamples) |
| held-out topology=hub | logistic | 0.042 [0.019, 0.088] (6 of 144 runs; Wilson) | 0.019 [0.003, 0.098] (1 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 2.088 [no interval: fewer than 2 runs in a resampling stratum] (1 of 54 runs; 0/200 resamples) |
| held-out topology=hub | boosted | 0.076 [0.043, 0.132] (11 of 144 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 1.854 [1.342, 2.358] (5 of 54 runs; 200/200 resamples) |
| held-out topology=hub | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=peer | volume (family-independent) | 0.028 [0.011, 0.069] (4 of 144 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 3.784 [2.724, 5.087] (5 of 54 runs; 200/200 resamples) |
| held-out topology=peer | logistic | 0.132 [0.086, 0.197] (19 of 144 runs; Wilson) | 0.130 [0.064, 0.244] (7 of 54 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.722 [0.442, 1.003] (7 of 54 runs; 200/200 resamples) |
| held-out topology=peer | boosted | 0.146 [0.097, 0.213] (21 of 144 runs; Wilson) | 0.167 [0.090, 0.287] (9 of 54 runs; Wilson) | 0.148 [0.077, 0.266] (8 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.761 [0.602, 0.950] (9 of 54 runs; 200/200 resamples) |
| held-out topology=peer | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |

### Attribution

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Method | Precision | Recall |
| --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=message | logistic | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=message | boosted | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=message | rule | not available at this tier | not available at this tier |
| held-out channel=message | pairs | 0.000 (0 of 189 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population precision) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | volume (family-independent) | 0.000 [no interval: only 130 of 200 resamples defined] (0 of 5 agents; 130/200 resamples) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | logistic | 0.000 [no interval: only 122 of 200 resamples defined] (0 of 8 agents; 122/200 resamples) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | boosted | 0.000 (0 of 15 agents; 198/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population precision) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | rule | not available at this tier | not available at this tier |
| held-out channel=preplanned | pairs | 0.009 [0.000, 0.022] (2 of 228 agents; 200/200 resamples) | 0.017 [0.000, 0.043] (2 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | volume (family-independent) | 0.195 [0.000, 0.401] (8 of 41 agents; 200/200 resamples) | 0.067 [0.000, 0.180] (8 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | logistic | 0.233 [0.000, 0.420] (10 of 43 agents; 196/200 resamples) | 0.083 [0.000, 0.197] (10 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | boosted | 0.077 [0.000, 0.374] (2 of 26 agents; 198/200 resamples) | 0.017 [0.000, 0.057] (2 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | rule | not available at this tier | not available at this tier |
| held-out channel=shared_file | pairs | 0.138 [0.120, 0.156] (120 of 869 agents; 200/200 resamples) | 1.000 (120 of 120 agents; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population recall of one) |
| held-out topology=hub | volume (family-independent) | 0.246 [0.105, 0.412] (17 of 69 agents; 200/200 resamples) | 0.094 [0.030, 0.168] (17 of 180 agents; 200/200 resamples) |
| held-out topology=hub | logistic | 0.000 [no interval: only 173 of 200 resamples defined] (0 of 15 agents; 173/200 resamples) | 0.000 (0 of 180 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out topology=hub | boosted | 0.129 [0.049, 0.209] (22 of 171 agents; 200/200 resamples) | 0.122 [0.043, 0.202] (22 of 180 agents; 200/200 resamples) |
| held-out topology=hub | rule | not available at this tier | not available at this tier |
| held-out topology=hub | pairs | 0.136 [0.120, 0.153] (170 of 1247 agents; 200/200 resamples) | 0.944 [0.898, 0.989] (170 of 180 agents; 200/200 resamples) |
| held-out topology=peer | volume (family-independent) | 0.304 [0.000, 1.000] (7 of 23 agents; 196/200 resamples) | 0.039 [0.000, 0.105] (7 of 180 agents; 200/200 resamples) |
| held-out topology=peer | logistic | 0.099 [0.029, 0.172] (17 of 171 agents; 200/200 resamples) | 0.094 [0.023, 0.191] (17 of 180 agents; 200/200 resamples) |
| held-out topology=peer | boosted | 0.146 [0.041, 0.269] (25 of 171 agents; 200/200 resamples) | 0.139 [0.043, 0.257] (25 of 180 agents; 200/200 resamples) |
| held-out topology=peer | rule | not available at this tier | not available at this tier |
| held-out topology=peer | pairs | 0.136 [0.122, 0.151] (172 of 1267 agents; 200/200 resamples) | 0.956 [0.920, 0.988] (172 of 180 agents; 200/200 resamples) |

### Group reconstruction

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Method | Mean Jaccard overlap of proposed group | Reconstructed exactly |
| --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=message | logistic | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=message | boosted | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=message | rule | not available at this tier | not available at this tier |
| held-out channel=message | pairs | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | volume (family-independent) | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | logistic | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | boosted | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | rule | not available at this tier | not available at this tier |
| held-out channel=preplanned | pairs | 0.012 [0.000, 0.031] (36 of 36 runs; 200/200 resamples) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=shared_file | volume (family-independent) | 0.024 [0.000, 0.066] (36 of 36 runs; 200/200 resamples) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=shared_file | logistic | 0.024 [0.000, 0.065] (36 of 36 runs; 200/200 resamples) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=shared_file | boosted | 0.014 [0.000, 0.042] (36 of 36 runs; 200/200 resamples) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=shared_file | rule | not available at this tier | not available at this tier |
| held-out channel=shared_file | pairs | 0.664 [0.576, 0.771] (36 of 36 runs; 200/200 resamples) | 0.389 [0.250, 0.528] (14 of 36 runs; 200/200 resamples) |
| held-out topology=hub | volume (family-independent) | 0.065 [0.015, 0.130] (54 of 54 runs; 200/200 resamples) | 0.037 [0.000, 0.093] (2 of 54 runs; 200/200 resamples) |
| held-out topology=hub | logistic | 0.000 (54 of 54 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 54 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out topology=hub | boosted | 0.078 [0.018, 0.137] (54 of 54 runs; 200/200 resamples) | 0.056 [0.000, 0.130] (3 of 54 runs; 200/200 resamples) |
| held-out topology=hub | rule | not available at this tier | not available at this tier |
| held-out topology=hub | pairs | 0.575 [0.501, 0.655] (54 of 54 runs; 200/200 resamples) | 0.333 [0.204, 0.463] (18 of 54 runs; 200/200 resamples) |
| held-out topology=peer | volume (family-independent) | 0.031 [0.000, 0.080] (54 of 54 runs; 200/200 resamples) | 0.019 [0.000, 0.056] (1 of 54 runs; 200/200 resamples) |
| held-out topology=peer | logistic | 0.029 [0.000, 0.055] (54 of 54 runs; 200/200 resamples) | 0.000 (0 of 54 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out topology=peer | boosted | 0.100 [0.030, 0.182] (54 of 54 runs; 200/200 resamples) | 0.074 [0.019, 0.148] (4 of 54 runs; 200/200 resamples) |
| held-out topology=peer | rule | not available at this tier | not available at this tier |
| held-out topology=peer | pairs | 0.633 [0.557, 0.705] (54 of 54 runs; 200/200 resamples) | 0.370 [0.241, 0.500] (20 of 54 runs; 200/200 resamples) |

### Wrongly named agents

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Method | Wrongly named | benign_solo | benign_team, sharing team | benign_team, non-sharing team | benign_team, sharing unresolved | benign_team, no sharing metadata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out channel=message | logistic | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out channel=message | boosted | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out channel=message | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=message | pairs | 189 agents | 0 | 2 | 172 | 15 | 0 |
| held-out channel=preplanned | volume (family-independent) | 5 agents | 0 | 0 | 0 | 5 | 0 |
| held-out channel=preplanned | logistic | 8 agents | 0 | 0 | 8 | 0 | 0 |
| held-out channel=preplanned | boosted | 15 agents | 0 | 0 | 8 | 7 | 0 |
| held-out channel=preplanned | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=preplanned | pairs | 226 agents | 0 | 0 | 165 | 61 | 0 |
| held-out channel=shared_file | volume (family-independent) | 33 agents | 0 | 5 | 15 | 13 | 0 |
| held-out channel=shared_file | logistic | 33 agents | 1 | 0 | 13 | 19 | 0 |
| held-out channel=shared_file | boosted | 24 agents | 0 | 0 | 2 | 22 | 0 |
| held-out channel=shared_file | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=shared_file | pairs | 749 agents | 3 | 23 | 533 | 190 | 0 |
| held-out topology=hub | volume (family-independent) | 52 agents | 0 | 2 | 40 | 10 | 0 |
| held-out topology=hub | logistic | 15 agents | 0 | 0 | 15 | 0 | 0 |
| held-out topology=hub | boosted | 149 agents | 0 | 0 | 108 | 41 | 0 |
| held-out topology=hub | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=hub | pairs | 1077 agents | 0 | 18 | 866 | 193 | 0 |
| held-out topology=peer | volume (family-independent) | 16 agents | 0 | 0 | 16 | 0 | 0 |
| held-out topology=peer | logistic | 154 agents | 0 | 0 | 117 | 37 | 0 |
| held-out topology=peer | boosted | 146 agents | 0 | 8 | 104 | 34 | 0 |
| held-out topology=peer | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=peer | pairs | 1095 agents | 0 | 37 | 852 | 206 | 0 |
