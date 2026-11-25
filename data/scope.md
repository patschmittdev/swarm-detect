# Scope experiment

Seed: 20261120; dataset: scope; tier: V1.

Command: `swarmtrace scope --seed 20261120 --out DIR --workers N`.
DIR and N are execution choices and do not change recorded bytes.

Split: by run, stratified by kind and mistake rate; test fraction 0.3000; calibration fraction of training 0.3000; target FPR 0.0500.
Split and evaluation seeds use child_seed(seed, 97, ...). Bootstrap replicates: 200; confidence: 0.9500.

Realised test set sharing controls: 24; in-scope relays: 48.

Strict: scope violations are positive; in-scope relays are controls. Legacy: every relay is positive.

Grid: coordinated_groups=(1, 2, 3); channels=('message', 'shared_file', 'preplanned'); topologies=('hub', 'peer'); group_sizes=(2, 3, 5); mistake_rates=(0, 2, 5); control_repeats=9; offensive_repeats=1; identical_repeats=2; n_ticks=160.
Sharing rate: 10 percent; scope: on.

| Partition | Benign controls | Sharing controls | In-scope relays | Violation 1 | Violation 2 | Violation 5 |
| --- | --- | --- | --- | --- | --- | --- |
| all | 486 | 77 | 162 | 162 | 162 | 162 |
| fitting | 237 | 40 | 81 | 81 | 81 | 81 |
| calibration | 102 | 13 | 33 | 33 | 33 | 33 |
| test | 147 | 24 | 48 | 48 | 48 | 48 |

