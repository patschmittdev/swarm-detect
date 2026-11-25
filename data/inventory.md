# Reproduction inventory

Seed: 20261120

Command template: `swarmtrace reproduce --seed 20261120 --out DIR --runs-per-condition 2 --control-repeats 8 --ticks 160 --checkpoint-every 8 --bootstrap 200 --shuffle-repeats 20 --sample-runs 6 --hold-out channel topology`

Checkpoint cadence: 8 ticks.

| dataset | positive | controls |
| --- | --- | --- |
| main | 108 | 288 |
| benign | 0 | 18 |
| loud | 3 | 0 |

Per-class counts below are disjoint fitting, calibration, and test runs.

| split | fitting_controls | fitting_positive | calibration_controls | calibration_positive | test_controls | test_positive |
| --- | --- | --- | --- | --- | --- | --- |
| by run | 141 | 53 | 61 | 23 | 86 | 32 |
| held-out channel=message | 134 | 50 | 58 | 22 | 96 | 36 |
| held-out channel=preplanned | 134 | 50 | 58 | 22 | 96 | 36 |
| held-out channel=shared_file | 134 | 50 | 58 | 22 | 96 | 36 |
| held-out topology=hub | 101 | 38 | 43 | 16 | 144 | 54 |
| held-out topology=peer | 101 | 38 | 43 | 16 | 144 | 54 |
