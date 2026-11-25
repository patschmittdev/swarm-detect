# Benign credential-sharing sweep

Seed: 20261120. Rates are percentages of benign teams.

A first sweep of 792 runs (one positive replicate, 8 control repeats) was too small to distinguish 1 - q/2 from 1 - q at rates 5 and 10 and was replaced by this one before any conclusion was written.

Predeclared rule: Containment uses unrounded overall AUROC bounds and is undefined with fewer than two sharing test controls or a withheld interval.

V1, aggregation features, by-run split. Each rate has independently seeded runs and its own fitted models and calibrated thresholds. Training, calibration and test runs are disjoint. The test fraction and calibration fraction of training runs are both 0.3, stratified by class. Thresholds target FPR 0.05 and flag strictly greater scores. q counts test controls with at least one sharing team.

The calibrated threshold is the conformal quantile of the calibration-control scores, with the number of calibration controls in each row; once more than about 5 percent of controls contain a sharing team the threshold falls inside the sharing-score range.

160 ticks; 200 bootstrap resamples. AUROC intervals use the existing stratified bootstrap over runs; rates use 95% Wilson intervals and print k of n. Withheld intervals retain their reason. A_s compares all positive test runs with sharing test controls only. The non-sharing AUROC and the one-team and two-or-more-team A_s rows use the same positive test runs and their named control subset, without refitting. Subgroup counts are out of all sharing test controls.

Identity: overall AUROC = 1 - q(1 - A_s) when non-sharing controls are perfectly separated.

Simulation, split and evaluation roots use child_seed(seed, 91, rate_index, 2, 0/1/2), respectively. make_jobs spawns simulation children; the unchanged harness derives calibration, fit and bootstrap seeds from the evaluation root with distinct subkeys. Restricted-control bootstrap seeds use child_seed(seed, 91, rate_index, 2, 3, detector_index, subset_index), with subset indices 0 (non-sharing), 1 (one team) and 2 (two or more teams). All child_seed keys contain at least two elements.

| rate | runs_per_condition | control_repeats | calibration_controls | simulation_seed | split_seed | evaluation_seed |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 3 | 90 | 340 | 1485089140 | 2165823489 | 3744619567 |
| 5 | 3 | 90 | 340 | 3843921407 | 3548108890 | 1337050239 |
| 10 | 3 | 90 | 340 | 849477235 | 810212255 | 69047363 |
| 30 | 3 | 90 | 340 | 865478623 | 3247380807 | 895250153 |

## rule

| rate | runs | fitting (positive, control) | calibration (positive, control) | test (positive, control) | sharing test controls (q) | A_s | AUROC vs non-sharing controls | overall AUROC | expected 1 - q/2 | interval contains 1 - q/2 | interval contains 1 - q | detection rate | FPR | calibration controls | threshold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 1782 (162 positive, 1620 control) | 79 positive, 794 control | 34 positive, 340 control | 49 positive, 486 control | 0 of 486; 0.000 [0.000, 0.008] Wilson | undefined: no sharing controls | 1.000 [1.000, 1.000] (535 of 535 runs; 200/200 resamples) | 1.000 [1.000, 1.000] (535 of 535 runs; 200/200 resamples) | 1.0000 | undefined: no sharing controls | undefined: no sharing controls | 1.000 [0.927, 1.000] (49 of 49 runs; Wilson) | 0.000 [0.000, 0.008] (0 of 486 runs; Wilson) | 340 | 0.000000 |
| 5 | 1782 (162 positive, 1620 control) | 79 positive, 794 control | 34 positive, 340 control | 49 positive, 486 control | 57 of 486; 0.117 [0.092, 0.149] Wilson | 0.422 [0.320, 0.526] (106 of 106 runs; 200/200 resamples) | 1.000 [1.000, 1.000] (478 of 478 runs; 200/200 resamples) | 0.932 [0.912, 0.953] (535 of 535 runs; 200/200 resamples) | 0.9414 | yes | no | 0.510 [0.375, 0.644] (25 of 49 runs; Wilson) | 0.066 [0.047, 0.091] (32 of 486 runs; Wilson) | 340 | 2.000000 |
| 10 | 1782 (162 positive, 1620 control) | 79 positive, 794 control | 34 positive, 340 control | 49 positive, 486 control | 100 of 486; 0.206 [0.172, 0.244] Wilson | 0.548 [0.453, 0.641] (149 of 149 runs; 200/200 resamples) | 1.000 [1.000, 1.000] (435 of 435 runs; 200/200 resamples) | 0.907 [0.882, 0.931] (535 of 535 runs; 200/200 resamples) | 0.8971 | yes | no | 0.245 [0.146, 0.381] (12 of 49 runs; Wilson) | 0.037 [0.024, 0.058] (18 of 486 runs; Wilson) | 340 | 4.000000 |
| 30 | 1782 (162 positive, 1620 control) | 79 positive, 794 control | 34 positive, 340 control | 49 positive, 486 control | 245 of 486; 0.504 [0.460, 0.548] Wilson | 0.528 [0.434, 0.609] (294 of 294 runs; 200/200 resamples) | 1.000 [1.000, 1.000] (290 of 290 runs; 200/200 resamples) | 0.762 [0.721, 0.807] (535 of 535 runs; 200/200 resamples) | 0.7479 | yes | no | 0.061 [0.021, 0.165] (3 of 49 runs; Wilson) | 0.031 [0.019, 0.050] (15 of 486 runs; Wilson) | 340 | 6.000000 |

