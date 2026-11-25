# Split stability

20 different by-run split seeds on the same recorded runs. The first uses child_seed(seed, 0), the reported split; the other 19 use child_seed(seed, 80, i), i=1..19. Fit and calibration seeds and fractions are unchanged. The single value uses the exact reported full-trace fitting recipe. SD is the sample standard deviation across splits, not an uncertainty interval. No online model or bootstrap is run. Class counts are identical across splits. --workers is ignored for recorded datasets.

| seed | split | tier | family | detector | split_seeds | single_auroc | auroc_mean | auroc_std | fitting_controls | fitting_positive | calibration_controls | calibration_positive | test_controls | test_positive |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 20261120 | by run | V0 | generic | volume (family-independent) | 20 | 0.525073 | 0.502380 | 0.042791 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V0 | generic | logistic | 20 | 0.439680 | 0.450363 | 0.040793 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V0 | generic | boosted | 20 | 0.417696 | 0.469595 | 0.051737 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V0 | generic | rule | 20 | not available at this tier | not available at this tier | not available at this tier | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V0 | aggregation | volume (family-independent) | 20 | 0.525073 | 0.502380 | 0.042791 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V0 | aggregation | logistic | 20 | 0.442042 | 0.446530 | 0.042097 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V0 | aggregation | boosted | 20 | 0.487827 | 0.491633 | 0.049165 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V0 | aggregation | rule | 20 | not available at this tier | not available at this tier | not available at this tier | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V0 | all | volume (family-independent) | 20 | 0.525073 | 0.502380 | 0.042791 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V0 | all | logistic | 20 | 0.434956 | 0.444658 | 0.039996 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V0 | all | boosted | 20 | 0.406613 | 0.460120 | 0.046270 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V0 | all | rule | 20 | not available at this tier | not available at this tier | not available at this tier | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V1 | generic | volume (family-independent) | 20 | 0.525073 | 0.502380 | 0.042791 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V1 | generic | logistic | 20 | 0.439680 | 0.450363 | 0.040793 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V1 | generic | boosted | 20 | 0.417696 | 0.469595 | 0.051737 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V1 | generic | rule | 20 | not available without aggregation features | not available without aggregation features | not available without aggregation features | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V1 | aggregation | volume (family-independent) | 20 | 0.525073 | 0.502380 | 0.042791 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V1 | aggregation | logistic | 20 | 0.920422 | 0.923065 | 0.016496 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V1 | aggregation | boosted | 20 | 0.925509 | 0.923964 | 0.020111 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V1 | aggregation | rule | 20 | 0.909157 | 0.927916 | 0.019010 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V1 | all | volume (family-independent) | 20 | 0.525073 | 0.502380 | 0.042791 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V1 | all | logistic | 20 | 0.911337 | 0.913027 | 0.019479 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V1 | all | boosted | 20 | 0.899709 | 0.912500 | 0.019510 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V1 | all | rule | 20 | 0.909157 | 0.927916 | 0.019010 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V2 | generic | volume (family-independent) | 20 | 0.525073 | 0.502380 | 0.042791 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V2 | generic | logistic | 20 | 0.440770 | 0.446403 | 0.039577 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V2 | generic | boosted | 20 | 0.388445 | 0.463136 | 0.056457 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V2 | generic | rule | 20 | not available without aggregation features | not available without aggregation features | not available without aggregation features | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V2 | aggregation | volume (family-independent) | 20 | 0.525073 | 0.502380 | 0.042791 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V2 | aggregation | logistic | 20 | 0.920422 | 0.923065 | 0.016496 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V2 | aggregation | boosted | 20 | 0.925509 | 0.923964 | 0.020111 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V2 | aggregation | rule | 20 | 0.909157 | 0.927916 | 0.019010 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V2 | all | volume (family-independent) | 20 | 0.525073 | 0.502380 | 0.042791 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V2 | all | logistic | 20 | 0.912791 | 0.912246 | 0.019474 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V2 | all | boosted | 20 | 0.902616 | 0.912336 | 0.020755 | 141 | 53 | 61 | 23 | 86 | 32 |
| 20261120 | by run | V2 | all | rule | 20 | 0.909157 | 0.927916 | 0.019010 | 141 | 53 | 61 | 23 | 86 | 32 |