## all: split

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| fitting_runs | 561 | 561 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| calibration_runs | 234 | 234 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| calibration_controls | 135 | 102 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| test_runs | 339 | 339 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## aggregation-only reference: rule

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 5.0000 | 4.0000 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.8146 [0.7584, 0.8555] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.9121 [0.8767, 0.9447] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.4628 [0.3414, 0.5618] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.4618 [0.3527, 0.5900] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 7 of 144; 0.0486 [0.0237, 0.0969] Wilson | 43 of 192; 0.2240 [0.1707, 0.2880] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 5 of 195; 0.0256 [0.0110, 0.0586] Wilson | 5 of 147; 0.0340 [0.0146, 0.0771] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 1 of 24; 0.0417 [0.0074, 0.2024] Wilson | 5 of 24; 0.2083 [0.0924, 0.4047] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 4 of 48; 0.0833 [0.0329, 0.1955] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 5 of 48; 0.1042 [0.0453, 0.2217] Wilson | 13 of 48; 0.2708 [0.1657, 0.4100] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 5 of 48; 0.1042 [0.0453, 0.2217] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 2 of 48; 0.0417 [0.0115, 0.1398] Wilson | 12 of 48; 0.2500 [0.1492, 0.3878] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 2 of 48; 0.0417 [0.0115, 0.1398] Wilson | 16 of 64; 0.2500 [0.1601, 0.3682] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 2 of 48; 0.0417 [0.0115, 0.1398] Wilson | 14 of 64; 0.2188 [0.1350, 0.3343] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 3 of 48; 0.0625 [0.0215, 0.1684] Wilson | 13 of 64; 0.2031 [0.1227, 0.3171] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 3 of 65; 0.0462 [0.0158, 0.1271] Wilson | 1 of 49; 0.0204 [0.0036, 0.1069] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 1 of 65; 0.0154 [0.0027, 0.0821] Wilson | 1 of 49; 0.0204 [0.0036, 0.1069] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 1 of 65; 0.0154 [0.0027, 0.0821] Wilson | 3 of 49; 0.0612 [0.0210, 0.1652] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.4588 [0.3141, 0.5747] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.4588 [0.3185, 0.5700] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.5153 [0.4047, 0.6265] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.5380 [0.4274, 0.6398] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.4826 [0.3701, 0.5903] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 0.5252 [0.4222, 0.6439] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.4733 [0.3014, 0.6644] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.4167 [0.2726, 0.5743] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.6576 [0.5258, 0.7930] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 13 of 48; 0.2708 [0.1657, 0.4100] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## aggregation-only reference: scope_rule

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | nan; not available: no scope_rule column at this context | nan; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | nan [nan, nan] bootstrap; 0 positive / 0 control; bootstrap 0 of 200; not available: no scope_rule column at this context | nan [nan, nan] bootstrap; 0 positive / 0 control; bootstrap 0 of 200; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | nan [nan, nan] bootstrap; 0 positive / 0 control; bootstrap 0 of 200; not available: no scope_rule column at this context | nan [nan, nan] bootstrap; 0 positive / 0 control; bootstrap 0 of 200; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | nan [nan, nan] bootstrap; 0 positive / 0 control; bootstrap 0 of 200; not available: no scope_rule column at this context; reported, not gated | nan [nan, nan] bootstrap; 0 positive / 0 control; bootstrap 0 of 200; not available: no scope_rule column at this context; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | nan [nan, nan] bootstrap; 0 positive / 0 control; bootstrap 0 of 200; not available: no scope_rule column at this context | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | nan [nan, nan] bootstrap; 0 positive / 0 control; bootstrap 0 of 200; not available: no scope_rule column at this context | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | nan [nan, nan] bootstrap; 0 positive / 0 control; bootstrap 0 of 200; not available: no scope_rule column at this context | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | nan [nan, nan] bootstrap; 0 positive / 0 control; bootstrap 0 of 200; not available: no scope_rule column at this context | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | nan [nan, nan] bootstrap; 0 positive / 0 control; bootstrap 0 of 200; not available: no scope_rule column at this context | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | nan [nan, nan] bootstrap; 0 positive / 0 control; bootstrap 0 of 200; not available: no scope_rule column at this context | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | nan [nan, nan] bootstrap; 0 positive / 0 control; bootstrap 0 of 200; not available: no scope_rule column at this context | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 0 of 0; nan [nan, nan] Wilson; not available: no scope_rule column at this context | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## aggregation-only reference: files_rule

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 6.0000 | 7.0000 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.7933 [0.7367, 0.8343] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.7259 [0.6838, 0.7733] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.7930 [0.7043, 0.8668] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.7190 [0.6310, 0.7933] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 48 of 144; 0.3333 [0.2616, 0.4138] Wilson | 34 of 192; 0.1771 [0.1296, 0.2373] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 2 of 195; 0.0103 [0.0028, 0.0366] Wilson | 0 of 147; 0.0000 [0.0000, 0.0255] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 2 of 123; 0.0163 [0.0045, 0.0574] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 0 of 24; 0.0000 [0.0000, 0.1380] Wilson | 0 of 24; 0.0000 [0.0000, 0.1380] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 6 of 48; 0.1250 [0.0586, 0.2470] Wilson | 1 of 48; 0.0208 [0.0037, 0.1090] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 42 of 48; 0.8750 [0.7530, 0.9414] Wilson | 33 of 48; 0.6875 [0.5467, 0.8005] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 12 of 48; 0.2500 [0.1492, 0.3878] Wilson | 11 of 64; 0.1719 [0.0988, 0.2821] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 17 of 48; 0.3542 [0.2343, 0.4956] Wilson | 12 of 64; 0.1875 [0.1106, 0.2997] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 19 of 48; 0.3958 [0.2702, 0.5369] Wilson | 11 of 64; 0.1719 [0.0988, 0.2821] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 2 of 65; 0.0308 [0.0085, 0.1054] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.4970 [0.3619, 0.6138] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.4970 [0.3931, 0.6133] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.7836 [0.7254, 0.8524] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.6430 [0.5289, 0.7397] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.7222 [0.6310, 0.8108] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 0.9857 [0.9688, 0.9961] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.7988 [0.7005, 0.8986] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.7663 [0.6287, 0.8797] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.7917 [0.6835, 0.8870] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## aggregation-only reference: logistic

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 0.8141 | 0.9793 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.8000 [0.7539, 0.8404] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.9180 [0.8895, 0.9505] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.4829 [0.3540, 0.5984] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.4980 [0.3819, 0.6118] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 18 of 144; 0.1250 [0.0806, 0.1889] Wilson | 30 of 192; 0.1562 [0.1117, 0.2143] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 14 of 195; 0.0718 [0.0432, 0.1169] Wilson | 5 of 147; 0.0340 [0.0146, 0.0771] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 5 of 24; 0.2083 [0.0924, 0.4047] Wilson | 5 of 24; 0.2083 [0.0924, 0.4047] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 9 of 48; 0.1875 [0.1019, 0.3194] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 5 of 48; 0.1042 [0.0453, 0.2217] Wilson | 6 of 48; 0.1250 [0.0586, 0.2470] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 7 of 48; 0.1458 [0.0725, 0.2717] Wilson | 10 of 48; 0.2083 [0.1173, 0.3426] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 6 of 48; 0.1250 [0.0586, 0.2470] Wilson | 4 of 48; 0.0833 [0.0329, 0.1955] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 3 of 48; 0.0625 [0.0215, 0.1684] Wilson | 9 of 64; 0.1406 [0.0758, 0.2462] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 5 of 48; 0.1042 [0.0453, 0.2217] Wilson | 9 of 64; 0.1406 [0.0758, 0.2462] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 10 of 48; 0.2083 [0.1173, 0.3426] Wilson | 12 of 64; 0.1875 [0.1106, 0.2997] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 7 of 65; 0.1077 [0.0532, 0.2060] Wilson | 3 of 49; 0.0612 [0.0210, 0.1652] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 3 of 65; 0.0462 [0.0158, 0.1271] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 4 of 65; 0.0615 [0.0242, 0.1478] Wilson | 2 of 49; 0.0408 [0.0113, 0.1371] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.5391 [0.3922, 0.6963] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.5321 [0.4006, 0.6789] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.4460 [0.3471, 0.5432] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.4112 [0.2965, 0.5282] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.4950 [0.3922, 0.5943] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 0.4316 [0.3454, 0.5328] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.4401 [0.2840, 0.5970] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.3796 [0.2242, 0.5497] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.5241 [0.3728, 0.6642] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 10 of 48; 0.2083 [0.1173, 0.3426] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## aggregation-only reference: boosted

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 0.8121 | 0.9277 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.7937 [0.7420, 0.8330] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.9197 [0.8812, 0.9530] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.4583 [0.3300, 0.5723] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.5080 [0.3819, 0.6372] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 11 of 144; 0.0764 [0.0432, 0.1316] Wilson | 93 of 192; 0.4844 [0.4147, 0.5547] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 14 of 195; 0.0718 [0.0432, 0.1169] Wilson | 12 of 147; 0.0816 [0.0473, 0.1373] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 5 of 24; 0.2083 [0.0924, 0.4047] Wilson | 12 of 24; 0.5000 [0.3143, 0.6857] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 9 of 48; 0.1875 [0.1019, 0.3194] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 4 of 48; 0.0833 [0.0329, 0.1955] Wilson | 21 of 48; 0.4375 [0.3070, 0.5772] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 7 of 48; 0.1458 [0.0725, 0.2717] Wilson | 25 of 48; 0.5208 [0.3833, 0.6553] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 19 of 48; 0.3958 [0.2702, 0.5369] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 4 of 48; 0.0833 [0.0329, 0.1955] Wilson | 35 of 64; 0.5469 [0.4257, 0.6627] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 4 of 48; 0.0833 [0.0329, 0.1955] Wilson | 25 of 64; 0.3906 [0.2806, 0.5131] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 3 of 48; 0.0625 [0.0215, 0.1684] Wilson | 33 of 64; 0.5156 [0.3958, 0.6337] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 5 of 65; 0.0769 [0.0333, 0.1678] Wilson | 2 of 49; 0.0408 [0.0113, 0.1371] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 5 of 65; 0.0769 [0.0333, 0.1678] Wilson | 2 of 49; 0.0408 [0.0113, 0.1371] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 4 of 65; 0.0615 [0.0242, 0.1478] Wilson | 8 of 49; 0.1633 [0.0851, 0.2904] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.5269 [0.3698, 0.6781] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.5451 [0.3889, 0.6933] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.4327 [0.3362, 0.5333] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.4110 [0.2942, 0.5079] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.5395 [0.4140, 0.6389] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 0.3474 [0.2441, 0.4942] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.4023 [0.2499, 0.5437] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.3366 [0.1853, 0.4786] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.5553 [0.3698, 0.7126] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 28 of 48; 0.5833 [0.4428, 0.7115] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## C0: rule

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 5.0000 | 4.0000 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.8146 [0.7639, 0.8612] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.9121 [0.8724, 0.9496] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.4628 [0.3565, 0.5722] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.4618 [0.3434, 0.5669] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 7 of 144; 0.0486 [0.0237, 0.0969] Wilson | 43 of 192; 0.2240 [0.1707, 0.2880] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 5 of 195; 0.0256 [0.0110, 0.0586] Wilson | 5 of 147; 0.0340 [0.0146, 0.0771] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 1 of 24; 0.0417 [0.0074, 0.2024] Wilson | 5 of 24; 0.2083 [0.0924, 0.4047] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 4 of 48; 0.0833 [0.0329, 0.1955] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 5 of 48; 0.1042 [0.0453, 0.2217] Wilson | 13 of 48; 0.2708 [0.1657, 0.4100] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 5 of 48; 0.1042 [0.0453, 0.2217] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 2 of 48; 0.0417 [0.0115, 0.1398] Wilson | 12 of 48; 0.2500 [0.1492, 0.3878] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 2 of 48; 0.0417 [0.0115, 0.1398] Wilson | 16 of 64; 0.2500 [0.1601, 0.3682] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 2 of 48; 0.0417 [0.0115, 0.1398] Wilson | 14 of 64; 0.2188 [0.1350, 0.3343] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 3 of 48; 0.0625 [0.0215, 0.1684] Wilson | 13 of 64; 0.2031 [0.1227, 0.3171] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 3 of 65; 0.0462 [0.0158, 0.1271] Wilson | 1 of 49; 0.0204 [0.0036, 0.1069] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 1 of 65; 0.0154 [0.0027, 0.0821] Wilson | 1 of 49; 0.0204 [0.0036, 0.1069] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 1 of 65; 0.0154 [0.0027, 0.0821] Wilson | 3 of 49; 0.0612 [0.0210, 0.1652] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.4588 [0.3297, 0.5718] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.4588 [0.3336, 0.5990] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.5153 [0.4050, 0.6102] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.5380 [0.4429, 0.6576] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.4826 [0.3775, 0.6042] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 0.5252 [0.4153, 0.6351] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.4733 [0.3078, 0.6856] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.4167 [0.2493, 0.5906] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.6576 [0.4931, 0.8010] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 13 of 48; 0.2708 [0.1657, 0.4100] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## C0: scope_rule

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 4.0000 | 4.0000 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.9405 [0.9210, 0.9597] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.9590 [0.9363, 0.9746] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.8367 [0.7715, 0.8894] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.7486 [0.6841, 0.8152] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 88 of 144; 0.6111 [0.5296, 0.6869] Wilson | 88 of 192; 0.4583 [0.3894, 0.5289] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 0 of 195; 0.0000 [0.0000, 0.0193] Wilson | 0 of 147; 0.0000 [0.0000, 0.0255] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 0 of 24; 0.0000 [0.0000, 0.1380] Wilson | 0 of 24; 0.0000 [0.0000, 0.1380] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 14 of 48; 0.2917 [0.1824, 0.4318] Wilson | 14 of 48; 0.2917 [0.1824, 0.4318] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 26 of 48; 0.5417 [0.4029, 0.6742] Wilson | 26 of 48; 0.5417 [0.4029, 0.6742] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 28 of 48; 0.5833 [0.4428, 0.7115] Wilson | 28 of 64; 0.4375 [0.3229, 0.5591] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 29 of 48; 0.6042 [0.4631, 0.7298] Wilson | 29 of 64; 0.4531 [0.3373, 0.5743] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 31 of 48; 0.6458 [0.5044, 0.7657] Wilson | 31 of 64; 0.4844 [0.3663, 0.6042] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.4844 [0.3528, 0.5991] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.4844 [0.3550, 0.6260] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.8400 [0.7872, 0.8919] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.6749 [0.5890, 0.7807] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.8451 [0.7898, 0.9087] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 1.0000 [1.0000, 1.0000] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.7708 [0.6782, 0.8568] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.8717 [0.7949, 0.9356] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.8724 [0.8004, 0.9440] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## C0: files_rule

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 6.0000 | 7.0000 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.7933 [0.7430, 0.8433] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.7259 [0.6738, 0.7698] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.7930 [0.7141, 0.8622] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.7190 [0.6471, 0.8022] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 48 of 144; 0.3333 [0.2616, 0.4138] Wilson | 34 of 192; 0.1771 [0.1296, 0.2373] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 2 of 195; 0.0103 [0.0028, 0.0366] Wilson | 0 of 147; 0.0000 [0.0000, 0.0255] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 2 of 123; 0.0163 [0.0045, 0.0574] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 0 of 24; 0.0000 [0.0000, 0.1380] Wilson | 0 of 24; 0.0000 [0.0000, 0.1380] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 6 of 48; 0.1250 [0.0586, 0.2470] Wilson | 1 of 48; 0.0208 [0.0037, 0.1090] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 42 of 48; 0.8750 [0.7530, 0.9414] Wilson | 33 of 48; 0.6875 [0.5467, 0.8005] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 12 of 48; 0.2500 [0.1492, 0.3878] Wilson | 11 of 64; 0.1719 [0.0988, 0.2821] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 17 of 48; 0.3542 [0.2343, 0.4956] Wilson | 12 of 64; 0.1875 [0.1106, 0.2997] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 19 of 48; 0.3958 [0.2702, 0.5369] Wilson | 11 of 64; 0.1719 [0.0988, 0.2821] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 2 of 65; 0.0308 [0.0085, 0.1054] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.4970 [0.3623, 0.6269] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.4970 [0.3537, 0.6026] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.7836 [0.7195, 0.8465] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.6430 [0.5335, 0.7507] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.7222 [0.6229, 0.8087] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 0.9857 [0.9689, 0.9954] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.7988 [0.6947, 0.8998] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.7663 [0.6275, 0.8811] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.7917 [0.6627, 0.8948] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## C0: logistic

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 0.5807 | 0.9377 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.9409 [0.9241, 0.9600] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.9596 [0.9389, 0.9757] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.8585 [0.8046, 0.9116] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.7523 [0.6818, 0.8350] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 98 of 144; 0.6806 [0.6006, 0.7512] Wilson | 102 of 192; 0.5312 [0.4607, 0.6005] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 11 of 195; 0.0564 [0.0318, 0.0982] Wilson | 2 of 147; 0.0136 [0.0037, 0.0482] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 2 of 24; 0.0833 [0.0232, 0.2585] Wilson | 2 of 24; 0.0833 [0.0232, 0.2585] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 9 of 48; 0.1875 [0.1019, 0.3194] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 17 of 48; 0.3542 [0.2343, 0.4956] Wilson | 14 of 48; 0.2917 [0.1824, 0.4318] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 33 of 48; 0.6875 [0.5467, 0.8005] Wilson | 32 of 48; 0.6667 [0.5254, 0.7832] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 32 of 48; 0.6667 [0.5254, 0.7832] Wilson | 34 of 64; 0.5312 [0.4107, 0.6482] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 32 of 48; 0.6667 [0.5254, 0.7832] Wilson | 32 of 64; 0.5000 [0.3810, 0.6190] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 34 of 48; 0.7083 [0.5682, 0.8176] Wilson | 36 of 64; 0.5625 [0.4409, 0.6771] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 6 of 65; 0.0923 [0.0430, 0.1871] Wilson | 2 of 49; 0.0408 [0.0113, 0.1371] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 4 of 65; 0.0615 [0.0242, 0.1478] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 1 of 65; 0.0154 [0.0027, 0.0821] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.5612 [0.4322, 0.7132] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.5395 [0.4092, 0.6672] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.8307 [0.7718, 0.8900] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.6194 [0.4873, 0.7329] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.8728 [0.7873, 0.9293] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 1.0000 [1.0000, 1.0000] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.7773 [0.6522, 0.8881] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.8229 [0.7109, 0.9076] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.8854 [0.8060, 0.9635] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 8 of 48; 0.1667 [0.0870, 0.2958] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## C0: boosted

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 0.6865 | 0.9216 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.9236 [0.9013, 0.9456] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.9590 [0.9361, 0.9770] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.8079 [0.7285, 0.8809] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.7487 [0.6620, 0.8242] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 90 of 144; 0.6250 [0.5436, 0.6999] Wilson | 133 of 192; 0.6927 [0.6242, 0.7537] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 7 of 195; 0.0359 [0.0175, 0.0722] Wilson | 9 of 147; 0.0612 [0.0325, 0.1123] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 2 of 24; 0.0833 [0.0232, 0.2585] Wilson | 9 of 24; 0.3750 [0.2116, 0.5729] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 5 of 48; 0.1042 [0.0453, 0.2217] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 16 of 48; 0.3333 [0.2168, 0.4746] Wilson | 25 of 48; 0.5208 [0.3833, 0.6553] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 26 of 48; 0.5417 [0.4029, 0.6742] Wilson | 37 of 48; 0.7708 [0.6346, 0.8669] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 29 of 48; 0.6042 [0.4631, 0.7298] Wilson | 47 of 64; 0.7344 [0.6152, 0.8270] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 30 of 48; 0.6250 [0.4836, 0.7478] Wilson | 43 of 64; 0.6719 [0.5500, 0.7743] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 31 of 48; 0.6458 [0.5044, 0.7657] Wilson | 43 of 64; 0.6719 [0.5500, 0.7743] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 1 of 65; 0.0154 [0.0027, 0.0821] Wilson | 2 of 49; 0.0408 [0.0113, 0.1371] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 3 of 65; 0.0462 [0.0158, 0.1271] Wilson | 1 of 49; 0.0204 [0.0036, 0.1069] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 3 of 65; 0.0462 [0.0158, 0.1271] Wilson | 6 of 49; 0.1224 [0.0573, 0.2424] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.5443 [0.4158, 0.6925] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.5938 [0.4565, 0.7131] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.7857 [0.7263, 0.8394] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.6042 [0.4856, 0.7243] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.7530 [0.6361, 0.8562] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 1.0000 [1.0000, 1.0000] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.7565 [0.6289, 0.8640] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.7786 [0.6457, 0.8959] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.8177 [0.6965, 0.9038] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 23 of 48; 0.4792 [0.3447, 0.6167] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## C1: rule

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 5.0000 | 4.0000 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.8146 [0.7732, 0.8526] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.9121 [0.8722, 0.9467] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.4628 [0.3515, 0.5987] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.4618 [0.3736, 0.5757] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 7 of 144; 0.0486 [0.0237, 0.0969] Wilson | 43 of 192; 0.2240 [0.1707, 0.2880] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 5 of 195; 0.0256 [0.0110, 0.0586] Wilson | 5 of 147; 0.0340 [0.0146, 0.0771] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 1 of 24; 0.0417 [0.0074, 0.2024] Wilson | 5 of 24; 0.2083 [0.0924, 0.4047] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 4 of 48; 0.0833 [0.0329, 0.1955] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 5 of 48; 0.1042 [0.0453, 0.2217] Wilson | 13 of 48; 0.2708 [0.1657, 0.4100] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 5 of 48; 0.1042 [0.0453, 0.2217] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 2 of 48; 0.0417 [0.0115, 0.1398] Wilson | 12 of 48; 0.2500 [0.1492, 0.3878] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 2 of 48; 0.0417 [0.0115, 0.1398] Wilson | 16 of 64; 0.2500 [0.1601, 0.3682] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 2 of 48; 0.0417 [0.0115, 0.1398] Wilson | 14 of 64; 0.2188 [0.1350, 0.3343] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 3 of 48; 0.0625 [0.0215, 0.1684] Wilson | 13 of 64; 0.2031 [0.1227, 0.3171] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 3 of 65; 0.0462 [0.0158, 0.1271] Wilson | 1 of 49; 0.0204 [0.0036, 0.1069] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 1 of 65; 0.0154 [0.0027, 0.0821] Wilson | 1 of 49; 0.0204 [0.0036, 0.1069] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 1 of 65; 0.0154 [0.0027, 0.0821] Wilson | 3 of 49; 0.0612 [0.0210, 0.1652] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.4588 [0.3458, 0.5890] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.4588 [0.3366, 0.5838] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.5153 [0.4207, 0.5952] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.5380 [0.4305, 0.6520] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.4826 [0.3694, 0.5845] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 0.5252 [0.4083, 0.6110] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.4733 [0.3112, 0.6149] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.4167 [0.2402, 0.6094] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.6576 [0.5073, 0.7761] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 13 of 48; 0.2708 [0.1657, 0.4100] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## C1: scope_rule

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 4.0000 | 4.0000 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.9405 [0.9194, 0.9584] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.9590 [0.9404, 0.9755] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.8367 [0.7717, 0.8944] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.7486 [0.6847, 0.8082] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 88 of 144; 0.6111 [0.5296, 0.6869] Wilson | 88 of 192; 0.4583 [0.3894, 0.5289] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 0 of 195; 0.0000 [0.0000, 0.0193] Wilson | 0 of 147; 0.0000 [0.0000, 0.0255] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 0 of 24; 0.0000 [0.0000, 0.1380] Wilson | 0 of 24; 0.0000 [0.0000, 0.1380] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 14 of 48; 0.2917 [0.1824, 0.4318] Wilson | 14 of 48; 0.2917 [0.1824, 0.4318] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 26 of 48; 0.5417 [0.4029, 0.6742] Wilson | 26 of 48; 0.5417 [0.4029, 0.6742] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 28 of 48; 0.5833 [0.4428, 0.7115] Wilson | 28 of 64; 0.4375 [0.3229, 0.5591] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 29 of 48; 0.6042 [0.4631, 0.7298] Wilson | 29 of 64; 0.4531 [0.3373, 0.5743] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 31 of 48; 0.6458 [0.5044, 0.7657] Wilson | 31 of 64; 0.4844 [0.3663, 0.6042] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.4844 [0.3622, 0.5903] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.4844 [0.3345, 0.6084] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.8400 [0.7956, 0.8906] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.6749 [0.5793, 0.7640] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.8451 [0.7738, 0.9061] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 1.0000 [1.0000, 1.0000] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.7708 [0.6584, 0.8724] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.8717 [0.7929, 0.9343] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.8724 [0.7891, 0.9427] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## C1: files_rule

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 6.0000 | 7.0000 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.7933 [0.7425, 0.8424] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.7259 [0.6705, 0.7679] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.7930 [0.7160, 0.8720] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.7190 [0.6352, 0.7980] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 48 of 144; 0.3333 [0.2616, 0.4138] Wilson | 34 of 192; 0.1771 [0.1296, 0.2373] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 2 of 195; 0.0103 [0.0028, 0.0366] Wilson | 0 of 147; 0.0000 [0.0000, 0.0255] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 2 of 123; 0.0163 [0.0045, 0.0574] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 0 of 24; 0.0000 [0.0000, 0.1380] Wilson | 0 of 24; 0.0000 [0.0000, 0.1380] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 6 of 48; 0.1250 [0.0586, 0.2470] Wilson | 1 of 48; 0.0208 [0.0037, 0.1090] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 42 of 48; 0.8750 [0.7530, 0.9414] Wilson | 33 of 48; 0.6875 [0.5467, 0.8005] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 12 of 48; 0.2500 [0.1492, 0.3878] Wilson | 11 of 64; 0.1719 [0.0988, 0.2821] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 17 of 48; 0.3542 [0.2343, 0.4956] Wilson | 12 of 64; 0.1875 [0.1106, 0.2997] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 19 of 48; 0.3958 [0.2702, 0.5369] Wilson | 11 of 64; 0.1719 [0.0988, 0.2821] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 2 of 65; 0.0308 [0.0085, 0.1054] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.4970 [0.3810, 0.6202] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.4970 [0.3723, 0.6163] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.7836 [0.7265, 0.8399] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.6430 [0.5275, 0.7440] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.7222 [0.6217, 0.8110] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 0.9857 [0.9666, 0.9957] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.7988 [0.6562, 0.8945] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.7663 [0.6178, 0.8750] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.7917 [0.6620, 0.8803] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## C1: logistic

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 0.5807 | 0.9377 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.9409 [0.9173, 0.9602] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.9596 [0.9403, 0.9782] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.8585 [0.7992, 0.9098] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.7523 [0.6776, 0.8269] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 98 of 144; 0.6806 [0.6006, 0.7512] Wilson | 102 of 192; 0.5312 [0.4607, 0.6005] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 11 of 195; 0.0564 [0.0318, 0.0982] Wilson | 2 of 147; 0.0136 [0.0037, 0.0482] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 2 of 24; 0.0833 [0.0232, 0.2585] Wilson | 2 of 24; 0.0833 [0.0232, 0.2585] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 9 of 48; 0.1875 [0.1019, 0.3194] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 17 of 48; 0.3542 [0.2343, 0.4956] Wilson | 14 of 48; 0.2917 [0.1824, 0.4318] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 33 of 48; 0.6875 [0.5467, 0.8005] Wilson | 32 of 48; 0.6667 [0.5254, 0.7832] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 32 of 48; 0.6667 [0.5254, 0.7832] Wilson | 34 of 64; 0.5312 [0.4107, 0.6482] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 32 of 48; 0.6667 [0.5254, 0.7832] Wilson | 32 of 64; 0.5000 [0.3810, 0.6190] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 34 of 48; 0.7083 [0.5682, 0.8176] Wilson | 36 of 64; 0.5625 [0.4409, 0.6771] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 6 of 65; 0.0923 [0.0430, 0.1871] Wilson | 2 of 49; 0.0408 [0.0113, 0.1371] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 4 of 65; 0.0615 [0.0242, 0.1478] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 1 of 65; 0.0154 [0.0027, 0.0821] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.5612 [0.4300, 0.7196] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.5395 [0.3937, 0.6715] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.8307 [0.7734, 0.8718] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.6194 [0.4945, 0.7144] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.8728 [0.7977, 0.9275] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 1.0000 [1.0000, 1.0000] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.7773 [0.6722, 0.8809] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.8229 [0.7291, 0.9167] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.8854 [0.8034, 0.9598] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 8 of 48; 0.1667 [0.0870, 0.2958] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## C1: boosted

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 0.6865 | 0.9216 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.9236 [0.8927, 0.9452] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.9590 [0.9396, 0.9757] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.8079 [0.7418, 0.8712] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.7487 [0.6519, 0.8241] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 90 of 144; 0.6250 [0.5436, 0.6999] Wilson | 133 of 192; 0.6927 [0.6242, 0.7537] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 7 of 195; 0.0359 [0.0175, 0.0722] Wilson | 9 of 147; 0.0612 [0.0325, 0.1123] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 2 of 24; 0.0833 [0.0232, 0.2585] Wilson | 9 of 24; 0.3750 [0.2116, 0.5729] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 5 of 48; 0.1042 [0.0453, 0.2217] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 16 of 48; 0.3333 [0.2168, 0.4746] Wilson | 25 of 48; 0.5208 [0.3833, 0.6553] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 26 of 48; 0.5417 [0.4029, 0.6742] Wilson | 37 of 48; 0.7708 [0.6346, 0.8669] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 29 of 48; 0.6042 [0.4631, 0.7298] Wilson | 47 of 64; 0.7344 [0.6152, 0.8270] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 30 of 48; 0.6250 [0.4836, 0.7478] Wilson | 43 of 64; 0.6719 [0.5500, 0.7743] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 31 of 48; 0.6458 [0.5044, 0.7657] Wilson | 43 of 64; 0.6719 [0.5500, 0.7743] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 1 of 65; 0.0154 [0.0027, 0.0821] Wilson | 2 of 49; 0.0408 [0.0113, 0.1371] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 3 of 65; 0.0462 [0.0158, 0.1271] Wilson | 1 of 49; 0.0204 [0.0036, 0.1069] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 3 of 65; 0.0462 [0.0158, 0.1271] Wilson | 6 of 49; 0.1224 [0.0573, 0.2424] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.5443 [0.3995, 0.6905] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.5938 [0.4570, 0.7270] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.7857 [0.7216, 0.8494] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.6042 [0.4794, 0.7278] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.7530 [0.6584, 0.8421] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 1.0000 [1.0000, 1.0000] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.7565 [0.6503, 0.8744] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.7786 [0.6706, 0.8867] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.8177 [0.6965, 0.9012] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 23 of 48; 0.4792 [0.3447, 0.6167] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## C2: rule

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 5.0000 | 4.0000 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.8146 [0.7664, 0.8571] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.9121 [0.8731, 0.9470] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.4628 [0.3439, 0.5844] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.4618 [0.3509, 0.5767] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 7 of 144; 0.0486 [0.0237, 0.0969] Wilson | 43 of 192; 0.2240 [0.1707, 0.2880] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 5 of 195; 0.0256 [0.0110, 0.0586] Wilson | 5 of 147; 0.0340 [0.0146, 0.0771] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 1 of 24; 0.0417 [0.0074, 0.2024] Wilson | 5 of 24; 0.2083 [0.0924, 0.4047] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 4 of 48; 0.0833 [0.0329, 0.1955] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 5 of 48; 0.1042 [0.0453, 0.2217] Wilson | 13 of 48; 0.2708 [0.1657, 0.4100] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 5 of 48; 0.1042 [0.0453, 0.2217] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 2 of 48; 0.0417 [0.0115, 0.1398] Wilson | 12 of 48; 0.2500 [0.1492, 0.3878] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 2 of 48; 0.0417 [0.0115, 0.1398] Wilson | 16 of 64; 0.2500 [0.1601, 0.3682] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 2 of 48; 0.0417 [0.0115, 0.1398] Wilson | 14 of 64; 0.2188 [0.1350, 0.3343] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 3 of 48; 0.0625 [0.0215, 0.1684] Wilson | 13 of 64; 0.2031 [0.1227, 0.3171] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 3 of 65; 0.0462 [0.0158, 0.1271] Wilson | 1 of 49; 0.0204 [0.0036, 0.1069] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 1 of 65; 0.0154 [0.0027, 0.0821] Wilson | 1 of 49; 0.0204 [0.0036, 0.1069] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 1 of 65; 0.0154 [0.0027, 0.0821] Wilson | 3 of 49; 0.0612 [0.0210, 0.1652] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.4588 [0.3050, 0.5869] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.4588 [0.3306, 0.5821] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.5153 [0.4202, 0.6083] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.5380 [0.4309, 0.6589] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.4826 [0.3717, 0.6101] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 0.5252 [0.4211, 0.6485] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.4733 [0.3137, 0.6760] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.4167 [0.2578, 0.5893] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.6576 [0.5160, 0.7722] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 13 of 48; 0.2708 [0.1657, 0.4100] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## C2: scope_rule

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 1.0000 | 0.0000 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.9894 [0.9814, 0.9956] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.8937 [0.8639, 0.9230] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.9818 [0.9616, 0.9958] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.8695 [0.8251, 0.9141] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 102 of 144; 0.7083 [0.6295, 0.7764] Wilson | 153 of 192; 0.7969 [0.7344, 0.8477] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 1 of 195; 0.0051 [0.0009, 0.0285] Wilson | 3 of 147; 0.0204 [0.0070, 0.0583] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 0 of 24; 0.0000 [0.0000, 0.1380] Wilson | 3 of 24; 0.1250 [0.0434, 0.3100] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 1 of 48; 0.0208 [0.0037, 0.1090] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 6 of 48; 0.1250 [0.0586, 0.2470] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 32 of 48; 0.6667 [0.5254, 0.7832] Wilson | 48 of 64; 0.7500 [0.6318, 0.8399] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 33 of 48; 0.6875 [0.5467, 0.8005] Wilson | 52 of 64; 0.8125 [0.7003, 0.8894] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 37 of 48; 0.7708 [0.6346, 0.8669] Wilson | 53 of 64; 0.8281 [0.7179, 0.9012] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 1 of 65; 0.0154 [0.0027, 0.0821] Wilson | 3 of 49; 0.0612 [0.0210, 0.1652] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.5326 [0.4502, 0.6155] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.5326 [0.4452, 0.6060] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.9661 [0.9377, 0.9867] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.9076 [0.8507, 0.9653] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.9907 [0.9720, 1.0000] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 1.0000 [1.0000, 1.0000] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 1.0000 [1.0000, 1.0000] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.9609 [0.9219, 0.9909] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.9460 [0.8932, 0.9883] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 9 of 48; 0.1875 [0.1019, 0.3194] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## C2: files_rule

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 6.0000 | 7.0000 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.7933 [0.7459, 0.8386] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.7259 [0.6824, 0.7779] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.7930 [0.7215, 0.8640] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.7190 [0.6185, 0.7993] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 48 of 144; 0.3333 [0.2616, 0.4138] Wilson | 34 of 192; 0.1771 [0.1296, 0.2373] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 2 of 195; 0.0103 [0.0028, 0.0366] Wilson | 0 of 147; 0.0000 [0.0000, 0.0255] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 2 of 123; 0.0163 [0.0045, 0.0574] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 0 of 24; 0.0000 [0.0000, 0.1380] Wilson | 0 of 24; 0.0000 [0.0000, 0.1380] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 6 of 48; 0.1250 [0.0586, 0.2470] Wilson | 1 of 48; 0.0208 [0.0037, 0.1090] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 42 of 48; 0.8750 [0.7530, 0.9414] Wilson | 33 of 48; 0.6875 [0.5467, 0.8005] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 12 of 48; 0.2500 [0.1492, 0.3878] Wilson | 11 of 64; 0.1719 [0.0988, 0.2821] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 17 of 48; 0.3542 [0.2343, 0.4956] Wilson | 12 of 64; 0.1875 [0.1106, 0.2997] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 19 of 48; 0.3958 [0.2702, 0.5369] Wilson | 11 of 64; 0.1719 [0.0988, 0.2821] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 2 of 65; 0.0308 [0.0085, 0.1054] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.4970 [0.3728, 0.6133] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.4970 [0.3813, 0.6230] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.7836 [0.7195, 0.8404] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.6430 [0.5415, 0.7566] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.7222 [0.6296, 0.8088] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 0.9857 [0.9737, 0.9961] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 0.7988 [0.6992, 0.9024] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.7663 [0.6249, 0.8757] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.7917 [0.6672, 0.8939] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## C2: logistic

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 0.4431 | 0.8629 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.9874 [0.9779, 0.9948] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.9747 [0.9583, 0.9878] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.9796 [0.9525, 1.0000] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.8451 [0.7883, 0.8983] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 140 of 144; 0.9722 [0.9308, 0.9891] Wilson | 146 of 192; 0.7604 [0.6953, 0.8153] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 11 of 195; 0.0564 [0.0318, 0.0982] Wilson | 6 of 147; 0.0408 [0.0188, 0.0862] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 2 of 24; 0.0833 [0.0232, 0.2585] Wilson | 6 of 24; 0.2500 [0.1200, 0.4490] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 9 of 48; 0.1875 [0.1019, 0.3194] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 44 of 48; 0.9167 [0.8045, 0.9671] Wilson | 35 of 48; 0.7292 [0.5900, 0.8343] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 46 of 48; 0.9583 [0.8602, 0.9885] Wilson | 47 of 64; 0.7344 [0.6152, 0.8270] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 47 of 48; 0.9792 [0.8910, 0.9963] Wilson | 51 of 64; 0.7969 [0.6829, 0.8773] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 47 of 48; 0.9792 [0.8910, 0.9963] Wilson | 48 of 64; 0.7500 [0.6318, 0.8399] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 1 of 49; 0.0204 [0.0036, 0.1069] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 4 of 65; 0.0615 [0.0242, 0.1478] Wilson | 0 of 49; 0.0000 [0.0000, 0.0727] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 7 of 65; 0.1077 [0.0532, 0.2060] Wilson | 5 of 49; 0.1020 [0.0444, 0.2176] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.6159 [0.4973, 0.7587] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.5334 [0.4140, 0.6809] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.9591 [0.9210, 0.9832] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.8941 [0.8142, 0.9486] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.9831 [0.9517, 1.0000] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 1.0000 [1.0000, 1.0000] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 1.0000 [1.0000, 1.0000] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.9609 [0.9217, 0.9935] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.9336 [0.8606, 0.9832] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 15 of 48; 0.3125 [0.1995, 0.4533] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## C2: boosted