## logistic

| rate | runs | fitting (positive, control) | calibration (positive, control) | test (positive, control) | sharing test controls (q) | A_s | AUROC vs non-sharing controls | overall AUROC | expected 1 - q/2 | interval contains 1 - q/2 | interval contains 1 - q | detection rate | FPR | calibration controls | threshold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 1782 (162 positive, 1620 control) | 79 positive, 794 control | 34 positive, 340 control | 49 positive, 486 control | 0 of 486; 0.000 [0.000, 0.008] Wilson | undefined: no sharing controls | 1.000 [1.000, 1.000] (535 of 535 runs; 200/200 resamples) | 1.000 [1.000, 1.000] (535 of 535 runs; 200/200 resamples) | 1.0000 | undefined: no sharing controls | undefined: no sharing controls | 1.000 [0.927, 1.000] (49 of 49 runs; Wilson) | 0.000 [0.000, 0.008] (0 of 486 runs; Wilson) | 340 | 0.000709 |
| 5 | 1782 (162 positive, 1620 control) | 79 positive, 794 control | 34 positive, 340 control | 49 positive, 486 control | 57 of 486; 0.117 [0.092, 0.149] Wilson | 0.453 [0.347, 0.572] (106 of 106 runs; 200/200 resamples) | 1.000 [1.000, 1.000] (478 of 478 runs; 200/200 resamples) | 0.936 [0.914, 0.958] (535 of 535 runs; 200/200 resamples) | 0.9414 | yes | no | 0.612 [0.472, 0.736] (30 of 49 runs; Wilson) | 0.078 [0.057, 0.106] (38 of 486 runs; Wilson) | 340 | 0.342864 |
| 10 | 1782 (162 positive, 1620 control) | 79 positive, 794 control | 34 positive, 340 control | 49 positive, 486 control | 100 of 486; 0.206 [0.172, 0.244] Wilson | 0.579 [0.478, 0.668] (149 of 149 runs; 200/200 resamples) | 1.000 [1.000, 1.000] (435 of 435 runs; 200/200 resamples) | 0.913 [0.886, 0.937] (535 of 535 runs; 200/200 resamples) | 0.8971 | yes | no | 0.347 [0.229, 0.487] (17 of 49 runs; Wilson) | 0.058 [0.040, 0.082] (28 of 486 runs; Wilson) | 340 | 0.381860 |
| 30 | 1782 (162 positive, 1620 control) | 79 positive, 794 control | 34 positive, 340 control | 49 positive, 486 control | 245 of 486; 0.504 [0.460, 0.548] Wilson | 0.591 [0.507, 0.667] (294 of 294 runs; 200/200 resamples) | 1.000 [1.000, 1.000] (290 of 290 runs; 200/200 resamples) | 0.794 [0.750, 0.839] (535 of 535 runs; 200/200 resamples) | 0.7479 | no | no | 0.102 [0.044, 0.218] (5 of 49 runs; Wilson) | 0.041 [0.027, 0.063] (20 of 486 runs; Wilson) | 340 | 0.277235 |

## boosted

