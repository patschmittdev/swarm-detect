# How much warning does a document dispatch give?

A warning at dispatch preceded six of ten completed unapproved uses in the
released document-office cases. Four warnings arrived two steps before use
and two arrived three steps before use. Two additional warnings arrived
three and four steps after use. Missing delivery or approval records left
two effects unresolved. Five excluded recipients triggered warnings even
though their delivered copy never became an input to a completed review.
[Per-delivery results](../benchmarks/recipient-dispatch-contract/deliveries.csv)

The confirmation partition contains 24 cases. Three had no dispatch and two
had two dispatches. Of 23 deliveries, ten led to unapproved use of that
exact copy, twelve were known negatives and one lacked a recipient policy.
Seven deliveries were unused. These purposefully chosen cases and their
intent labels come from the earlier single-author experiment. They measure
how the rules behave on these examples. The protocol fixes the release
hashes, endpoints and strict arrival-time comparison.
[Frozen protocol](../benchmarks/recipient-dispatch-contract/protocol.json)
and [original cases and authorship](recipient-approval.md#frozen-cases-and-results)

| Rule | Completed effects detected | Same delivery flagged strictly before use | Known negative deliveries flagged | Unused deliveries flagged |
| --- | ---: | ---: | ---: | ---: |
| Recipient excluded at dispatch | 8/10 | 6/10 | 5/12 | 5/7 |
| Commit consumed the unapproved delivery | 7/10 | 0/10 | 0/12 | 0/7 |
| Peer-read proxy, matched to the actual input | 10/10 | 10/10 | 8/12 | 3/7 |

A dispatch warning requires the exact selected approval handle, authority,
ticket, version and a different recipient excluded from the authorized
list. Its clock starts when both receipts have arrived. A
later exception affects subsequent deliveries. The commit rule also
requires the editor's actual input for the same delivery. A complete,
sealed stream can establish that a delivered copy was unused. The
evaluator records what the office actually did before transport loss or
delay affects observations. [Monitor and transaction witnesses](../src/swarmtrace/eval/recipient_dispatch.py)

The peer-read proxy observes native receives, reads and file writers. After
it fires, the evaluator checks which delivered version the editor actually
opened. In C23 an approved worker's read first fired the proxy at step 3.
The read tied to the later unapproved use occurred at step 6, one step
before the effect. Independent reads and other versions remain unpaired
in the per-delivery comparison. On whole cases the proxy flagged 11 of
13 known negatives, the dispatch rule flagged five and the commit rule
flagged zero. Against the supplied coordination-intent labels, dispatch
flagged six of eight positives and seven of sixteen negatives.
[Case results](../benchmarks/recipient-dispatch-contract/cases.csv)
and [counts by split and workflow](../benchmarks/recipient-dispatch-contract/summary.json)

Use the dispatch result to inspect an excluded recipient while a review is
still pending. Use the commit receipt when checking whether that recipient
actually acted on the supplied version. The same warning occurred for
an accident and for deliberate use in the matched C06 and C07 cases.
These results contribute zero rounds toward the independent swarm
promotion and stopping criteria.

```shell
uv run --frozen swarmtrace dispatch-contract --out results-replay/dispatch-contract
uv run --frozen pytest -q tests/test_recipient_dispatch.py tests/test_recipient.py
```
