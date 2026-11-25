# Reproducing the results

The README gives the short version. This page has every command, the seeds,
the grids and what each command writes. Commands are shown for PowerShell; on
other shells use `uv run --frozen swarmtrace ...` in place of
`.\.venv\Scripts\swarmtrace ...`; that form is portable.

Use Python 3.12 and the dependency versions in `uv.lock` for byte regeneration.

```powershell
uv sync --python 3.12 --extra dev --frozen
.\.venv\Scripts\python -m pytest -q -p no:cacheprovider
.\.venv\Scripts\ruff check .
.\.venv\Scripts\swarmtrace reproduce --seed 20261120 --out reproduce-out --workers 4 --readme RESULTS.md
.\.venv\Scripts\swarmtrace evasion --seed 20261120 --out evasion-out --workers 4
```

The command simulates the grid, extracts features, fits detectors, evaluates
by-run and held-out splits, and writes Markdown tables in `reproduce-out/`.
Compare the generated files with the corresponding artifacts in `data/` using
the SHA-256 hashes in each `experiment.json`. The source revision and settings
must match for byte comparisons. `--readme RESULTS.md` pastes a short block
between the markers above, after the loud control passes. `headline.md` holds
the full headline. Full reports remain separate files. Use a fresh output
directory for another run;
an output directory containing only `README.md` and/or a separately generated
`split-stability.md` is also allowed. Nothing is committed
automatically. A non-zero exit is not a successful reproduction, even if tables
were written. Null and unflattering results are kept as measured. After
copying a regeneration into `data/` and running the split-stability command
below, `swarmtrace verify --data data` must exit 0.

Run the separate 0%, 5%, 10% and 30% benign credential-sharing experiment into
a fresh directory, then copy its report and V1 run tables into `data/`:

```powershell
.\.venv\Scripts\swarmtrace sharing-sweep --seed 20261120 --out sharing-sweep-out --workers 4
Copy-Item sharing-sweep-out/sharing-sweep.md data/sharing-sweep.md
Copy-Item sharing-sweep-out/sharing-sweep data/ -Recurse
.\.venv\Scripts\swarmtrace verify --data data
```

`--out data` refuses because artifacts already exist there. Use a new output
directory for each invocation. `--workers` has the same default as `reproduce`.
Each rate uses three replicates per positive condition and 90 runs per control
condition: 162 positive and 1,620 control runs, with 340 calibration controls.
Preflight refuses fewer than 19 calibration controls. The replacement sweep's
run, split, calibration, fit and bootstrap seeds descend from
`child_seed(seed, 91, rate_index, 2, ...)`; the main dataset's seeds are unchanged.
Each rate fits and calibrates its own models. The report includes restricted
and overall AUROCs with intervals, sharing-control counts, both interval
containment checks, detection rates, FPRs and calibrated thresholds.
The final fenced hash block lists each rate's `runs.csv.gz`; verify checks the sweep hashes
and fails on a missing or changed file or a malformed block. `sharing-sweep.md`
itself is excluded from the unlisted-file warning. Sweep hashes stay separate
from the main `experiment.json`.

The separate scope experiment first checks every identical-policy twin, then
writes `scope.md`, `scope-identical.md`, `scope/runs.csv.gz`, and two raw samples.
Use a fresh output directory. Time 50 simulations first to print a simulation
runtime projection; timing mode leaves no result artifacts. The full experiment
also extracts features, fits detectors, and writes reports.

```powershell
.\.venv\Scripts\swarmtrace scope --seed 20261120 --out scope-timing --workers 4 --time-runs 50
.\.venv\Scripts\swarmtrace scope --seed 20261120 --out scope-out --workers 4
```

The seed is **20261120**. The main grid is coordinated groups {1, 2, 3}, channel
{message, shared_file, preplanned}, topology {hub, peer}, and offensive group size
{0, 2, 3, 5}. Each positive condition has two replicates. Control conditions use
eight repeats per replicate, giving 16 independently seeded runs per control
condition: **108 positive and 288 control runs** in total. This oversampling is
recorded in `experiment.json`; it supplies enough
calibration controls for every reported split at a 5% target false-positive rate.

The separate all-benign sweep has **18 control runs**, one per combination of
group count, channel and topology, including the same 10% sloppy-sharing rate.
The loud sweep has **3 positive runs**, one per channel, with five members, peer
topology and 32 extra uses of the borrowed credential per member after completing
their assignment. Neither sweep contributes to fitting or calibration. Both
logistic and boosted at V1 using aggregation features must flag every loud run
at the calibrated threshold and score it strictly above every calibration control
with `benign_sharing_teams == 0`. In the recorded data the second bar is implied
by the first, because the highest such control scores far below the threshold.
Logistic must additionally score every loud run
strictly above every calibration control. Ties fail strict comparisons. The
boosted comparison against all calibration controls remains a separate,
non-gating row in `controls.md`, with its measured outcome and score bounds.
The comparison subsets use conditions from the recorded main dataset after
model fitting and calibration; they do not change model inputs or thresholds.
If a required bar fails, the command exits non-zero, names the detector and bar,
and retains the diagnostic tables. The loud configuration remains unchanged.