| rate | runs | fitting (positive, control) | calibration (positive, control) | test (positive, control) | sharing test controls (q) | A_s | AUROC vs non-sharing controls | overall AUROC | expected 1 - q/2 | interval contains 1 - q/2 | interval contains 1 - q | detection rate | FPR | calibration controls | threshold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 1782 (162 positive, 1620 control) | 79 positive, 794 control | 34 positive, 340 control | 49 positive, 486 control | 0 of 486; 0.000 [0.000, 0.008] Wilson | undefined: no sharing controls | 1.000 [1.000, 1.000] (535 of 535 runs; 200/200 resamples) | 1.000 [1.000, 1.000] (535 of 535 runs; 200/200 resamples) | 1.0000 | undefined: no sharing controls | undefined: no sharing controls | 1.000 [0.927, 1.000] (49 of 49 runs; Wilson) | 0.000 [0.000, 0.008] (0 of 486 runs; Wilson) | 340 | 0.000004 |
| 5 | 1782 (162 positive, 1620 control) | 79 positive, 794 control | 34 positive, 340 control | 49 positive, 486 control | 57 of 486; 0.117 [0.092, 0.149] Wilson | 0.473 [0.380, 0.594] (106 of 106 runs; 200/200 resamples) | 1.000 [1.000, 1.000] (478 of 478 runs; 200/200 resamples) | 0.938 [0.916, 0.955] (535 of 535 runs; 200/200 resamples) | 0.9414 | yes | no | 0.510 [0.375, 0.644] (25 of 49 runs; Wilson) | 0.072 [0.052, 0.099] (35 of 486 runs; Wilson) | 340 | 0.449962 |
| 10 | 1782 (162 positive, 1620 control) | 79 positive, 794 control | 34 positive, 340 control | 49 positive, 486 control | 100 of 486; 0.206 [0.172, 0.244] Wilson | 0.576 [0.475, 0.672] (149 of 149 runs; 200/200 resamples) | 1.000 [1.000, 1.000] (435 of 435 runs; 200/200 resamples) | 0.913 [0.888, 0.936] (535 of 535 runs; 200/200 resamples) | 0.8971 | yes | no | 0.327 [0.212, 0.466] (16 of 49 runs; Wilson) | 0.060 [0.042, 0.084] (29 of 486 runs; Wilson) | 340 | 0.380677 |
| 30 | 1782 (162 positive, 1620 control) | 79 positive, 794 control | 34 positive, 340 control | 49 positive, 486 control | 245 of 486; 0.504 [0.460, 0.548] Wilson | 0.541 [0.460, 0.618] (294 of 294 runs; 200/200 resamples) | 1.000 [1.000, 1.000] (290 of 290 runs; 200/200 resamples) | 0.769 [0.726, 0.818] (535 of 535 runs; 200/200 resamples) | 0.7479 | yes | no | 0.041 [0.011, 0.137] (2 of 49 runs; Wilson) | 0.025 [0.014, 0.043] (12 of 486 runs; Wilson) | 340 | 0.469194 |

## A_s by sharing-team count

| rate | detector | sharing teams | sharing controls k of n | A_s |
| --- | --- | --- | --- | --- |
| 0 | rule | one team | 0 of 0 | undefined: no sharing controls |
| 0 | rule | two or more | 0 of 0 | undefined: no sharing controls |
| 0 | logistic | one team | 0 of 0 | undefined: no sharing controls |
| 0 | logistic | two or more | 0 of 0 | undefined: no sharing controls |
| 0 | boosted | one team | 0 of 0 | undefined: no sharing controls |
| 0 | boosted | two or more | 0 of 0 | undefined: no sharing controls |
| 5 | rule | one team | 55 of 57 | 0.435 [0.325, 0.536] (104 of 104 runs; 200/200 resamples) |
| 5 | rule | two or more | 2 of 57 | 0.061 [0.000, 0.143] (51 of 51 runs; 200/200 resamples) |
| 5 | logistic | one team | 55 of 57 | 0.466 [0.352, 0.582] (104 of 104 runs; 200/200 resamples) |
| 5 | logistic | two or more | 2 of 57 | 0.092 [0.000, 0.205] (51 of 51 runs; 200/200 resamples) |
| 5 | boosted | one team | 55 of 57 | 0.477 [0.371, 0.591] (104 of 104 runs; 200/200 resamples) |
| 5 | boosted | two or more | 2 of 57 | 0.367 [0.184, 0.531] (51 of 51 runs; 200/200 resamples) |
| 10 | rule | one team | 91 of 100 | 0.581 [0.479, 0.683] (140 of 140 runs; 200/200 resamples) |
| 10 | rule | two or more | 9 of 100 | 0.222 [0.102, 0.343] (58 of 58 runs; 200/200 resamples) |
| 10 | logistic | one team | 91 of 100 | 0.623 [0.542, 0.712] (140 of 140 runs; 200/200 resamples) |
| 10 | logistic | two or more | 9 of 100 | 0.139 [0.057, 0.240] (58 of 58 runs; 200/200 resamples) |
| 10 | boosted | one team | 91 of 100 | 0.605 [0.494, 0.716] (140 of 140 runs; 200/200 resamples) |
| 10 | boosted | two or more | 9 of 100 | 0.286 [0.075, 0.527] (58 of 58 runs; 200/200 resamples) |
| 30 | rule | one team | 195 of 245 | 0.610 [0.517, 0.689] (244 of 244 runs; 200/200 resamples) |
| 30 | rule | two or more | 50 of 245 | 0.207 [0.143, 0.296] (99 of 99 runs; 200/200 resamples) |
| 30 | logistic | one team | 195 of 245 | 0.676 [0.604, 0.745] (244 of 244 runs; 200/200 resamples) |
| 30 | logistic | two or more | 50 of 245 | 0.261 [0.173, 0.367] (99 of 99 runs; 200/200 resamples) |
| 30 | boosted | one team | 195 of 245 | 0.548 [0.470, 0.627] (244 of 244 runs; 200/200 resamples) |
| 30 | boosted | two or more | 50 of 245 | 0.515 [0.405, 0.623] (99 of 99 runs; 200/200 resamples) |

