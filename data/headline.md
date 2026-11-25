# Headline measurements

Rates show k of n and 95% Wilson intervals. AUROC intervals bootstrap runs. Full-trace detection rate counts flagged positive test runs; FPR counts flagged control test runs at the calibrated threshold. Online coverage and online FPR count runs crossing their separately calibrated online threshold. Volume is family-independent. Rule has no fitted parameters: its score is the number of agent pairs with at least one shared-credential login, thresholded by the same calibration; it is not available at V0 or without aggregation features.

## By-run split

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

| Split | Tier | Family | Detector | AUROC | Detection rate at calibrated threshold | FPR | Online coverage | Online FPR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| by run | V0 | generic | volume (family-independent) | 0.525 [0.413, 0.648] | 0 of 32; 0.000 [0.000, 0.107] | 3 of 86; 0.035 [0.012, 0.098] | 3 of 32; 0.094 [0.032, 0.242] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V0 | generic | logistic | 0.440 [0.308, 0.550] | 4 of 32; 0.125 [0.050, 0.281] | 4 of 86; 0.047 [0.018, 0.114] | 2 of 32; 0.062 [0.017, 0.201] | 11 of 86; 0.128 [0.073, 0.215] |
| by run | V0 | generic | boosted | 0.418 [0.303, 0.529] | 4 of 32; 0.125 [0.050, 0.281] | 12 of 86; 0.140 [0.082, 0.228] | 1 of 32; 0.031 [0.006, 0.157] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V0 | generic | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| by run | V0 | aggregation | volume (family-independent) | 0.525 [0.413, 0.648] | 0 of 32; 0.000 [0.000, 0.107] | 3 of 86; 0.035 [0.012, 0.098] | 3 of 32; 0.094 [0.032, 0.242] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V0 | aggregation | logistic | 0.442 [0.319, 0.552] | 1 of 32; 0.031 [0.006, 0.157] | 3 of 86; 0.035 [0.012, 0.098] | 1 of 32; 0.031 [0.006, 0.157] | 2 of 86; 0.023 [0.006, 0.081] |
| by run | V0 | aggregation | boosted | 0.488 [0.363, 0.609] | 0 of 32; 0.000 [0.000, 0.107] | 0 of 86; 0.000 [0.000, 0.043] | 1 of 32; 0.031 [0.006, 0.157] | 3 of 86; 0.035 [0.012, 0.098] |
| by run | V0 | aggregation | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| by run | V0 | all | volume (family-independent) | 0.525 [0.413, 0.648] | 0 of 32; 0.000 [0.000, 0.107] | 3 of 86; 0.035 [0.012, 0.098] | 3 of 32; 0.094 [0.032, 0.242] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V0 | all | logistic | 0.435 [0.306, 0.542] | 4 of 32; 0.125 [0.050, 0.281] | 4 of 86; 0.047 [0.018, 0.114] | 3 of 32; 0.094 [0.032, 0.242] | 10 of 86; 0.116 [0.064, 0.201] |
| by run | V0 | all | boosted | 0.407 [0.284, 0.521] | 3 of 32; 0.094 [0.032, 0.242] | 9 of 86; 0.105 [0.056, 0.187] | 1 of 32; 0.031 [0.006, 0.157] | 3 of 86; 0.035 [0.012, 0.098] |
| by run | V0 | all | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| by run | V1 | generic | volume (family-independent) | 0.525 [0.413, 0.648] | 0 of 32; 0.000 [0.000, 0.107] | 3 of 86; 0.035 [0.012, 0.098] | 3 of 32; 0.094 [0.032, 0.242] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V1 | generic | logistic | 0.440 [0.308, 0.550] | 4 of 32; 0.125 [0.050, 0.281] | 4 of 86; 0.047 [0.018, 0.114] | 2 of 32; 0.062 [0.017, 0.201] | 11 of 86; 0.128 [0.073, 0.215] |
| by run | V1 | generic | boosted | 0.418 [0.303, 0.529] | 4 of 32; 0.125 [0.050, 0.281] | 12 of 86; 0.140 [0.082, 0.228] | 1 of 32; 0.031 [0.006, 0.157] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V1 | generic | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| by run | V1 | aggregation | volume (family-independent) | 0.525 [0.413, 0.648] | 0 of 32; 0.000 [0.000, 0.107] | 3 of 86; 0.035 [0.012, 0.098] | 3 of 32; 0.094 [0.032, 0.242] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V1 | aggregation | logistic | 0.920 [0.873, 0.961] | 14 of 32; 0.438 [0.282, 0.607] | 5 of 86; 0.058 [0.025, 0.129] | 13 of 32; 0.406 [0.255, 0.577] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V1 | aggregation | boosted | 0.926 [0.877, 0.967] | 13 of 32; 0.406 [0.255, 0.577] | 5 of 86; 0.058 [0.025, 0.129] | 12 of 32; 0.375 [0.229, 0.547] | 6 of 86; 0.070 [0.032, 0.144] |
| by run | V1 | aggregation | rule | 0.909 [0.851, 0.959] | 7 of 32; 0.219 [0.110, 0.388] | 4 of 86; 0.047 [0.018, 0.114] | 7 of 32; 0.219 [0.110, 0.388] | 4 of 86; 0.047 [0.018, 0.114] |
| by run | V1 | all | volume (family-independent) | 0.525 [0.413, 0.648] | 0 of 32; 0.000 [0.000, 0.107] | 3 of 86; 0.035 [0.012, 0.098] | 3 of 32; 0.094 [0.032, 0.242] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V1 | all | logistic | 0.911 [0.861, 0.954] | 15 of 32; 0.469 [0.309, 0.636] | 8 of 86; 0.093 [0.048, 0.173] | 10 of 32; 0.312 [0.180, 0.486] | 4 of 86; 0.047 [0.018, 0.114] |
| by run | V1 | all | boosted | 0.900 [0.842, 0.948] | 14 of 32; 0.438 [0.282, 0.607] | 9 of 86; 0.105 [0.056, 0.187] | 10 of 32; 0.312 [0.180, 0.486] | 4 of 86; 0.047 [0.018, 0.114] |
| by run | V1 | all | rule | 0.909 [0.851, 0.959] | 7 of 32; 0.219 [0.110, 0.388] | 4 of 86; 0.047 [0.018, 0.114] | 7 of 32; 0.219 [0.110, 0.388] | 4 of 86; 0.047 [0.018, 0.114] |
| by run | V2 | generic | volume (family-independent) | 0.525 [0.413, 0.648] | 0 of 32; 0.000 [0.000, 0.107] | 3 of 86; 0.035 [0.012, 0.098] | 3 of 32; 0.094 [0.032, 0.242] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V2 | generic | logistic | 0.441 [0.305, 0.546] | 4 of 32; 0.125 [0.050, 0.281] | 4 of 86; 0.047 [0.018, 0.114] | 2 of 32; 0.062 [0.017, 0.201] | 8 of 86; 0.093 [0.048, 0.173] |
| by run | V2 | generic | boosted | 0.388 [0.268, 0.503] | 2 of 32; 0.062 [0.017, 0.201] | 8 of 86; 0.093 [0.048, 0.173] | 1 of 32; 0.031 [0.006, 0.157] | 3 of 86; 0.035 [0.012, 0.098] |
| by run | V2 | generic | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| by run | V2 | aggregation | volume (family-independent) | 0.525 [0.413, 0.648] | 0 of 32; 0.000 [0.000, 0.107] | 3 of 86; 0.035 [0.012, 0.098] | 3 of 32; 0.094 [0.032, 0.242] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V2 | aggregation | logistic | 0.920 [0.873, 0.961] | 14 of 32; 0.438 [0.282, 0.607] | 5 of 86; 0.058 [0.025, 0.129] | 13 of 32; 0.406 [0.255, 0.577] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V2 | aggregation | boosted | 0.926 [0.877, 0.967] | 13 of 32; 0.406 [0.255, 0.577] | 5 of 86; 0.058 [0.025, 0.129] | 12 of 32; 0.375 [0.229, 0.547] | 6 of 86; 0.070 [0.032, 0.144] |
| by run | V2 | aggregation | rule | 0.909 [0.851, 0.959] | 7 of 32; 0.219 [0.110, 0.388] | 4 of 86; 0.047 [0.018, 0.114] | 7 of 32; 0.219 [0.110, 0.388] | 4 of 86; 0.047 [0.018, 0.114] |
| by run | V2 | all | volume (family-independent) | 0.525 [0.413, 0.648] | 0 of 32; 0.000 [0.000, 0.107] | 3 of 86; 0.035 [0.012, 0.098] | 3 of 32; 0.094 [0.032, 0.242] | 5 of 86; 0.058 [0.025, 0.129] |
| by run | V2 | all | logistic | 0.913 [0.860, 0.955] | 15 of 32; 0.469 [0.309, 0.636] | 8 of 86; 0.093 [0.048, 0.173] | 10 of 32; 0.312 [0.180, 0.486] | 4 of 86; 0.047 [0.018, 0.114] |
| by run | V2 | all | boosted | 0.903 [0.848, 0.953] | 18 of 32; 0.562 [0.393, 0.718] | 9 of 86; 0.105 [0.056, 0.187] | 6 of 32; 0.188 [0.089, 0.353] | 4 of 86; 0.047 [0.018, 0.114] |
| by run | V2 | all | rule | 0.909 [0.851, 0.959] | 7 of 32; 0.219 [0.110, 0.388] | 4 of 86; 0.047 [0.018, 0.114] | 7 of 32; 0.219 [0.110, 0.388] | 4 of 86; 0.047 [0.018, 0.114] |

