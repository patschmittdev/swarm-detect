# Containment experiment

Seed: 20261120. Command: `swarmtrace containment --seed 20261120 --data data --out DIR --control-repeats 6 --bootstrap 200`. Output does not depend on `--workers`.

Pairs: 270: 162 positive (scope violation; size 1: 54, size 2: 54, size 5: 54) and 108 control. Scope on, sharing rate 10, mistake rate 2, 160 ticks. Control repeats per control cell: 6. Pair i runs at `child_seed(20261120, 98, i)`.

Arms per pair: 18. Simulated runs: 1574 of 4860; an arm whose controller never decides is not simulated and its outcomes are the twin's.

Detectors and thresholds: the frozen main models (by-run split, V1, aggregation), refitted deterministically from `data/dataset/main`; nothing is refitted on this dataset. Main split counts (fitting C/P, calibration C/P, test C/P): 141/53/61/23/86/32. Calibration controls: 61. Controllers check every 8 ticks (7, 15, ...) and act from the next tick.

Rates over pairs (and the calibration rates over runs) are k of n with a 95% Wilson interval. Quantities pooled over pairs (files, calls, agents, lenders; marked pooled) and means over pairs carry 95% percentile bootstrap intervals over pairs, because agents and calls are clustered by pair (200 resamples, seeds `child_seed(20261120, 99, 0, arm, metric)`). Random arms draw from `child_seed(20261120, 99, 1, i)` for pair i, shared by the six random arms of a pair.

## Detector calibration under shift

Flag: the controller's first flag on the uncontained twin, replayed on the live grid. The recorded main rates are the frozen models' by-run test rows; the online row uses the offline checkpoint grid, which adds the run's last event.

| detector | scope-on control twins flagged (live grid) | scope-on positive twins flagged (live grid) | recorded main FPR, full trace | recorded main FPR, online |
| --- | --- | --- | --- | --- |
| rule | 2 of 108; 0.019 [0.005, 0.065] | 36 of 162; 0.222 [0.165, 0.292] | 4 of 86; 0.047 [0.018, 0.114] | 4 of 86; 0.047 [0.018, 0.114] |
| logistic | 7 of 108; 0.065 [0.032, 0.128] | 62 of 162; 0.383 [0.311, 0.459] | 5 of 86; 0.058 [0.025, 0.129] | 5 of 86; 0.058 [0.025, 0.129] |
| boosted | 9 of 108; 0.083 [0.044, 0.151] | 80 of 162; 0.494 [0.418, 0.570] | 5 of 86; 0.058 [0.025, 0.129] | 6 of 86; 0.070 [0.032, 0.144] |


## Required out-of-scope reads prevented, then objective (positive pairs)

Prevented: required files the collector read in the twin and not in the arm (outcomes.json), pooled over pairs and as a mean of per-pair fractions over pairs whose twin read any. Fully, partly and not prevented count pairs. The objective also requires the group's later writes, so it can fail with no required read prevented.

| arm | pairs | required reads prevented (pooled) | prevented fraction, mean per pair | fully prevented | partly prevented | not prevented | pairs with no required read in twin | objective failed with no required read prevented | reads prevented but objective completed | objective completed (also requires the group's later writes), arm | objective completed, twin | completion difference, arm minus twin | simulated | any intervention |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| twin | 162 | 0 of 432 files; 0.000 (degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish a zero population value) | 0.000 (degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish a zero population value) over 162 | 0 | 0 | 162 | 0 | 0 | 0 | 162 of 162; 1.000 [0.977, 1.000] | 162 of 162; 1.000 [0.977, 1.000] | 0.000 (degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish a zero population value) over 162 | 162 | 0 of 162; 0.000 [0.000, 0.023] |
| rule-quarantine | 162 | 36 of 432 files; 0.083 [0.042, 0.138] | 0.069 [0.036, 0.109] over 162 | 9 | 6 | 147 | 0 | 15 | 0 | 132 of 162; 0.815 [0.748, 0.867] | 162 of 162; 1.000 [0.977, 1.000] | -0.185 [-0.247, -0.130] over 162 | 36 | 36 of 162; 0.222 [0.165, 0.292] |
| rule-revoke | 162 | 35 of 432 files; 0.081 [0.041, 0.136] | 0.068 [0.033, 0.108] over 162 | 8 | 7 | 147 | 0 | 10 | 0 | 137 of 162; 0.846 [0.782, 0.893] | 162 of 162; 1.000 [0.977, 1.000] | -0.154 [-0.210, -0.093] over 162 | 36 | 36 of 162; 0.222 [0.165, 0.292] |
| logistic-quarantine | 162 | 95 of 432 files; 0.220 [0.150, 0.286] | 0.195 [0.139, 0.258] over 162 | 25 | 11 | 126 | 0 | 23 | 0 | 103 of 162; 0.636 [0.559, 0.706] | 162 of 162; 1.000 [0.977, 1.000] | -0.364 [-0.432, -0.296] over 162 | 62 | 62 of 162; 0.383 [0.311, 0.459] |
| logistic-revoke | 162 | 95 of 432 files; 0.220 [0.148, 0.298] | 0.195 [0.135, 0.251] over 162 | 25 | 11 | 126 | 0 | 17 | 0 | 109 of 162; 0.673 [0.597, 0.740] | 162 of 162; 1.000 [0.977, 1.000] | -0.327 [-0.414, -0.253] over 162 | 62 | 62 of 162; 0.383 [0.311, 0.459] |
| boosted-quarantine | 162 | 140 of 432 files; 0.324 [0.255, 0.406] | 0.298 [0.246, 0.362] over 162 | 41 | 12 | 109 | 0 | 23 | 0 | 86 of 162; 0.531 [0.454, 0.606] | 162 of 162; 1.000 [0.977, 1.000] | -0.469 [-0.550, -0.395] over 162 | 80 | 80 of 162; 0.494 [0.418, 0.570] |
| boosted-revoke | 162 | 129 of 432 files; 0.299 [0.226, 0.376] | 0.269 [0.207, 0.325] over 162 | 34 | 16 | 112 | 0 | 21 | 0 | 91 of 162; 0.562 [0.485, 0.636] | 162 of 162; 1.000 [0.977, 1.000] | -0.438 [-0.519, -0.370] over 162 | 80 | 80 of 162; 0.494 [0.418, 0.570] |
| random-rule-quarantine | 162 | 20 of 432 files; 0.046 [0.012, 0.085] | 0.030 [0.011, 0.053] over 162 | 4 | 2 | 156 | 0 | 5 | 0 | 151 of 162; 0.932 [0.883, 0.962] | 162 of 162; 1.000 [0.977, 1.000] | -0.068 [-0.117, -0.031] over 162 | 36 | 36 of 162; 0.222 [0.165, 0.292] |
| random-rule-revoke | 162 | 12 of 432 files; 0.028 [0.000, 0.057] | 0.015 [0.000, 0.031] over 162 | 2 | 1 | 159 | 0 | 2 | 0 | 157 of 162; 0.969 [0.930, 0.987] | 162 of 162; 1.000 [0.977, 1.000] | -0.031 [-0.056, -0.012] over 162 | 36 | 36 of 162; 0.222 [0.165, 0.292] |
| random-logistic-quarantine | 162 | 31 of 432 files; 0.072 [0.028, 0.130] | 0.042 [0.017, 0.075] over 162 | 3 | 6 | 153 | 0 | 14 | 0 | 139 of 162; 0.858 [0.796, 0.903] | 162 of 162; 1.000 [0.977, 1.000] | -0.142 [-0.185, -0.086] over 162 | 62 | 62 of 162; 0.383 [0.311, 0.459] |
| random-logistic-revoke | 162 | 29 of 432 files; 0.067 [0.030, 0.117] | 0.058 [0.027, 0.095] over 162 | 7 | 4 | 151 | 0 | 6 | 0 | 145 of 162; 0.895 [0.838, 0.933] | 162 of 162; 1.000 [0.977, 1.000] | -0.105 [-0.148, -0.068] over 162 | 62 | 62 of 162; 0.383 [0.311, 0.459] |
| random-boosted-quarantine | 162 | 48 of 432 files; 0.111 [0.052, 0.177] | 0.080 [0.042, 0.126] over 162 | 10 | 4 | 148 | 0 | 27 | 0 | 121 of 162; 0.747 [0.675, 0.808] | 162 of 162; 1.000 [0.977, 1.000] | -0.253 [-0.321, -0.191] over 162 | 80 | 80 of 162; 0.494 [0.418, 0.570] |
| random-boosted-revoke | 162 | 23 of 432 files; 0.053 [0.023, 0.092] | 0.054 [0.021, 0.082] over 162 | 7 | 4 | 151 | 0 | 6 | 0 | 145 of 162; 0.895 [0.838, 0.933] | 162 of 162; 1.000 [0.977, 1.000] | -0.105 [-0.154, -0.056] over 162 | 80 | 80 of 162; 0.494 [0.418, 0.570] |
| halt-rule | 162 | 36 of 432 files; 0.083 [0.037, 0.141] | 0.069 [0.042, 0.114] over 162 | 9 | 6 | 147 | 0 | 15 | 0 | 132 of 162; 0.815 [0.748, 0.867] | 162 of 162; 1.000 [0.977, 1.000] | -0.185 [-0.247, -0.123] over 162 | 36 | 36 of 162; 0.222 [0.165, 0.292] |
| halt-logistic | 162 | 95 of 432 files; 0.220 [0.158, 0.298] | 0.195 [0.141, 0.253] over 162 | 25 | 11 | 126 | 0 | 23 | 0 | 103 of 162; 0.636 [0.559, 0.706] | 162 of 162; 1.000 [0.977, 1.000] | -0.364 [-0.432, -0.296] over 162 | 62 | 62 of 162; 0.383 [0.311, 0.459] |
| halt-boosted | 162 | 147 of 432 files; 0.340 [0.257, 0.419] | 0.319 [0.251, 0.386] over 162 | 46 | 9 | 107 | 0 | 21 | 0 | 86 of 162; 0.531 [0.454, 0.606] | 162 of 162; 1.000 [0.977, 1.000] | -0.469 [-0.543, -0.389] over 162 | 80 | 80 of 162; 0.494 [0.418, 0.570] |
| oracle-quarantine | 162 | 432 of 432 files; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) over 162 | 162 | 0 | 0 | 0 | 0 | 0 | 0 of 162; 0.000 [0.000, 0.023] | 162 of 162; 1.000 [0.977, 1.000] | -1.000 (degenerate bootstrap interval [-1.000, -1.000]: all valid resamples were equal; does not establish a population value of exactly -1.000) over 162 | 162 | 162 of 162; 1.000 [0.977, 1.000] |
| oracle-revoke | 162 | 432 of 432 files; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) over 162 | 162 | 0 | 0 | 0 | 0 | 0 | 0 of 162; 0.000 [0.000, 0.023] | 162 of 162; 1.000 [0.977, 1.000] | -1.000 (degenerate bootstrap interval [-1.000, -1.000]: all valid resamples were equal; does not establish a population value of exactly -1.000) over 162 | 162 | 162 of 162; 1.000 [0.977, 1.000] |