Default simulation length remains **160 ticks**. Reproduce and ordinary `eval`
on raw runs use checkpoints every **8 ticks**, plus the final tick. Saved datasets
carry their own cadence, recorded in the manifest and every results table.
Extraction uses standard-library processes across runs; model fitting also uses
processes with one native numerical thread each. `--workers` defaults to at most
four. RNG streams and output ordering are independent of worker count. The
command took **5 minutes 13 seconds** at `--workers 4` on a 20-core desktop
running Windows and Python 3.12. Laptop runtimes will vary.

The evaluator divides whole runs into fitting, calibration and test sets.
Imputation, scaling, classifier fitting and attribution's internal folds see only
fitting runs. Thresholds use calibration controls. Held-out channel and topology
results are reported separately from the by-run results. No test row enters a fit
or a threshold calculation. Rates use 95% Wilson intervals, including zero counts.
Attribution rates are counts of agents, with intervals from a bootstrap over runs
that reports valid and requested resamples. AUROC and means use 200 bootstrap
resamples, treating runs as independent even though each control condition has
16 replicates (2 runs per condition x 8 control repeats).

Each tier reports generic features alone, aggregation features alone and all
features for logistic and boosted detectors and the pair attribution scorer.
The unchanged volume baseline is repeated and labeled **family-independent** in
each table. Its columns do not change with the family setting. Detector-gated
attribution still uses the pair scorer for the selected family.

The negative control refits every detector and tier for 20 seeded permutations
of labels across whole runs, preserving class counts. It reports mean, standard
error (sample SD divided by the square root of the permutation count), and range
of by-run AUROC for every feature family. These describe permutation variability
on the same dataset, not uncertainty over new runs. No pass/fail criterion is
applied: the SE alone does not justify a general no-signal test on overlapping
splits. No permutation is selected or retried to obtain a favorable result.

The containment experiment (`docs/design-phase3.md` section 3) refits the frozen
main detectors from the recorded main dataset and runs paired arms:

```powershell
.\.venv\Scripts\swarmtrace containment --seed 20261120 --data data --out containment-out --workers 4
```

It writes `containment.md` and `containment/` (the run table and one raw twin
and contained arm), which correspond to `data/containment.md` and
`data/containment/`. Output does not depend on `--workers`.

## Recorded data and offline evaluation

The comparison of audit and scope detectors uses the archived fitting data
and two independent simulation seeds. Its commands and test-table hashes
are in the [detector accuracy study](detector-accuracy.md).

The read-authorization study includes event-level fixtures, 108 role-flipped
pairs, a held-out workflow and a fresh test of the alert cutoff. Its commands
rebuild the study from the simulator and archived fitting data.
[Read authorization study](read-authorization-round.md)

The grant-count study publishes both models' observable inputs, per-run
scores, controls, intervals and exact feature-vector collision counts. Its
follow-up records the independent same-issuer confirmation and the audit
of the original policy on runs without overlapping assignments.
[Protocol and replay commands](grant-scope-round.md)