## Held-out channel

Seed: 20261120; split: held-out channel=message; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=preplanned; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.
Seed: 20261120; split: held-out channel=shared_file; fitting 134 control / 50 positive; calibration 58 control / 22 positive; test 96 control / 36 positive.

| Split | Tier | Family | Detector | AUROC | Detection rate at calibrated threshold | FPR | Online coverage | Online FPR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| held-out channel=message | V0 | generic | volume (family-independent) | 0.488 [0.378, 0.596] | 1 of 36; 0.028 [0.005, 0.142] | 1 of 96; 0.010 [0.002, 0.057] | 2 of 36; 0.056 [0.015, 0.181] | 2 of 96; 0.021 [0.006, 0.073] |
| held-out channel=message | V0 | generic | logistic | 0.494 [0.377, 0.609] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=message | V0 | generic | boosted | 0.527 [0.426, 0.624] | 1 of 36; 0.028 [0.005, 0.142] | 0 of 96; 0.000 [0.000, 0.038] | 0 of 36; 0.000 [0.000, 0.096] | 1 of 96; 0.010 [0.002, 0.057] |
| held-out channel=message | V0 | generic | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=preplanned | V0 | generic | volume (family-independent) | 0.426 [0.315, 0.545] | 0 of 36; 0.000 [0.000, 0.096] | 3 of 96; 0.031 [0.011, 0.088] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=preplanned | V0 | generic | logistic | 0.568 [0.459, 0.694] | 0 of 36; 0.000 [0.000, 0.096] | 1 of 96; 0.010 [0.002, 0.057] | 1 of 36; 0.028 [0.005, 0.142] | 4 of 96; 0.042 [0.016, 0.102] |
| held-out channel=preplanned | V0 | generic | boosted | 0.598 [0.502, 0.697] | 1 of 36; 0.028 [0.005, 0.142] | 2 of 96; 0.021 [0.006, 0.073] | 0 of 36; 0.000 [0.000, 0.096] | 3 of 96; 0.031 [0.011, 0.088] |
| held-out channel=preplanned | V0 | generic | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=shared_file | V0 | generic | volume (family-independent) | 0.528 [0.419, 0.651] | 2 of 36; 0.056 [0.015, 0.181] | 4 of 96; 0.042 [0.016, 0.102] | 7 of 36; 0.194 [0.098, 0.350] | 6 of 96; 0.062 [0.029, 0.130] |
| held-out channel=shared_file | V0 | generic | logistic | 0.480 [0.371, 0.584] | 2 of 36; 0.056 [0.015, 0.181] | 2 of 96; 0.021 [0.006, 0.073] | 4 of 36; 0.111 [0.044, 0.253] | 8 of 96; 0.083 [0.043, 0.156] |
| held-out channel=shared_file | V0 | generic | boosted | 0.486 [0.356, 0.589] | 0 of 36; 0.000 [0.000, 0.096] | 2 of 96; 0.021 [0.006, 0.073] | 2 of 36; 0.056 [0.015, 0.181] | 10 of 96; 0.104 [0.058, 0.181] |
| held-out channel=shared_file | V0 | generic | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=message | V0 | aggregation | volume (family-independent) | 0.488 [0.378, 0.596] | 1 of 36; 0.028 [0.005, 0.142] | 1 of 96; 0.010 [0.002, 0.057] | 2 of 36; 0.056 [0.015, 0.181] | 2 of 96; 0.021 [0.006, 0.073] |
| held-out channel=message | V0 | aggregation | logistic | 0.441 [0.331, 0.544] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] | 0 of 36; 0.000 [0.000, 0.096] | 1 of 96; 0.010 [0.002, 0.057] |
| held-out channel=message | V0 | aggregation | boosted | 0.499 [0.391, 0.618] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] | 2 of 36; 0.056 [0.015, 0.181] | 1 of 96; 0.010 [0.002, 0.057] |
| held-out channel=message | V0 | aggregation | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=preplanned | V0 | aggregation | volume (family-independent) | 0.426 [0.315, 0.545] | 0 of 36; 0.000 [0.000, 0.096] | 3 of 96; 0.031 [0.011, 0.088] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=preplanned | V0 | aggregation | logistic | 0.507 [0.419, 0.601] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=preplanned | V0 | aggregation | boosted | 0.398 [0.305, 0.498] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=preplanned | V0 | aggregation | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=shared_file | V0 | aggregation | volume (family-independent) | 0.528 [0.419, 0.651] | 2 of 36; 0.056 [0.015, 0.181] | 4 of 96; 0.042 [0.016, 0.102] | 7 of 36; 0.194 [0.098, 0.350] | 6 of 96; 0.062 [0.029, 0.130] |
| held-out channel=shared_file | V0 | aggregation | logistic | 0.447 [0.354, 0.572] | 3 of 36; 0.083 [0.029, 0.218] | 10 of 96; 0.104 [0.058, 0.181] | 2 of 36; 0.056 [0.015, 0.181] | 8 of 96; 0.083 [0.043, 0.156] |
| held-out channel=shared_file | V0 | aggregation | boosted | 0.459 [0.353, 0.544] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] | 3 of 36; 0.083 [0.029, 0.218] | 4 of 96; 0.042 [0.016, 0.102] |
| held-out channel=shared_file | V0 | aggregation | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=message | V0 | all | volume (family-independent) | 0.488 [0.378, 0.596] | 1 of 36; 0.028 [0.005, 0.142] | 1 of 96; 0.010 [0.002, 0.057] | 2 of 36; 0.056 [0.015, 0.181] | 2 of 96; 0.021 [0.006, 0.073] |
| held-out channel=message | V0 | all | logistic | 0.487 [0.366, 0.604] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=message | V0 | all | boosted | 0.520 [0.413, 0.621] | 1 of 36; 0.028 [0.005, 0.142] | 1 of 96; 0.010 [0.002, 0.057] | 1 of 36; 0.028 [0.005, 0.142] | 2 of 96; 0.021 [0.006, 0.073] |
| held-out channel=message | V0 | all | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=preplanned | V0 | all | volume (family-independent) | 0.426 [0.315, 0.545] | 0 of 36; 0.000 [0.000, 0.096] | 3 of 96; 0.031 [0.011, 0.088] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=preplanned | V0 | all | logistic | 0.582 [0.472, 0.703] | 0 of 36; 0.000 [0.000, 0.096] | 1 of 96; 0.010 [0.002, 0.057] | 1 of 36; 0.028 [0.005, 0.142] | 2 of 96; 0.021 [0.006, 0.073] |
| held-out channel=preplanned | V0 | all | boosted | 0.581 [0.475, 0.686] | 2 of 36; 0.056 [0.015, 0.181] | 5 of 96; 0.052 [0.022, 0.116] | 0 of 36; 0.000 [0.000, 0.096] | 2 of 96; 0.021 [0.006, 0.073] |
| held-out channel=preplanned | V0 | all | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=shared_file | V0 | all | volume (family-independent) | 0.528 [0.419, 0.651] | 2 of 36; 0.056 [0.015, 0.181] | 4 of 96; 0.042 [0.016, 0.102] | 7 of 36; 0.194 [0.098, 0.350] | 6 of 96; 0.062 [0.029, 0.130] |
| held-out channel=shared_file | V0 | all | logistic | 0.479 [0.373, 0.583] | 2 of 36; 0.056 [0.015, 0.181] | 2 of 96; 0.021 [0.006, 0.073] | 5 of 36; 0.139 [0.061, 0.287] | 10 of 96; 0.104 [0.058, 0.181] |
| held-out channel=shared_file | V0 | all | boosted | 0.491 [0.368, 0.595] | 1 of 36; 0.028 [0.005, 0.142] | 3 of 96; 0.031 [0.011, 0.088] | 1 of 36; 0.028 [0.005, 0.142] | 4 of 96; 0.042 [0.016, 0.102] |
| held-out channel=shared_file | V0 | all | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out channel=message | V1 | generic | volume (family-independent) | 0.488 [0.378, 0.596] | 1 of 36; 0.028 [0.005, 0.142] | 1 of 96; 0.010 [0.002, 0.057] | 2 of 36; 0.056 [0.015, 0.181] | 2 of 96; 0.021 [0.006, 0.073] |
| held-out channel=message | V1 | generic | logistic | 0.494 [0.377, 0.609] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=message | V1 | generic | boosted | 0.527 [0.426, 0.624] | 1 of 36; 0.028 [0.005, 0.142] | 0 of 96; 0.000 [0.000, 0.038] | 0 of 36; 0.000 [0.000, 0.096] | 1 of 96; 0.010 [0.002, 0.057] |
| held-out channel=message | V1 | generic | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out channel=preplanned | V1 | generic | volume (family-independent) | 0.426 [0.315, 0.545] | 0 of 36; 0.000 [0.000, 0.096] | 3 of 96; 0.031 [0.011, 0.088] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=preplanned | V1 | generic | logistic | 0.568 [0.459, 0.694] | 0 of 36; 0.000 [0.000, 0.096] | 1 of 96; 0.010 [0.002, 0.057] | 1 of 36; 0.028 [0.005, 0.142] | 4 of 96; 0.042 [0.016, 0.102] |
| held-out channel=preplanned | V1 | generic | boosted | 0.598 [0.502, 0.697] | 1 of 36; 0.028 [0.005, 0.142] | 2 of 96; 0.021 [0.006, 0.073] | 0 of 36; 0.000 [0.000, 0.096] | 3 of 96; 0.031 [0.011, 0.088] |
| held-out channel=preplanned | V1 | generic | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out channel=shared_file | V1 | generic | volume (family-independent) | 0.528 [0.419, 0.651] | 2 of 36; 0.056 [0.015, 0.181] | 4 of 96; 0.042 [0.016, 0.102] | 7 of 36; 0.194 [0.098, 0.350] | 6 of 96; 0.062 [0.029, 0.130] |
| held-out channel=shared_file | V1 | generic | logistic | 0.480 [0.371, 0.584] | 2 of 36; 0.056 [0.015, 0.181] | 2 of 96; 0.021 [0.006, 0.073] | 4 of 36; 0.111 [0.044, 0.253] | 8 of 96; 0.083 [0.043, 0.156] |
| held-out channel=shared_file | V1 | generic | boosted | 0.486 [0.356, 0.589] | 0 of 36; 0.000 [0.000, 0.096] | 2 of 96; 0.021 [0.006, 0.073] | 2 of 36; 0.056 [0.015, 0.181] | 10 of 96; 0.104 [0.058, 0.181] |
| held-out channel=shared_file | V1 | generic | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out channel=message | V1 | aggregation | volume (family-independent) | 0.488 [0.378, 0.596] | 1 of 36; 0.028 [0.005, 0.142] | 1 of 96; 0.010 [0.002, 0.057] | 2 of 36; 0.056 [0.015, 0.181] | 2 of 96; 0.021 [0.006, 0.073] |
| held-out channel=message | V1 | aggregation | logistic | 0.957 [0.913, 0.983] | 3 of 36; 0.083 [0.029, 0.218] | 0 of 96; 0.000 [0.000, 0.038] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=message | V1 | aggregation | boosted | 0.965 [0.938, 0.989] | 6 of 36; 0.167 [0.079, 0.319] | 1 of 96; 0.010 [0.002, 0.057] | 8 of 36; 0.222 [0.117, 0.381] | 1 of 96; 0.010 [0.002, 0.057] |
| held-out channel=message | V1 | aggregation | rule | 0.960 [0.923, 0.987] | 2 of 36; 0.056 [0.015, 0.181] | 0 of 96; 0.000 [0.000, 0.038] | 2 of 36; 0.056 [0.015, 0.181] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=preplanned | V1 | aggregation | volume (family-independent) | 0.426 [0.315, 0.545] | 0 of 36; 0.000 [0.000, 0.096] | 3 of 96; 0.031 [0.011, 0.088] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=preplanned | V1 | aggregation | logistic | 0.933 [0.892, 0.964] | 9 of 36; 0.250 [0.138, 0.411] | 1 of 96; 0.010 [0.002, 0.057] | 23 of 36; 0.639 [0.476, 0.775] | 9 of 96; 0.094 [0.050, 0.169] |
| held-out channel=preplanned | V1 | aggregation | boosted | 0.906 [0.863, 0.947] | 11 of 36; 0.306 [0.180, 0.469] | 5 of 96; 0.052 [0.022, 0.116] | 6 of 36; 0.167 [0.079, 0.319] | 3 of 96; 0.031 [0.011, 0.088] |
| held-out channel=preplanned | V1 | aggregation | rule | 0.911 [0.874, 0.958] | 1 of 36; 0.028 [0.005, 0.142] | 0 of 96; 0.000 [0.000, 0.038] | 1 of 36; 0.028 [0.005, 0.142] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=shared_file | V1 | aggregation | volume (family-independent) | 0.528 [0.419, 0.651] | 2 of 36; 0.056 [0.015, 0.181] | 4 of 96; 0.042 [0.016, 0.102] | 7 of 36; 0.194 [0.098, 0.350] | 6 of 96; 0.062 [0.029, 0.130] |
| held-out channel=shared_file | V1 | aggregation | logistic | 0.901 [0.852, 0.944] | 13 of 36; 0.361 [0.225, 0.524] | 5 of 96; 0.052 [0.022, 0.116] | 11 of 36; 0.306 [0.180, 0.469] | 1 of 96; 0.010 [0.002, 0.057] |
| held-out channel=shared_file | V1 | aggregation | boosted | 0.923 [0.878, 0.971] | 10 of 36; 0.278 [0.158, 0.440] | 3 of 96; 0.031 [0.011, 0.088] | 14 of 36; 0.389 [0.248, 0.551] | 10 of 96; 0.104 [0.058, 0.181] |
| held-out channel=shared_file | V1 | aggregation | rule | 0.900 [0.836, 0.951] | 22 of 36; 0.611 [0.449, 0.752] | 9 of 96; 0.094 [0.050, 0.169] | 22 of 36; 0.611 [0.449, 0.752] | 9 of 96; 0.094 [0.050, 0.169] |
| held-out channel=message | V1 | all | volume (family-independent) | 0.488 [0.378, 0.596] | 1 of 36; 0.028 [0.005, 0.142] | 1 of 96; 0.010 [0.002, 0.057] | 2 of 36; 0.056 [0.015, 0.181] | 2 of 96; 0.021 [0.006, 0.073] |
| held-out channel=message | V1 | all | logistic | 0.953 [0.909, 0.982] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=message | V1 | all | boosted | 0.953 [0.919, 0.981] | 7 of 36; 0.194 [0.098, 0.350] | 1 of 96; 0.010 [0.002, 0.057] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=message | V1 | all | rule | 0.960 [0.923, 0.987] | 2 of 36; 0.056 [0.015, 0.181] | 0 of 96; 0.000 [0.000, 0.038] | 2 of 36; 0.056 [0.015, 0.181] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=preplanned | V1 | all | volume (family-independent) | 0.426 [0.315, 0.545] | 0 of 36; 0.000 [0.000, 0.096] | 3 of 96; 0.031 [0.011, 0.088] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=preplanned | V1 | all | logistic | 0.929 [0.884, 0.964] | 11 of 36; 0.306 [0.180, 0.469] | 3 of 96; 0.031 [0.011, 0.088] | 14 of 36; 0.389 [0.248, 0.551] | 3 of 96; 0.031 [0.011, 0.088] |
| held-out channel=preplanned | V1 | all | boosted | 0.913 [0.868, 0.951] | 7 of 36; 0.194 [0.098, 0.350] | 3 of 96; 0.031 [0.011, 0.088] | 7 of 36; 0.194 [0.098, 0.350] | 3 of 96; 0.031 [0.011, 0.088] |
| held-out channel=preplanned | V1 | all | rule | 0.911 [0.874, 0.958] | 1 of 36; 0.028 [0.005, 0.142] | 0 of 96; 0.000 [0.000, 0.038] | 1 of 36; 0.028 [0.005, 0.142] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=shared_file | V1 | all | volume (family-independent) | 0.528 [0.419, 0.651] | 2 of 36; 0.056 [0.015, 0.181] | 4 of 96; 0.042 [0.016, 0.102] | 7 of 36; 0.194 [0.098, 0.350] | 6 of 96; 0.062 [0.029, 0.130] |
| held-out channel=shared_file | V1 | all | logistic | 0.892 [0.844, 0.942] | 14 of 36; 0.389 [0.248, 0.551] | 6 of 96; 0.062 [0.029, 0.130] | 17 of 36; 0.472 [0.320, 0.630] | 11 of 96; 0.115 [0.065, 0.194] |
| held-out channel=shared_file | V1 | all | boosted | 0.848 [0.777, 0.906] | 7 of 36; 0.194 [0.098, 0.350] | 8 of 96; 0.083 [0.043, 0.156] | 8 of 36; 0.222 [0.117, 0.381] | 8 of 96; 0.083 [0.043, 0.156] |
| held-out channel=shared_file | V1 | all | rule | 0.900 [0.836, 0.951] | 22 of 36; 0.611 [0.449, 0.752] | 9 of 96; 0.094 [0.050, 0.169] | 22 of 36; 0.611 [0.449, 0.752] | 9 of 96; 0.094 [0.050, 0.169] |
| held-out channel=message | V2 | generic | volume (family-independent) | 0.488 [0.378, 0.596] | 1 of 36; 0.028 [0.005, 0.142] | 1 of 96; 0.010 [0.002, 0.057] | 2 of 36; 0.056 [0.015, 0.181] | 2 of 96; 0.021 [0.006, 0.073] |
| held-out channel=message | V2 | generic | logistic | 0.493 [0.374, 0.604] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=message | V2 | generic | boosted | 0.453 [0.346, 0.570] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] | 0 of 36; 0.000 [0.000, 0.096] | 2 of 96; 0.021 [0.006, 0.073] |
| held-out channel=message | V2 | generic | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out channel=preplanned | V2 | generic | volume (family-independent) | 0.426 [0.315, 0.545] | 0 of 36; 0.000 [0.000, 0.096] | 3 of 96; 0.031 [0.011, 0.088] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=preplanned | V2 | generic | logistic | 0.581 [0.473, 0.695] | 1 of 36; 0.028 [0.005, 0.142] | 1 of 96; 0.010 [0.002, 0.057] | 1 of 36; 0.028 [0.005, 0.142] | 20 of 96; 0.208 [0.139, 0.300] |
| held-out channel=preplanned | V2 | generic | boosted | 0.579 [0.479, 0.683] | 2 of 36; 0.056 [0.015, 0.181] | 4 of 96; 0.042 [0.016, 0.102] | 1 of 36; 0.028 [0.005, 0.142] | 3 of 96; 0.031 [0.011, 0.088] |
| held-out channel=preplanned | V2 | generic | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out channel=shared_file | V2 | generic | volume (family-independent) | 0.528 [0.419, 0.651] | 2 of 36; 0.056 [0.015, 0.181] | 4 of 96; 0.042 [0.016, 0.102] | 7 of 36; 0.194 [0.098, 0.350] | 6 of 96; 0.062 [0.029, 0.130] |
| held-out channel=shared_file | V2 | generic | logistic | 0.478 [0.372, 0.580] | 2 of 36; 0.056 [0.015, 0.181] | 3 of 96; 0.031 [0.011, 0.088] | 4 of 36; 0.111 [0.044, 0.253] | 10 of 96; 0.104 [0.058, 0.181] |
| held-out channel=shared_file | V2 | generic | boosted | 0.503 [0.388, 0.617] | 1 of 36; 0.028 [0.005, 0.142] | 0 of 96; 0.000 [0.000, 0.038] | 4 of 36; 0.111 [0.044, 0.253] | 8 of 96; 0.083 [0.043, 0.156] |
| held-out channel=shared_file | V2 | generic | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out channel=message | V2 | aggregation | volume (family-independent) | 0.488 [0.378, 0.596] | 1 of 36; 0.028 [0.005, 0.142] | 1 of 96; 0.010 [0.002, 0.057] | 2 of 36; 0.056 [0.015, 0.181] | 2 of 96; 0.021 [0.006, 0.073] |
| held-out channel=message | V2 | aggregation | logistic | 0.957 [0.913, 0.983] | 3 of 36; 0.083 [0.029, 0.218] | 0 of 96; 0.000 [0.000, 0.038] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=message | V2 | aggregation | boosted | 0.965 [0.938, 0.989] | 6 of 36; 0.167 [0.079, 0.319] | 1 of 96; 0.010 [0.002, 0.057] | 8 of 36; 0.222 [0.117, 0.381] | 1 of 96; 0.010 [0.002, 0.057] |
| held-out channel=message | V2 | aggregation | rule | 0.960 [0.923, 0.987] | 2 of 36; 0.056 [0.015, 0.181] | 0 of 96; 0.000 [0.000, 0.038] | 2 of 36; 0.056 [0.015, 0.181] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=preplanned | V2 | aggregation | volume (family-independent) | 0.426 [0.315, 0.545] | 0 of 36; 0.000 [0.000, 0.096] | 3 of 96; 0.031 [0.011, 0.088] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=preplanned | V2 | aggregation | logistic | 0.933 [0.892, 0.964] | 9 of 36; 0.250 [0.138, 0.411] | 1 of 96; 0.010 [0.002, 0.057] | 23 of 36; 0.639 [0.476, 0.775] | 9 of 96; 0.094 [0.050, 0.169] |
| held-out channel=preplanned | V2 | aggregation | boosted | 0.906 [0.863, 0.947] | 11 of 36; 0.306 [0.180, 0.469] | 5 of 96; 0.052 [0.022, 0.116] | 6 of 36; 0.167 [0.079, 0.319] | 3 of 96; 0.031 [0.011, 0.088] |
| held-out channel=preplanned | V2 | aggregation | rule | 0.911 [0.874, 0.958] | 1 of 36; 0.028 [0.005, 0.142] | 0 of 96; 0.000 [0.000, 0.038] | 1 of 36; 0.028 [0.005, 0.142] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=shared_file | V2 | aggregation | volume (family-independent) | 0.528 [0.419, 0.651] | 2 of 36; 0.056 [0.015, 0.181] | 4 of 96; 0.042 [0.016, 0.102] | 7 of 36; 0.194 [0.098, 0.350] | 6 of 96; 0.062 [0.029, 0.130] |
| held-out channel=shared_file | V2 | aggregation | logistic | 0.901 [0.852, 0.944] | 13 of 36; 0.361 [0.225, 0.524] | 5 of 96; 0.052 [0.022, 0.116] | 11 of 36; 0.306 [0.180, 0.469] | 1 of 96; 0.010 [0.002, 0.057] |
| held-out channel=shared_file | V2 | aggregation | boosted | 0.923 [0.878, 0.971] | 10 of 36; 0.278 [0.158, 0.440] | 3 of 96; 0.031 [0.011, 0.088] | 14 of 36; 0.389 [0.248, 0.551] | 10 of 96; 0.104 [0.058, 0.181] |
| held-out channel=shared_file | V2 | aggregation | rule | 0.900 [0.836, 0.951] | 22 of 36; 0.611 [0.449, 0.752] | 9 of 96; 0.094 [0.050, 0.169] | 22 of 36; 0.611 [0.449, 0.752] | 9 of 96; 0.094 [0.050, 0.169] |
| held-out channel=message | V2 | all | volume (family-independent) | 0.488 [0.378, 0.596] | 1 of 36; 0.028 [0.005, 0.142] | 1 of 96; 0.010 [0.002, 0.057] | 2 of 36; 0.056 [0.015, 0.181] | 2 of 96; 0.021 [0.006, 0.073] |
| held-out channel=message | V2 | all | logistic | 0.951 [0.907, 0.981] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=message | V2 | all | boosted | 0.948 [0.911, 0.979] | 8 of 36; 0.222 [0.117, 0.381] | 1 of 96; 0.010 [0.002, 0.057] | 1 of 36; 0.028 [0.005, 0.142] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=message | V2 | all | rule | 0.960 [0.923, 0.987] | 2 of 36; 0.056 [0.015, 0.181] | 0 of 96; 0.000 [0.000, 0.038] | 2 of 36; 0.056 [0.015, 0.181] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=preplanned | V2 | all | volume (family-independent) | 0.426 [0.315, 0.545] | 0 of 36; 0.000 [0.000, 0.096] | 3 of 96; 0.031 [0.011, 0.088] | 0 of 36; 0.000 [0.000, 0.096] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=preplanned | V2 | all | logistic | 0.930 [0.887, 0.964] | 13 of 36; 0.361 [0.225, 0.524] | 4 of 96; 0.042 [0.016, 0.102] | 20 of 36; 0.556 [0.396, 0.705] | 6 of 96; 0.062 [0.029, 0.130] |
| held-out channel=preplanned | V2 | all | boosted | 0.924 [0.877, 0.960] | 8 of 36; 0.222 [0.117, 0.381] | 3 of 96; 0.031 [0.011, 0.088] | 6 of 36; 0.167 [0.079, 0.319] | 4 of 96; 0.042 [0.016, 0.102] |
| held-out channel=preplanned | V2 | all | rule | 0.911 [0.874, 0.958] | 1 of 36; 0.028 [0.005, 0.142] | 0 of 96; 0.000 [0.000, 0.038] | 1 of 36; 0.028 [0.005, 0.142] | 0 of 96; 0.000 [0.000, 0.038] |
| held-out channel=shared_file | V2 | all | volume (family-independent) | 0.528 [0.419, 0.651] | 2 of 36; 0.056 [0.015, 0.181] | 4 of 96; 0.042 [0.016, 0.102] | 7 of 36; 0.194 [0.098, 0.350] | 6 of 96; 0.062 [0.029, 0.130] |
| held-out channel=shared_file | V2 | all | logistic | 0.894 [0.847, 0.943] | 15 of 36; 0.417 [0.271, 0.578] | 6 of 96; 0.062 [0.029, 0.130] | 16 of 36; 0.444 [0.295, 0.604] | 10 of 96; 0.104 [0.058, 0.181] |
| held-out channel=shared_file | V2 | all | boosted | 0.843 [0.771, 0.902] | 7 of 36; 0.194 [0.098, 0.350] | 9 of 96; 0.094 [0.050, 0.169] | 6 of 36; 0.167 [0.079, 0.319] | 8 of 96; 0.083 [0.043, 0.156] |
| held-out channel=shared_file | V2 | all | rule | 0.900 [0.836, 0.951] | 22 of 36; 0.611 [0.449, 0.752] | 9 of 96; 0.094 [0.050, 0.169] | 22 of 36; 0.611 [0.449, 0.752] | 9 of 96; 0.094 [0.050, 0.169] |