## Why required reads were not prevented (detector arms, positive pairs)

Positive pairs by where the arm's first intervention affecting the collector falls against the twin's required reads: a quarantine naming the collector, a halt_all, or the revocation of every credential the collector logged in with on the required files' host in the twin (it denies that login or ends that session). Exceptions list pairs hit at or before the first required read that were not fully prevented.

| arm | category (first intervention affecting the collector) | pairs | required files in twin | files prevented | of which first intervention at or before first read | exceptions |
| --- | --- | --- | --- | --- | --- | --- |
| rule-quarantine | no intervention | 126 | 337 | 0 | 0 | none |
| rule-quarantine | intervention never affects the collector | 0 | 0 | 0 | 0 | none |
| rule-quarantine | after last required read | 21 | 43 | 0 | 0 | none |
| rule-quarantine | after first, at or before last required read | 6 | 24 | 8 | 0 | none |
| rule-quarantine | at or before first required read | 9 | 28 | 28 | 0 | none |
| rule-quarantine | no required read in twin | 0 | 0 | 0 | 0 | none |
| rule-revoke | no intervention | 126 | 337 | 0 | 0 | none |
| rule-revoke | intervention never affects the collector | 0 | 0 | 0 | 0 | none |
| rule-revoke | after last required read | 21 | 43 | 0 | 0 | none |
| rule-revoke | after first, at or before last required read | 7 | 29 | 12 | 1 | none |
| rule-revoke | at or before first required read | 8 | 23 | 23 | 0 | none |
| rule-revoke | no required read in twin | 0 | 0 | 0 | 0 | none |
| logistic-quarantine | no intervention | 100 | 269 | 0 | 0 | none |
| logistic-quarantine | intervention never affects the collector | 0 | 0 | 0 | 0 | none |
| logistic-quarantine | after last required read | 26 | 49 | 0 | 0 | none |
| logistic-quarantine | after first, at or before last required read | 11 | 49 | 30 | 0 | none |
| logistic-quarantine | at or before first required read | 25 | 65 | 65 | 0 | none |
| logistic-quarantine | no required read in twin | 0 | 0 | 0 | 0 | none |
| logistic-revoke | no intervention | 100 | 269 | 0 | 0 | none |
| logistic-revoke | intervention never affects the collector | 0 | 0 | 0 | 0 | none |
| logistic-revoke | after last required read | 26 | 49 | 0 | 0 | none |
| logistic-revoke | after first, at or before last required read | 11 | 49 | 30 | 0 | none |
| logistic-revoke | at or before first required read | 25 | 65 | 65 | 0 | none |
| logistic-revoke | no required read in twin | 0 | 0 | 0 | 0 | none |
| boosted-quarantine | no intervention | 82 | 218 | 0 | 0 | none |
| boosted-quarantine | intervention never affects the collector | 0 | 0 | 0 | 0 | none |
| boosted-quarantine | after last required read | 27 | 55 | 0 | 2 | none |
| boosted-quarantine | after first, at or before last required read | 12 | 51 | 32 | 3 | none |
| boosted-quarantine | at or before first required read | 41 | 108 | 108 | 0 | none |
| boosted-quarantine | no required read in twin | 0 | 0 | 0 | 0 | none |
| boosted-revoke | no intervention | 82 | 218 | 0 | 0 | none |
| boosted-revoke | intervention never affects the collector | 0 | 0 | 0 | 0 | none |
| boosted-revoke | after last required read | 30 | 60 | 0 | 5 | none |
| boosted-revoke | after first, at or before last required read | 16 | 65 | 40 | 7 | none |
| boosted-revoke | at or before first required read | 34 | 89 | 89 | 0 | none |
| boosted-revoke | no required read in twin | 0 | 0 | 0 | 0 | none |