The assignment study scores each exercised grant and calibrates the maximum
on complete runs. Its follow-up compares against unrounded whole-run logistic
scores on ten further grids. Separate replays verify which team shared a
document and count false alerts from earlier accidental appendix reads. The
document-review replay measures when a verified receipt first establishes
unapproved downstream use. [Assignment commands](assignment-round.md#reproduction-and-inspection)
and [recipient commands](recipient-approval.md#reproduction)

The public-ticket study runs a document office on the 100 pinned EntCollabBench
approval tasks, with an optional download followed by fully offline replay.
Its review command verifies the blinded packets and recorded ballots. The
separate MCPHunt comparison replays both human annotators' published ratings
against the text reader and parser without loading model weights.
[Workflow and review commands](public-dispatch.md#reproduction),
[dispatch contract](dispatch-contract.md), [same-ticket role reader](dispatch-role-text.md#reproduction)
and [human-rated transfer reader](approval-text.md#reproduction-and-attribution)

To replay the public Claude Code and Grok captures, run
`uv run --frozen swarmtrace native-hook-benchmark --fetch --out results-replay/native-hooks`.
The command checks two pinned source files and writes aggregate counts. Omit
`--fetch` to replay offline from the same cache.
[Native hook benchmark and local review command](native-hook-review.md)

The operation-time test replays the same public tickets with one-time grants,
revocations and later exceptions. It also recovers missing dispatch approvals
from an issuer copy saved when each approval was issued.
[Workflow replay](operation-authority.md#reproduction) and [independent public evidence](approval-evidence-inventory.md#reproducing-the-checks)

`data/` contains the recorded dataset and generated results tables, totaling
**16 MB**. It includes compressed per-tier run, volume,
pair and checkpoint feature tables for **every** main, benign and loud run:
396 main runs, 18 independent benign runs and 3 loud runs. Run tables include labels
and conditions; manifests retain agent labels and objective outcomes for
attribution and timing. The simulator records `benign_sharing_teams` in each run's
manifest condition, never in the trace, to count benign teams assigned credential
sharing. The headline uses this label-side count to restrict one comparison to
positive runs versus test controls containing at least one such team.

Third parties fitting on recorded tables must drop every `label_*` and
`condition_*` column; these columns contain ground truth and experimental
conditions. The supplied loader performs this separation before passing matrices
to detectors. Raw samples contain full V2 trace, label and
manifest files, each gzip-compressed: six main runs covering channel and class,
one benign run, and all three loud runs. It does **not** contain raw traces for
the other runs, fitted models, private prompts, LLM outputs, network captures,
or observations from real users or organizations.

All files are generated from the seed. CSV uses UTF-8 and LF, with round-trip
floating-point precision. Gzip has `mtime=0` and no filename header. A top-level
manifest records conditions, run seeds, split membership, settings and artifact
SHA-256 hashes. Worker count and the output path do not enter artifact bytes.
The command rejects an output of 15,000,000 bytes or more. Regenerate into a fresh
directory with the same locked environment to compare bytes.

```powershell
$env:OMP_NUM_THREADS = "1"
$env:OPENBLAS_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
.\.venv\Scripts\swarmtrace eval --runs data --out results-replay --seed 20261120 --hold-out channel topology --bootstrap 200 --families generic aggregation all
```

This replays the main detection, online and attribution tables directly from saved
features, without simulation or raw traces. `eval --workers` is ignored for
recorded datasets; it only controls extraction from raw runs.
`eval --runs data/dataset/benign`
would instead fit on an all-benign dataset and cannot estimate a two-class
detector. The all-benign FPR and loud tests in `controls.md` use models trained on
the main dataset, as described above. The orchestration command writes those
controls and the shuffled-label table.

Split stability is a separate recorded-data diagnostic to keep those fits out
of the approximately ten-minute reproduction budget. The command below writes
`data/split-stability.md`, with mean and sample standard deviation of full-trace
test AUROC over 20 different by-run split seeds, beside the single reported value.
The original split is one of the 20. Fitting and calibration seeds and fractions
stay fixed. No online model or bootstrap is run in this diagnostic.
Include the generated `data/split-stability.md` when committing the recorded
results. Reproduce neither requires nor overwrites this separate artifact, and
excludes it from `experiment.json` artifact hashes, so generating it separately
does not change the reproduction manifest.

```powershell
.\.venv\Scripts\swarmtrace eval --runs data --out data --seed 20261120 --split-stability --families generic aggregation all
```

The committed-raw regression test regenerates four samples (two main, one benign,
one loud), compares all three compressed run files byte-for-byte, then compares
their V0, V1 and V2 run-feature rows.
It requires populated, current `data/` and does not silently skip missing samples.

Full generated reports: [V0](../data/results-V0.md), [V1](../data/results-V1.md),
[V2](../data/results-V2.md), [controls](../data/controls.md),
[shuffled labels](../data/negative-control.md), [inventory](../data/inventory.md),
and [split stability](../data/split-stability.md).

## Agent pilot

Background, caveats and what each command refuses to overwrite are in
[agent-pilot.md](agent-pilot.md#reproduce). The test-set and transfer scorers
write only to their fixed directories under `benchmarks/agent-pilot/results/`,
so a replay runs in a separate copy of the repository with that directory
removed. `batch` launches real agents.

```shell
uv run --frozen python -m swarmtrace.study pilot --runs benchmarks/agent-pilot/runs/test --protocol benchmarks/agent-pilot/protocol.json --set test --freeze benchmarks/agent-pilot/freeze.json
uv run --frozen python -m swarmtrace.study pilot --runs benchmarks/agent-pilot/runs/development --protocol benchmarks/agent-pilot/protocol.json --set development --freeze benchmarks/agent-pilot/freeze.json --out dev-scores
uv run --frozen python -m swarmtrace.pilot export --run benchmarks/agent-pilot/runs/test/test-19 --out OUTDIR/test-19.jsonl
uv run --frozen python -m swarmtrace.fleet score --events OUTDIR/test-19.jsonl --json
uv run --frozen python -m swarmtrace.fleet explain --events OUTDIR/test-19.jsonl
uv run --frozen python -m swarmtrace.pilot batch --protocol benchmarks/agent-pilot/protocol.json --set test --out NEW-RUNS --parallel 3
uv run --frozen python -m swarmtrace.study fetch-control --out CONTROL.tsv.bz2
uv run --frozen python -m swarmtrace.study transfer --incident INCIDENT-FILE --control CONTROL.tsv.bz2 --freeze benchmarks/agent-pilot/freeze.json
```