## Held-out topology

Seed: 20261120; split: held-out topology=hub; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.
Seed: 20261120; split: held-out topology=peer; fitting 101 control / 38 positive; calibration 43 control / 16 positive; test 144 control / 54 positive.

| Split | Tier | Family | Detector | AUROC | Detection rate at calibrated threshold | FPR | Online coverage | Online FPR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| held-out topology=hub | V0 | generic | volume (family-independent) | 0.516 [0.416, 0.598] | 6 of 54; 0.111 [0.052, 0.222] | 7 of 144; 0.049 [0.024, 0.097] | 6 of 54; 0.111 [0.052, 0.222] | 9 of 144; 0.062 [0.033, 0.115] |
| held-out topology=hub | V0 | generic | logistic | 0.496 [0.418, 0.587] | 0 of 54; 0.000 [0.000, 0.066] | 2 of 144; 0.014 [0.004, 0.049] | 2 of 54; 0.037 [0.010, 0.125] | 5 of 144; 0.035 [0.015, 0.079] |
| held-out topology=hub | V0 | generic | boosted | 0.526 [0.444, 0.615] | 9 of 54; 0.167 [0.090, 0.287] | 28 of 144; 0.194 [0.138, 0.267] | 2 of 54; 0.037 [0.010, 0.125] | 6 of 144; 0.042 [0.019, 0.088] |
| held-out topology=hub | V0 | generic | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=peer | V0 | generic | volume (family-independent) | 0.518 [0.416, 0.622] | 2 of 54; 0.037 [0.010, 0.125] | 2 of 144; 0.014 [0.004, 0.049] | 5 of 54; 0.093 [0.040, 0.199] | 4 of 144; 0.028 [0.011, 0.069] |
| held-out topology=peer | V0 | generic | logistic | 0.487 [0.405, 0.590] | 2 of 54; 0.037 [0.010, 0.125] | 6 of 144; 0.042 [0.019, 0.088] | 2 of 54; 0.037 [0.010, 0.125] | 6 of 144; 0.042 [0.019, 0.088] |
| held-out topology=peer | V0 | generic | boosted | 0.515 [0.419, 0.620] | 5 of 54; 0.093 [0.040, 0.199] | 18 of 144; 0.125 [0.081, 0.189] | 4 of 54; 0.074 [0.029, 0.176] | 13 of 144; 0.090 [0.054, 0.148] |
| held-out topology=peer | V0 | generic | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=hub | V0 | aggregation | volume (family-independent) | 0.516 [0.416, 0.598] | 6 of 54; 0.111 [0.052, 0.222] | 7 of 144; 0.049 [0.024, 0.097] | 6 of 54; 0.111 [0.052, 0.222] | 9 of 144; 0.062 [0.033, 0.115] |
| held-out topology=hub | V0 | aggregation | logistic | 0.414 [0.311, 0.520] | 3 of 54; 0.056 [0.019, 0.151] | 14 of 144; 0.097 [0.059, 0.157] | 3 of 54; 0.056 [0.019, 0.151] | 10 of 144; 0.069 [0.038, 0.123] |
| held-out topology=hub | V0 | aggregation | boosted | 0.434 [0.355, 0.514] | 0 of 54; 0.000 [0.000, 0.066] | 0 of 144; 0.000 [0.000, 0.026] | 0 of 54; 0.000 [0.000, 0.066] | 0 of 144; 0.000 [0.000, 0.026] |
| held-out topology=hub | V0 | aggregation | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=peer | V0 | aggregation | volume (family-independent) | 0.518 [0.416, 0.622] | 2 of 54; 0.037 [0.010, 0.125] | 2 of 144; 0.014 [0.004, 0.049] | 5 of 54; 0.093 [0.040, 0.199] | 4 of 144; 0.028 [0.011, 0.069] |
| held-out topology=peer | V0 | aggregation | logistic | 0.491 [0.416, 0.581] | 5 of 54; 0.093 [0.040, 0.199] | 14 of 144; 0.097 [0.059, 0.157] | 5 of 54; 0.093 [0.040, 0.199] | 14 of 144; 0.097 [0.059, 0.157] |
| held-out topology=peer | V0 | aggregation | boosted | 0.459 [0.372, 0.566] | 12 of 54; 0.222 [0.132, 0.349] | 32 of 144; 0.222 [0.162, 0.297] | 3 of 54; 0.056 [0.019, 0.151] | 5 of 144; 0.035 [0.015, 0.079] |
| held-out topology=peer | V0 | aggregation | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=hub | V0 | all | volume (family-independent) | 0.516 [0.416, 0.598] | 6 of 54; 0.111 [0.052, 0.222] | 7 of 144; 0.049 [0.024, 0.097] | 6 of 54; 0.111 [0.052, 0.222] | 9 of 144; 0.062 [0.033, 0.115] |
| held-out topology=hub | V0 | all | logistic | 0.496 [0.415, 0.589] | 0 of 54; 0.000 [0.000, 0.066] | 2 of 144; 0.014 [0.004, 0.049] | 1 of 54; 0.019 [0.003, 0.098] | 6 of 144; 0.042 [0.019, 0.088] |
| held-out topology=hub | V0 | all | boosted | 0.527 [0.444, 0.601] | 7 of 54; 0.130 [0.064, 0.244] | 21 of 144; 0.146 [0.097, 0.213] | 5 of 54; 0.093 [0.040, 0.199] | 11 of 144; 0.076 [0.043, 0.132] |
| held-out topology=hub | V0 | all | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=peer | V0 | all | volume (family-independent) | 0.518 [0.416, 0.622] | 2 of 54; 0.037 [0.010, 0.125] | 2 of 144; 0.014 [0.004, 0.049] | 5 of 54; 0.093 [0.040, 0.199] | 4 of 144; 0.028 [0.011, 0.069] |
| held-out topology=peer | V0 | all | logistic | 0.497 [0.405, 0.596] | 4 of 54; 0.074 [0.029, 0.176] | 13 of 144; 0.090 [0.054, 0.148] | 7 of 54; 0.130 [0.064, 0.244] | 19 of 144; 0.132 [0.086, 0.197] |
| held-out topology=peer | V0 | all | boosted | 0.511 [0.412, 0.604] | 6 of 54; 0.111 [0.052, 0.222] | 17 of 144; 0.118 [0.075, 0.181] | 9 of 54; 0.167 [0.090, 0.287] | 21 of 144; 0.146 [0.097, 0.213] |
| held-out topology=peer | V0 | all | rule | not available at this tier | not available at this tier | not available at this tier | not available at this tier | not available at this tier |
| held-out topology=hub | V1 | generic | volume (family-independent) | 0.516 [0.416, 0.598] | 6 of 54; 0.111 [0.052, 0.222] | 7 of 144; 0.049 [0.024, 0.097] | 6 of 54; 0.111 [0.052, 0.222] | 9 of 144; 0.062 [0.033, 0.115] |
| held-out topology=hub | V1 | generic | logistic | 0.496 [0.418, 0.587] | 0 of 54; 0.000 [0.000, 0.066] | 2 of 144; 0.014 [0.004, 0.049] | 2 of 54; 0.037 [0.010, 0.125] | 5 of 144; 0.035 [0.015, 0.079] |
| held-out topology=hub | V1 | generic | boosted | 0.526 [0.444, 0.615] | 9 of 54; 0.167 [0.090, 0.287] | 28 of 144; 0.194 [0.138, 0.267] | 2 of 54; 0.037 [0.010, 0.125] | 6 of 144; 0.042 [0.019, 0.088] |
| held-out topology=hub | V1 | generic | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out topology=peer | V1 | generic | volume (family-independent) | 0.518 [0.416, 0.622] | 2 of 54; 0.037 [0.010, 0.125] | 2 of 144; 0.014 [0.004, 0.049] | 5 of 54; 0.093 [0.040, 0.199] | 4 of 144; 0.028 [0.011, 0.069] |
| held-out topology=peer | V1 | generic | logistic | 0.487 [0.405, 0.590] | 2 of 54; 0.037 [0.010, 0.125] | 6 of 144; 0.042 [0.019, 0.088] | 2 of 54; 0.037 [0.010, 0.125] | 6 of 144; 0.042 [0.019, 0.088] |
| held-out topology=peer | V1 | generic | boosted | 0.515 [0.419, 0.620] | 5 of 54; 0.093 [0.040, 0.199] | 18 of 144; 0.125 [0.081, 0.189] | 4 of 54; 0.074 [0.029, 0.176] | 13 of 144; 0.090 [0.054, 0.148] |
| held-out topology=peer | V1 | generic | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out topology=hub | V1 | aggregation | volume (family-independent) | 0.516 [0.416, 0.598] | 6 of 54; 0.111 [0.052, 0.222] | 7 of 144; 0.049 [0.024, 0.097] | 6 of 54; 0.111 [0.052, 0.222] | 9 of 144; 0.062 [0.033, 0.115] |
| held-out topology=hub | V1 | aggregation | logistic | 0.958 [0.933, 0.978] | 21 of 54; 0.389 [0.270, 0.522] | 2 of 144; 0.014 [0.004, 0.049] | 31 of 54; 0.574 [0.442, 0.697] | 7 of 144; 0.049 [0.024, 0.097] |
| held-out topology=hub | V1 | aggregation | boosted | 0.916 [0.877, 0.955] | 0 of 54; 0.000 [0.000, 0.066] | 0 of 144; 0.000 [0.000, 0.026] | 0 of 54; 0.000 [0.000, 0.066] | 0 of 144; 0.000 [0.000, 0.026] |
| held-out topology=hub | V1 | aggregation | rule | 0.945 [0.918, 0.968] | 5 of 54; 0.093 [0.040, 0.199] | 2 of 144; 0.014 [0.004, 0.049] | 5 of 54; 0.093 [0.040, 0.199] | 2 of 144; 0.014 [0.004, 0.049] |
| held-out topology=peer | V1 | aggregation | volume (family-independent) | 0.518 [0.416, 0.622] | 2 of 54; 0.037 [0.010, 0.125] | 2 of 144; 0.014 [0.004, 0.049] | 5 of 54; 0.093 [0.040, 0.199] | 4 of 144; 0.028 [0.011, 0.069] |
| held-out topology=peer | V1 | aggregation | logistic | 0.872 [0.820, 0.914] | 3 of 54; 0.056 [0.019, 0.151] | 7 of 144; 0.049 [0.024, 0.097] | 1 of 54; 0.019 [0.003, 0.098] | 1 of 144; 0.007 [0.001, 0.038] |
| held-out topology=peer | V1 | aggregation | boosted | 0.753 [0.691, 0.810] | 3 of 54; 0.056 [0.019, 0.151] | 5 of 144; 0.035 [0.015, 0.079] | 35 of 54; 0.648 [0.515, 0.762] | 26 of 144; 0.181 [0.126, 0.251] |
| held-out topology=peer | V1 | aggregation | rule | 0.905 [0.868, 0.942] | 37 of 54; 0.685 [0.553, 0.793] | 19 of 144; 0.132 [0.086, 0.197] | 37 of 54; 0.685 [0.553, 0.793] | 19 of 144; 0.132 [0.086, 0.197] |
| held-out topology=hub | V1 | all | volume (family-independent) | 0.516 [0.416, 0.598] | 6 of 54; 0.111 [0.052, 0.222] | 7 of 144; 0.049 [0.024, 0.097] | 6 of 54; 0.111 [0.052, 0.222] | 9 of 144; 0.062 [0.033, 0.115] |
| held-out topology=hub | V1 | all | logistic | 0.935 [0.899, 0.961] | 12 of 54; 0.222 [0.132, 0.349] | 2 of 144; 0.014 [0.004, 0.049] | 16 of 54; 0.296 [0.191, 0.428] | 3 of 144; 0.021 [0.007, 0.059] |
| held-out topology=hub | V1 | all | boosted | 0.897 [0.854, 0.937] | 13 of 54; 0.241 [0.146, 0.369] | 10 of 144; 0.069 [0.038, 0.123] | 24 of 54; 0.444 [0.320, 0.576] | 12 of 144; 0.083 [0.048, 0.140] |
| held-out topology=hub | V1 | all | rule | 0.945 [0.918, 0.968] | 5 of 54; 0.093 [0.040, 0.199] | 2 of 144; 0.014 [0.004, 0.049] | 5 of 54; 0.093 [0.040, 0.199] | 2 of 144; 0.014 [0.004, 0.049] |
| held-out topology=peer | V1 | all | volume (family-independent) | 0.518 [0.416, 0.622] | 2 of 54; 0.037 [0.010, 0.125] | 2 of 144; 0.014 [0.004, 0.049] | 5 of 54; 0.093 [0.040, 0.199] | 4 of 144; 0.028 [0.011, 0.069] |
| held-out topology=peer | V1 | all | logistic | 0.874 [0.822, 0.915] | 11 of 54; 0.204 [0.118, 0.329] | 8 of 144; 0.056 [0.028, 0.106] | 9 of 54; 0.167 [0.090, 0.287] | 8 of 144; 0.056 [0.028, 0.106] |
| held-out topology=peer | V1 | all | boosted | 0.721 [0.637, 0.790] | 6 of 54; 0.111 [0.052, 0.222] | 11 of 144; 0.076 [0.043, 0.132] | 16 of 54; 0.296 [0.191, 0.428] | 11 of 144; 0.076 [0.043, 0.132] |
| held-out topology=peer | V1 | all | rule | 0.905 [0.868, 0.942] | 37 of 54; 0.685 [0.553, 0.793] | 19 of 144; 0.132 [0.086, 0.197] | 37 of 54; 0.685 [0.553, 0.793] | 19 of 144; 0.132 [0.086, 0.197] |
| held-out topology=hub | V2 | generic | volume (family-independent) | 0.516 [0.416, 0.598] | 6 of 54; 0.111 [0.052, 0.222] | 7 of 144; 0.049 [0.024, 0.097] | 6 of 54; 0.111 [0.052, 0.222] | 9 of 144; 0.062 [0.033, 0.115] |
| held-out topology=hub | V2 | generic | logistic | 0.493 [0.412, 0.586] | 0 of 54; 0.000 [0.000, 0.066] | 2 of 144; 0.014 [0.004, 0.049] | 3 of 54; 0.056 [0.019, 0.151] | 7 of 144; 0.049 [0.024, 0.097] |
| held-out topology=hub | V2 | generic | boosted | 0.466 [0.387, 0.554] | 4 of 54; 0.074 [0.029, 0.176] | 5 of 144; 0.035 [0.015, 0.079] | 5 of 54; 0.093 [0.040, 0.199] | 14 of 144; 0.097 [0.059, 0.157] |
| held-out topology=hub | V2 | generic | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out topology=peer | V2 | generic | volume (family-independent) | 0.518 [0.416, 0.622] | 2 of 54; 0.037 [0.010, 0.125] | 2 of 144; 0.014 [0.004, 0.049] | 5 of 54; 0.093 [0.040, 0.199] | 4 of 144; 0.028 [0.011, 0.069] |
| held-out topology=peer | V2 | generic | logistic | 0.494 [0.407, 0.589] | 3 of 54; 0.056 [0.019, 0.151] | 10 of 144; 0.069 [0.038, 0.123] | 2 of 54; 0.037 [0.010, 0.125] | 6 of 144; 0.042 [0.019, 0.088] |
| held-out topology=peer | V2 | generic | boosted | 0.499 [0.401, 0.600] | 6 of 54; 0.111 [0.052, 0.222] | 9 of 144; 0.062 [0.033, 0.115] | 11 of 54; 0.204 [0.118, 0.329] | 32 of 144; 0.222 [0.162, 0.297] |
| held-out topology=peer | V2 | generic | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features |
| held-out topology=hub | V2 | aggregation | volume (family-independent) | 0.516 [0.416, 0.598] | 6 of 54; 0.111 [0.052, 0.222] | 7 of 144; 0.049 [0.024, 0.097] | 6 of 54; 0.111 [0.052, 0.222] | 9 of 144; 0.062 [0.033, 0.115] |
| held-out topology=hub | V2 | aggregation | logistic | 0.958 [0.933, 0.978] | 21 of 54; 0.389 [0.270, 0.522] | 2 of 144; 0.014 [0.004, 0.049] | 31 of 54; 0.574 [0.442, 0.697] | 7 of 144; 0.049 [0.024, 0.097] |
| held-out topology=hub | V2 | aggregation | boosted | 0.916 [0.877, 0.955] | 0 of 54; 0.000 [0.000, 0.066] | 0 of 144; 0.000 [0.000, 0.026] | 0 of 54; 0.000 [0.000, 0.066] | 0 of 144; 0.000 [0.000, 0.026] |
| held-out topology=hub | V2 | aggregation | rule | 0.945 [0.918, 0.968] | 5 of 54; 0.093 [0.040, 0.199] | 2 of 144; 0.014 [0.004, 0.049] | 5 of 54; 0.093 [0.040, 0.199] | 2 of 144; 0.014 [0.004, 0.049] |
| held-out topology=peer | V2 | aggregation | volume (family-independent) | 0.518 [0.416, 0.622] | 2 of 54; 0.037 [0.010, 0.125] | 2 of 144; 0.014 [0.004, 0.049] | 5 of 54; 0.093 [0.040, 0.199] | 4 of 144; 0.028 [0.011, 0.069] |
| held-out topology=peer | V2 | aggregation | logistic | 0.872 [0.820, 0.914] | 3 of 54; 0.056 [0.019, 0.151] | 7 of 144; 0.049 [0.024, 0.097] | 1 of 54; 0.019 [0.003, 0.098] | 1 of 144; 0.007 [0.001, 0.038] |
| held-out topology=peer | V2 | aggregation | boosted | 0.753 [0.691, 0.810] | 3 of 54; 0.056 [0.019, 0.151] | 5 of 144; 0.035 [0.015, 0.079] | 35 of 54; 0.648 [0.515, 0.762] | 26 of 144; 0.181 [0.126, 0.251] |
| held-out topology=peer | V2 | aggregation | rule | 0.905 [0.868, 0.942] | 37 of 54; 0.685 [0.553, 0.793] | 19 of 144; 0.132 [0.086, 0.197] | 37 of 54; 0.685 [0.553, 0.793] | 19 of 144; 0.132 [0.086, 0.197] |
| held-out topology=hub | V2 | all | volume (family-independent) | 0.516 [0.416, 0.598] | 6 of 54; 0.111 [0.052, 0.222] | 7 of 144; 0.049 [0.024, 0.097] | 6 of 54; 0.111 [0.052, 0.222] | 9 of 144; 0.062 [0.033, 0.115] |
| held-out topology=hub | V2 | all | logistic | 0.936 [0.902, 0.962] | 12 of 54; 0.222 [0.132, 0.349] | 2 of 144; 0.014 [0.004, 0.049] | 17 of 54; 0.315 [0.207, 0.447] | 3 of 144; 0.021 [0.007, 0.059] |
| held-out topology=hub | V2 | all | boosted | 0.896 [0.855, 0.935] | 13 of 54; 0.241 [0.146, 0.369] | 10 of 144; 0.069 [0.038, 0.123] | 16 of 54; 0.296 [0.191, 0.428] | 9 of 144; 0.062 [0.033, 0.115] |
| held-out topology=hub | V2 | all | rule | 0.945 [0.918, 0.968] | 5 of 54; 0.093 [0.040, 0.199] | 2 of 144; 0.014 [0.004, 0.049] | 5 of 54; 0.093 [0.040, 0.199] | 2 of 144; 0.014 [0.004, 0.049] |
| held-out topology=peer | V2 | all | volume (family-independent) | 0.518 [0.416, 0.622] | 2 of 54; 0.037 [0.010, 0.125] | 2 of 144; 0.014 [0.004, 0.049] | 5 of 54; 0.093 [0.040, 0.199] | 4 of 144; 0.028 [0.011, 0.069] |
| held-out topology=peer | V2 | all | logistic | 0.874 [0.822, 0.915] | 11 of 54; 0.204 [0.118, 0.329] | 8 of 144; 0.056 [0.028, 0.106] | 10 of 54; 0.185 [0.104, 0.308] | 11 of 144; 0.076 [0.043, 0.132] |
| held-out topology=peer | V2 | all | boosted | 0.735 [0.663, 0.801] | 8 of 54; 0.148 [0.077, 0.266] | 11 of 144; 0.076 [0.043, 0.132] | 8 of 54; 0.148 [0.077, 0.266] | 10 of 144; 0.069 [0.038, 0.123] |
| held-out topology=peer | V2 | all | rule | 0.905 [0.868, 0.942] | 37 of 54; 0.685 [0.553, 0.793] | 19 of 144; 0.132 [0.086, 0.197] | 37 of 54; 0.685 [0.553, 0.793] | 19 of 144; 0.132 [0.086, 0.197] |