## Matched on the number of sharing-like teams

| rate | detector | sharing-like teams K | relay test runs (positives) k | sharing test controls k | AUROC (matched) | population |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | rule | 1 | 48 | 55 | 0.423 [0.326, 0.535] (103 of 103 runs; 200/200 resamples) | test split |
| 5 | rule | 2 | 1 | 2 | undefined: 1 relay run | test split |
| 5 | rule | 3-or-more | 0 | 0 | undefined: 0 relay runs; 0 sharing controls | test split |
| 5 | logistic | 1 | 48 | 55 | 0.472 [0.364, 0.600] (103 of 103 runs; 200/200 resamples) | test split |
| 5 | logistic | 2 | 1 | 2 | undefined: 1 relay run | test split |
| 5 | logistic | 3-or-more | 0 | 0 | undefined: 0 relay runs; 0 sharing controls | test split |
| 5 | boosted | 1 | 48 | 55 | 0.484 [0.365, 0.590] (103 of 103 runs; 200/200 resamples) | test split |
| 5 | boosted | 2 | 1 | 2 | undefined: 1 relay run | test split |
| 5 | boosted | 3-or-more | 0 | 0 | undefined: 0 relay runs; 0 sharing controls | test split |
| 5 | rule | 1 | 153 | 165 | 0.472 [0.412, 0.531] (318 of 318 runs; 200/200 resamples) | pooled over all runs of the rate (fitting, calibration and test); rule only, legitimate only because the rule has no fitted parameters |
| 5 | rule | 2 | 9 | 5 | 0.500 [0.222, 0.801] (14 of 14 runs; 200/200 resamples) | pooled over all runs of the rate (fitting, calibration and test); rule only, legitimate only because the rule has no fitted parameters |
| 5 | rule | 3-or-more | 0 | 0 | undefined: 0 relay runs; 0 sharing controls | pooled over all runs of the rate (fitting, calibration and test); rule only, legitimate only because the rule has no fitted parameters |
| 10 | rule | 1 | 44 | 91 | 0.535 [0.445, 0.622] (135 of 135 runs; 200/200 resamples) | test split |
| 10 | rule | 2 | 5 | 9 | 0.778 [0.511, 0.967] (14 of 14 runs; 200/200 resamples) | test split |
| 10 | rule | 3-or-more | 0 | 0 | undefined: 0 relay runs; 0 sharing controls | test split |
| 10 | logistic | 1 | 44 | 91 | 0.600 [0.504, 0.681] (135 of 135 runs; 200/200 resamples) | test split |
| 10 | logistic | 2 | 5 | 9 | 0.433 [0.099, 0.823] (14 of 14 runs; 200/200 resamples) | test split |
| 10 | logistic | 3-or-more | 0 | 0 | undefined: 0 relay runs; 0 sharing controls | test split |
| 10 | boosted | 1 | 44 | 91 | 0.609 [0.513, 0.707] (135 of 135 runs; 200/200 resamples) | test split |
| 10 | boosted | 2 | 5 | 9 | 0.256 [0.000, 0.578] (14 of 14 runs; 200/200 resamples) | test split |
| 10 | boosted | 3-or-more | 0 | 0 | undefined: 0 relay runs; 0 sharing controls | test split |
| 10 | rule | 1 | 149 | 293 | 0.463 [0.403, 0.522] (442 of 442 runs; 200/200 resamples) | pooled over all runs of the rate (fitting, calibration and test); rule only, legitimate only because the rule has no fitted parameters |
| 10 | rule | 2 | 12 | 19 | 0.518 [0.324, 0.715] (31 of 31 runs; 200/200 resamples) | pooled over all runs of the rate (fitting, calibration and test); rule only, legitimate only because the rule has no fitted parameters |
| 10 | rule | 3-or-more | 1 | 0 | undefined: 1 relay run; 0 sharing controls | pooled over all runs of the rate (fitting, calibration and test); rule only, legitimate only because the rule has no fitted parameters |
| 30 | rule | 1 | 33 | 195 | 0.499 [0.383, 0.612] (228 of 228 runs; 200/200 resamples) | test split |
| 30 | rule | 2 | 13 | 43 | 0.381 [0.199, 0.569] (56 of 56 runs; 200/200 resamples) | test split |
| 30 | rule | 3-or-more | 3 | 7 | 0.381 [0.000, 0.763] (10 of 10 runs; 200/200 resamples) | test split |
| 30 | logistic | 1 | 33 | 195 | 0.589 [0.480, 0.686] (228 of 228 runs; 200/200 resamples) | test split |
| 30 | logistic | 2 | 13 | 43 | 0.403 [0.240, 0.572] (56 of 56 runs; 200/200 resamples) | test split |
| 30 | logistic | 3-or-more | 3 | 7 | 0.429 [0.000, 0.763] (10 of 10 runs; 200/200 resamples) | test split |
| 30 | boosted | 1 | 33 | 195 | 0.527 [0.433, 0.613] (228 of 228 runs; 200/200 resamples) | test split |
| 30 | boosted | 2 | 13 | 43 | 0.594 [0.387, 0.793] (56 of 56 runs; 200/200 resamples) | test split |
| 30 | boosted | 3-or-more | 3 | 7 | 0.238 [0.000, 0.525] (10 of 10 runs; 200/200 resamples) | test split |
| 30 | rule | 1 | 115 | 622 | 0.491 [0.442, 0.542] (737 of 737 runs; 200/200 resamples) | pooled over all runs of the rate (fitting, calibration and test); rule only, legitimate only because the rule has no fitted parameters |
| 30 | rule | 2 | 42 | 136 | 0.477 [0.384, 0.571] (178 of 178 runs; 200/200 resamples) | pooled over all runs of the rate (fitting, calibration and test); rule only, legitimate only because the rule has no fitted parameters |
| 30 | rule | 3-or-more | 5 | 23 | 0.513 [0.222, 0.805] (28 of 28 runs; 200/200 resamples) | pooled over all runs of the rate (fitting, calibration and test); rule only, legitimate only because the rule has no fitted parameters |

