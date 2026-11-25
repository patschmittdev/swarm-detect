# Named evasion: owner-silent credential relay against frozen detectors

Prediction (written before the run): with the owner silent, the shared-credential feature is zero for the relay group, and the frozen detectors flag owner-silent relay runs at about the rate they flag control runs, because the only remaining shared logins come from benign sharing teams in the same run.

Outcome: the shared-credential feature is zero for every lender-borrower pair under owner_silent (180 of 180 pairs). It is not zero for the relay group as a whole in hubs of three or more members, where two or more borrowers log in with the same hub credential (18 runs). Owner-silent runs with no benign sharing team: pairs and peer rings flagged 0 of 31 by rule, 0 of 31 by logistic, 0 of 31 by boosted; hubs of five flagged 0 of 9, 7 of 9, 8 of 9. Main test controls with no sharing team: 0 of 72, 0 of 72, 0 of 72. The prediction held for pairs and peer rings and did not hold for hubs of five.

Seed: 20261120; V1 aggregation; split: paired evasion against main by run.

Simulation namespace: child_seed(seed, 92, 0, i), one replicate per positive condition in grid order, with the same seed for both styles.

Main reconstruction: seed 20261120, test fraction 0.3, split key (0,), evaluation key (1, 0), with the harness's unchanged descendant keys.

Main reconstruction bootstrap resamples: 200; reported rates use 95% Wilson intervals and strict score > threshold flags.

| seed | split | subset | positive runs | control runs |
| --- | --- | --- | --- | --- |
| 20261120 | by run | fitting | 53 | 141 |
| 20261120 | by run | calibration | 23 | 61 |
| 20261120 | by run | test | 32 | 86 |
| 20261120 | paired evasion | standard | 54 | 0 |
| 20261120 | paired evasion | owner_silent | 54 | 0 |

## Detection by detector

Seed: 20261120; split: paired evasion; each style: 54 positive, 0 control; main by-run test (seed 20261120): 32 positive, 86 control.

| detector | main test standard relays | main test controls | main test controls without a sharing team, k of 72 | standard | owner_silent | standard only (paired) | owner_silent only (paired) | threshold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rule | 7 of 32; 0.219 [0.110, 0.388] Wilson | 4 of 86; 0.047 [0.018, 0.114] Wilson | 0 of 72; 0.000 [0.000, 0.051] Wilson | 11 of 54; 0.204 [0.118, 0.329] Wilson | 2 of 54; 0.037 [0.010, 0.125] Wilson | 9 of 54; 0.167 [0.090, 0.287] Wilson | 0 of 54; 0.000 [0.000, 0.066] Wilson | 4 |
| logistic | 14 of 32; 0.438 [0.282, 0.607] Wilson | 5 of 86; 0.058 [0.025, 0.129] Wilson | 0 of 72; 0.000 [0.000, 0.051] Wilson | 20 of 54; 0.370 [0.254, 0.504] Wilson | 8 of 54; 0.148 [0.077, 0.266] Wilson | 12 of 54; 0.222 [0.132, 0.349] Wilson | 0 of 54; 0.000 [0.000, 0.066] Wilson | 0.71675637804096926 |
| boosted | 13 of 32; 0.406 [0.255, 0.577] Wilson | 5 of 86; 0.058 [0.025, 0.129] Wilson | 0 of 72; 0.000 [0.000, 0.051] Wilson | 28 of 54; 0.519 [0.389, 0.646] Wilson | 11 of 54; 0.204 [0.118, 0.329] Wilson | 17 of 54; 0.315 [0.207, 0.447] Wilson | 0 of 54; 0.000 [0.000, 0.066] Wilson | 0.67118478858702724 |

## Shared credential features

Seed: 20261120; split: paired evasion; each style: 54 positive, 0 control; main by-run test (seed 20261120): 32 positive, 86 control.