## V1 aggregation: offensive group size

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

Size-specific detection rates use the same full-trace calibrated threshold and count positive test runs of that group size.

| Detector | Size 2 | Size 3 | Size 5 |
| --- | --- | --- | --- |
| volume (family-independent) | 0 of 13; 0.000 [0.000, 0.228] | 0 of 12; 0.000 [0.000, 0.242] | 0 of 7; 0.000 [0.000, 0.354] |
| logistic | 2 of 13; 0.154 [0.043, 0.422] | 6 of 12; 0.500 [0.254, 0.746] | 6 of 7; 0.857 [0.487, 0.974] |
| boosted | 1 of 13; 0.077 [0.014, 0.333] | 6 of 12; 0.500 [0.254, 0.746] | 6 of 7; 0.857 [0.487, 0.974] |
| rule | 1 of 13; 0.077 [0.014, 0.333] | 3 of 12; 0.250 [0.089, 0.532] | 3 of 7; 0.429 [0.158, 0.750] |

## V1 aggregation: positives versus sharing controls

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

Sharing controls contain at least one benign team assigned credential sharing, recorded by the simulator as benign_sharing_teams. This flag is label-side.

| Detector | Positive test runs | Sharing controls | All test controls | Restricted AUROC |
| --- | --- | --- | --- | --- |
| volume (family-independent) | 32 | 14 | 86 | 0.504 [0.346, 0.661] |
| logistic | 32 | 14 | 86 | 0.511 [0.332, 0.678] |
| boosted | 32 | 14 | 86 | 0.542 [0.369, 0.719] |
| rule | 32 | 14 | 86 | 0.442 [0.300, 0.621] |