Seed: 20261120; split: by run; V1.

| Metric | Strict | Legacy | Strict calibration controls | Legacy calibration controls | Strict class counts | Legacy class counts |
| --- | --- | --- | --- | --- | --- | --- |
| full_trace_threshold | 0.4060 | 0.9009 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| auroc | 0.9886 [0.9794, 0.9958] bootstrap; 144 positive / 195 control; bootstrap 200 of 200 | 0.9756 [0.9562, 0.9877] bootstrap; 192 positive / 147 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| sharing_control_auroc | 0.9813 [0.9549, 1.0000] bootstrap; 144 positive / 24 control; bootstrap 200 of 200 | 0.8503 [0.7870, 0.9028] bootstrap; 192 positive / 24 control; bootstrap 200 of 200 | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate | 139 of 144; 0.9653 [0.9213, 0.9851] Wilson | 154 of 192; 0.8021 [0.7400, 0.8523] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| false_positive_rate | 10 of 195; 0.0513 [0.0281, 0.0918] Wilson | 9 of 147; 0.0612 [0.0325, 0.1123] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_nonsharing_controls | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 0 of 123; 0.0000 [0.0000, 0.0303] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_sharing_controls | 3 of 24; 0.1250 [0.0434, 0.3100] Wilson | 9 of 24; 0.3750 [0.2116, 0.5729] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_in_scope_relays | 7 of 48; 0.1458 [0.0725, 0.2717] Wilson | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_1 | 43 of 48; 0.8958 [0.7783, 0.9547] Wilson | 37 of 48; 0.7708 [0.6346, 0.8669] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_2 | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_5 | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_0 | 46 of 48; 0.9583 [0.8602, 0.9885] Wilson | 47 of 64; 0.7344 [0.6152, 0.8270] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_2 | 47 of 48; 0.9792 [0.8910, 0.9963] Wilson | 53 of 64; 0.8281 [0.7179, 0.9012] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_mistake_rate_5 | 46 of 48; 0.9583 [0.8602, 0.9885] Wilson | 54 of 64; 0.8438 [0.7357, 0.9129] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_0 | 0 of 65; 0.0000 [0.0000, 0.0558] Wilson | 1 of 49; 0.0204 [0.0036, 0.1069] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_2 | 3 of 65; 0.0462 [0.0158, 0.1271] Wilson | 1 of 49; 0.0204 [0.0036, 0.1069] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| fpr_mistake_rate_5 | 7 of 65; 0.1077 [0.0532, 0.2060] Wilson | 7 of 49; 0.1429 [0.0710, 0.2667] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| in_scope_vs_sharing_auroc | 0.5386 [0.4075, 0.6878] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 0.5872 [0.4566, 0.7153] bootstrap; 48 positive / 24 control; bootstrap 200 of 200; reported, not gated | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc | 0.9631 [0.9200, 0.9884] bootstrap; 144 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_1 | 0.9145 [0.8572, 0.9668] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_2 | 0.9878 [0.9583, 1.0000] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_size_5 | 0.9870 [0.9583, 1.0000] bootstrap; 48 positive / 48 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_0 | 1.0000 [1.0000, 1.0000] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_2 | 0.9818 [0.9531, 1.0000] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| violation_vs_in_scope_auroc_mistake_rate_5 | 0.9206 [0.8147, 0.9870] bootstrap; 48 positive / 16 control; bootstrap 200 of 200 | not applicable | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |
| detection_rate_violation_size_0 | not applicable | 21 of 48; 0.4375 [0.3070, 0.5772] Wilson | 135 | 102 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |

## Calibration diagnostics

Seed: 20261120; split: by run; V1.

Conformal rank: ceil((n+1)*0.95) of n calibration controls.

| Labelling | Context | Detector | Rank | Threshold | Calibration controls | Control kind | Kind controls | Score > 0 | Score >= threshold | Class counts | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| strict | aggregation-only reference | rule | 130 of 135 | 5.0000 | 135 | nonsharing | 89 | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | aggregation-only reference | rule | 130 of 135 | 5.0000 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 4 of 13; 0.3077 [0.1268, 0.5763] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | aggregation-only reference | rule | 130 of 135 | 5.0000 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 5 of 33; 0.1515 [0.0665, 0.3092] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | aggregation-only reference | scope_rule | 130 of 135 | nan | 135 | nonsharing | 89 | not available | not available | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | not available: no scope_rule column at this context |
| strict | aggregation-only reference | scope_rule | 130 of 135 | nan | 135 | sharing | 13 | not available | not available | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | not available: no scope_rule column at this context |
| strict | aggregation-only reference | scope_rule | 130 of 135 | nan | 135 | in_scope | 33 | not available | not available | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P | not available: no scope_rule column at this context |
| strict | aggregation-only reference | logistic | 130 of 135 | 0.8141 | 135 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | aggregation-only reference | logistic | 130 of 135 | 0.8141 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 2 of 13; 0.1538 [0.0433, 0.4223] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | aggregation-only reference | logistic | 130 of 135 | 0.8141 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 4 of 33; 0.1212 [0.0482, 0.2733] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | aggregation-only reference | boosted | 130 of 135 | 0.8121 | 135 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | aggregation-only reference | boosted | 130 of 135 | 0.8121 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 1 of 13; 0.0769 [0.0137, 0.3331] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | aggregation-only reference | boosted | 130 of 135 | 0.8121 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 5 of 33; 0.1515 [0.0665, 0.3092] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | aggregation-only reference | files_rule | 130 of 135 | 6.0000 | 135 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 18 of 89; 0.2022 [0.1319, 0.2972] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | aggregation-only reference | files_rule | 130 of 135 | 6.0000 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 3 of 13; 0.2308 [0.0818, 0.5026] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | aggregation-only reference | files_rule | 130 of 135 | 6.0000 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 12 of 33; 0.3636 [0.2219, 0.5338] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C0 | rule | 130 of 135 | 5.0000 | 135 | nonsharing | 89 | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C0 | rule | 130 of 135 | 5.0000 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 4 of 13; 0.3077 [0.1268, 0.5763] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C0 | rule | 130 of 135 | 5.0000 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 5 of 33; 0.1515 [0.0665, 0.3092] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C0 | scope_rule | 130 of 135 | 4.0000 | 135 | nonsharing | 89 | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C0 | scope_rule | 130 of 135 | 4.0000 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 9 of 13; 0.6923 [0.4237, 0.8732] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C0 | scope_rule | 130 of 135 | 4.0000 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 24 of 33; 0.7273 [0.5578, 0.8493] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C0 | logistic | 130 of 135 | 0.5807 | 135 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C0 | logistic | 130 of 135 | 0.5807 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 3 of 13; 0.2308 [0.0818, 0.5026] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C0 | logistic | 130 of 135 | 0.5807 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 3 of 33; 0.0909 [0.0314, 0.2357] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C0 | boosted | 130 of 135 | 0.6865 | 135 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C0 | boosted | 130 of 135 | 0.6865 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 3 of 13; 0.2308 [0.0818, 0.5026] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C0 | boosted | 130 of 135 | 0.6865 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 3 of 33; 0.0909 [0.0314, 0.2357] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C0 | files_rule | 130 of 135 | 6.0000 | 135 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 18 of 89; 0.2022 [0.1319, 0.2972] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C0 | files_rule | 130 of 135 | 6.0000 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 3 of 13; 0.2308 [0.0818, 0.5026] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C0 | files_rule | 130 of 135 | 6.0000 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 12 of 33; 0.3636 [0.2219, 0.5338] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C1 | rule | 130 of 135 | 5.0000 | 135 | nonsharing | 89 | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C1 | rule | 130 of 135 | 5.0000 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 4 of 13; 0.3077 [0.1268, 0.5763] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C1 | rule | 130 of 135 | 5.0000 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 5 of 33; 0.1515 [0.0665, 0.3092] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C1 | scope_rule | 130 of 135 | 4.0000 | 135 | nonsharing | 89 | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C1 | scope_rule | 130 of 135 | 4.0000 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 9 of 13; 0.6923 [0.4237, 0.8732] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C1 | scope_rule | 130 of 135 | 4.0000 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 24 of 33; 0.7273 [0.5578, 0.8493] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C1 | logistic | 130 of 135 | 0.5807 | 135 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C1 | logistic | 130 of 135 | 0.5807 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 3 of 13; 0.2308 [0.0818, 0.5026] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C1 | logistic | 130 of 135 | 0.5807 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 3 of 33; 0.0909 [0.0314, 0.2357] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C1 | boosted | 130 of 135 | 0.6865 | 135 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C1 | boosted | 130 of 135 | 0.6865 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 3 of 13; 0.2308 [0.0818, 0.5026] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C1 | boosted | 130 of 135 | 0.6865 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 3 of 33; 0.0909 [0.0314, 0.2357] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C1 | files_rule | 130 of 135 | 6.0000 | 135 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 18 of 89; 0.2022 [0.1319, 0.2972] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C1 | files_rule | 130 of 135 | 6.0000 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 3 of 13; 0.2308 [0.0818, 0.5026] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C1 | files_rule | 130 of 135 | 6.0000 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 12 of 33; 0.3636 [0.2219, 0.5338] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C2 | rule | 130 of 135 | 5.0000 | 135 | nonsharing | 89 | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C2 | rule | 130 of 135 | 5.0000 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 4 of 13; 0.3077 [0.1268, 0.5763] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C2 | rule | 130 of 135 | 5.0000 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 5 of 33; 0.1515 [0.0665, 0.3092] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C2 | scope_rule | 130 of 135 | 1.0000 | 135 | nonsharing | 89 | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C2 | scope_rule | 130 of 135 | 1.0000 | 135 | sharing | 13 | 3 of 13; 0.2308 [0.0818, 0.5026] Wilson | 3 of 13; 0.2308 [0.0818, 0.5026] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C2 | scope_rule | 130 of 135 | 1.0000 | 135 | in_scope | 33 | 3 of 33; 0.0909 [0.0314, 0.2357] Wilson | 3 of 33; 0.0909 [0.0314, 0.2357] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C2 | logistic | 130 of 135 | 0.4431 | 135 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C2 | logistic | 130 of 135 | 0.4431 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 3 of 13; 0.2308 [0.0818, 0.5026] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C2 | logistic | 130 of 135 | 0.4431 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 3 of 33; 0.0909 [0.0314, 0.2357] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C2 | boosted | 130 of 135 | 0.4060 | 135 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C2 | boosted | 130 of 135 | 0.4060 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 3 of 13; 0.2308 [0.0818, 0.5026] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C2 | boosted | 130 of 135 | 0.4060 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 3 of 33; 0.0909 [0.0314, 0.2357] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C2 | files_rule | 130 of 135 | 6.0000 | 135 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 18 of 89; 0.2022 [0.1319, 0.2972] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C2 | files_rule | 130 of 135 | 6.0000 | 135 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 3 of 13; 0.2308 [0.0818, 0.5026] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| strict | C2 | files_rule | 130 of 135 | 6.0000 | 135 | in_scope | 33 | 33 of 33; 1.0000 [0.8957, 1.0000] Wilson | 12 of 33; 0.3636 [0.2219, 0.5338] Wilson | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |  |
| legacy | aggregation-only reference | rule | 98 of 102 | 4.0000 | 102 | nonsharing | 89 | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | aggregation-only reference | rule | 98 of 102 | 4.0000 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 9 of 13; 0.6923 [0.4237, 0.8732] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | aggregation-only reference | scope_rule | 98 of 102 | nan | 102 | nonsharing | 89 | not available | not available | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P | not available: no scope_rule column at this context |
| legacy | aggregation-only reference | scope_rule | 98 of 102 | nan | 102 | sharing | 13 | not available | not available | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P | not available: no scope_rule column at this context |
| legacy | aggregation-only reference | logistic | 98 of 102 | 0.9793 | 102 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | aggregation-only reference | logistic | 98 of 102 | 0.9793 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 5 of 13; 0.3846 [0.1771, 0.6448] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | aggregation-only reference | boosted | 98 of 102 | 0.9277 | 102 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | aggregation-only reference | boosted | 98 of 102 | 0.9277 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 5 of 13; 0.3846 [0.1771, 0.6448] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | aggregation-only reference | files_rule | 98 of 102 | 7.0000 | 102 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 4 of 89; 0.0449 [0.0176, 0.1099] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | aggregation-only reference | files_rule | 98 of 102 | 7.0000 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 1 of 13; 0.0769 [0.0137, 0.3331] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C0 | rule | 98 of 102 | 4.0000 | 102 | nonsharing | 89 | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C0 | rule | 98 of 102 | 4.0000 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 9 of 13; 0.6923 [0.4237, 0.8732] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C0 | scope_rule | 98 of 102 | 4.0000 | 102 | nonsharing | 89 | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C0 | scope_rule | 98 of 102 | 4.0000 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 9 of 13; 0.6923 [0.4237, 0.8732] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C0 | logistic | 98 of 102 | 0.9377 | 102 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C0 | logistic | 98 of 102 | 0.9377 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 5 of 13; 0.3846 [0.1771, 0.6448] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C0 | boosted | 98 of 102 | 0.9216 | 102 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C0 | boosted | 98 of 102 | 0.9216 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 5 of 13; 0.3846 [0.1771, 0.6448] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C0 | files_rule | 98 of 102 | 7.0000 | 102 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 4 of 89; 0.0449 [0.0176, 0.1099] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C0 | files_rule | 98 of 102 | 7.0000 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 1 of 13; 0.0769 [0.0137, 0.3331] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C1 | rule | 98 of 102 | 4.0000 | 102 | nonsharing | 89 | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C1 | rule | 98 of 102 | 4.0000 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 9 of 13; 0.6923 [0.4237, 0.8732] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C1 | scope_rule | 98 of 102 | 4.0000 | 102 | nonsharing | 89 | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C1 | scope_rule | 98 of 102 | 4.0000 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 9 of 13; 0.6923 [0.4237, 0.8732] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C1 | logistic | 98 of 102 | 0.9377 | 102 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C1 | logistic | 98 of 102 | 0.9377 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 5 of 13; 0.3846 [0.1771, 0.6448] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C1 | boosted | 98 of 102 | 0.9216 | 102 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C1 | boosted | 98 of 102 | 0.9216 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 5 of 13; 0.3846 [0.1771, 0.6448] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C1 | files_rule | 98 of 102 | 7.0000 | 102 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 4 of 89; 0.0449 [0.0176, 0.1099] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C1 | files_rule | 98 of 102 | 7.0000 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 1 of 13; 0.0769 [0.0137, 0.3331] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C2 | rule | 98 of 102 | 4.0000 | 102 | nonsharing | 89 | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C2 | rule | 98 of 102 | 4.0000 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 9 of 13; 0.6923 [0.4237, 0.8732] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C2 | scope_rule | 98 of 102 | 0.0000 | 102 | nonsharing | 89 | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C2 | scope_rule | 98 of 102 | 0.0000 | 102 | sharing | 13 | 3 of 13; 0.2308 [0.0818, 0.5026] Wilson | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C2 | logistic | 98 of 102 | 0.8629 | 102 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C2 | logistic | 98 of 102 | 0.8629 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 5 of 13; 0.3846 [0.1771, 0.6448] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C2 | boosted | 98 of 102 | 0.9009 | 102 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 0 of 89; 0.0000 [0.0000, 0.0414] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C2 | boosted | 98 of 102 | 0.9009 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 5 of 13; 0.3846 [0.1771, 0.6448] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C2 | files_rule | 98 of 102 | 7.0000 | 102 | nonsharing | 89 | 89 of 89; 1.0000 [0.9586, 1.0000] Wilson | 4 of 89; 0.0449 [0.0176, 0.1099] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |
| legacy | C2 | files_rule | 98 of 102 | 7.0000 | 102 | sharing | 13 | 13 of 13; 1.0000 [0.7719, 1.0000] Wilson | 1 of 13; 0.0769 [0.0137, 0.3331] Wilson | fit 237 C / 324 P; cal 102 C / 132 P; test 147 C / 192 P |  |