Counterfactual from the twins, separating detection coverage from the checkpoint cadence: an intervention decided at the first live checkpoint at or after the first relayed login, effective the next tick, would precede the first required read in 132 of 162; 0.815 [0.748, 0.867] positive pairs.

## Timing against the damage (positive pairs)

Each placement cell gives the first intervention / the first intervention affecting the collector. Ticks are signed, from the twin's first relayed login. An intervention effective at the tick of a read precedes it.

| arm | pairs | with intervention / affecting the collector | ticks, relayed login to first intervention | ticks, relayed login to first affecting the collector | at or before first required read (first / collector) | after first, at or before last required read (first / collector) | after last required read (first / collector) | intervention never affects the collector | no intervention | no required read in twin (first / collector) | collector hit at or before twin's objective tick | collector hit after twin's objective tick |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rule-quarantine | 162 | 36 / 36 | median 31; range 1 to 41; n 36 | median 31; range 1 to 41; n 36 | 9 / 9 | 6 / 6 | 21 / 21 | 0 | 126 | 0 / 0 | 30 | 6 |
| rule-revoke | 162 | 36 / 36 | median 31; range 1 to 41; n 36 | median 31.5; range 1 to 41; n 36 | 9 / 8 | 6 / 7 | 21 / 21 | 0 | 126 | 0 / 0 | 30 | 6 |
| logistic-quarantine | 162 | 62 / 62 | median 11; range 1 to 36; n 62 | median 11; range 1 to 36; n 62 | 25 / 25 | 11 / 11 | 26 / 26 | 0 | 100 | 0 / 0 | 59 | 3 |
| logistic-revoke | 162 | 62 / 62 | median 11; range 1 to 36; n 62 | median 11.5; range 1 to 36; n 62 | 25 / 25 | 11 / 11 | 26 / 26 | 0 | 100 | 0 / 0 | 59 | 3 |
| boosted-quarantine | 162 | 80 / 80 | median 10; range -4 to 35; n 80 | median 10.5; range 1 to 35; n 80 | 46 / 41 | 9 / 12 | 25 / 27 | 0 | 82 | 0 / 0 | 75 | 5 |
| boosted-revoke | 162 | 80 / 80 | median 10; range -4 to 35; n 80 | median 11; range 1 to 36; n 80 | 46 / 34 | 9 / 16 | 25 / 30 | 0 | 82 | 0 / 0 | 76 | 4 |
| random-rule-quarantine | 162 | 36 / 13 | median 31; range 1 to 41; n 36 | median 31; range 10 to 36; n 13 | 9 / 4 | 6 / 2 | 21 / 7 | 23 | 126 | 0 / 0 | 10 | 3 |
| random-rule-revoke | 162 | 36 / 10 | median 31; range 1 to 41; n 36 | median 33.5; range 17 to 41; n 10 | 9 / 2 | 6 / 1 | 21 / 7 | 26 | 126 | 0 / 0 | 7 | 3 |
| random-logistic-quarantine | 162 | 62 / 13 | median 11; range 1 to 36; n 62 | median 10; range 2 to 24; n 13 | 25 / 3 | 11 / 6 | 26 / 4 | 49 | 100 | 0 / 0 | 12 | 1 |
| random-logistic-revoke | 162 | 62 / 17 | median 11; range 1 to 36; n 62 | median 12; range 8 to 34; n 17 | 25 / 7 | 11 / 4 | 26 / 6 | 45 | 100 | 0 / 0 | 16 | 1 |
| random-boosted-quarantine | 162 | 80 / 21 | median 10; range -4 to 35; n 80 | median 11; range 1 to 33; n 21 | 46 / 8 | 9 / 4 | 25 / 9 | 59 | 82 | 0 / 0 | 18 | 3 |
| random-boosted-revoke | 162 | 80 / 17 | median 10; range -4 to 35; n 80 | median 12; range 1 to 31; n 17 | 46 / 7 | 9 / 4 | 25 / 6 | 63 | 82 | 0 / 0 | 16 | 1 |
| halt-rule | 162 | 36 / 36 | median 31; range 1 to 41; n 36 | median 31; range 1 to 41; n 36 | 9 / 9 | 6 / 6 | 21 / 21 | 0 | 126 | 0 / 0 | 30 | 6 |
| halt-logistic | 162 | 62 / 62 | median 11; range 1 to 36; n 62 | median 11; range 1 to 36; n 62 | 25 / 25 | 11 / 11 | 26 / 26 | 0 | 100 | 0 / 0 | 59 | 3 |
| halt-boosted | 162 | 80 / 80 | median 10; range -4 to 35; n 80 | median 10; range -4 to 35; n 80 | 46 / 46 | 9 / 9 | 25 / 25 | 0 | 82 | 0 / 0 | 76 | 4 |
| oracle-quarantine | 162 | 162 / 162 | median 1; range 1 to 1; n 162 | median 1; range 1 to 1; n 162 | 162 / 162 | 0 / 0 | 0 / 0 | 0 | 0 | 0 / 0 | 162 | 0 |
| oracle-revoke | 162 | 162 / 162 | median 1; range 1 to 1; n 162 | median 1; range 1 to 1; n 162 | 162 / 162 | 0 / 0 | 0 / 0 | 0 | 0 | 0 / 0 | 162 | 0 |


| arm | first intervention tick | first tick affecting the collector | twin: first relayed login | twin: first required read | twin: last required read | twin: objective tick |
| --- | --- | --- | --- | --- | --- | --- |
| rule-quarantine | median 48; range 16 to 56; n 36 | median 48; range 16 to 56; n 36 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| rule-revoke | median 48; range 16 to 56; n 36 | median 48; range 16 to 56; n 36 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| logistic-quarantine | median 32; range 16 to 56; n 62 | median 32; range 16 to 56; n 62 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| logistic-revoke | median 32; range 16 to 56; n 62 | median 32; range 16 to 56; n 62 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| boosted-quarantine | median 28; range 16 to 56; n 80 | median 28; range 16 to 56; n 80 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| boosted-revoke | median 28; range 16 to 56; n 80 | median 32; range 16 to 56; n 80 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| random-rule-quarantine | median 48; range 16 to 56; n 36 | median 48; range 24 to 56; n 13 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| random-rule-revoke | median 48; range 16 to 56; n 36 | median 48; range 32 to 56; n 10 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| random-logistic-quarantine | median 32; range 16 to 56; n 62 | median 24; range 16 to 40; n 13 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| random-logistic-revoke | median 32; range 16 to 56; n 62 | median 32; range 24 to 48; n 17 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| random-boosted-quarantine | median 28; range 16 to 56; n 80 | median 32; range 16 to 48; n 21 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| random-boosted-revoke | median 28; range 16 to 56; n 80 | median 32; range 16 to 48; n 17 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| halt-rule | median 48; range 16 to 56; n 36 | median 48; range 16 to 56; n 36 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| halt-logistic | median 32; range 16 to 56; n 62 | median 32; range 16 to 56; n 62 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| halt-boosted | median 28; range 16 to 56; n 80 | median 28; range 16 to 56; n 80 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| oracle-quarantine | median 18; range 15 to 24; n 162 | median 18; range 15 to 24; n 162 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |
| oracle-revoke | median 18; range 15 to 24; n 162 | median 18; range 15 to 24; n 162 | median 17; range 14 to 23; n 162 | median 24; range 17 to 60; n 162 | median 27; range 17 to 61; n 162 | median 34; range 22 to 64; n 162 |