The one-team and two-or-more rows above compare runs with different numbers of sharing-like teams; this table matches them.
Bootstrap keys: child_seed(config.seed, NAMESPACE, rate_index, REVISION, 4, detector_index, k_index) for test rows and child_seed(config.seed, NAMESPACE, rate_index, REVISION, 5, detector_index, k_index) for pooled rule rows; NAMESPACE = 91, REVISION = 2, detector_index = SEED_INDEX[method], k_index = 0/1/2 for K = 1/2/3-or-more; K counts the relay group as one sharing-like team.

## Recorded V1 run tables

```swarmtrace-sharing-sha256
path | sha256
sharing-sweep/rate-0/runs.csv.gz | 8ceb4d98d44422bb1ca8bb7e53f5c6b53d626fb02fd0debba587be6eb75a8ff3
sharing-sweep/rate-5/runs.csv.gz | d090e85815e85a0fa33c3d4bf789dafc60c723ca9e371e8c264ed406e544009a
sharing-sweep/rate-10/runs.csv.gz | 0ef2f5900d55a056f839d523ea4adbb6155f01b05d65bed6a876808c6b48b51f
sharing-sweep/rate-30/runs.csv.gz | cd733348be5dbc55cdda152449d719cdd0f02eefdbe3f64c44eb81c17a78e980
```