At C2 under the strict labelling the threshold is set by in-scope relays that made an out-of-scope mistake read.

C0 and C1 scope columns are identical in every run; their rows differ only in bootstrap seed.

## Observed borrowed-session breadth

Seed: 20261120; population: all scope runs; column: borrowed_session_breadth_max__C0.

| Population | Runs | Minimum | Median | Maximum |
| --- | --- | --- | --- | --- |
| in-scope relays | 162 | 1.0000 | 4.0000 | 5.0000 |
| benign controls | 486 | 0.0000 | 0.0000 | 6.0000 |

## Strict detection by violation size

Seed: 20261120; split: by run; V1; labelling: strict.

| Context | Detector | Size 1 | Size 2 | Size 5 | Calibration controls | Class counts |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | scope_rule | 14 of 48; 0.2917 [0.1824, 0.4318] Wilson | 26 of 48; 0.5417 [0.4029, 0.6742] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |
| C0 | files_rule | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 6 of 48; 0.1250 [0.0586, 0.2470] Wilson | 42 of 48; 0.8750 [0.7530, 0.9414] Wilson | 135 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |
| C0 | logistic | 17 of 48; 0.3542 [0.2343, 0.4956] Wilson | 33 of 48; 0.6875 [0.5467, 0.8005] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |
| C0 | boosted | 16 of 48; 0.3333 [0.2168, 0.4746] Wilson | 26 of 48; 0.5417 [0.4029, 0.6742] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |
| C2 | scope_rule | 6 of 48; 0.1250 [0.0586, 0.2470] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |
| C2 | files_rule | 0 of 48; 0.0000 [0.0000, 0.0741] Wilson | 6 of 48; 0.1250 [0.0586, 0.2470] Wilson | 42 of 48; 0.8750 [0.7530, 0.9414] Wilson | 135 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |
| C2 | logistic | 44 of 48; 0.9167 [0.8045, 0.9671] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |
| C2 | boosted | 43 of 48; 0.8958 [0.7783, 0.9547] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 48 of 48; 1.0000 [0.9259, 1.0000] Wilson | 135 | fit 318 C / 243 P; cal 135 C / 99 P; test 195 C / 144 P |

