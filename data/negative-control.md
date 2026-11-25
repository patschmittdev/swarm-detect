# Shuffled-label negative control

20 seeded permutations of labels across whole main runs; models refitted for each permutation. By-run splits only. AUROC mean, standard error (sample SD / sqrt(permutations)), and range describe permutation variability on this fixed dataset. They are not uncertainty estimates over new runs. No pass/fail criterion is applied: the overlapping splits reuse one dataset, and the SE alone does not justify a general no-signal test. Split class counts are identical across permutations. The volume reference is family-independent. Attribution and timing are not interpreted for fake labels.

| seed | split | tier | family | method | repeats | auroc_mean | auroc_se | auroc_min | auroc_max | fitting_controls | fitting_positive | calibration_controls | calibration_positive | test_controls | test_positive |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 20261120 | by run (permuted) | V0 | generic | volume (family-independent) | 20 | 0.4807 | 0.0151 | 0.3739 | 0.6192 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V0 | generic | logistic | 20 | 0.4952 | 0.0161 | 0.3303 | 0.6090 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V0 | generic | boosted | 20 | 0.5146 | 0.0150 | 0.3423 | 0.5883 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V0 | generic | rule | 20 | not available at this tier | not available at this tier | not available at this tier | not available at this tier | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V0 | aggregation | volume (family-independent) | 20 | 0.4807 | 0.0151 | 0.3739 | 0.6192 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V0 | aggregation | logistic | 20 | 0.4925 | 0.0149 | 0.3419 | 0.6619 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V0 | aggregation | boosted | 20 | 0.5174 | 0.0107 | 0.3761 | 0.6094 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V0 | aggregation | rule | 20 | not available at this tier | not available at this tier | not available at this tier | not available at this tier | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V0 | all | volume (family-independent) | 20 | 0.4807 | 0.0151 | 0.3739 | 0.6192 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V0 | all | logistic | 20 | 0.4966 | 0.0189 | 0.3318 | 0.7060 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V0 | all | boosted | 20 | 0.5183 | 0.0151 | 0.3368 | 0.6068 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V0 | all | rule | 20 | not available at this tier | not available at this tier | not available at this tier | not available at this tier | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V1 | generic | volume (family-independent) | 20 | 0.4807 | 0.0151 | 0.3739 | 0.6192 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V1 | generic | logistic | 20 | 0.4952 | 0.0161 | 0.3303 | 0.6090 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V1 | generic | boosted | 20 | 0.5146 | 0.0150 | 0.3423 | 0.5883 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V1 | generic | rule | 20 | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V1 | aggregation | volume (family-independent) | 20 | 0.4807 | 0.0151 | 0.3739 | 0.6192 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V1 | aggregation | logistic | 20 | 0.4914 | 0.0136 | 0.3963 | 0.6125 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V1 | aggregation | boosted | 20 | 0.5166 | 0.0159 | 0.3623 | 0.6541 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V1 | aggregation | rule | 20 | 0.5031 | 0.0096 | 0.4231 | 0.5847 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V1 | all | volume (family-independent) | 20 | 0.4807 | 0.0151 | 0.3739 | 0.6192 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V1 | all | logistic | 20 | 0.4938 | 0.0196 | 0.2852 | 0.7024 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V1 | all | boosted | 20 | 0.5103 | 0.0166 | 0.2929 | 0.6065 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V1 | all | rule | 20 | 0.5031 | 0.0096 | 0.4231 | 0.5847 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V2 | generic | volume (family-independent) | 20 | 0.4807 | 0.0151 | 0.3739 | 0.6192 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V2 | generic | logistic | 20 | 0.4971 | 0.0180 | 0.3314 | 0.6726 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V2 | generic | boosted | 20 | 0.5095 | 0.0140 | 0.3543 | 0.5868 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V2 | generic | rule | 20 | not available without aggregation features | not available without aggregation features | not available without aggregation features | not available without aggregation features | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V2 | aggregation | volume (family-independent) | 20 | 0.4807 | 0.0151 | 0.3739 | 0.6192 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V2 | aggregation | logistic | 20 | 0.4914 | 0.0136 | 0.3963 | 0.6125 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V2 | aggregation | boosted | 20 | 0.5166 | 0.0159 | 0.3623 | 0.6541 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V2 | aggregation | rule | 20 | 0.5031 | 0.0096 | 0.4231 | 0.5847 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V2 | all | volume (family-independent) | 20 | 0.4807 | 0.0151 | 0.3739 | 0.6192 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V2 | all | logistic | 20 | 0.4942 | 0.0198 | 0.2892 | 0.7060 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V2 | all | boosted | 20 | 0.5124 | 0.0154 | 0.3318 | 0.6003 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run (permuted) | V2 | all | rule | 20 | 0.5031 | 0.0096 | 0.4231 | 0.5847 | 141 | 53 | 61 | 23 | 86 | 32 |
