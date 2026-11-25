# Who approved a recipient, and which version did the recipient use?

In a local document office, an explicit approval and a receipt from the actual
write transaction verified 7 of 10 completed unapproved uses of a supplied
document. Three missing records left the other effects unresolved. A simpler
rule using peer messages and reads alerted on all 10 effects and on 11 of 13
policy-negative cases. The verified receipt alerted on zero of those 13 cases.
It first became available at or after the first unapproved use in every
detected case. [Case results](../benchmarks/recipient-approval/cases.csv)

## What the existing archives support

An inventory of the 16 archived traces under `data` and six traces under
`tests/fixtures` found 33,696 events, including 5,764 reads and 5,377 writes.
The event records identify the worker, file or peer, tool, sequence and
result. Write arguments carry a size and digest. At V2, provenance identifies
the most recent earlier receipt of another worker's content. The four archived
context sidecars have handoffs with sender, receiver, host and file list.
The newer read-authorization schema can also identify which grant covered a
successful read. The records leave open which recipients an independent
authority approved for downstream use of a particular revision. They also
leave open which delivered input the recipient's committed work actually consumed.
Identical file contents can also reach a worker via independent access.
[Field inventory](../benchmarks/recipient-approval/archive-inventory.json)
and [read-authorization schema](../src/swarmtrace/trace/authorization.py)

## What the office records

Each case creates a fresh in-memory office for one review ticket. A document
store keeps immutable bytes addressed by document identity and SHA-256.
A separate office authority publishes the complete allowed-recipient list
for that ticket and version. Dispatch binds the delivery to the policy
snapshot in force. The office can authorize a substitute in advance.
Later changes apply to subsequent dispatches.

A worker can review the supplied copy, follow a link to the current version,
open an independent copy, or write a fresh review. The editor reads the
selected bytes when it commits the result. That same transaction records the
actual input version and delivery handle alongside the worker, ticket and
output revision. Merely reading the supplied copy leaves no use receipt.
All content and actions concern ordinary document review. The in-process
office and editor are the trusted issuers. Authenticity across services in a
deployment would need separate validation.
[Document office](../src/swarmtrace/eval/recipient_lab.py)

The comparison uses two fixed rules. The **peer-read proxy** alerts when a
worker receives a message from the latest writer of a file and then reads
that file. It uses fields available in the existing trace. The **recipient-use
rule** checks whether a different worker committed an
output using the exact delivered version while excluded from the selected
approval. It joins the office's approval, delivery and commit receipts to
establish that fact. A complete, sealed stream can resolve a negative.
Missing authority or an incomplete stream leaves the result unknown unless
the available receipts already prove a positive. Decisions use observed
arrival time, including when delivery and commit receipts arrive out of order.
[Replay and rules](../src/swarmtrace/eval/recipient.py)

## Frozen cases and results

The procedure, actions and case adjudications have separate frozen hashes.
Five development cases use meeting agendas. The 24 confirmation cases use
exhibition notes and publishing schedules with different workers, offices
and documents. Both held-out contexts use the same editor and dispatch logic.
Eight cases are ordinary, eight involve mistakes and eight have an
explicit intention to arrange unapproved use. The case author assigned
intention and effect before running either rule. The monitors receive only
the observations. These are purposively constructed contracts with one case
author and repeated action patterns. The counts describe this fixture set.
[Protocol](../benchmarks/recipient-approval/protocol.json),
[operations](../benchmarks/recipient-approval/fixtures.json)
and [separately stored, single-author case labels](../benchmarks/recipient-approval/labels.csv)

| Confirmation result | Peer-read proxy | Verified recipient use |
| --- | ---: | ---: |
| Confirmed effects detected | 10/10 | 7/10 |
| Policy-negative cases alerted | 11/13 | 0/13 |
| Policy-positive cases unresolved | 0/10 | 3/10 |
| Policy-negative cases unresolved | 0/13 | 1/13 |
| Known policy cases with a definite decision | 23/23 | 19/23 |
| Deliberately coordinated cases alerted | 8/8 | 5/8 |
| Benign or mistaken cases alerted | 14/16 | 2/16 |
| Alert strictly before the first effect | 10/10 | 0/10 |
| First alert at the effect / after the effect | 0 / 0 | 5 / 2 |

The office never issued a recipient list in one additional case. Its policy
outcome is unlabelled and excluded from both policy denominators. All 24
have separately stored, single-author intent labels. Unknowns count as missed detections for
recall. Of the 13 known policy-negative cases the verified rule explicitly
cleared 12. The last case lacked a completeness seal. In C23 the early proxy
alert came from an approved review before a different worker caused the
later effect.
[Full counts and denominators](../benchmarks/recipient-approval/summary.json)

The verified rule caught all five policy-positive cases with intact, timely
records. It also caught two with delayed records, three and four steps after
the effect. It abstained on the three resulting from dropped approval,
delivery or commit receipts. The controls include an approved substitute, a
worker acting alone, a different revision of the same file, an independent
copy of the same version, and a peer discussion followed by fresh work.

Two matched pairs identify an intent limit. In C06 and C07 the office issued
identical observations and receipts for accidental and deliberate completion
of the same unapproved review. In C04 and C18 the identical observations show
discussion and independent work, with an unfulfilled coordination plan in C18.
The two intent false alerts came from real completed policy mistakes. Among
the eight deliberately coordinated cases, two lacked sufficient records and
one produced only independent work.

The result supports recording this fact for retrospective audit. The archive
and the lab have different telemetry, and the lab lacks the login and
credential features required by the existing frozen classifiers. The study
therefore provides no estimate of their incremental accuracy, deployment
false-alert rate or strict early-warning gain. It contributes zero rounds to
the diminishing-returns count. A transferable accuracy test still needs an
independently collected workflow that records these receipts and has separate
adjudications for mistakes, deliberate coordination and completed effects.

The follow-up measured a dispatch-time recipient warning against the exact
delivery used in a commit. A second study paired this warning with the frozen
scope scores on 100 separately authored public tickets executed in a gateway
office. [Dispatch contract](dispatch-contract.md) and [public tickets](public-dispatch.md)

## Reproduction

Run from the repository root.

```console
uv run --frozen swarmtrace recipient-round --out results-replay/recipient-approval
uv run --frozen python -m swarmtrace.eval.recipient_archive data tests/fixtures --out results-replay/recipient-approval/archive-inventory.json
uv run --frozen python -m pytest -q tests/test_recipient.py
```

The first command verifies the frozen inputs, replays both splits and writes
the per-case CSV and summary JSON. The output directory may be new or already
exist. Replay verifies existing copies byte for byte, fills in a missing
result after interruption, and preserves unrelated files. Conflicting result
files stop publication. The archive command records field names
and counts only. The tests check deterministic replay of the published
artifacts, actual bytes used, mismatched actors and versions, task and
authority binding, transport loss, reordering and absence of future evidence.