```text
2ba4d5c349cf902244afeac4b72068ac297a93d30d6cfc3748b651944af789a3  scope/runs.csv.gz
a56df6f842f42cf3a5333db1f5978b39b4658c5958b110fc2381577c99d6c976  scope/raw/001959db1fc523e8/context.json
45fb58a5a8ce8d84be5ee8c4fde0d601d29cb5fba683f131dfa4c74b8cf44a75  scope/raw/001959db1fc523e8/labels.json
0e4193cb8ac1b065291478923a78bc7cd7f666944642f70c98150af5c3e184e0  scope/raw/001959db1fc523e8/manifest.json
adb50bd58520f0b7cb22d7c155a6a23a3e214b15c6cbb489424e21291d762347  scope/raw/001959db1fc523e8/outcomes.json
75066e7bc09d8b18fb423b1b0015527c14bf32414947c4d1da13f07bfdb84798  scope/raw/001959db1fc523e8/trace.jsonl
37032c3ce08b7165435593d92d0aec8e23e41515c2a9069617de7e87e9e764ab  scope/raw/4504ec2ac3d715de/context.json
5eb95b3f70deae45e0f302b0882edf980291c67df7a7074e1f25bb5cb5c55f6e  scope/raw/4504ec2ac3d715de/labels.json
8987b7dee4f98a648d2fce796b033b900fd36d24a691a9766bd1e4726327953f  scope/raw/4504ec2ac3d715de/manifest.json
a058d423a36ea4d6544899c7461edb0df3f6ac93fb482b3dc0bf0cb1d5685b9e  scope/raw/4504ec2ac3d715de/outcomes.json
bcf94f7b803572150cfec878fbdd93ec6751252eeae20f7c58d50f5b2a0a60dd  scope/raw/4504ec2ac3d715de/trace.jsonl
```