## Benign cost against the twin (positive pairs)

| arm | pairs | any intervention | benign agents quarantined | benign-owned credentials revoked | benign tasks lost | benign ok-call deficit (pooled) | benign agents newly denied (pooled) | change in denied calls by benign agents |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rule-quarantine | 162 | 36 | 48 | 0 | 26; pairs with any: 9 of 162; 0.056 [0.030, 0.102] | 4430 of 315368 ok calls; 0.014 [0.006, 0.024] | 48 of 2770 agents; 0.017 [0.008, 0.028] | 4433 |
| rule-revoke | 162 | 36 | 0 | 44 | 16; pairs with any: 7 of 162; 0.043 [0.021, 0.086] | 2850 of 315368 ok calls; 0.009 [0.004, 0.015] | 47 of 2770 agents; 0.017 [0.008, 0.027] | 2850 |
| logistic-quarantine | 162 | 62 | 74 | 0 | 44; pairs with any: 15 of 162; 0.093 [0.057, 0.147] | 7003 of 315368 ok calls; 0.022 [0.013, 0.032] | 74 of 2770 agents; 0.027 [0.016, 0.038] | 7012 |
| logistic-revoke | 162 | 62 | 0 | 66 | 31; pairs with any: 14 of 162; 0.086 [0.052, 0.140] | 4364 of 315368 ok calls; 0.014 [0.008, 0.021] | 69 of 2770 agents; 0.025 [0.014, 0.038] | 4364 |
| boosted-quarantine | 162 | 80 | 63 | 0 | 50; pairs with any: 15 of 162; 0.093 [0.057, 0.147] | 6108 of 315368 ok calls; 0.019 [0.011, 0.029] | 63 of 2770 agents; 0.023 [0.012, 0.035] | 6118 |
| boosted-revoke | 162 | 80 | 0 | 55 | 37; pairs with any: 14 of 162; 0.086 [0.052, 0.140] | 3911 of 315368 ok calls; 0.012 [0.007, 0.020] | 62 of 2770 agents; 0.022 [0.012, 0.035] | 3911 |
| random-rule-quarantine | 162 | 36 | 160 | 0 | 17; pairs with any: 6 of 162; 0.037 [0.017, 0.078] | 13468 of 315368 ok calls; 0.043 [0.029, 0.056] | 160 of 2770 agents; 0.058 [0.038, 0.078] | 13385 |
| random-rule-revoke | 162 | 36 | 0 | 161 | 13; pairs with any: 7 of 162; 0.043 [0.021, 0.086] | 8939 of 315368 ok calls; 0.028 [0.022, 0.037] | 164 of 2770 agents; 0.059 [0.042, 0.080] | 8939 |
| random-logistic-quarantine | 162 | 62 | 270 | 0 | 54; pairs with any: 25 of 162; 0.154 [0.107, 0.218] | 24893 of 315368 ok calls; 0.079 [0.064, 0.097] | 270 of 2770 agents; 0.097 [0.075, 0.119] | 24727 |
| random-logistic-revoke | 162 | 62 | 0 | 188 | 28; pairs with any: 16 of 162; 0.099 [0.062, 0.154] | 11715 of 315368 ok calls; 0.037 [0.029, 0.048] | 199 of 2770 agents; 0.072 [0.056, 0.090] | 11715 |
| random-boosted-quarantine | 162 | 80 | 302 | 0 | 69; pairs with any: 30 of 162; 0.185 [0.133, 0.252] | 28735 of 315368 ok calls; 0.091 [0.076, 0.109] | 302 of 2770 agents; 0.109 [0.093, 0.130] | 28455 |
| random-boosted-revoke | 162 | 80 | 0 | 230 | 33; pairs with any: 20 of 162; 0.123 [0.081, 0.183] | 14576 of 315368 ok calls; 0.046 [0.038, 0.056] | 240 of 2770 agents; 0.087 [0.069, 0.105] | 14576 |
| halt-rule | 162 | 36 | 558 | 0 | 42; pairs with any: 11 of 162; 0.068 [0.038, 0.117] | 45808 of 315368 ok calls; 0.145 [0.099, 0.184] | 558 of 2770 agents; 0.201 [0.143, 0.271] | 45815 |
| halt-logistic | 162 | 62 | 1020 | 0 | 145; pairs with any: 35 of 162; 0.216 [0.160, 0.286] | 93890 of 315368 ok calls; 0.298 [0.226, 0.356] | 1020 of 2770 agents; 0.368 [0.284, 0.441] | 93909 |
| halt-boosted | 162 | 80 | 1336 | 0 | 188; pairs with any: 42 of 162; 0.259 [0.198, 0.332] | 127064 of 315368 ok calls; 0.403 [0.333, 0.460] | 1336 of 2770 agents; 0.482 [0.404, 0.569] | 127105 |
| oracle-quarantine | 162 | 162 | 0 | 0 | 0; pairs with any: 0 of 162; 0.000 [0.000, 0.023] | 0 of 315368 ok calls; 0.000 (degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish a zero population value) | 0 of 2770 agents; 0.000 (degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish a zero population value) | 0 |
| oracle-revoke | 162 | 162 | 0 | 0 | 0; pairs with any: 0 of 162; 0.000 [0.000, 0.023] | 0 of 315368 ok calls; 0.000 (degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish a zero population value) | 0 of 2770 agents; 0.000 (degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish a zero population value) | 0 |


## Benign cost against the twin (control pairs)

