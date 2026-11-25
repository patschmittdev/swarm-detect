# Results, tier V1

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
| by run | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features |

### Online detection

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Detector | Online FPR on controls | Detection coverage | Detected strictly before completion | Detected at completion | Time to detection (conditional on detection) |
| --- | --- | --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 0.058 [0.025, 0.129] (5 of 86 runs; Wilson) | 0.094 [0.032, 0.242] (3 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 2.422 [1.571, 4.077] (3 of 32 runs; 200/200 resamples) |
| by run | logistic | 0.128 [0.073, 0.215] (11 of 86 runs; Wilson) | 0.062 [0.017, 0.201] (2 of 32 runs; Wilson) | 0.062 [0.017, 0.201] (2 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.764 [0.622, 0.907] (2 of 32 runs; 200/200 resamples) |
| by run | boosted | 0.058 [0.025, 0.129] (5 of 86 runs; Wilson) | 0.031 [0.006, 0.157] (1 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.031 [0.006, 0.157] (1 of 32 runs; Wilson) | 1.000 [no interval: fewer than 2 runs in a resampling stratum] (1 of 32 runs; 0/200 resamples) |
| by run | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |

### Attribution

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Precision | Recall |
| --- | --- | --- | --- |
| by run | volume (family-independent) | 0.000 (0 of 22 agents; 190/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population precision) | 0.000 (0 of 97 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| by run | logistic | 0.226 [0.081, 0.465] (14 of 62 agents; 200/200 resamples) | 0.144 [0.000, 0.307] (14 of 97 agents; 200/200 resamples) |
| by run | boosted | 0.133 [0.027, 0.239] (16 of 120 agents; 200/200 resamples) | 0.165 [0.031, 0.346] (16 of 97 agents; 200/200 resamples) |
| by run | rule | not available without aggregation features | not available without aggregation features |
| by run | pairs | 0.119 [0.100, 0.136] (89 of 751 agents; 200/200 resamples) | 0.918 [0.844, 0.979] (89 of 97 agents; 200/200 resamples) |

### Group reconstruction

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Mean Jaccard overlap of proposed group | Reconstructed exactly |
| --- | --- | --- | --- |
| by run | volume (family-independent) | 0.000 (32 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| by run | logistic | 0.055 [0.012, 0.113] (32 of 32 runs; 200/200 resamples) | 0.000 (0 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| by run | boosted | 0.054 [0.013, 0.109] (32 of 32 runs; 200/200 resamples) | 0.000 (0 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| by run | rule | not available without aggregation features | not available without aggregation features |
| by run | pairs | 0.584 [0.479, 0.690] (32 of 32 runs; 200/200 resamples) | 0.344 [0.188, 0.531] (11 of 32 runs; 200/200 resamples) |

### Wrongly named agents

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Wrongly named | benign_solo | benign_team, sharing team | benign_team, non-sharing team | benign_team, sharing unresolved | benign_team, no sharing metadata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 22 agents | 0 | 0 | 22 | 0 | 0 |
| by run | logistic | 48 agents | 0 | 10 | 38 | 0 | 0 |
| by run | boosted | 104 agents | 0 | 12 | 92 | 0 | 0 |
| by run | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| by run | pairs | 662 agents | 0 | 78 | 584 | 0 | 0 |

### Features: aggregation

Volume is a family-independent reference; its columns do not change.

### Full-trace detection

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Detector | AUROC | Detection rate at calibrated threshold | FPR on controls |
| --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 0.525 [0.413, 0.648] (118 of 118 runs; 200/200 resamples) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.035 [0.012, 0.098] (3 of 86 runs; Wilson) |
| by run | logistic | 0.920 [0.873, 0.961] (118 of 118 runs; 200/200 resamples) | 0.438 [0.282, 0.607] (14 of 32 runs; Wilson) | 0.058 [0.025, 0.129] (5 of 86 runs; Wilson) |
| by run | boosted | 0.926 [0.877, 0.967] (118 of 118 runs; 200/200 resamples) | 0.406 [0.255, 0.577] (13 of 32 runs; Wilson) | 0.058 [0.025, 0.129] (5 of 86 runs; Wilson) |
| by run | rule | 0.909 [0.851, 0.959] (118 of 118 runs; 200/200 resamples) | 0.219 [0.110, 0.388] (7 of 32 runs; Wilson) | 0.047 [0.018, 0.114] (4 of 86 runs; Wilson) |

### Online detection

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Detector | Online FPR on controls | Detection coverage | Detected strictly before completion | Detected at completion | Time to detection (conditional on detection) |
| --- | --- | --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 0.058 [0.025, 0.129] (5 of 86 runs; Wilson) | 0.094 [0.032, 0.242] (3 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 2.422 [1.571, 4.077] (3 of 32 runs; 200/200 resamples) |
| by run | logistic | 0.058 [0.025, 0.129] (5 of 86 runs; Wilson) | 0.406 [0.255, 0.577] (13 of 32 runs; Wilson) | 0.219 [0.110, 0.388] (7 of 32 runs; Wilson) | 0.062 [0.017, 0.201] (2 of 32 runs; Wilson) | 1.017 [0.931, 1.120] (13 of 32 runs; 200/200 resamples) |
| by run | boosted | 0.070 [0.032, 0.144] (6 of 86 runs; Wilson) | 0.375 [0.229, 0.547] (12 of 32 runs; Wilson) | 0.344 [0.204, 0.517] (11 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.824 [0.695, 0.971] (12 of 32 runs; 200/200 resamples) |
| by run | rule | 0.047 [0.018, 0.114] (4 of 86 runs; Wilson) | 0.219 [0.110, 0.388] (7 of 32 runs; Wilson) | 0.094 [0.032, 0.242] (3 of 32 runs; Wilson) | 0.031 [0.006, 0.157] (1 of 32 runs; Wilson) | 1.086 [0.921, 1.333] (7 of 32 runs; 200/200 resamples) |

### Attribution

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Precision | Recall |
| --- | --- | --- | --- |
| by run | volume (family-independent) | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 97 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| by run | logistic | 0.505 [0.356, 0.691] (52 of 103 agents; 200/200 resamples) | 0.536 [0.297, 0.716] (52 of 97 agents; 200/200 resamples) |
| by run | boosted | 0.505 [0.363, 0.641] (50 of 99 agents; 200/200 resamples) | 0.515 [0.312, 0.667] (50 of 97 agents; 200/200 resamples) |
| by run | rule | 0.382 [0.214, 0.591] (26 of 68 agents; 200/200 resamples) | 0.268 [0.091, 0.473] (26 of 97 agents; 200/200 resamples) |
| by run | pairs | 0.551 [0.464, 0.669] (97 of 176 agents; 200/200 resamples) | 1.000 (97 of 97 agents; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population recall of one) |

### Group reconstruction

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Mean Jaccard overlap of proposed group | Reconstructed exactly |
| --- | --- | --- | --- |
| by run | volume (family-independent) | 0.000 (32 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| by run | logistic | 0.438 [0.281, 0.594] (32 of 32 runs; 200/200 resamples) | 0.438 [0.281, 0.594] (14 of 32 runs; 200/200 resamples) |
| by run | boosted | 0.406 [0.281, 0.594] (32 of 32 runs; 200/200 resamples) | 0.406 [0.219, 0.563] (13 of 32 runs; 200/200 resamples) |
| by run | rule | 0.219 [0.062, 0.375] (32 of 32 runs; 200/200 resamples) | 0.219 [0.094, 0.344] (7 of 32 runs; 200/200 resamples) |
| by run | pairs | 1.000 (32 of 32 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population mean Jaccard overlap of one) | 1.000 (32 of 32 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population exact-reconstruction rate of one) |

### Wrongly named agents

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Wrongly named | benign_solo | benign_team, sharing team | benign_team, non-sharing team | benign_team, sharing unresolved | benign_team, no sharing metadata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 0 agents | 0 | 0 | 0 | 0 | 0 |
| by run | logistic | 51 agents | 0 | 51 | 0 | 0 | 0 |
| by run | boosted | 49 agents | 0 | 49 | 0 | 0 | 0 |
| by run | rule | 42 agents | 0 | 42 | 0 | 0 | 0 |
| by run | pairs | 79 agents | 0 | 79 | 0 | 0 | 0 |

### Features: all

Volume is a family-independent reference; its columns do not change.

### Full-trace detection

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Detector | AUROC | Detection rate at calibrated threshold | FPR on controls |
| --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 0.525 [0.413, 0.648] (118 of 118 runs; 200/200 resamples) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.035 [0.012, 0.098] (3 of 86 runs; Wilson) |
| by run | logistic | 0.911 [0.861, 0.954] (118 of 118 runs; 200/200 resamples) | 0.469 [0.309, 0.636] (15 of 32 runs; Wilson) | 0.093 [0.048, 0.173] (8 of 86 runs; Wilson) |
| by run | boosted | 0.900 [0.842, 0.948] (118 of 118 runs; 200/200 resamples) | 0.438 [0.282, 0.607] (14 of 32 runs; Wilson) | 0.105 [0.056, 0.187] (9 of 86 runs; Wilson) |
| by run | rule | 0.909 [0.851, 0.959] (118 of 118 runs; 200/200 resamples) | 0.219 [0.110, 0.388] (7 of 32 runs; Wilson) | 0.047 [0.018, 0.114] (4 of 86 runs; Wilson) |

### Online detection

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Detector | Online FPR on controls | Detection coverage | Detected strictly before completion | Detected at completion | Time to detection (conditional on detection) |
| --- | --- | --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 0.058 [0.025, 0.129] (5 of 86 runs; Wilson) | 0.094 [0.032, 0.242] (3 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 2.422 [1.571, 4.077] (3 of 32 runs; 200/200 resamples) |
| by run | logistic | 0.047 [0.018, 0.114] (4 of 86 runs; Wilson) | 0.312 [0.180, 0.486] (10 of 32 runs; Wilson) | 0.250 [0.133, 0.421] (8 of 32 runs; Wilson) | 0.000 [0.000, 0.107] (0 of 32 runs; Wilson) | 0.926 [0.778, 1.155] (10 of 32 runs; 200/200 resamples) |
| by run | boosted | 0.047 [0.018, 0.114] (4 of 86 runs; Wilson) | 0.312 [0.180, 0.486] (10 of 32 runs; Wilson) | 0.125 [0.050, 0.281] (4 of 32 runs; Wilson) | 0.062 [0.017, 0.201] (2 of 32 runs; Wilson) | 1.580 [1.042, 2.383] (10 of 32 runs; 200/200 resamples) |
| by run | rule | 0.047 [0.018, 0.114] (4 of 86 runs; Wilson) | 0.219 [0.110, 0.388] (7 of 32 runs; Wilson) | 0.094 [0.032, 0.242] (3 of 32 runs; Wilson) | 0.031 [0.006, 0.157] (1 of 32 runs; Wilson) | 1.086 [0.921, 1.333] (7 of 32 runs; 200/200 resamples) |

### Attribution

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Precision | Recall |
| --- | --- | --- | --- |
| by run | volume (family-independent) | 0.000 [no interval: only 116 of 200 resamples defined] (0 of 4 agents; 116/200 resamples) | 0.000 (0 of 97 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| by run | logistic | 0.434 [0.299, 0.585] (56 of 129 agents; 200/200 resamples) | 0.577 [0.388, 0.717] (56 of 97 agents; 200/200 resamples) |
| by run | boosted | 0.491 [0.330, 0.664] (52 of 106 agents; 200/200 resamples) | 0.536 [0.322, 0.713] (52 of 97 agents; 200/200 resamples) |
| by run | rule | 0.366 [0.204, 0.565] (26 of 71 agents; 200/200 resamples) | 0.268 [0.091, 0.473] (26 of 97 agents; 200/200 resamples) |
| by run | pairs | 0.364 [0.302, 0.449] (94 of 258 agents; 200/200 resamples) | 0.969 [0.918, 1.000] (94 of 97 agents; 200/200 resamples) |

### Group reconstruction

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Mean Jaccard overlap of proposed group | Reconstructed exactly |
| --- | --- | --- | --- |
| by run | volume (family-independent) | 0.000 (32 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 32 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| by run | logistic | 0.420 [0.271, 0.578] (32 of 32 runs; 200/200 resamples) | 0.344 [0.188, 0.500] (11 of 32 runs; 200/200 resamples) |
| by run | boosted | 0.403 [0.237, 0.562] (32 of 32 runs; 200/200 resamples) | 0.312 [0.156, 0.438] (10 of 32 runs; 200/200 resamples) |
| by run | rule | 0.188 [0.062, 0.304] (32 of 32 runs; 200/200 resamples) | 0.156 [0.031, 0.281] (5 of 32 runs; 200/200 resamples) |
| by run | pairs | 0.912 [0.825, 0.977] (32 of 32 runs; 200/200 resamples) | 0.812 [0.656, 0.938] (26 of 32 runs; 200/200 resamples) |

### Wrongly named agents

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Method | Wrongly named | benign_solo | benign_team, sharing team | benign_team, non-sharing team | benign_team, sharing unresolved | benign_team, no sharing metadata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| by run | volume (family-independent) | 4 agents | 0 | 0 | 4 | 0 | 0 |
| by run | logistic | 73 agents | 0 | 62 | 11 | 0 | 0 |
| by run | boosted | 54 agents | 0 | 41 | 13 | 0 | 0 |
| by run | rule | 45 agents | 0 | 42 | 3 | 0 | 0 |
| by run | pairs | 164 agents | 0 | 79 | 85 | 0 | 0 |

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
| held-out channel=message | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out channel=preplanned | volume (family-independent) | 0.426 [0.315, 0.545] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.031 [0.011, 0.088] (3 of 96 runs; Wilson) |
| held-out channel=preplanned | logistic | 0.568 [0.459, 0.694] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.010 [0.002, 0.057] (1 of 96 runs; Wilson) |
| held-out channel=preplanned | boosted | 0.598 [0.502, 0.697] (132 of 132 runs; 200/200 resamples) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.021 [0.006, 0.073] (2 of 96 runs; Wilson) |
| held-out channel=preplanned | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out channel=shared_file | volume (family-independent) | 0.528 [0.419, 0.651] (132 of 132 runs; 200/200 resamples) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.042 [0.016, 0.102] (4 of 96 runs; Wilson) |
| held-out channel=shared_file | logistic | 0.480 [0.371, 0.584] (132 of 132 runs; 200/200 resamples) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.021 [0.006, 0.073] (2 of 96 runs; Wilson) |
| held-out channel=shared_file | boosted | 0.486 [0.356, 0.589] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.021 [0.006, 0.073] (2 of 96 runs; Wilson) |
| held-out channel=shared_file | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out topology=hub | volume (family-independent) | 0.516 [0.416, 0.598] (198 of 198 runs; 200/200 resamples) | 0.111 [0.052, 0.222] (6 of 54 runs; Wilson) | 0.049 [0.024, 0.097] (7 of 144 runs; Wilson) |
| held-out topology=hub | logistic | 0.496 [0.418, 0.587] (198 of 198 runs; 200/200 resamples) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.014 [0.004, 0.049] (2 of 144 runs; Wilson) |
| held-out topology=hub | boosted | 0.526 [0.444, 0.615] (198 of 198 runs; 200/200 resamples) | 0.167 [0.090, 0.287] (9 of 54 runs; Wilson) | 0.194 [0.138, 0.267] (28 of 144 runs; Wilson) |
| held-out topology=hub | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out topology=peer | volume (family-independent) | 0.518 [0.416, 0.622] (198 of 198 runs; 200/200 resamples) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.014 [0.004, 0.049] (2 of 144 runs; Wilson) |
| held-out topology=peer | logistic | 0.487 [0.405, 0.590] (198 of 198 runs; 200/200 resamples) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.042 [0.019, 0.088] (6 of 144 runs; Wilson) |
| held-out topology=peer | boosted | 0.515 [0.419, 0.620] (198 of 198 runs; 200/200 resamples) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.125 [0.081, 0.189] (18 of 144 runs; Wilson) |
| held-out topology=peer | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features |

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
| held-out channel=message | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out channel=preplanned | volume (family-independent) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=preplanned | logistic | 0.042 [0.016, 0.102] (4 of 96 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 1.746 [no interval: fewer than 2 runs in a resampling stratum] (1 of 36 runs; 0/200 resamples) |
| held-out channel=preplanned | boosted | 0.031 [0.011, 0.088] (3 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=preplanned | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out channel=shared_file | volume (family-independent) | 0.062 [0.029, 0.130] (6 of 96 runs; Wilson) | 0.194 [0.098, 0.350] (7 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 4.835 [3.761, 5.933] (7 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | logistic | 0.083 [0.043, 0.156] (8 of 96 runs; Wilson) | 0.111 [0.044, 0.253] (4 of 36 runs; Wilson) | 0.083 [0.029, 0.218] (3 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.777 [0.401, 1.172] (4 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | boosted | 0.104 [0.058, 0.181] (10 of 96 runs; Wilson) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 1.115 [0.714, 1.516] (2 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out topology=hub | volume (family-independent) | 0.062 [0.033, 0.115] (9 of 144 runs; Wilson) | 0.111 [0.052, 0.222] (6 of 54 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.871 [0.685, 1.084] (6 of 54 runs; 200/200 resamples) |
| held-out topology=hub | logistic | 0.035 [0.015, 0.079] (5 of 144 runs; Wilson) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 2.630 [2.088, 3.171] (2 of 54 runs; 200/200 resamples) |
| held-out topology=hub | boosted | 0.042 [0.019, 0.088] (6 of 144 runs; Wilson) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 1.628 [1.348, 1.909] (2 of 54 runs; 200/200 resamples) |
| held-out topology=hub | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out topology=peer | volume (family-independent) | 0.028 [0.011, 0.069] (4 of 144 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 3.784 [2.724, 5.087] (5 of 54 runs; 200/200 resamples) |
| held-out topology=peer | logistic | 0.042 [0.019, 0.088] (6 of 144 runs; Wilson) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.877 [0.867, 0.886] (2 of 54 runs; 200/200 resamples) |
| held-out topology=peer | boosted | 0.090 [0.054, 0.148] (13 of 144 runs; Wilson) | 0.074 [0.029, 0.176] (4 of 54 runs; Wilson) | 0.074 [0.029, 0.176] (4 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.586 [0.501, 0.685] (4 of 54 runs; 200/200 resamples) |
| held-out topology=peer | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |

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
| held-out channel=message | rule | not available without aggregation features | not available without aggregation features |
| held-out channel=message | pairs | 0.000 (0 of 189 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population precision) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | volume (family-independent) | 0.000 [no interval: only 130 of 200 resamples defined] (0 of 5 agents; 130/200 resamples) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | logistic | 0.000 [no interval: only 122 of 200 resamples defined] (0 of 8 agents; 122/200 resamples) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | boosted | 0.000 (0 of 12 agents; 190/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population precision) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | rule | not available without aggregation features | not available without aggregation features |
| held-out channel=preplanned | pairs | 0.009 [0.000, 0.022] (2 of 228 agents; 200/200 resamples) | 0.017 [0.000, 0.043] (2 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | volume (family-independent) | 0.195 [0.000, 0.401] (8 of 41 agents; 200/200 resamples) | 0.067 [0.000, 0.180] (8 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | logistic | 0.233 [0.000, 0.420] (10 of 43 agents; 196/200 resamples) | 0.083 [0.000, 0.197] (10 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | boosted | 0.000 [no interval: only 171 of 200 resamples defined] (0 of 16 agents; 171/200 resamples) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=shared_file | rule | not available without aggregation features | not available without aggregation features |
| held-out channel=shared_file | pairs | 0.138 [0.120, 0.156] (120 of 869 agents; 200/200 resamples) | 1.000 (120 of 120 agents; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population recall of one) |
| held-out topology=hub | volume (family-independent) | 0.246 [0.105, 0.412] (17 of 69 agents; 200/200 resamples) | 0.094 [0.030, 0.168] (17 of 180 agents; 200/200 resamples) |
| held-out topology=hub | logistic | 0.000 [no interval: only 173 of 200 resamples defined] (0 of 15 agents; 173/200 resamples) | 0.000 (0 of 180 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out topology=hub | boosted | 0.120 [0.047, 0.183] (27 of 225 agents; 200/200 resamples) | 0.150 [0.052, 0.234] (27 of 180 agents; 200/200 resamples) |
| held-out topology=hub | rule | not available without aggregation features | not available without aggregation features |
| held-out topology=hub | pairs | 0.136 [0.120, 0.153] (170 of 1247 agents; 200/200 resamples) | 0.944 [0.898, 0.989] (170 of 180 agents; 200/200 resamples) |
| held-out topology=peer | volume (family-independent) | 0.304 [0.000, 1.000] (7 of 23 agents; 196/200 resamples) | 0.039 [0.000, 0.105] (7 of 180 agents; 200/200 resamples) |
| held-out topology=peer | logistic | 0.114 [0.000, 0.242] (9 of 79 agents; 200/200 resamples) | 0.050 [0.000, 0.128] (9 of 180 agents; 200/200 resamples) |
| held-out topology=peer | boosted | 0.112 [0.028, 0.234] (20 of 178 agents; 200/200 resamples) | 0.111 [0.029, 0.207] (20 of 180 agents; 200/200 resamples) |
| held-out topology=peer | rule | not available without aggregation features | not available without aggregation features |
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
| held-out channel=message | rule | not available without aggregation features | not available without aggregation features |
| held-out channel=message | pairs | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | volume (family-independent) | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | logistic | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | boosted | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | rule | not available without aggregation features | not available without aggregation features |
| held-out channel=preplanned | pairs | 0.012 [0.000, 0.031] (36 of 36 runs; 200/200 resamples) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=shared_file | volume (family-independent) | 0.024 [0.000, 0.066] (36 of 36 runs; 200/200 resamples) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=shared_file | logistic | 0.024 [0.000, 0.065] (36 of 36 runs; 200/200 resamples) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=shared_file | boosted | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=shared_file | rule | not available without aggregation features | not available without aggregation features |
| held-out channel=shared_file | pairs | 0.664 [0.576, 0.771] (36 of 36 runs; 200/200 resamples) | 0.389 [0.250, 0.528] (14 of 36 runs; 200/200 resamples) |
| held-out topology=hub | volume (family-independent) | 0.065 [0.015, 0.130] (54 of 54 runs; 200/200 resamples) | 0.037 [0.000, 0.093] (2 of 54 runs; 200/200 resamples) |
| held-out topology=hub | logistic | 0.000 (54 of 54 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 54 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out topology=hub | boosted | 0.087 [0.025, 0.154] (54 of 54 runs; 200/200 resamples) | 0.056 [0.000, 0.130] (3 of 54 runs; 200/200 resamples) |
| held-out topology=hub | rule | not available without aggregation features | not available without aggregation features |
| held-out topology=hub | pairs | 0.575 [0.501, 0.655] (54 of 54 runs; 200/200 resamples) | 0.333 [0.204, 0.463] (18 of 54 runs; 200/200 resamples) |
| held-out topology=peer | volume (family-independent) | 0.031 [0.000, 0.080] (54 of 54 runs; 200/200 resamples) | 0.019 [0.000, 0.056] (1 of 54 runs; 200/200 resamples) |
| held-out topology=peer | logistic | 0.015 [0.000, 0.036] (54 of 54 runs; 200/200 resamples) | 0.000 (0 of 54 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out topology=peer | boosted | 0.082 [0.019, 0.161] (54 of 54 runs; 200/200 resamples) | 0.056 [0.000, 0.112] (3 of 54 runs; 200/200 resamples) |
| held-out topology=peer | rule | not available without aggregation features | not available without aggregation features |
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
| held-out channel=message | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out channel=message | pairs | 189 agents | 0 | 9 | 180 | 0 | 0 |
| held-out channel=preplanned | volume (family-independent) | 5 agents | 0 | 0 | 5 | 0 | 0 |
| held-out channel=preplanned | logistic | 8 agents | 0 | 0 | 8 | 0 | 0 |
| held-out channel=preplanned | boosted | 12 agents | 0 | 0 | 12 | 0 | 0 |
| held-out channel=preplanned | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out channel=preplanned | pairs | 226 agents | 0 | 19 | 207 | 0 | 0 |
| held-out channel=shared_file | volume (family-independent) | 33 agents | 0 | 9 | 24 | 0 | 0 |
| held-out channel=shared_file | logistic | 33 agents | 1 | 10 | 22 | 0 | 0 |
| held-out channel=shared_file | boosted | 16 agents | 0 | 8 | 8 | 0 | 0 |
| held-out channel=shared_file | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out channel=shared_file | pairs | 749 agents | 3 | 106 | 640 | 0 | 0 |
| held-out topology=hub | volume (family-independent) | 52 agents | 0 | 7 | 45 | 0 | 0 |
| held-out topology=hub | logistic | 15 agents | 0 | 0 | 15 | 0 | 0 |
| held-out topology=hub | boosted | 198 agents | 0 | 27 | 171 | 0 | 0 |
| held-out topology=hub | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out topology=hub | pairs | 1077 agents | 0 | 96 | 981 | 0 | 0 |
| held-out topology=peer | volume (family-independent) | 16 agents | 0 | 0 | 16 | 0 | 0 |
| held-out topology=peer | logistic | 70 agents | 0 | 5 | 65 | 0 | 0 |
| held-out topology=peer | boosted | 158 agents | 0 | 19 | 139 | 0 | 0 |
| held-out topology=peer | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out topology=peer | pairs | 1095 agents | 0 | 124 | 971 | 0 | 0 |

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
| held-out channel=message | logistic | 0.957 [0.913, 0.983] (132 of 132 runs; 200/200 resamples) | 0.083 [0.029, 0.218] (3 of 36 runs; Wilson) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) |
| held-out channel=message | boosted | 0.965 [0.938, 0.989] (132 of 132 runs; 200/200 resamples) | 0.167 [0.079, 0.319] (6 of 36 runs; Wilson) | 0.010 [0.002, 0.057] (1 of 96 runs; Wilson) |
| held-out channel=message | rule | 0.960 [0.923, 0.987] (132 of 132 runs; 200/200 resamples) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) |
| held-out channel=preplanned | volume (family-independent) | 0.426 [0.315, 0.545] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.031 [0.011, 0.088] (3 of 96 runs; Wilson) |
| held-out channel=preplanned | logistic | 0.933 [0.892, 0.964] (132 of 132 runs; 200/200 resamples) | 0.250 [0.138, 0.411] (9 of 36 runs; Wilson) | 0.010 [0.002, 0.057] (1 of 96 runs; Wilson) |
| held-out channel=preplanned | boosted | 0.906 [0.863, 0.947] (132 of 132 runs; 200/200 resamples) | 0.306 [0.180, 0.469] (11 of 36 runs; Wilson) | 0.052 [0.022, 0.116] (5 of 96 runs; Wilson) |
| held-out channel=preplanned | rule | 0.911 [0.874, 0.958] (132 of 132 runs; 200/200 resamples) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) |
| held-out channel=shared_file | volume (family-independent) | 0.528 [0.419, 0.651] (132 of 132 runs; 200/200 resamples) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.042 [0.016, 0.102] (4 of 96 runs; Wilson) |
| held-out channel=shared_file | logistic | 0.901 [0.852, 0.944] (132 of 132 runs; 200/200 resamples) | 0.361 [0.225, 0.524] (13 of 36 runs; Wilson) | 0.052 [0.022, 0.116] (5 of 96 runs; Wilson) |
| held-out channel=shared_file | boosted | 0.923 [0.878, 0.971] (132 of 132 runs; 200/200 resamples) | 0.278 [0.158, 0.440] (10 of 36 runs; Wilson) | 0.031 [0.011, 0.088] (3 of 96 runs; Wilson) |
| held-out channel=shared_file | rule | 0.900 [0.836, 0.951] (132 of 132 runs; 200/200 resamples) | 0.611 [0.449, 0.752] (22 of 36 runs; Wilson) | 0.094 [0.050, 0.169] (9 of 96 runs; Wilson) |
| held-out topology=hub | volume (family-independent) | 0.516 [0.416, 0.598] (198 of 198 runs; 200/200 resamples) | 0.111 [0.052, 0.222] (6 of 54 runs; Wilson) | 0.049 [0.024, 0.097] (7 of 144 runs; Wilson) |
| held-out topology=hub | logistic | 0.958 [0.933, 0.978] (198 of 198 runs; 200/200 resamples) | 0.389 [0.270, 0.522] (21 of 54 runs; Wilson) | 0.014 [0.004, 0.049] (2 of 144 runs; Wilson) |
| held-out topology=hub | boosted | 0.916 [0.877, 0.955] (198 of 198 runs; 200/200 resamples) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.026] (0 of 144 runs; Wilson) |
| held-out topology=hub | rule | 0.945 [0.918, 0.968] (198 of 198 runs; 200/200 resamples) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.014 [0.004, 0.049] (2 of 144 runs; Wilson) |
| held-out topology=peer | volume (family-independent) | 0.518 [0.416, 0.622] (198 of 198 runs; 200/200 resamples) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.014 [0.004, 0.049] (2 of 144 runs; Wilson) |
| held-out topology=peer | logistic | 0.872 [0.820, 0.914] (198 of 198 runs; 200/200 resamples) | 0.056 [0.019, 0.151] (3 of 54 runs; Wilson) | 0.049 [0.024, 0.097] (7 of 144 runs; Wilson) |
| held-out topology=peer | boosted | 0.753 [0.691, 0.810] (198 of 198 runs; 200/200 resamples) | 0.056 [0.019, 0.151] (3 of 54 runs; Wilson) | 0.035 [0.015, 0.079] (5 of 144 runs; Wilson) |
| held-out topology=peer | rule | 0.905 [0.868, 0.942] (198 of 198 runs; 200/200 resamples) | 0.685 [0.553, 0.793] (37 of 54 runs; Wilson) | 0.132 [0.086, 0.197] (19 of 144 runs; Wilson) |

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
| held-out channel=message | boosted | 0.010 [0.002, 0.057] (1 of 96 runs; Wilson) | 0.222 [0.117, 0.381] (8 of 36 runs; Wilson) | 0.111 [0.044, 0.253] (4 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 1.132 [0.945, 1.457] (8 of 36 runs; 200/200 resamples) |
| held-out channel=message | rule | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 1.223 [0.886, 1.560] (2 of 36 runs; 200/200 resamples) |
| held-out channel=preplanned | volume (family-independent) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=preplanned | logistic | 0.094 [0.050, 0.169] (9 of 96 runs; Wilson) | 0.639 [0.476, 0.775] (23 of 36 runs; Wilson) | 0.472 [0.320, 0.630] (17 of 36 runs; Wilson) | 0.167 [0.079, 0.319] (6 of 36 runs; Wilson) | 0.919 [0.879, 0.948] (23 of 36 runs; 200/200 resamples) |
| held-out channel=preplanned | boosted | 0.031 [0.011, 0.088] (3 of 96 runs; Wilson) | 0.167 [0.079, 0.319] (6 of 36 runs; Wilson) | 0.139 [0.061, 0.287] (5 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.896 [0.787, 0.992] (6 of 36 runs; 200/200 resamples) |
| held-out channel=preplanned | rule | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.907 [no interval: fewer than 2 runs in a resampling stratum] (1 of 36 runs; 0/200 resamples) |
| held-out channel=shared_file | volume (family-independent) | 0.062 [0.029, 0.130] (6 of 96 runs; Wilson) | 0.194 [0.098, 0.350] (7 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 4.835 [3.761, 5.933] (7 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | logistic | 0.010 [0.002, 0.057] (1 of 96 runs; Wilson) | 0.306 [0.180, 0.469] (11 of 36 runs; Wilson) | 0.111 [0.044, 0.253] (4 of 36 runs; Wilson) | 0.111 [0.044, 0.253] (4 of 36 runs; Wilson) | 1.034 [0.956, 1.159] (11 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | boosted | 0.104 [0.058, 0.181] (10 of 96 runs; Wilson) | 0.389 [0.248, 0.551] (14 of 36 runs; Wilson) | 0.139 [0.061, 0.287] (5 of 36 runs; Wilson) | 0.111 [0.044, 0.253] (4 of 36 runs; Wilson) | 0.992 [0.831, 1.139] (14 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | rule | 0.094 [0.050, 0.169] (9 of 96 runs; Wilson) | 0.611 [0.449, 0.752] (22 of 36 runs; Wilson) | 0.389 [0.248, 0.551] (14 of 36 runs; Wilson) | 0.167 [0.079, 0.319] (6 of 36 runs; Wilson) | 0.916 [0.875, 0.958] (22 of 36 runs; 200/200 resamples) |
| held-out topology=hub | volume (family-independent) | 0.062 [0.033, 0.115] (9 of 144 runs; Wilson) | 0.111 [0.052, 0.222] (6 of 54 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.871 [0.685, 1.084] (6 of 54 runs; 200/200 resamples) |
| held-out topology=hub | logistic | 0.049 [0.024, 0.097] (7 of 144 runs; Wilson) | 0.574 [0.442, 0.697] (31 of 54 runs; Wilson) | 0.389 [0.270, 0.522] (21 of 54 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.961 [0.933, 0.985] (31 of 54 runs; 200/200 resamples) |
| held-out topology=hub | boosted | 0.000 [0.000, 0.026] (0 of 144 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | undefined (0 of 54 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out topology=hub | rule | 0.014 [0.004, 0.049] (2 of 144 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.019 [0.003, 0.098] (1 of 54 runs; Wilson) | 1.189 [0.967, 1.521] (5 of 54 runs; 200/200 resamples) |
| held-out topology=peer | volume (family-independent) | 0.028 [0.011, 0.069] (4 of 144 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 3.784 [2.724, 5.087] (5 of 54 runs; 200/200 resamples) |
| held-out topology=peer | logistic | 0.007 [0.001, 0.038] (1 of 144 runs; Wilson) | 0.019 [0.003, 0.098] (1 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.019 [0.003, 0.098] (1 of 54 runs; Wilson) | 1.000 [no interval: fewer than 2 runs in a resampling stratum] (1 of 54 runs; 0/200 resamples) |
| held-out topology=peer | boosted | 0.181 [0.126, 0.251] (26 of 144 runs; Wilson) | 0.648 [0.515, 0.762] (35 of 54 runs; Wilson) | 0.611 [0.478, 0.730] (33 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.636 [0.566, 0.729] (35 of 54 runs; 200/200 resamples) |
| held-out topology=peer | rule | 0.132 [0.086, 0.197] (19 of 144 runs; Wilson) | 0.685 [0.553, 0.793] (37 of 54 runs; Wilson) | 0.593 [0.460, 0.713] (32 of 54 runs; Wilson) | 0.019 [0.003, 0.098] (1 of 54 runs; Wilson) | 0.720 [0.663, 0.778] (37 of 54 runs; 200/200 resamples) |

### Attribution

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Method | Precision | Recall |
| --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 1.000 [no interval: only 130 of 200 resamples defined] (3 of 3 agents; 130/200 resamples) | 0.025 [0.000, 0.079] (3 of 120 agents; 200/200 resamples) |
| held-out channel=message | logistic | 0.722 [0.375, 1.000] (13 of 18 agents; 188/200 resamples) | 0.108 [0.000, 0.216] (13 of 120 agents; 200/200 resamples) |
| held-out channel=message | boosted | 0.857 [0.554, 1.000] (30 of 35 agents; 200/200 resamples) | 0.250 [0.090, 0.420] (30 of 120 agents; 200/200 resamples) |
| held-out channel=message | rule | 0.444 [no interval: only 178 of 200 resamples defined] (8 of 18 agents; 178/200 resamples) | 0.067 [0.000, 0.174] (8 of 120 agents; 200/200 resamples) |
| held-out channel=message | pairs | 0.745 [0.646, 0.868] (120 of 161 agents; 200/200 resamples) | 1.000 (120 of 120 agents; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population recall of one) |
| held-out channel=preplanned | volume (family-independent) | 0.000 [no interval: only 130 of 200 resamples defined] (0 of 2 agents; 130/200 resamples) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | logistic | 0.731 [0.512, 0.950] (38 of 52 agents; 200/200 resamples) | 0.317 [0.131, 0.500] (38 of 120 agents; 200/200 resamples) |
| held-out channel=preplanned | boosted | 0.595 [0.411, 0.809] (44 of 74 agents; 200/200 resamples) | 0.367 [0.190, 0.517] (44 of 120 agents; 200/200 resamples) |
| held-out channel=preplanned | rule | 0.375 [no interval: only 119 of 200 resamples defined] (3 of 8 agents; 119/200 resamples) | 0.025 [0.000, 0.079] (3 of 120 agents; 200/200 resamples) |
| held-out channel=preplanned | pairs | 0.609 [0.509, 0.734] (120 of 197 agents; 200/200 resamples) | 1.000 (120 of 120 agents; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population recall of one) |
| held-out channel=shared_file | volume (family-independent) | 0.471 [0.000, 1.000] (8 of 17 agents; 196/200 resamples) | 0.067 [0.000, 0.180] (8 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | logistic | 0.505 [0.343, 0.719] (48 of 95 agents; 200/200 resamples) | 0.400 [0.224, 0.551] (48 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | boosted | 0.618 [0.368, 0.897] (34 of 55 agents; 200/200 resamples) | 0.283 [0.127, 0.442] (34 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | rule | 0.550 [0.423, 0.718] (88 of 160 agents; 200/200 resamples) | 0.733 [0.586, 0.861] (88 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | pairs | 0.526 [0.435, 0.624] (120 of 228 agents; 200/200 resamples) | 1.000 (120 of 120 agents; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population recall of one) |
| held-out topology=hub | volume (family-independent) | 0.720 [0.409, 1.000] (18 of 25 agents; 200/200 resamples) | 0.100 [0.038, 0.179] (18 of 180 agents; 200/200 resamples) |
| held-out topology=hub | logistic | 0.680 [0.538, 0.824] (85 of 125 agents; 200/200 resamples) | 0.472 [0.325, 0.609] (85 of 180 agents; 200/200 resamples) |
| held-out topology=hub | boosted | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 180 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out topology=hub | rule | 0.319 [0.107, 0.500] (15 of 47 agents; 200/200 resamples) | 0.083 [0.018, 0.180] (15 of 180 agents; 200/200 resamples) |
| held-out topology=hub | pairs | 0.647 [0.569, 0.729] (180 of 278 agents; 200/200 resamples) | 1.000 (180 of 180 agents; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population recall of one) |
| held-out topology=peer | volume (family-independent) | 1.000 (8 of 8 agents; 183/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population precision of one) | 0.044 [0.000, 0.121] (8 of 180 agents; 200/200 resamples) |
| held-out topology=peer | logistic | 0.174 [0.000, 0.350] (8 of 46 agents; 200/200 resamples) | 0.044 [0.000, 0.111] (8 of 180 agents; 200/200 resamples) |
| held-out topology=peer | boosted | 0.250 [0.000, 0.501] (7 of 28 agents; 200/200 resamples) | 0.039 [0.010, 0.084] (7 of 180 agents; 200/200 resamples) |
| held-out topology=peer | rule | 0.575 [0.480, 0.689] (146 of 254 agents; 200/200 resamples) | 0.811 [0.721, 0.899] (146 of 180 agents; 200/200 resamples) |
| held-out topology=peer | pairs | 0.584 [0.507, 0.673] (180 of 308 agents; 200/200 resamples) | 1.000 (180 of 180 agents; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population recall of one) |

### Group reconstruction

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Method | Mean Jaccard overlap of proposed group | Reconstructed exactly |
| --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 0.028 [0.000, 0.083] (36 of 36 runs; 200/200 resamples) | 0.028 [0.000, 0.083] (1 of 36 runs; 200/200 resamples) |
| held-out channel=message | logistic | 0.083 [0.000, 0.194] (36 of 36 runs; 200/200 resamples) | 0.083 [0.000, 0.194] (3 of 36 runs; 200/200 resamples) |
| held-out channel=message | boosted | 0.167 [0.056, 0.306] (36 of 36 runs; 200/200 resamples) | 0.167 [0.056, 0.278] (6 of 36 runs; 200/200 resamples) |
| held-out channel=message | rule | 0.056 [0.000, 0.139] (36 of 36 runs; 200/200 resamples) | 0.056 [0.000, 0.139] (2 of 36 runs; 200/200 resamples) |
| held-out channel=message | pairs | 1.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population mean Jaccard overlap of one) | 1.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population exact-reconstruction rate of one) |
| held-out channel=preplanned | volume (family-independent) | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | logistic | 0.250 [0.138, 0.389] (36 of 36 runs; 200/200 resamples) | 0.250 [0.111, 0.389] (9 of 36 runs; 200/200 resamples) |
| held-out channel=preplanned | boosted | 0.306 [0.167, 0.445] (36 of 36 runs; 200/200 resamples) | 0.306 [0.167, 0.445] (11 of 36 runs; 200/200 resamples) |
| held-out channel=preplanned | rule | 0.028 [0.000, 0.083] (36 of 36 runs; 200/200 resamples) | 0.028 [0.000, 0.084] (1 of 36 runs; 200/200 resamples) |
| held-out channel=preplanned | pairs | 1.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population mean Jaccard overlap of one) | 1.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population exact-reconstruction rate of one) |
| held-out channel=shared_file | volume (family-independent) | 0.056 [0.000, 0.140] (36 of 36 runs; 200/200 resamples) | 0.056 [0.000, 0.139] (2 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | logistic | 0.361 [0.222, 0.500] (36 of 36 runs; 200/200 resamples) | 0.361 [0.194, 0.528] (13 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | boosted | 0.278 [0.167, 0.417] (36 of 36 runs; 200/200 resamples) | 0.278 [0.111, 0.417] (10 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | rule | 0.611 [0.444, 0.750] (36 of 36 runs; 200/200 resamples) | 0.611 [0.417, 0.778] (22 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | pairs | 1.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population mean Jaccard overlap of one) | 1.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population exact-reconstruction rate of one) |
| held-out topology=hub | volume (family-independent) | 0.111 [0.019, 0.204] (54 of 54 runs; 200/200 resamples) | 0.111 [0.037, 0.204] (6 of 54 runs; 200/200 resamples) |
| held-out topology=hub | logistic | 0.389 [0.259, 0.519] (54 of 54 runs; 200/200 resamples) | 0.389 [0.259, 0.519] (21 of 54 runs; 200/200 resamples) |
| held-out topology=hub | boosted | 0.000 (54 of 54 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 54 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out topology=hub | rule | 0.093 [0.019, 0.167] (54 of 54 runs; 200/200 resamples) | 0.093 [0.019, 0.167] (5 of 54 runs; 200/200 resamples) |
| held-out topology=hub | pairs | 1.000 (54 of 54 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population mean Jaccard overlap of one) | 1.000 (54 of 54 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population exact-reconstruction rate of one) |
| held-out topology=peer | volume (family-independent) | 0.037 [0.000, 0.093] (54 of 54 runs; 200/200 resamples) | 0.037 [0.000, 0.093] (2 of 54 runs; 200/200 resamples) |
| held-out topology=peer | logistic | 0.056 [0.000, 0.130] (54 of 54 runs; 200/200 resamples) | 0.056 [0.000, 0.111] (3 of 54 runs; 200/200 resamples) |
| held-out topology=peer | boosted | 0.056 [0.000, 0.111] (54 of 54 runs; 200/200 resamples) | 0.056 [0.000, 0.130] (3 of 54 runs; 200/200 resamples) |
| held-out topology=peer | rule | 0.685 [0.574, 0.796] (54 of 54 runs; 200/200 resamples) | 0.685 [0.574, 0.815] (37 of 54 runs; 200/200 resamples) |
| held-out topology=peer | pairs | 1.000 (54 of 54 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population mean Jaccard overlap of one) | 1.000 (54 of 54 runs; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population exact-reconstruction rate of one) |

### Wrongly named agents

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Method | Wrongly named | benign_solo | benign_team, sharing team | benign_team, non-sharing team | benign_team, sharing unresolved | benign_team, no sharing metadata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out channel=message | logistic | 5 agents | 0 | 5 | 0 | 0 | 0 |
| held-out channel=message | boosted | 5 agents | 0 | 5 | 0 | 0 | 0 |
| held-out channel=message | rule | 10 agents | 0 | 10 | 0 | 0 | 0 |
| held-out channel=message | pairs | 41 agents | 0 | 41 | 0 | 0 | 0 |
| held-out channel=preplanned | volume (family-independent) | 2 agents | 0 | 2 | 0 | 0 | 0 |
| held-out channel=preplanned | logistic | 14 agents | 0 | 14 | 0 | 0 | 0 |
| held-out channel=preplanned | boosted | 30 agents | 0 | 30 | 0 | 0 | 0 |
| held-out channel=preplanned | rule | 5 agents | 0 | 5 | 0 | 0 | 0 |
| held-out channel=preplanned | pairs | 77 agents | 0 | 77 | 0 | 0 | 0 |
| held-out channel=shared_file | volume (family-independent) | 9 agents | 0 | 9 | 0 | 0 | 0 |
| held-out channel=shared_file | logistic | 47 agents | 0 | 47 | 0 | 0 | 0 |
| held-out channel=shared_file | boosted | 21 agents | 0 | 21 | 0 | 0 | 0 |
| held-out channel=shared_file | rule | 72 agents | 0 | 72 | 0 | 0 | 0 |
| held-out channel=shared_file | pairs | 108 agents | 0 | 108 | 0 | 0 | 0 |
| held-out topology=hub | volume (family-independent) | 7 agents | 0 | 7 | 0 | 0 | 0 |
| held-out topology=hub | logistic | 40 agents | 0 | 40 | 0 | 0 | 0 |
| held-out topology=hub | boosted | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out topology=hub | rule | 32 agents | 0 | 32 | 0 | 0 | 0 |
| held-out topology=hub | pairs | 98 agents | 0 | 98 | 0 | 0 | 0 |
| held-out topology=peer | volume (family-independent) | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out topology=peer | logistic | 38 agents | 0 | 38 | 0 | 0 | 0 |
| held-out topology=peer | boosted | 21 agents | 0 | 21 | 0 | 0 | 0 |
| held-out topology=peer | rule | 108 agents | 0 | 108 | 0 | 0 | 0 |
| held-out topology=peer | pairs | 128 agents | 0 | 128 | 0 | 0 | 0 |

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
| held-out channel=message | logistic | 0.953 [0.909, 0.982] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) |
| held-out channel=message | boosted | 0.953 [0.919, 0.981] (132 of 132 runs; 200/200 resamples) | 0.194 [0.098, 0.350] (7 of 36 runs; Wilson) | 0.010 [0.002, 0.057] (1 of 96 runs; Wilson) |
| held-out channel=message | rule | 0.960 [0.923, 0.987] (132 of 132 runs; 200/200 resamples) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) |
| held-out channel=preplanned | volume (family-independent) | 0.426 [0.315, 0.545] (132 of 132 runs; 200/200 resamples) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.031 [0.011, 0.088] (3 of 96 runs; Wilson) |
| held-out channel=preplanned | logistic | 0.929 [0.884, 0.964] (132 of 132 runs; 200/200 resamples) | 0.306 [0.180, 0.469] (11 of 36 runs; Wilson) | 0.031 [0.011, 0.088] (3 of 96 runs; Wilson) |
| held-out channel=preplanned | boosted | 0.913 [0.868, 0.951] (132 of 132 runs; 200/200 resamples) | 0.194 [0.098, 0.350] (7 of 36 runs; Wilson) | 0.031 [0.011, 0.088] (3 of 96 runs; Wilson) |
| held-out channel=preplanned | rule | 0.911 [0.874, 0.958] (132 of 132 runs; 200/200 resamples) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) |
| held-out channel=shared_file | volume (family-independent) | 0.528 [0.419, 0.651] (132 of 132 runs; 200/200 resamples) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.042 [0.016, 0.102] (4 of 96 runs; Wilson) |
| held-out channel=shared_file | logistic | 0.892 [0.844, 0.942] (132 of 132 runs; 200/200 resamples) | 0.389 [0.248, 0.551] (14 of 36 runs; Wilson) | 0.062 [0.029, 0.130] (6 of 96 runs; Wilson) |
| held-out channel=shared_file | boosted | 0.848 [0.777, 0.906] (132 of 132 runs; 200/200 resamples) | 0.194 [0.098, 0.350] (7 of 36 runs; Wilson) | 0.083 [0.043, 0.156] (8 of 96 runs; Wilson) |
| held-out channel=shared_file | rule | 0.900 [0.836, 0.951] (132 of 132 runs; 200/200 resamples) | 0.611 [0.449, 0.752] (22 of 36 runs; Wilson) | 0.094 [0.050, 0.169] (9 of 96 runs; Wilson) |
| held-out topology=hub | volume (family-independent) | 0.516 [0.416, 0.598] (198 of 198 runs; 200/200 resamples) | 0.111 [0.052, 0.222] (6 of 54 runs; Wilson) | 0.049 [0.024, 0.097] (7 of 144 runs; Wilson) |
| held-out topology=hub | logistic | 0.935 [0.899, 0.961] (198 of 198 runs; 200/200 resamples) | 0.222 [0.132, 0.349] (12 of 54 runs; Wilson) | 0.014 [0.004, 0.049] (2 of 144 runs; Wilson) |
| held-out topology=hub | boosted | 0.897 [0.854, 0.937] (198 of 198 runs; 200/200 resamples) | 0.241 [0.146, 0.369] (13 of 54 runs; Wilson) | 0.069 [0.038, 0.123] (10 of 144 runs; Wilson) |
| held-out topology=hub | rule | 0.945 [0.918, 0.968] (198 of 198 runs; 200/200 resamples) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.014 [0.004, 0.049] (2 of 144 runs; Wilson) |
| held-out topology=peer | volume (family-independent) | 0.518 [0.416, 0.622] (198 of 198 runs; 200/200 resamples) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.014 [0.004, 0.049] (2 of 144 runs; Wilson) |
| held-out topology=peer | logistic | 0.874 [0.822, 0.915] (198 of 198 runs; 200/200 resamples) | 0.204 [0.118, 0.329] (11 of 54 runs; Wilson) | 0.056 [0.028, 0.106] (8 of 144 runs; Wilson) |
| held-out topology=peer | boosted | 0.721 [0.637, 0.790] (198 of 198 runs; 200/200 resamples) | 0.111 [0.052, 0.222] (6 of 54 runs; Wilson) | 0.076 [0.043, 0.132] (11 of 144 runs; Wilson) |
| held-out topology=peer | rule | 0.905 [0.868, 0.942] (198 of 198 runs; 200/200 resamples) | 0.685 [0.553, 0.793] (37 of 54 runs; Wilson) | 0.132 [0.086, 0.197] (19 of 144 runs; Wilson) |

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
| held-out channel=message | boosted | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=message | rule | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 1.223 [0.886, 1.560] (2 of 36 runs; 200/200 resamples) |
| held-out channel=preplanned | volume (family-independent) | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | undefined (0 of 36 runs; 0/200 resamples; fewer than 2 runs in a resampling stratum) |
| held-out channel=preplanned | logistic | 0.031 [0.011, 0.088] (3 of 96 runs; Wilson) | 0.389 [0.248, 0.551] (14 of 36 runs; Wilson) | 0.222 [0.117, 0.381] (8 of 36 runs; Wilson) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 1.317 [0.984, 1.737] (14 of 36 runs; 200/200 resamples) |
| held-out channel=preplanned | boosted | 0.031 [0.011, 0.088] (3 of 96 runs; Wilson) | 0.194 [0.098, 0.350] (7 of 36 runs; Wilson) | 0.139 [0.061, 0.287] (5 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.935 [0.719, 1.236] (7 of 36 runs; 200/200 resamples) |
| held-out channel=preplanned | rule | 0.000 [0.000, 0.038] (0 of 96 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.028 [0.005, 0.142] (1 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.907 [no interval: fewer than 2 runs in a resampling stratum] (1 of 36 runs; 0/200 resamples) |
| held-out channel=shared_file | volume (family-independent) | 0.062 [0.029, 0.130] (6 of 96 runs; Wilson) | 0.194 [0.098, 0.350] (7 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 4.835 [3.761, 5.933] (7 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | logistic | 0.115 [0.065, 0.194] (11 of 96 runs; Wilson) | 0.472 [0.320, 0.630] (17 of 36 runs; Wilson) | 0.361 [0.225, 0.524] (13 of 36 runs; Wilson) | 0.000 [0.000, 0.096] (0 of 36 runs; Wilson) | 0.866 [0.756, 0.976] (17 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | boosted | 0.083 [0.043, 0.156] (8 of 96 runs; Wilson) | 0.222 [0.117, 0.381] (8 of 36 runs; Wilson) | 0.056 [0.015, 0.181] (2 of 36 runs; Wilson) | 0.083 [0.029, 0.218] (3 of 36 runs; Wilson) | 1.364 [0.955, 2.122] (8 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | rule | 0.094 [0.050, 0.169] (9 of 96 runs; Wilson) | 0.611 [0.449, 0.752] (22 of 36 runs; Wilson) | 0.389 [0.248, 0.551] (14 of 36 runs; Wilson) | 0.167 [0.079, 0.319] (6 of 36 runs; Wilson) | 0.916 [0.875, 0.958] (22 of 36 runs; 200/200 resamples) |
| held-out topology=hub | volume (family-independent) | 0.062 [0.033, 0.115] (9 of 144 runs; Wilson) | 0.111 [0.052, 0.222] (6 of 54 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.871 [0.685, 1.084] (6 of 54 runs; 200/200 resamples) |
| held-out topology=hub | logistic | 0.021 [0.007, 0.059] (3 of 144 runs; Wilson) | 0.296 [0.191, 0.428] (16 of 54 runs; Wilson) | 0.148 [0.077, 0.266] (8 of 54 runs; Wilson) | 0.074 [0.029, 0.176] (4 of 54 runs; Wilson) | 1.070 [0.964, 1.190] (16 of 54 runs; 200/200 resamples) |
| held-out topology=hub | boosted | 0.083 [0.048, 0.140] (12 of 144 runs; Wilson) | 0.444 [0.320, 0.576] (24 of 54 runs; Wilson) | 0.167 [0.090, 0.287] (9 of 54 runs; Wilson) | 0.019 [0.003, 0.098] (1 of 54 runs; Wilson) | 1.493 [1.187, 1.880] (24 of 54 runs; 200/200 resamples) |
| held-out topology=hub | rule | 0.014 [0.004, 0.049] (2 of 144 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 0.019 [0.003, 0.098] (1 of 54 runs; Wilson) | 1.189 [0.967, 1.521] (5 of 54 runs; 200/200 resamples) |
| held-out topology=peer | volume (family-independent) | 0.028 [0.011, 0.069] (4 of 144 runs; Wilson) | 0.093 [0.040, 0.199] (5 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 0.000 [0.000, 0.066] (0 of 54 runs; Wilson) | 3.784 [2.724, 5.087] (5 of 54 runs; 200/200 resamples) |
| held-out topology=peer | logistic | 0.056 [0.028, 0.106] (8 of 144 runs; Wilson) | 0.167 [0.090, 0.287] (9 of 54 runs; Wilson) | 0.111 [0.052, 0.222] (6 of 54 runs; Wilson) | 0.019 [0.003, 0.098] (1 of 54 runs; Wilson) | 0.863 [0.742, 0.987] (9 of 54 runs; 200/200 resamples) |
| held-out topology=peer | boosted | 0.076 [0.043, 0.132] (11 of 144 runs; Wilson) | 0.296 [0.191, 0.428] (16 of 54 runs; Wilson) | 0.204 [0.118, 0.329] (11 of 54 runs; Wilson) | 0.037 [0.010, 0.125] (2 of 54 runs; Wilson) | 1.009 [0.837, 1.219] (16 of 54 runs; 200/200 resamples) |
| held-out topology=peer | rule | 0.132 [0.086, 0.197] (19 of 144 runs; Wilson) | 0.685 [0.553, 0.793] (37 of 54 runs; Wilson) | 0.593 [0.460, 0.713] (32 of 54 runs; Wilson) | 0.019 [0.003, 0.098] (1 of 54 runs; Wilson) | 0.720 [0.663, 0.778] (37 of 54 runs; 200/200 resamples) |

### Attribution

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Method | Precision | Recall |
| --- | --- | --- | --- |
| held-out channel=message | volume (family-independent) | 1.000 [no interval: only 130 of 200 resamples defined] (3 of 3 agents; 130/200 resamples) | 0.025 [0.000, 0.079] (3 of 120 agents; 200/200 resamples) |
| held-out channel=message | logistic | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=message | boosted | 0.622 [0.458, 0.821] (28 of 45 agents; 200/200 resamples) | 0.233 [0.088, 0.400] (28 of 120 agents; 200/200 resamples) |
| held-out channel=message | rule | 0.444 [no interval: only 178 of 200 resamples defined] (8 of 18 agents; 178/200 resamples) | 0.067 [0.000, 0.174] (8 of 120 agents; 200/200 resamples) |
| held-out channel=message | pairs | 0.471 [0.398, 0.557] (120 of 255 agents; 200/200 resamples) | 1.000 (120 of 120 agents; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population recall of one) |
| held-out channel=preplanned | volume (family-independent) | undefined (0 of 0 agents; 0/200 resamples; only 0 of 200 resamples defined) | 0.000 (0 of 120 agents; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population recall) |
| held-out channel=preplanned | logistic | 0.655 [0.318, 0.923] (19 of 29 agents; 200/200 resamples) | 0.158 [0.063, 0.276] (19 of 120 agents; 200/200 resamples) |
| held-out channel=preplanned | boosted | 0.625 [0.103, 0.867] (15 of 24 agents; 200/200 resamples) | 0.125 [0.033, 0.246] (15 of 120 agents; 200/200 resamples) |
| held-out channel=preplanned | rule | 0.286 [no interval: only 119 of 200 resamples defined] (2 of 7 agents; 119/200 resamples) | 0.017 [0.000, 0.053] (2 of 120 agents; 200/200 resamples) |
| held-out channel=preplanned | pairs | 0.367 [0.255, 0.494] (51 of 139 agents; 200/200 resamples) | 0.425 [0.295, 0.554] (51 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | volume (family-independent) | 0.421 [0.000, 0.833] (8 of 19 agents; 199/200 resamples) | 0.067 [0.000, 0.180] (8 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | logistic | 0.477 [0.319, 0.681] (51 of 107 agents; 200/200 resamples) | 0.425 [0.241, 0.600] (51 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | boosted | 0.393 [0.200, 0.652] (24 of 61 agents; 200/200 resamples) | 0.200 [0.078, 0.358] (24 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | rule | 0.512 [0.400, 0.649] (88 of 172 agents; 200/200 resamples) | 0.733 [0.586, 0.861] (88 of 120 agents; 200/200 resamples) |
| held-out channel=shared_file | pairs | 0.387 [0.327, 0.455] (120 of 310 agents; 200/200 resamples) | 1.000 (120 of 120 agents; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population recall of one) |
| held-out topology=hub | volume (family-independent) | 0.517 [0.231, 0.816] (15 of 29 agents; 200/200 resamples) | 0.083 [0.030, 0.141] (15 of 180 agents; 200/200 resamples) |
| held-out topology=hub | logistic | 0.646 [0.465, 0.857] (51 of 79 agents; 200/200 resamples) | 0.283 [0.173, 0.424] (51 of 180 agents; 200/200 resamples) |
| held-out topology=hub | boosted | 0.500 [0.338, 0.675] (40 of 80 agents; 200/200 resamples) | 0.222 [0.118, 0.327] (40 of 180 agents; 200/200 resamples) |
| held-out topology=hub | rule | 0.319 [0.107, 0.500] (15 of 47 agents; 200/200 resamples) | 0.083 [0.018, 0.180] (15 of 180 agents; 200/200 resamples) |
| held-out topology=hub | pairs | 0.420 [0.362, 0.470] (171 of 407 agents; 200/200 resamples) | 0.950 [0.901, 0.984] (171 of 180 agents; 200/200 resamples) |
| held-out topology=peer | volume (family-independent) | 0.571 [0.000, 1.000] (8 of 14 agents; 194/200 resamples) | 0.044 [0.000, 0.121] (8 of 180 agents; 200/200 resamples) |
| held-out topology=peer | logistic | 0.385 [0.208, 0.586] (30 of 78 agents; 200/200 resamples) | 0.167 [0.072, 0.278] (30 of 180 agents; 200/200 resamples) |
| held-out topology=peer | boosted | 0.167 [0.064, 0.333] (13 of 78 agents; 200/200 resamples) | 0.072 [0.022, 0.127] (13 of 180 agents; 200/200 resamples) |
| held-out topology=peer | rule | 0.483 [0.404, 0.586] (146 of 302 agents; 200/200 resamples) | 0.811 [0.721, 0.899] (146 of 180 agents; 200/200 resamples) |
| held-out topology=peer | pairs | 0.324 [0.290, 0.370] (180 of 556 agents; 200/200 resamples) | 1.000 (180 of 180 agents; 200/200 resamples; degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population recall of one) |

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
| held-out channel=message | boosted | 0.194 [0.083, 0.306] (36 of 36 runs; 200/200 resamples) | 0.194 [0.056, 0.333] (7 of 36 runs; 200/200 resamples) |
| held-out channel=message | rule | 0.056 [0.000, 0.139] (36 of 36 runs; 200/200 resamples) | 0.056 [0.000, 0.139] (2 of 36 runs; 200/200 resamples) |
| held-out channel=message | pairs | 0.977 [0.940, 1.000] (36 of 36 runs; 200/200 resamples) | 0.944 [0.861, 1.000] (34 of 36 runs; 200/200 resamples) |
| held-out channel=preplanned | volume (family-independent) | 0.000 (36 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population mean Jaccard overlap) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | logistic | 0.124 [0.044, 0.206] (36 of 36 runs; 200/200 resamples) | 0.056 [0.000, 0.139] (2 of 36 runs; 200/200 resamples) |
| held-out channel=preplanned | boosted | 0.072 [0.011, 0.144] (36 of 36 runs; 200/200 resamples) | 0.028 [0.000, 0.083] (1 of 36 runs; 200/200 resamples) |
| held-out channel=preplanned | rule | 0.019 [0.000, 0.056] (36 of 36 runs; 200/200 resamples) | 0.000 (0 of 36 runs; 200/200 resamples; degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish zero population exact-reconstruction rate) |
| held-out channel=preplanned | pairs | 0.370 [0.254, 0.487] (36 of 36 runs; 200/200 resamples) | 0.139 [0.028, 0.278] (5 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | volume (family-independent) | 0.056 [0.000, 0.140] (36 of 36 runs; 200/200 resamples) | 0.056 [0.000, 0.139] (2 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | logistic | 0.372 [0.228, 0.494] (36 of 36 runs; 200/200 resamples) | 0.306 [0.167, 0.444] (11 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | boosted | 0.187 [0.056, 0.326] (36 of 36 runs; 200/200 resamples) | 0.167 [0.056, 0.333] (6 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | rule | 0.589 [0.414, 0.728] (36 of 36 runs; 200/200 resamples) | 0.500 [0.306, 0.667] (18 of 36 runs; 200/200 resamples) |
| held-out channel=shared_file | pairs | 0.978 [0.954, 0.995] (36 of 36 runs; 200/200 resamples) | 0.889 [0.778, 0.972] (32 of 36 runs; 200/200 resamples) |
| held-out topology=hub | volume (family-independent) | 0.086 [0.019, 0.167] (54 of 54 runs; 200/200 resamples) | 0.074 [0.019, 0.148] (4 of 54 runs; 200/200 resamples) |
| held-out topology=hub | logistic | 0.209 [0.121, 0.316] (54 of 54 runs; 200/200 resamples) | 0.167 [0.074, 0.278] (9 of 54 runs; 200/200 resamples) |
| held-out topology=hub | boosted | 0.225 [0.130, 0.327] (54 of 54 runs; 200/200 resamples) | 0.204 [0.111, 0.315] (11 of 54 runs; 200/200 resamples) |
| held-out topology=hub | rule | 0.068 [0.010, 0.142] (54 of 54 runs; 200/200 resamples) | 0.056 [0.000, 0.130] (3 of 54 runs; 200/200 resamples) |
| held-out topology=hub | pairs | 0.863 [0.789, 0.925] (54 of 54 runs; 200/200 resamples) | 0.722 [0.611, 0.815] (39 of 54 runs; 200/200 resamples) |
| held-out topology=peer | volume (family-independent) | 0.037 [0.000, 0.093] (54 of 54 runs; 200/200 resamples) | 0.037 [0.000, 0.093] (2 of 54 runs; 200/200 resamples) |
| held-out topology=peer | logistic | 0.204 [0.111, 0.315] (54 of 54 runs; 200/200 resamples) | 0.204 [0.093, 0.333] (11 of 54 runs; 200/200 resamples) |
| held-out topology=peer | boosted | 0.111 [0.037, 0.204] (54 of 54 runs; 200/200 resamples) | 0.111 [0.019, 0.204] (6 of 54 runs; 200/200 resamples) |
| held-out topology=peer | rule | 0.673 [0.562, 0.790] (54 of 54 runs; 200/200 resamples) | 0.648 [0.519, 0.778] (35 of 54 runs; 200/200 resamples) |
| held-out topology=peer | pairs | 0.979 [0.955, 1.000] (54 of 54 runs; 200/200 resamples) | 0.944 [0.888, 1.000] (51 of 54 runs; 200/200 resamples) |

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
| held-out channel=message | boosted | 17 agents | 0 | 10 | 7 | 0 | 0 |
| held-out channel=message | rule | 10 agents | 0 | 10 | 0 | 0 | 0 |
| held-out channel=message | pairs | 135 agents | 0 | 41 | 94 | 0 | 0 |
| held-out channel=preplanned | volume (family-independent) | 0 agents | 0 | 0 | 0 | 0 | 0 |
| held-out channel=preplanned | logistic | 10 agents | 0 | 10 | 0 | 0 | 0 |
| held-out channel=preplanned | boosted | 9 agents | 0 | 9 | 0 | 0 | 0 |
| held-out channel=preplanned | rule | 5 agents | 0 | 5 | 0 | 0 | 0 |
| held-out channel=preplanned | pairs | 88 agents | 0 | 42 | 46 | 0 | 0 |
| held-out channel=shared_file | volume (family-independent) | 11 agents | 0 | 9 | 2 | 0 | 0 |
| held-out channel=shared_file | logistic | 56 agents | 0 | 50 | 6 | 0 | 0 |
| held-out channel=shared_file | boosted | 37 agents | 0 | 35 | 2 | 0 | 0 |
| held-out channel=shared_file | rule | 84 agents | 0 | 72 | 12 | 0 | 0 |
| held-out channel=shared_file | pairs | 190 agents | 0 | 108 | 82 | 0 | 0 |
| held-out topology=hub | volume (family-independent) | 14 agents | 0 | 7 | 7 | 0 | 0 |
| held-out topology=hub | logistic | 28 agents | 0 | 24 | 4 | 0 | 0 |
| held-out topology=hub | boosted | 40 agents | 0 | 38 | 2 | 0 | 0 |
| held-out topology=hub | rule | 32 agents | 0 | 32 | 0 | 0 | 0 |
| held-out topology=hub | pairs | 236 agents | 0 | 90 | 146 | 0 | 0 |
| held-out topology=peer | volume (family-independent) | 6 agents | 0 | 0 | 6 | 0 | 0 |
| held-out topology=peer | logistic | 48 agents | 0 | 43 | 5 | 0 | 0 |
| held-out topology=peer | boosted | 65 agents | 0 | 43 | 22 | 0 | 0 |
| held-out topology=peer | rule | 156 agents | 0 | 108 | 48 | 0 | 0 |
| held-out topology=peer | pairs | 376 agents | 0 | 128 | 248 | 0 | 0 |
