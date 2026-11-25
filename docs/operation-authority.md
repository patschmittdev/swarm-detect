# Which permission applied when a worker used a document?

On 58 public approval tickets replayed in the local office, the operation-time
reviewer confirmed **20 of 26 unapproved uses** and raised **zero alerts on
32 control tasks**. Looking up the final saved permissions also found 20
violations, but flagged ten controls. Those ten workers had permission when
they acted. The operation-time reviewer left six positives and three controls
unresolved because evidence was missing or contradictory.
[Primary counts and paired comparisons](../benchmarks/operation-authority/results/summary.json)

| Evidence used to judge the completed use | Violations flagged, of 26 | Controls flagged, of 32 | Unresolved positives / controls |
| --- | ---: | ---: | ---: |
| Original ticket's recipient list | 14 | 3 | 3 / 3 |
| Permission when the copy was sent | 17 | 6 | 3 / 3 |
| Final durable permission snapshot | 20 | 10 | 3 / 3 |
| Permission at the worker's write | 20 | 0 | 6 / 3 |

The identical total for the snapshot and operation-time checks hides a
different set of decisions. Each found three violations the other missed.
The snapshot falsely flagged four completed one-time uses, three explicitly
renewed one-time permissions and three uses revoked only after completion.
Compared with checking at dispatch, the operation-time check gained six
violations and lost three where the authority history was incomplete. Of its
20 confirmations, 17 arrived at the write and three arrived afterward when a
delayed revocation receipt became available. It gave zero pre-use warnings.
[Individual operations](../benchmarks/operation-authority/results/operations.csv.gz)

The 58 primary tasks contained 64 writes, including three tasks with both
an authorized first use and an unapproved repeat. Across the 38 authorized
or nonmatching writes, the final snapshot flagged 16. The operation-time
reviewer flagged zero. Every detected positive task had a warning on its
actual unapproved use. Writes on the same ticket and the stress runs reuse
evidence. Their interval calculations should be read as descriptions of those
samples. [Per-write scorecard](../benchmarks/operation-authority/results/summary.json)

## What was measured

The protocol was fixed before scoring; the commit order that shows this is
not part of this release. A hash-ordered rotation assigned
one of 18 conditions per ticket. These were the same 58 previously examined
EntCollabBench tickets across 43 topic groups. Each source document came from
the publisher's original, hash-verified asset. Swarmtrace supplied the workers,
timing, permissions and execution. Running every condition once on every
ticket produced 1,044 runs and 1,160 editor writes. Only the 58 preselected
runs enter the primary table. [Frozen protocol](../benchmarks/operation-authority/protocol.json)
and [individual task decisions](../benchmarks/operation-authority/results/cases.csv.gz)

The local gateway supplies the worker, session and write sequence. At write
time the editor records the delivery handle and input version. The evaluator
checks the bytes in the actual output against that input's SHA-256. An
independent input with the same bytes and a newer version opened through the
same handle are controls for a claim about the original delivery. The
SQLite register holds the live permission used for the evaluation. Each
write commits the output bytes, one-time consumption and authority receipt
in one transaction before the local office publishes the editor state. The
reviewer gets the observed request, result, input and authority history. It
never reads the live evaluation table.
[Office transactions](../src/swarmtrace/eval/operation_office.py)
and [passive reviewer](../src/swarmtrace/eval/operation_authority.py)

The experiment uses direct grants. The worker needs permission for this
ticket and document version when its completed edit consumes the delivery.
A separate system can grant a lease that survives revocation of the original
approval. Four independently published service attempts consumed a still-valid
reservation after the source approval was lost. The governing rule and its
issuer must be established before interpreting an outside system's receipts.
[External service evidence and human-rated cases](approval-evidence-inventory.md)

## Could we recover the nine earlier misses?

Yes, in the office where the issuer retained its copy. We reran all 58 prior
primary schedules and checked each original decision and physical outcome
against the archive. The issuer saved its approval at issuance through a
separate path. At case end the reviewer requested only missing handles named
by observed deliveries and checked the issuer, ticket, version and validity at
dispatch. All nine missing records were recovered. Confirmed completed
violations rose from **23/32 to 32/32**, with **0/26 control alerts** both
times. When the issuer returned nothing, the same nine cases stayed
unresolved. This is recovery at case end under the original dispatch rule.
[Case-by-case recovery](../benchmarks/operation-authority/results/historical-recovery.csv)

## What this changes for swarm detection

Use effective permission history for after-the-fact access review. The
one-sided exact 95% upper false-alert bound for zero in 32 controls is
**8.94%**, even under a binomial calculation treating tickets as independent.
The 43 shared topic groups further limit a field-rate interpretation. A 5%
deployment ceiling cannot be established from this test.

Across all 58 tickets the clerical mistake and the scripted deliberate use
produced byte-identical reviewer inputs on the same ticket. The public
human-rated cases concerned reciprocal agreement in a grading game. None
linked those judgments to changing approvals and actual file consumption.
This contributes **zero independently labeled swarm-accuracy rounds**.
[Matched evidence fingerprints](../benchmarks/operation-authority/results/motive-pairs.csv),
[source inventory](approval-evidence-inventory.md) and [round criteria](detector-rounds.md#measuring-diminishing-returns)

## Reproduction

From the repository root, run the first command to fetch missing pinned
ticket inputs and reproduce the five artifacts. The second command uses
the same cached inputs offline. Each output directory must be new.

```shell
uv run --frozen swarmtrace operation-authority --fetch --out results-replay/operation-first
uv run --frozen swarmtrace operation-authority --out results-replay/operation-offline
```

The optional external replay checks the published service and human study
against their own labels. [External replay commands](approval-evidence-inventory.md#reproducing-the-checks)