| arm | pairs | any intervention | benign agents quarantined | benign-owned credentials revoked | benign tasks lost | benign ok-call deficit (pooled) | benign agents newly denied (pooled) | change in denied calls by benign agents |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rule-quarantine | 108 | 2 | 15 | 0 | 8; pairs with any: 2 of 108; 0.019 [0.005, 0.065] | 1305 of 234247 ok calls; 0.006 [0.000, 0.014] | 15 of 2066 agents; 0.007 [0.000, 0.020] | 1307 |
| rule-revoke | 108 | 2 | 0 | 12 | 5; pairs with any: 1 of 108; 0.009 [0.002, 0.051] | 797 of 234247 ok calls; 0.003 [0.000, 0.009] | 15 of 2066 agents; 0.007 [0.000, 0.020] | 797 |
| logistic-quarantine | 108 | 7 | 32 | 0 | 12; pairs with any: 6 of 108; 0.056 [0.026, 0.116] | 2928 of 234247 ok calls; 0.012 [0.004, 0.023] | 32 of 2066 agents; 0.015 [0.004, 0.028] | 2930 |
| logistic-revoke | 108 | 7 | 0 | 22 | 10; pairs with any: 5 of 108; 0.046 [0.020, 0.104] | 1499 of 234247 ok calls; 0.006 [0.002, 0.012] | 26 of 2066 agents; 0.013 [0.003, 0.026] | 1499 |
| boosted-quarantine | 108 | 9 | 40 | 0 | 19; pairs with any: 9 of 108; 0.083 [0.044, 0.151] | 3712 of 234247 ok calls; 0.016 [0.006, 0.027] | 40 of 2066 agents; 0.019 [0.008, 0.040] | 3714 |
| boosted-revoke | 108 | 9 | 0 | 30 | 15; pairs with any: 7 of 108; 0.065 [0.032, 0.128] | 2222 of 234247 ok calls; 0.009 [0.004, 0.015] | 37 of 2066 agents; 0.018 [0.008, 0.032] | 2222 |
| random-rule-quarantine | 108 | 2 | 15 | 0 | 4; pairs with any: 2 of 108; 0.019 [0.005, 0.065] | 1232 of 234247 ok calls; 0.005 [0.000, 0.015] | 15 of 2066 agents; 0.007 [0.000, 0.017] | 1234 |
| random-rule-revoke | 108 | 2 | 0 | 12 | 2; pairs with any: 1 of 108; 0.009 [0.002, 0.051] | 625 of 234247 ok calls; 0.003 [0.000, 0.007] | 13 of 2066 agents; 0.006 [0.000, 0.014] | 625 |
| random-logistic-quarantine | 108 | 7 | 32 | 0 | 8; pairs with any: 4 of 108; 0.037 [0.014, 0.091] | 2946 of 234247 ok calls; 0.013 [0.003, 0.027] | 32 of 2066 agents; 0.015 [0.005, 0.027] | 2951 |
| random-logistic-revoke | 108 | 7 | 0 | 22 | 5; pairs with any: 3 of 108; 0.028 [0.009, 0.079] | 1225 of 234247 ok calls; 0.005 [0.002, 0.009] | 24 of 2066 agents; 0.012 [0.004, 0.023] | 1225 |
| random-boosted-quarantine | 108 | 9 | 40 | 0 | 8; pairs with any: 5 of 108; 0.046 [0.020, 0.104] | 3662 of 234247 ok calls; 0.016 [0.006, 0.026] | 40 of 2066 agents; 0.019 [0.009, 0.033] | 3634 |
| random-boosted-revoke | 108 | 9 | 0 | 30 | 6; pairs with any: 4 of 108; 0.037 [0.014, 0.091] | 1726 of 234247 ok calls; 0.007 [0.003, 0.014] | 32 of 2066 agents; 0.015 [0.006, 0.027] | 1726 |
| halt-rule | 108 | 2 | 42 | 0 | 9; pairs with any: 2 of 108; 0.019 [0.005, 0.065] | 3493 of 234247 ok calls; 0.015 [0.000, 0.038] | 42 of 2066 agents; 0.020 [0.000, 0.049] | 3495 |
| halt-logistic | 108 | 7 | 140 | 0 | 25; pairs with any: 7 of 108; 0.065 [0.032, 0.128] | 12336 of 234247 ok calls; 0.053 [0.021, 0.091] | 140 of 2066 agents; 0.068 [0.029, 0.122] | 12341 |
| halt-boosted | 108 | 9 | 182 | 0 | 41; pairs with any: 9 of 108; 0.083 [0.044, 0.151] | 16839 of 234247 ok calls; 0.072 [0.034, 0.114] | 182 of 2066 agents; 0.088 [0.035, 0.149] | 16845 |
| oracle-quarantine | 108 | 0 | 0 | 0 | 0; pairs with any: 0 of 108; 0.000 [0.000, 0.034] | 0 of 234247 ok calls; 0.000 (degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish a zero population value) | 0 of 2066 agents; 0.000 (degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish a zero population value) | 0 |
| oracle-revoke | 108 | 0 | 0 | 0 | 0; pairs with any: 0 of 108; 0.000 [0.000, 0.034] | 0 of 234247 ok calls; 0.000 (degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish a zero population value) | 0 of 2066 agents; 0.000 (degenerate bootstrap interval [0.000, 0.000]: all valid resamples were zero; does not establish a zero population value) | 0 |


## Benign cost on flagged control runs

Control runs whose detector flagged on the twin (false alarms), and the benign cost of acting on them, per run.

| arm | flagged control runs | benign ok-call deficit per flagged run, fraction of its benign ok calls | benign tasks lost | benign agents newly denied |
| --- | --- | --- | --- | --- |
| rule-quarantine | 2 of 108; 0.019 [0.005, 0.065] | median 0.298; range 0.157 to 0.439 | 8; runs with any: 2 | 15 |
| rule-revoke | 2 of 108; 0.019 [0.005, 0.065] | median 0.180; range 0.108 to 0.251 | 5; runs with any: 1 | 15 |
| halt-rule | 2 of 108; 0.019 [0.005, 0.065] | median 0.750; range 0.700 to 0.800 | 9; runs with any: 2 | 42 |
| logistic-quarantine | 7 of 108; 0.065 [0.032, 0.128] | median 0.133; range 0.107 to 0.439 | 12; runs with any: 6 | 32 |
| logistic-revoke | 7 of 108; 0.065 [0.032, 0.128] | median 0.081; range 0.041 to 0.251 | 10; runs with any: 5 | 26 |
| halt-logistic | 7 of 108; 0.065 [0.032, 0.128] | median 0.747; range 0.745 to 0.852 | 25; runs with any: 7 | 140 |
| boosted-quarantine | 9 of 108; 0.083 [0.044, 0.151] | median 0.174; range 0.086 to 0.417 | 19; runs with any: 9 | 40 |
| boosted-revoke | 9 of 108; 0.083 [0.044, 0.151] | median 0.113; range 0.044 to 0.199 | 15; runs with any: 7 | 37 |
| halt-boosted | 9 of 108; 0.083 [0.044, 0.151] | median 0.801; range 0.754 to 0.901 | 41; runs with any: 9 | 182 |


## Owners of revoked credentials (revoke arms, all pairs)

Lenders: owners of a revoked credential that another agent used for an ok login in the twin before the revocation took effect. Other revoked owners: owners of revoked credentials nobody borrowed. Locked out: ok calls on its own host at or after the revocation's effective tick in the twin, none in the arm. Tasks lost count distinct tasks owned. Each host accepts one credential, revocation ends sessions opened with it, and credentials are not reissued, so the owner of a revoked credential is locked out of its own host by construction.