| style | feature | mean | zero runs |
| --- | --- | --- | --- |
| standard | shared_credential_logins_max | 1.7037 | 0 of 54; 0.000 [0.000, 0.066] Wilson |
| standard | shared_credential_logins_top_k_mean | 0.9691 | 0 of 54; 0.000 [0.000, 0.066] Wilson |
| standard | shared_credential_logins_n_above | 2.9630 | 0 of 54; 0.000 [0.000, 0.066] Wilson |
| owner_silent | shared_credential_logins_max | 0.4815 | 31 of 54; 0.574 [0.442, 0.697] Wilson |
| owner_silent | shared_credential_logins_top_k_mean | 0.3086 | 31 of 54; 0.574 [0.442, 0.697] Wilson |
| owner_silent | shared_credential_logins_n_above | 0.9630 | 31 of 54; 0.574 [0.442, 0.697] Wilson |

## Objective completion

Seed: 20261120; split: paired evasion; each style: 54 positive, 0 control; main by-run test (seed 20261120): 32 positive, 86 control.

| style | offensive size | completed |
| --- | --- | --- |
| standard | all | 54 of 54; 1.000 [0.934, 1.000] Wilson |
| standard | 2 | 18 of 18; 1.000 [0.824, 1.000] Wilson |
| standard | 3 | 18 of 18; 1.000 [0.824, 1.000] Wilson |
| standard | 5 | 18 of 18; 1.000 [0.824, 1.000] Wilson |
| owner_silent | all | 54 of 54; 1.000 [0.934, 1.000] Wilson |
| owner_silent | 2 | 18 of 18; 1.000 [0.824, 1.000] Wilson |
| owner_silent | 3 | 18 of 18; 1.000 [0.824, 1.000] Wilson |
| owner_silent | 5 | 18 of 18; 1.000 [0.824, 1.000] Wilson |

## Calibration control median

Seed: 20261120; split: paired evasion; each style: 54 positive, 0 control; main by-run test (seed 20261120): 32 positive, 86 control.

| detector | calibration controls | median calibration control score | owner_silent at or below median |
| --- | --- | --- | --- |
| rule | 61 | 0.0000 | 31 of 54; 0.574 [0.442, 0.697] Wilson |
| logistic | 61 | 0.0158 | 11 of 54; 0.204 [0.118, 0.329] Wilson |
| boosted | 61 | 0.0004 | 26 of 54; 0.481 [0.354, 0.611] Wilson |

## Benign sharing teams

Seed: 20261120; split: paired evasion; each style: 54 positive, 0 control; main by-run test (seed 20261120): 32 positive, 86 control.

| style | benign sharing teams | detector | flagged |
| --- | --- | --- | --- |
| standard | 0 | rule | 8 of 49; 0.163 [0.085, 0.290] Wilson |
| standard | 0 | logistic | 15 of 49; 0.306 [0.195, 0.445] Wilson |
| standard | 0 | boosted | 24 of 49; 0.490 [0.356, 0.625] Wilson |
| standard | >=1 | rule | 3 of 5; 0.600 [0.231, 0.882] Wilson |
| standard | >=1 | logistic | 5 of 5; 1.000 [0.566, 1.000] Wilson |
| standard | >=1 | boosted | 4 of 5; 0.800 [0.376, 0.964] Wilson |
| owner_silent | 0 | rule | 0 of 49; 0.000 [0.000, 0.073] Wilson |
| owner_silent | 0 | logistic | 7 of 49; 0.143 [0.071, 0.267] Wilson |
| owner_silent | 0 | boosted | 8 of 49; 0.163 [0.085, 0.290] Wilson |
| owner_silent | >=1 | rule | 2 of 5; 0.400 [0.118, 0.769] Wilson |
| owner_silent | >=1 | logistic | 1 of 5; 0.200 [0.036, 0.624] Wilson |
| owner_silent | >=1 | boosted | 3 of 5; 0.600 [0.231, 0.882] Wilson |

## Topology and group size

Seed: 20261120; split: paired evasion; each style: 54 positive, 0 control; main by-run test (seed 20261120): 32 positive, 86 control.