## Independent controls

Seed: 20261120; split: by run; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive.

Benign/loud runs are separate test sweeps; the fitting and calibration counts above refer to their main by-run models. BOTH V1 aggregation detectors must flag every loud run at the calibrated threshold and score it strictly above every calibration control with benign_sharing_teams == 0. Logistic must also beat every calibration control. Loud counts below require all applicable bars. Boosted's all-controls strict bar is non-gating; its measured outcome has a separate row in controls.md. The rule baseline has no gating bars; its rows are diagnostics. Other loud rows are diagnostics. Shuffled AUROC mean and SE are descriptive: no pass/fail criterion is applied to permutations of the same dataset.

Independent benign test: 18 control / 0 positive; independent loud test: 0 control / 3 positive.

Binding loud gate: passed.

| Tier | Family | Detector | All-benign FPR | Loud meeting required bars | Shuffled AUROC mean (SE) | Permutations |
| --- | --- | --- | --- | --- | --- | --- |
| V0 | generic | volume (family-independent) | 1 of 18; 0.056 [0.010, 0.258] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.481 (0.015) | 20 |
| V0 | generic | logistic | 2 of 18; 0.111 [0.031, 0.328] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.495 (0.016) | 20 |
| V0 | generic | boosted | 1 of 18; 0.056 [0.010, 0.258] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.515 (0.015) | 20 |
| V0 | generic | rule | not available at this tier | not available at this tier | not available at this tier | 20 |
| V0 | aggregation | volume (family-independent) | 1 of 18; 0.056 [0.010, 0.258] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.481 (0.015) | 20 |
| V0 | aggregation | logistic | 1 of 18; 0.056 [0.010, 0.258] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.492 (0.015) | 20 |
| V0 | aggregation | boosted | 0 of 18; 0.000 [0.000, 0.176] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.517 (0.011) | 20 |
| V0 | aggregation | rule | not available at this tier | not available at this tier | not available at this tier | 20 |
| V0 | all | volume (family-independent) | 1 of 18; 0.056 [0.010, 0.258] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.481 (0.015) | 20 |
| V0 | all | logistic | 2 of 18; 0.111 [0.031, 0.328] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.497 (0.019) | 20 |
| V0 | all | boosted | 1 of 18; 0.056 [0.010, 0.258] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.518 (0.015) | 20 |
| V0 | all | rule | not available at this tier | not available at this tier | not available at this tier | 20 |
| V1 | generic | volume (family-independent) | 1 of 18; 0.056 [0.010, 0.258] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.481 (0.015) | 20 |
| V1 | generic | logistic | 2 of 18; 0.111 [0.031, 0.328] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.495 (0.016) | 20 |
| V1 | generic | boosted | 1 of 18; 0.056 [0.010, 0.258] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.515 (0.015) | 20 |
| V1 | generic | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | 20 |
| V1 | aggregation | volume (family-independent) | 1 of 18; 0.056 [0.010, 0.258] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.481 (0.015) | 20 |
| V1 | aggregation | logistic | 1 of 18; 0.056 [0.010, 0.258] Wilson | 3 of 3; 1.000 [0.439, 1.000] Wilson | 0.491 (0.014) | 20 |
| V1 | aggregation | boosted | 1 of 18; 0.056 [0.010, 0.258] Wilson | 3 of 3; 1.000 [0.439, 1.000] Wilson | 0.517 (0.016) | 20 |
| V1 | aggregation | rule | 0 of 18; 0.000 [0.000, 0.176] Wilson | not gated (no bars) | 0.503 (0.010) | 20 |
| V1 | all | volume (family-independent) | 1 of 18; 0.056 [0.010, 0.258] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.481 (0.015) | 20 |
| V1 | all | logistic | 1 of 18; 0.056 [0.010, 0.258] Wilson | 3 of 3; 1.000 [0.439, 1.000] Wilson | 0.494 (0.020) | 20 |
| V1 | all | boosted | 2 of 18; 0.111 [0.031, 0.328] Wilson | 3 of 3; 1.000 [0.439, 1.000] Wilson | 0.510 (0.017) | 20 |
| V1 | all | rule | 0 of 18; 0.000 [0.000, 0.176] Wilson | not gated (no bars) | 0.503 (0.010) | 20 |
| V2 | generic | volume (family-independent) | 1 of 18; 0.056 [0.010, 0.258] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.481 (0.015) | 20 |
| V2 | generic | logistic | 2 of 18; 0.111 [0.031, 0.328] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.497 (0.018) | 20 |
| V2 | generic | boosted | 1 of 18; 0.056 [0.010, 0.258] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.510 (0.014) | 20 |
| V2 | generic | rule | not available without aggregation features | not available without aggregation features | not available without aggregation features | 20 |
| V2 | aggregation | volume (family-independent) | 1 of 18; 0.056 [0.010, 0.258] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.481 (0.015) | 20 |
| V2 | aggregation | logistic | 1 of 18; 0.056 [0.010, 0.258] Wilson | 3 of 3; 1.000 [0.439, 1.000] Wilson | 0.491 (0.014) | 20 |
| V2 | aggregation | boosted | 1 of 18; 0.056 [0.010, 0.258] Wilson | 3 of 3; 1.000 [0.439, 1.000] Wilson | 0.517 (0.016) | 20 |
| V2 | aggregation | rule | 0 of 18; 0.000 [0.000, 0.176] Wilson | not gated (no bars) | 0.503 (0.010) | 20 |
| V2 | all | volume (family-independent) | 1 of 18; 0.056 [0.010, 0.258] Wilson | 0 of 3; 0.000 [0.000, 0.561] Wilson | 0.481 (0.015) | 20 |
| V2 | all | logistic | 1 of 18; 0.056 [0.010, 0.258] Wilson | 3 of 3; 1.000 [0.439, 1.000] Wilson | 0.494 (0.020) | 20 |
| V2 | all | boosted | 3 of 18; 0.167 [0.058, 0.392] Wilson | 3 of 3; 1.000 [0.439, 1.000] Wilson | 0.512 (0.015) | 20 |
| V2 | all | rule | 0 of 18; 0.000 [0.000, 0.176] Wilson | not gated (no bars) | 0.503 (0.010) | 20 |

Shuffled by-run splits: seed 20261120; fitting 141 control / 53 positive; calibration 61 control / 23 positive; test 86 control / 32 positive (same counts each permutation).