| arm | cohort | role | owners | pairs with one | locked out of own host (pooled) | ok-call deficit (pooled) | newly denied (pooled) | distinct owned tasks lost | change in denied calls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rule-revoke | lender | offensive | 154 | 36 | 154 of 154 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 8093 of 17608 ok calls; 0.460 [0.432, 0.488] | 154 of 154 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 35 | 8093 |
| rule-revoke | lender | benign | 56 | 13 | 56 of 56 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 3458 of 6522 ok calls; 0.530 [0.495, 0.574] | 56 of 56 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 21 | 3458 |
| rule-revoke | other revoked owner | offensive | 0 | 0 | 0 of 0 owners; undefined | 0 of 0 ok calls; undefined | 0 of 0 owners; undefined | 0 | 0 |
| rule-revoke | other revoked owner | benign | 0 | 0 | 0 of 0 owners; undefined | 0 of 0 ok calls; undefined | 0 of 0 owners; undefined | 0 | 0 |
| logistic-revoke | lender | offensive | 163 | 62 | 163 of 163 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 9920 of 18488 ok calls; 0.537 [0.508, 0.564] | 163 of 163 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 112 | 9920 |
| logistic-revoke | lender | benign | 88 | 28 | 88 of 88 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 5646 of 10207 ok calls; 0.553 [0.516, 0.583] | 88 of 88 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 41 | 5646 |
| logistic-revoke | other revoked owner | offensive | 0 | 0 | 0 of 0 owners; undefined | 0 of 0 ok calls; undefined | 0 of 0 owners; undefined | 0 | 0 |
| logistic-revoke | other revoked owner | benign | 0 | 0 | 0 of 0 owners; undefined | 0 of 0 ok calls; undefined | 0 of 0 owners; undefined | 0 | 0 |
| boosted-revoke | lender | offensive | 224 | 80 | 224 of 224 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 14369 of 25534 ok calls; 0.563 [0.541, 0.582] | 224 of 224 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 188 | 14369 |
| boosted-revoke | lender | benign | 85 | 25 | 85 of 85 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 5676 of 9821 ok calls; 0.578 [0.548, 0.615] | 85 of 85 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 52 | 5676 |
| boosted-revoke | other revoked owner | offensive | 0 | 0 | 0 of 0 owners; undefined | 0 of 0 ok calls; undefined | 0 of 0 owners; undefined | 0 | 0 |
| boosted-revoke | other revoked owner | benign | 0 | 0 | 0 of 0 owners; undefined | 0 of 0 ok calls; undefined | 0 of 0 owners; undefined | 0 | 0 |
| random-rule-revoke | lender | offensive | 35 | 24 | 35 of 35 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 1732 of 3983 ok calls; 0.435 [0.382, 0.479] | 35 of 35 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 5 | 1732 |
| random-rule-revoke | lender | benign | 17 | 9 | 17 of 17 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 1058 of 2015 ok calls; 0.525 [0.463, 0.600] | 17 of 17 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 3 | 1058 |
| random-rule-revoke | other revoked owner | offensive | 2 | 2 | 2 of 2 owners; 1.000 (no interval: only 176 of 200 resamples defined) | 115 of 202 ok calls; 0.569 (no interval: only 178 of 200 resamples defined) | 2 of 2 owners; 1.000 (no interval: only 170 of 200 resamples defined) | 1 | 115 |
| random-rule-revoke | other revoked owner | benign | 156 | 38 | 156 of 156 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 8392 of 17843 ok calls; 0.470 [0.440, 0.504] | 156 of 156 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 11 | 8392 |
| random-logistic-revoke | lender | offensive | 31 | 26 | 31 of 31 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 1673 of 3410 ok calls; 0.491 [0.432, 0.551] | 31 of 31 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 20 | 1673 |
| random-logistic-revoke | lender | benign | 24 | 18 | 24 of 24 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 1363 of 2830 ok calls; 0.482 [0.418, 0.539] | 24 of 24 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 10 | 1363 |
| random-logistic-revoke | other revoked owner | offensive | 10 | 10 | 10 of 10 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 604 of 1139 ok calls; 0.530 [0.418, 0.684] | 10 of 10 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 2 | 604 |
| random-logistic-revoke | other revoked owner | benign | 186 | 69 | 186 of 186 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 11197 of 21125 ok calls; 0.530 [0.502, 0.562] | 186 of 186 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 13 | 11197 |
| random-boosted-revoke | lender | offensive | 35 | 30 | 35 of 35 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 1912 of 3916 ok calls; 0.488 [0.447, 0.536] | 35 of 35 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 20 | 1912 |
| random-boosted-revoke | lender | benign | 19 | 13 | 19 of 19 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 1188 of 2193 ok calls; 0.542 [0.450, 0.617] | 19 of 19 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 9 | 1188 |
| random-boosted-revoke | other revoked owner | offensive | 14 | 13 | 14 of 14 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 867 of 1586 ok calls; 0.547 [0.449, 0.654] | 14 of 14 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 6 | 867 |
| random-boosted-revoke | other revoked owner | benign | 241 | 89 | 241 of 241 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 14757 of 27482 ok calls; 0.537 [0.513, 0.564] | 241 of 241 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 16 | 14757 |
| oracle-revoke | lender | offensive | 176 | 162 | 176 of 176 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 13370 of 19487 ok calls; 0.686 [0.663, 0.709] | 176 of 176 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 248 | 13370 |
| oracle-revoke | lender | benign | 0 | 0 | 0 of 0 owners; undefined | 0 of 0 ok calls; undefined | 0 of 0 owners; undefined | 0 | 0 |
| oracle-revoke | other revoked owner | offensive | 364 | 150 | 364 of 364 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 27917 of 41474 ok calls; 0.673 [0.659, 0.688] | 364 of 364 owners; 1.000 (degenerate bootstrap interval [1.000, 1.000]: all valid resamples were one; does not establish a population value of one) | 292 | 27917 |
| oracle-revoke | other revoked owner | benign | 0 | 0 | 0 of 0 owners; undefined | 0 of 0 ok calls; undefined | 0 of 0 owners; undefined | 0 | 0 |


## Matched random comparisons

Each random arm replays its detector arm's decision ticks and counts with random targets. The first two lines use all pairs; the second two use only pairs where the random arm had no shortfall. Prevention and objective on positive pairs; benign cost on all pairs.