| style | topology | offensive size | positive runs | control runs | mean shared_credential_logins_max | rule | logistic | boosted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| standard | hub | 2 | 9 | 0 | 2.0000 | 0 of 9; 0.000 [0.000, 0.299] Wilson | 1 of 9; 0.111 [0.020, 0.435] Wilson | 0 of 9; 0.000 [0.000, 0.299] Wilson |
| standard | hub | 3 | 9 | 0 | 2.0000 | 0 of 9; 0.000 [0.000, 0.299] Wilson | 2 of 9; 0.222 [0.063, 0.547] Wilson | 2 of 9; 0.222 [0.063, 0.547] Wilson |
| standard | hub | 5 | 9 | 0 | 2.0000 | 0 of 9; 0.000 [0.000, 0.299] Wilson | 9 of 9; 1.000 [0.701, 1.000] Wilson | 9 of 9; 1.000 [0.701, 1.000] Wilson |
| standard | peer | 2 | 9 | 0 | 2.0000 | 0 of 9; 0.000 [0.000, 0.299] Wilson | 0 of 9; 0.000 [0.000, 0.299] Wilson | 0 of 9; 0.000 [0.000, 0.299] Wilson |
| standard | peer | 3 | 9 | 0 | 1.1111 | 2 of 9; 0.222 [0.063, 0.547] Wilson | 5 of 9; 0.556 [0.267, 0.811] Wilson | 9 of 9; 1.000 [0.701, 1.000] Wilson |
| standard | peer | 5 | 9 | 0 | 1.1111 | 9 of 9; 1.000 [0.701, 1.000] Wilson | 3 of 9; 0.333 [0.121, 0.646] Wilson | 8 of 9; 0.889 [0.565, 0.980] Wilson |
| owner_silent | hub | 2 | 9 | 0 | 0.2222 | 0 of 9; 0.000 [0.000, 0.299] Wilson | 0 of 9; 0.000 [0.000, 0.299] Wilson | 0 of 9; 0.000 [0.000, 0.299] Wilson |
| owner_silent | hub | 3 | 9 | 0 | 1.0000 | 0 of 9; 0.000 [0.000, 0.299] Wilson | 0 of 9; 0.000 [0.000, 0.299] Wilson | 0 of 9; 0.000 [0.000, 0.299] Wilson |
| owner_silent | hub | 5 | 9 | 0 | 1.0000 | 0 of 9; 0.000 [0.000, 0.299] Wilson | 7 of 9; 0.778 [0.453, 0.937] Wilson | 8 of 9; 0.889 [0.565, 0.980] Wilson |
| owner_silent | peer | 2 | 9 | 0 | 0.0000 | 0 of 9; 0.000 [0.000, 0.299] Wilson | 0 of 9; 0.000 [0.000, 0.299] Wilson | 0 of 9; 0.000 [0.000, 0.299] Wilson |
| owner_silent | peer | 3 | 9 | 0 | 0.4444 | 2 of 9; 0.222 [0.063, 0.547] Wilson | 0 of 9; 0.000 [0.000, 0.299] Wilson | 2 of 9; 0.222 [0.063, 0.547] Wilson |
| owner_silent | peer | 5 | 9 | 0 | 0.2222 | 0 of 9; 0.000 [0.000, 0.299] Wilson | 1 of 9; 0.111 [0.020, 0.435] Wilson | 1 of 9; 0.111 [0.020, 0.435] Wilson |

## Owner-silent detection by shape

Seed: 20261120; split: paired evasion; each style: 54 positive, 0 control; main by-run test (seed 20261120): 32 positive, 86 control.

The breakdown by topology and size was added after an 18-run exploratory probe on other seeds, run after the prediction was committed and before this sweep; it is post hoc. The prediction text was not changed.

