# Detector accuracy on two independent simulation seeds

With a credential directory and a file scope for each hand-off (C2), using
session breadth to break ties in the count rule caught 225 additional
violations across the two grids. All 225 were one-file violations. It also
flagged 61 additional controls. The existing logistic model had the highest
scope accuracy on both grids. With audit logs alone, grouping agents by their
interactions improved average precision over the pair-count rule on both
grids. Only 13 of 216 relay runs crossed the graph rule's alert threshold.

The follow-up includes a third grid, the zero-shot comparison and the criteria
for continuing each detector experiment. [Detector improvement rounds](detector-rounds.md)

## Held-out results

Each seed supplied 108 relay runs and 288 controls for the audit task, plus
486 violations and 648 controls for the scope task. The two count rules,
the existing logistic and boosted models, and the first two candidates were
specified before scoring seed 20261123. The conditional logistic models were
added after seeing that first grid. Seed 20261124 was their independent test.
Every model used the same original fitting and calibration partitions for
both evaluations.

| Task | Detector | Detected / false alerts, 20261123 | Detected / false alerts, 20261124 | Accuracy, 20261124 | Average precision, 20261124 | Hard-control AUROC, 20261124 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Audit | Shared pair count | 23 / 15 | 23 / 8 | 76.5% | 0.710 | 0.546 |
| Audit | Sharing components | 4 / 0 | 9 / 1 | 74.7% | 0.716 | 0.577 |
| Audit | Logistic | 34 / 14 | 40 / 14 | 79.3% | 0.709 | 0.547 |
| Audit | Boosted | 50 / 24 | 52 / 23 | 80.1% | 0.686 | 0.520 |
| Audit | Conditional logistic | Exploratory | 30 / 14 | 76.8% | 0.689 | 0.521 |
| Scope | Out-of-scope count | 342 / 3 | 336 / 3 | 86.5% | 0.975 | 0.976 |
| Scope | Count with breadth tie-breaker | 454 / 34 | 449 / 33 | 93.8% | 0.978 | 0.971 |
| Scope | Logistic | 481 / 33 | 474 / 35 | 95.9% | 0.986 | 0.980 |
| Scope | Boosted | 471 / 32 | 470 / 32 | 95.8% | 0.983 | 0.978 |
| Scope | Conditional logistic | Exploratory | 455 / 28 | 94.8% | 0.986 | 0.981 |

On seed 20261124 the audit logistic model flagged 4.86% of controls and the
boosted model flagged 7.99%. All audit false alerts for these models were on
benign runs containing a sharing team. Restricting the AUROC calculation to
those controls gives the hard-control column above. For scope, the comparison
uses violations against the 162 in-scope relays on each grid.

Replaying the original identical-policy control produced byte-identical traces
and context in all 108 pairs. Each pair contains a benign sharing team and
an in-scope relay. Their role labels differ and both are controls in the
strict scope evaluation. A deterministic scorer using those observations
must give both runs the same score. [Identical-policy control](../data/scope-identical.md)

On the 162 one-file violations per seed, the scope count rule caught 18 and
12, the breadth rule caught 130 and 125, and logistic caught 157 and 150.
Both count rules caught every two-file and five-file violation on both grids.
The breadth rule's observed false-positive rates were 5.25% and 5.09%, with
95% Wilson intervals of 3.78% to 7.24% and 3.65% to 7.07%. On the second
grid, conditional scope logistic removed eight of the original logistic
model's false alerts and added one, while gaining one violation and losing 20.
The conditional models' accuracy differences against logistic on that grid
were -2.53 percentage points for audit (paired 95% interval -5.56 to +0.51)
and -1.06 points for scope (-2.03 to -0.18).

## What the candidates measure