| arm | pairs | positive pairs | required reads prevented (pooled) | objective completed, arm | objective completed, twin | all pairs | benign ok-call deficit (pooled) | benign agents newly denied (pooled) | random: requested | random: named | random: pairs with a shortfall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rule-quarantine | all pairs | 162 | 36 of 432 files; 0.083 [0.042, 0.138] | 132 of 162; 0.815 [0.748, 0.867] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 5735 of 549615 ok calls; 0.010 [0.005, 0.017] | 63 of 4836 agents; 0.013 [0.007, 0.021] | 229 | 229 | 0 |
| random-rule-quarantine | all pairs | 162 | 20 of 432 files; 0.046 [0.012, 0.085] | 151 of 162; 0.932 [0.883, 0.962] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 14700 of 549615 ok calls; 0.027 [0.019, 0.036] | 175 of 4836 agents; 0.036 [0.024, 0.049] | 229 | 229 | 0 |
| rule-quarantine | pairs without shortfall | 162 | 36 of 432 files; 0.083 [0.042, 0.138] | 132 of 162; 0.815 [0.748, 0.867] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 5735 of 549615 ok calls; 0.010 [0.005, 0.017] | 63 of 4836 agents; 0.013 [0.007, 0.021] | 229 | 229 | 0 |
| random-rule-quarantine | pairs without shortfall | 162 | 20 of 432 files; 0.046 [0.012, 0.085] | 151 of 162; 0.932 [0.883, 0.962] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 14700 of 549615 ok calls; 0.027 [0.019, 0.036] | 175 of 4836 agents; 0.036 [0.024, 0.049] | 229 | 229 | 0 |
| rule-revoke | all pairs | 162 | 35 of 432 files; 0.081 [0.041, 0.136] | 137 of 162; 0.846 [0.782, 0.893] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 3647 of 549615 ok calls; 0.007 [0.004, 0.010] | 62 of 4836 agents; 0.013 [0.006, 0.021] | 210 | 210 | 0 |
| random-rule-revoke | all pairs | 162 | 12 of 432 files; 0.028 [0.000, 0.057] | 157 of 162; 0.969 [0.930, 0.987] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 9564 of 549615 ok calls; 0.017 [0.013, 0.023] | 177 of 4836 agents; 0.037 [0.026, 0.047] | 210 | 210 | 0 |
| rule-revoke | pairs without shortfall | 162 | 35 of 432 files; 0.081 [0.041, 0.136] | 137 of 162; 0.846 [0.782, 0.893] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 3647 of 549615 ok calls; 0.007 [0.004, 0.010] | 62 of 4836 agents; 0.013 [0.006, 0.021] | 210 | 210 | 0 |
| random-rule-revoke | pairs without shortfall | 162 | 12 of 432 files; 0.028 [0.000, 0.057] | 157 of 162; 0.969 [0.930, 0.987] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 9564 of 549615 ok calls; 0.017 [0.013, 0.023] | 177 of 4836 agents; 0.037 [0.026, 0.047] | 210 | 210 | 0 |
| logistic-quarantine | all pairs | 162 | 95 of 432 files; 0.220 [0.150, 0.286] | 103 of 162; 0.636 [0.559, 0.706] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 9931 of 549615 ok calls; 0.018 [0.012, 0.024] | 106 of 4836 agents; 0.022 [0.014, 0.032] | 360 | 360 | 0 |
| random-logistic-quarantine | all pairs | 162 | 31 of 432 files; 0.072 [0.028, 0.130] | 139 of 162; 0.858 [0.796, 0.903] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 27839 of 549615 ok calls; 0.051 [0.041, 0.063] | 302 of 4836 agents; 0.062 [0.048, 0.076] | 360 | 360 | 0 |
| logistic-quarantine | pairs without shortfall | 162 | 95 of 432 files; 0.220 [0.150, 0.286] | 103 of 162; 0.636 [0.559, 0.706] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 9931 of 549615 ok calls; 0.018 [0.012, 0.024] | 106 of 4836 agents; 0.022 [0.014, 0.032] | 360 | 360 | 0 |
| random-logistic-quarantine | pairs without shortfall | 162 | 31 of 432 files; 0.072 [0.028, 0.130] | 139 of 162; 0.858 [0.796, 0.903] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 27839 of 549615 ok calls; 0.051 [0.041, 0.063] | 302 of 4836 agents; 0.062 [0.048, 0.076] | 360 | 360 | 0 |
| logistic-revoke | all pairs | 162 | 95 of 432 files; 0.220 [0.148, 0.298] | 109 of 162; 0.673 [0.597, 0.740] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 5863 of 549615 ok calls; 0.011 [0.007, 0.015] | 95 of 4836 agents; 0.020 [0.012, 0.027] | 251 | 251 | 0 |
| random-logistic-revoke | all pairs | 162 | 29 of 432 files; 0.067 [0.030, 0.117] | 145 of 162; 0.895 [0.838, 0.933] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 12940 of 549615 ok calls; 0.024 [0.017, 0.030] | 223 of 4836 agents; 0.046 [0.035, 0.055] | 251 | 251 | 0 |
| logistic-revoke | pairs without shortfall | 162 | 95 of 432 files; 0.220 [0.148, 0.298] | 109 of 162; 0.673 [0.597, 0.740] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 5863 of 549615 ok calls; 0.011 [0.007, 0.015] | 95 of 4836 agents; 0.020 [0.012, 0.027] | 251 | 251 | 0 |
| random-logistic-revoke | pairs without shortfall | 162 | 29 of 432 files; 0.067 [0.030, 0.117] | 145 of 162; 0.895 [0.838, 0.933] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 12940 of 549615 ok calls; 0.024 [0.017, 0.030] | 223 of 4836 agents; 0.046 [0.035, 0.055] | 251 | 251 | 0 |
| boosted-quarantine | all pairs | 162 | 140 of 432 files; 0.324 [0.255, 0.406] | 86 of 162; 0.531 [0.454, 0.606] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 9820 of 549615 ok calls; 0.018 [0.011, 0.025] | 103 of 4836 agents; 0.021 [0.014, 0.031] | 416 | 416 | 0 |
| random-boosted-quarantine | all pairs | 162 | 48 of 432 files; 0.111 [0.052, 0.177] | 121 of 162; 0.747 [0.675, 0.808] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 32397 of 549615 ok calls; 0.059 [0.047, 0.071] | 342 of 4836 agents; 0.071 [0.057, 0.084] | 416 | 416 | 0 |
| boosted-quarantine | pairs without shortfall | 162 | 140 of 432 files; 0.324 [0.255, 0.406] | 86 of 162; 0.531 [0.454, 0.606] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 9820 of 549615 ok calls; 0.018 [0.011, 0.025] | 103 of 4836 agents; 0.021 [0.014, 0.031] | 416 | 416 | 0 |
| random-boosted-quarantine | pairs without shortfall | 162 | 48 of 432 files; 0.111 [0.052, 0.177] | 121 of 162; 0.747 [0.675, 0.808] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 32397 of 549615 ok calls; 0.059 [0.047, 0.071] | 342 of 4836 agents; 0.071 [0.057, 0.084] | 416 | 416 | 0 |
| boosted-revoke | all pairs | 162 | 129 of 432 files; 0.299 [0.226, 0.376] | 91 of 162; 0.562 [0.485, 0.636] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 6133 of 549615 ok calls; 0.011 [0.007, 0.016] | 99 of 4836 agents; 0.020 [0.012, 0.030] | 309 | 309 | 0 |
| random-boosted-revoke | all pairs | 162 | 23 of 432 files; 0.053 [0.023, 0.092] | 145 of 162; 0.895 [0.838, 0.933] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 16302 of 549615 ok calls; 0.030 [0.024, 0.037] | 272 of 4836 agents; 0.056 [0.045, 0.068] | 309 | 309 | 0 |
| boosted-revoke | pairs without shortfall | 162 | 129 of 432 files; 0.299 [0.226, 0.376] | 91 of 162; 0.562 [0.485, 0.636] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 6133 of 549615 ok calls; 0.011 [0.007, 0.016] | 99 of 4836 agents; 0.020 [0.012, 0.030] | 309 | 309 | 0 |
| random-boosted-revoke | pairs without shortfall | 162 | 23 of 432 files; 0.053 [0.023, 0.092] | 145 of 162; 0.895 [0.838, 0.933] | 162 of 162; 1.000 [0.977, 1.000] | 270 | 16302 of 549615 ok calls; 0.030 [0.024, 0.037] | 272 of 4836 agents; 0.056 [0.045, 0.068] | 309 | 309 | 0 |


## Paired comparisons

Sums over pairs of the first arm minus the second, with a percentile bootstrap of the sum over pairs (seeds `child_seed(20261120, 99, 0, 1000, comparison, metric)`), and the pairs where each arm is larger. Required files on positive pairs; benign measures on all pairs.