| benign sharing teams | shape | detector | owner_silent flagged | main test controls with no sharing team, k of 72 | all main test controls, k of 86 |
| --- | --- | --- | --- | --- | --- |
| 0 | pairs and peer rings | rule | 0 of 31; 0.000 [0.000, 0.110] Wilson | 0 of 72; 0.000 [0.000, 0.051] Wilson | 4 of 86; 0.047 [0.018, 0.114] Wilson |
| 0 | pairs and peer rings | logistic | 0 of 31; 0.000 [0.000, 0.110] Wilson | 0 of 72; 0.000 [0.000, 0.051] Wilson | 5 of 86; 0.058 [0.025, 0.129] Wilson |
| 0 | pairs and peer rings | boosted | 0 of 31; 0.000 [0.000, 0.110] Wilson | 0 of 72; 0.000 [0.000, 0.051] Wilson | 5 of 86; 0.058 [0.025, 0.129] Wilson |
| 0 | hubs of 3 | rule | 0 of 9; 0.000 [0.000, 0.299] Wilson | 0 of 72; 0.000 [0.000, 0.051] Wilson | 4 of 86; 0.047 [0.018, 0.114] Wilson |
| 0 | hubs of 3 | logistic | 0 of 9; 0.000 [0.000, 0.299] Wilson | 0 of 72; 0.000 [0.000, 0.051] Wilson | 5 of 86; 0.058 [0.025, 0.129] Wilson |
| 0 | hubs of 3 | boosted | 0 of 9; 0.000 [0.000, 0.299] Wilson | 0 of 72; 0.000 [0.000, 0.051] Wilson | 5 of 86; 0.058 [0.025, 0.129] Wilson |
| 0 | hubs of 5 | rule | 0 of 9; 0.000 [0.000, 0.299] Wilson | 0 of 72; 0.000 [0.000, 0.051] Wilson | 4 of 86; 0.047 [0.018, 0.114] Wilson |
| 0 | hubs of 5 | logistic | 7 of 9; 0.778 [0.453, 0.937] Wilson | 0 of 72; 0.000 [0.000, 0.051] Wilson | 5 of 86; 0.058 [0.025, 0.129] Wilson |
| 0 | hubs of 5 | boosted | 8 of 9; 0.889 [0.565, 0.980] Wilson | 0 of 72; 0.000 [0.000, 0.051] Wilson | 5 of 86; 0.058 [0.025, 0.129] Wilson |
| >=1 | any shape | rule | 2 of 5; 0.400 [0.118, 0.769] Wilson | 0 of 72; 0.000 [0.000, 0.051] Wilson | 4 of 86; 0.047 [0.018, 0.114] Wilson |
| >=1 | any shape | logistic | 1 of 5; 0.200 [0.036, 0.624] Wilson | 0 of 72; 0.000 [0.000, 0.051] Wilson | 5 of 86; 0.058 [0.025, 0.129] Wilson |
| >=1 | any shape | boosted | 3 of 5; 0.600 [0.231, 0.882] Wilson | 0 of 72; 0.000 [0.000, 0.051] Wilson | 5 of 86; 0.058 [0.025, 0.129] Wilson |

## Shared credential features by topology and size

Seed: 20261120; split: paired evasion; each style: 54 positive, 0 control; main by-run test (seed 20261120): 32 positive, 86 control.