- **Sharing components** (`component_rule`). Pacheco et al. infer coordination
  networks from shared behavioral traces. Here a direct message, read after
  another agent's write, or shared login connects two agents. The score is
  the number of connected groups containing a shared login divided by one
  plus the number of connected groups with any observed interaction. Repeated
  evidence inside a group contributes once. A single observed group that
  shares scores exactly 0.5. That tied the frozen cutoff and produced no
  alert on either grid. [Pacheco et al., Uncovering Coordinated Networks on Social Media](https://arxiv.org/abs/2001.05658)
- **Scope and breadth** (`scope_breadth_rule`). NIST describes evaluating
  access using attributes of the subject, resource and requested operation
  against authorization policy. Swarmtrace's C2 context supplies ownership
  and the allowed files for each hand-off. For a positive maximum count of
  out-of-scope borrowed reads `m` and maximum borrowed-session breadth `b`,
  the score is `m + b/(1+b)`. A zero count scores zero. Breadth orders ties
  between equal positive counts. Both maxima are run-wide and can come from
  different pairs. [NIST SP 800-162](https://csrc.nist.gov/pubs/sp/800/162/upd2/final)
- **Conditional logistic** (`sharing_logistic` and `scope_logistic`). Viola
  and Jones trained later detection stages on examples surviving earlier
  stages. Here the first stage requires an observed shared login in the audit
  task or an out-of-scope borrowed read in the scope task. Only fitting runs
  that pass this check train the logistic classifier, including its imputer
  and scaler. All calibration controls contribute to the threshold. This
  left 30 eligible fitting controls for audit and 27 for scope. Both models
  lost accuracy against ordinary logistic on the second grid. [Viola and Jones, Rapid Object Detection Using a Boosted Cascade of Simple Features](https://www.cs.columbia.edu/~jebara/6772/papers/violaJones_CVPR2001.pdf)

## Evaluation and next measurement

The archive split seed was 20261120. Audit fitting used 53 positives and 141
controls, with 61 separate controls for calibration. Strict scope fitting
used 243 positives and 318 controls, with 135 controls for calibration.
In-scope relays and benign teams count as controls, including when an agent
makes an accidental out-of-scope read. Each detector flags a score strictly
above its own split-conformal threshold at a 5% target.
The realized false-positive rate varies with the calibration sample and the
test population. [Bates et al., Testing for Outliers with Conformal p-values](https://arxiv.org/abs/2104.08279)

Run counts and precision describe the alerts a reviewer would see at the
threshold. Average precision and AUROC describe ranking across thresholds.
Precision depends on prevalence, so each task retains its own denominators.
The CSV includes both ranking metrics. [Saito and Rehmsmeier, Precision-Recall Plots for Imbalanced Datasets](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0118432)

The original and conditional logistic models use the same six audit
aggregation features. The scope fits add nine C2 features. The comparison
reports 95% Wilson intervals for recall and false-positive rate.
Accuracy differences against the existing logistic model have 95%
paired percentile intervals from 2,000 bootstrap resamples of test runs within
each true class, conditional on the fitted models and frozen thresholds. [Comparison code](../src/swarmtrace/eval/comparison.py)

The original read event identifies an agent and file. The scope estimator
collects files first read by that agent after a login. When sessions overlap,
the log lacks the grant identifier that would tie a read to a particular
handoff. The follow-up records that identifier at the gateway and tests it
on overlapping assignments and held-out workflows.
[Scope features](../src/swarmtrace/features/scope.py) and [read attribution results](read-authorization-round.md)

Peters-Gill et al. describe a multi-agent protocol that preserves provenance
across agent boundaries. That offers a design precedent for carrying a grant
identifier through a hand-off. The accuracy measured here covers full traces
from the scripted simulator. Real-agent accuracy and online detection timing
require separate measurements. [Peters-Gill et al., Can CaMeLs Talk?](https://arxiv.org/abs/2610.05640)

## Reproduce

Run the comparison from the repository root after installing the locked
dependencies. The first command replays the original held-out split. Each
generator invocation writes a new directory containing the two compact test
tables. To score existing tables again, run the corresponding
`compare-detectors` command. The commands below use four simulation workers.

```shell
uv run --frozen swarmtrace compare-detectors --data data --seed 20261120 --out results-replay/archive.csv
uv run --frozen python -m swarmtrace.reproduce.accuracy_holdout --out results-replay/fresh --seed 20261123 --workers 4
uv run --frozen swarmtrace compare-detectors --data data --seed 20261120 --test-tables results-replay/fresh --out results-replay/first.csv
uv run --frozen python -m swarmtrace.reproduce.accuracy_holdout --out results-replay/confirm --seed 20261124 --workers 4
uv run --frozen swarmtrace compare-detectors --data data --seed 20261120 --test-tables results-replay/confirm --out results-replay/confirm.csv
```

Regeneration with four and ten workers produced byte-identical tables for
both seeds. The original and independent grids had disjoint run identifiers.

| Simulation seed | SHA-256 of `main/runs.csv.gz` | SHA-256 of `scope/runs.csv.gz` |
| --- | --- | --- |
| 20261123 | `c78b85bd64acc363e8453fca35079207288460bc3abf9f9f1bc2c5e322042f37` | `d33da24eed282947f9e1b529fc901ceb7dbd58b7725d69db3d000208b5d27db4` |
| 20261124 | `8f2b435d7aa8e7370a9bad83ceb88840081a565d1e6a1eb7169f987a9dc4e682` | `64b0aa0b8156693d82393eccc6de22d1f343eabb178e46659a97f298321ff4ad` |