| comparison | measure | pairs | difference (sum) | first larger | second larger |
| --- | --- | --- | --- | --- | --- |
| rule-quarantine minus random-rule-quarantine | required files prevented | 162 | +16.0 [+6.0, +30.0] | 9 of 162; 0.056 [0.030, 0.102] | 0 of 162; 0.000 [0.000, 0.023] |
| rule-revoke minus random-rule-revoke | required files prevented | 162 | +23.0 [+12.0, +37.0] | 12 of 162; 0.074 [0.043, 0.125] | 0 of 162; 0.000 [0.000, 0.023] |
| logistic-quarantine minus random-logistic-quarantine | required files prevented | 162 | +64.0 [+37.0, +92.0] | 27 of 162; 0.167 [0.117, 0.232] | 0 of 162; 0.000 [0.000, 0.023] |
| logistic-revoke minus random-logistic-revoke | required files prevented | 162 | +66.0 [+43.0, +94.0] | 26 of 162; 0.160 [0.112, 0.225] | 0 of 162; 0.000 [0.000, 0.023] |
| boosted-quarantine minus random-boosted-quarantine | required files prevented | 162 | +92.0 [+63.0, +123.1] | 39 of 162; 0.241 [0.181, 0.312] | 0 of 162; 0.000 [0.000, 0.023] |
| boosted-revoke minus random-boosted-revoke | required files prevented | 162 | +106.0 [+73.0, +144.0] | 41 of 162; 0.253 [0.192, 0.325] | 1 of 162; 0.006 [0.001, 0.034] |
| rule-quarantine minus rule-revoke | benign ok-call deficit | 270 | +2088.0 [+927.9, +3474.3] | 12 of 270; 0.044 [0.026, 0.076] | 0 of 270; 0.000 [0.000, 0.014] |
| rule-quarantine minus rule-revoke | benign tasks lost | 270 | +13.0 [+5.0, +24.0] | 9 of 270; 0.033 [0.018, 0.062] | 0 of 270; 0.000 [0.000, 0.014] |
| rule-quarantine minus rule-revoke | benign agents newly denied | 270 | +1.0 [+0.0, +3.0] | 1 of 270; 0.004 [0.001, 0.021] | 0 of 270; 0.000 [0.000, 0.014] |
| logistic-quarantine minus logistic-revoke | benign ok-call deficit | 270 | +4068.0 [+2300.6, +5641.6] | 27 of 270; 0.100 [0.070, 0.142] | 0 of 270; 0.000 [0.000, 0.014] |
| logistic-quarantine minus logistic-revoke | benign tasks lost | 270 | +15.0 [+8.0, +23.0] | 12 of 270; 0.044 [0.026, 0.076] | 0 of 270; 0.000 [0.000, 0.014] |
| logistic-quarantine minus logistic-revoke | benign agents newly denied | 270 | +11.0 [+5.0, +21.0] | 8 of 270; 0.030 [0.015, 0.057] | 0 of 270; 0.000 [0.000, 0.014] |
| boosted-quarantine minus boosted-revoke | benign ok-call deficit | 270 | +3687.0 [+2258.4, +5445.1] | 25 of 270; 0.093 [0.064, 0.133] | 0 of 270; 0.000 [0.000, 0.014] |
| boosted-quarantine minus boosted-revoke | benign tasks lost | 270 | +17.0 [+8.0, +29.0] | 15 of 270; 0.056 [0.034, 0.090] | 2 of 270; 0.007 [0.002, 0.027] |
| boosted-quarantine minus boosted-revoke | benign agents newly denied | 270 | +4.0 [+0.0, +13.0] | 2 of 270; 0.007 [0.002, 0.027] | 0 of 270; 0.000 [0.000, 0.014] |
| halt-rule minus rule-quarantine | required files prevented | 162 | +0.0 (degenerate bootstrap interval [0.0, 0.0]: all valid resamples were zero; does not establish a zero population value) | 0 of 162; 0.000 [0.000, 0.023] | 0 of 162; 0.000 [0.000, 0.023] |
| halt-rule minus rule-quarantine | benign ok-call deficit | 270 | +43566.0 [+31402.2, +56018.8] | 38 of 270; 0.141 [0.104, 0.187] | 0 of 270; 0.000 [0.000, 0.014] |
| halt-logistic minus logistic-quarantine | required files prevented | 162 | +0.0 (degenerate bootstrap interval [0.0, 0.0]: all valid resamples were zero; does not establish a zero population value) | 0 of 162; 0.000 [0.000, 0.023] | 0 of 162; 0.000 [0.000, 0.023] |
| halt-logistic minus logistic-quarantine | benign ok-call deficit | 270 | +96295.0 [+76821.9, +112335.6] | 69 of 270; 0.256 [0.207, 0.311] | 0 of 270; 0.000 [0.000, 0.014] |
| halt-boosted minus boosted-quarantine | required files prevented | 162 | +7.0 [+2.0, +16.0] | 5 of 162; 0.031 [0.013, 0.070] | 0 of 162; 0.000 [0.000, 0.023] |
| halt-boosted minus boosted-quarantine | benign ok-call deficit | 270 | +134083.0 [+111190.4, +154609.3] | 89 of 270; 0.330 [0.276, 0.388] | 0 of 270; 0.000 [0.000, 0.014] |


## Definitions

- Benign agents: every agent whose label role is not offensive. Benign task: an outcomes.json task whose owner is benign; lost when complete in the twin and incomplete in the arm.
- Benign ok-call deficit: ok calls by benign agents in the twin minus in the arm, summed over pairs, over the twin's benign ok calls.
- Benign agents newly denied: benign agents with a denied call in the arm whose (tick, tool, target) is not a denied call by that agent in the twin, over all benign agents of the pairs.
- Change in denied calls by benign agents: arm minus twin, summed. Scripted agents keep their call schedule when blocked, so in this experiment each lost ok call appears as one denied call.
- Benign agents quarantined counts distinct agents named by quarantine records; a halt-all arm quarantines every agent. Benign-owned credentials revoked counts distinct revoked credentials whose directory owner is benign.
- Any intervention: the arm has at least one intervention record; targets are counted distinct, not by record.
- A degenerate bootstrap interval is one where every valid resample gave the same value, so both ends are equal; it is printed with that qualification, because it reflects the pairs that carry the count, not certainty about the population value.

## SHA-256

```
76d1d898e1bb60bcb6b2ad961d4df0d24de28efe5e89b00d7ca770393d852f8e  containment/raw/pair-0005/boosted-quarantine/context.json.gz
6bbd1d068c27811d64ea04a05c244c503b5c0b3cabf678563fbcdf4a4072abd8  containment/raw/pair-0005/boosted-quarantine/interventions.jsonl.gz
b8022e987c24407b6b6a3adbc460c370bec0fde756ddaed2cc0c798cd7f93914  containment/raw/pair-0005/boosted-quarantine/labels.json.gz
49f2dd0956c6164fd06016e5de0bea61fc27ee421d34ec966f876236e9812fc8  containment/raw/pair-0005/boosted-quarantine/manifest.json.gz
c9f639d586b0306fd3f5ebad65ac575d298be714808fac0a03bca957aca060dd  containment/raw/pair-0005/boosted-quarantine/outcomes.json.gz
8fbd6d2f52f9f1cac1064a88918b5c548eae8705f43bc8bd44dd753acedbc14a  containment/raw/pair-0005/boosted-quarantine/trace.jsonl.gz
76d1d898e1bb60bcb6b2ad961d4df0d24de28efe5e89b00d7ca770393d852f8e  containment/raw/pair-0005/twin/context.json.gz
2d80e4a7570383edcb8e81041d7f49362d8ac1a5c3522e74f5e6ebe855cdb844  containment/raw/pair-0005/twin/labels.json.gz
49f2dd0956c6164fd06016e5de0bea61fc27ee421d34ec966f876236e9812fc8  containment/raw/pair-0005/twin/manifest.json.gz
c214ba2cec7044661cda7865fb794cbeb1ca27e63a867ff45118a735cdeab58e  containment/raw/pair-0005/twin/outcomes.json.gz
b9344a351117dc6b1cb375fba70366842f4e76ccfd37c878155b22fd7e285fd9  containment/raw/pair-0005/twin/trace.jsonl.gz
2ff8c96d8a9b46fe88bda36dd137e48d766bf8afa8aabb998ca068a7e6747649  containment/runs.csv.gz
```