| population | style | topology | offensive size | runs | mean shared_credential_logins_max | mean shared_credential_logins_top_k_mean | mean shared_credential_logins_n_above |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all runs | standard | hub | 2 | 9 | 2.0000 | 0.7407 | 1.1111 |
| zero benign sharing teams | standard | hub | 2 | 8 | 2.0000 | 0.6667 | 1.0000 |
| all runs | standard | hub | 3 | 9 | 2.0000 | 1.0000 | 2.0000 |
| zero benign sharing teams | standard | hub | 3 | 9 | 2.0000 | 1.0000 | 2.0000 |
| all runs | standard | hub | 5 | 9 | 2.0000 | 1.3333 | 4.0000 |
| zero benign sharing teams | standard | hub | 5 | 9 | 2.0000 | 1.3333 | 4.0000 |
| all runs | standard | peer | 2 | 9 | 2.0000 | 0.6667 | 1.0000 |
| zero benign sharing teams | standard | peer | 2 | 9 | 2.0000 | 0.6667 | 1.0000 |
| all runs | standard | peer | 3 | 9 | 1.1111 | 1.0370 | 4.2222 |
| zero benign sharing teams | standard | peer | 3 | 6 | 1.0000 | 1.0000 | 3.0000 |
| all runs | standard | peer | 5 | 9 | 1.1111 | 1.0370 | 5.4444 |
| zero benign sharing teams | standard | peer | 5 | 8 | 1.0000 | 1.0000 | 5.0000 |
| all runs | owner_silent | hub | 2 | 9 | 0.2222 | 0.0741 | 0.1111 |
| zero benign sharing teams | owner_silent | hub | 2 | 8 | 0.0000 | 0.0000 | 0.0000 |
| all runs | owner_silent | hub | 3 | 9 | 1.0000 | 0.3333 | 1.0000 |
| zero benign sharing teams | owner_silent | hub | 3 | 9 | 1.0000 | 0.3333 | 1.0000 |
| all runs | owner_silent | hub | 5 | 9 | 1.0000 | 1.0000 | 3.0000 |
| zero benign sharing teams | owner_silent | hub | 5 | 9 | 1.0000 | 1.0000 | 3.0000 |
| all runs | owner_silent | peer | 2 | 9 | 0.0000 | 0.0000 | 0.0000 |
| zero benign sharing teams | owner_silent | peer | 2 | 9 | 0.0000 | 0.0000 | 0.0000 |
| all runs | owner_silent | peer | 3 | 9 | 0.4444 | 0.2963 | 1.2222 |
| zero benign sharing teams | owner_silent | peer | 3 | 6 | 0.0000 | 0.0000 | 0.0000 |
| all runs | owner_silent | peer | 5 | 9 | 0.2222 | 0.1481 | 0.4444 |
| zero benign sharing teams | owner_silent | peer | 5 | 8 | 0.0000 | 0.0000 | 0.0000 |

## Table notes

- owner_silent applies to offensive groups only; benign sharing teams keep standard behaviour because a benign team would have no reason to hide.
- Models and thresholds are frozen from the reconstructed main by-run split, with no refit or recalibration on either paired dataset.
- Detectors never see label_ or condition_ columns.
- Objective completion shows whether the evasion broke the offence.
- In hubs with at least three members, two borrowers can share the hub's credential.
- The aggregation family's other feature, access expansion after receipt, also falls under owner_silent, because it too reads logins.
- Lender-borrower counts use directed RelayRequirement owner/recipient pairs per run; their V1 pair-feature counts are kept in memory for the verdict only.
- The combined table uses style:run_id as its unique index, and joins use (style, run_id).
- condition_source_run_id stores `run:<original-id>` to keep hexadecimal ids as strings, and condition_paired_seed records the shared simulation seed.
- Raw samples are the first peer group of size 3 in grid order, one run per style with the same seed; a subgrid without that condition records no raw samples.
- An empty subgroup has 0 of 0 and an undefined interval.

## Recorded V1 run table

```swarmtrace-evasion-sha256
path | sha256
evasion/runs.csv.gz | f13532791e0c72d50e2cc79740e174e16d9eccdff332453081f19c540019fdf4
evasion/raw/owner_silent/46fcfaac678c1252/labels.json | a9f6e93905e61356ef3711630b620187aef6ae2964f4c8b6a689144048cfc719
evasion/raw/owner_silent/46fcfaac678c1252/manifest.json | a1bf0eec40760567ee1f46b2e41648af9b049dc711d9e0a57a471ca007000178
evasion/raw/owner_silent/46fcfaac678c1252/trace.jsonl | 774ad0052b4d73d9d3672f9cf02e8c1662d0282c72c8bfa745acf565e3721be4
evasion/raw/standard/46fcfaac678c1252/labels.json | a9f6e93905e61356ef3711630b620187aef6ae2964f4c8b6a689144048cfc719
evasion/raw/standard/46fcfaac678c1252/manifest.json | 9bfc8a784f30a31ef80ae6b260cf9cec5e35ea38542840dd0fd4c5594b86cd7a
evasion/raw/standard/46fcfaac678c1252/trace.jsonl | 5a457402bff2b5872bd3a811b03e64dbd6c20db1692c57223db2f8e69aa301ae
```
