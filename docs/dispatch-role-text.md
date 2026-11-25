# Reading the recipient on a public approval ticket

Use the plain parser for tickets following this routing grammar. Both readers identified every named specialist on the 58 held-out tasks. Recovering the complete set also required correctly excluding the other candidates. The parser recovered 58 of 58 complete sets. DeBERTa recovered seven and abstained on at least one role in the other 51. A classifier supplied no additional correct designations. [Confirmation results](../benchmarks/dispatch-role-text/results/summary.json)

## What the reference establishes

EntCollabBench v1 provides 100 approval tasks; the release files contain 135 stages. The publisher names the reviewers in each stage's instructions and separately stores a business decision under the key for each participating specialist. We used only the presence of each role key to evaluate who was requested. The code reads no approval or rejection values. The three specialist roles are legal, procurement and finance. A fourth candidate, the unlisted records clerk used in the office replay, appears in none of the publisher's stage keys. These are externally authored scenarios with issuer-supplied structured answers. They have no separate human adjudication of role routing or swarm intent. [Publisher's paper](https://arxiv.org/abs/2605.08761v1) · [Pinned approval tasks](https://huggingface.co/datasets/Kirito-Lab/EntCollabBench/tree/df95c87317863d507f229df190b2c0a29c4e4afc)

Each reader saw exactly the same original lines spelling out the reviewers, document paths and instruction to route only to designated specialists. The question named one candidate role. The parser interpreted the publisher's explicit routing grammar. DeBERTa scored a fixed pair of statements about whether that recipient was designated or excluded. A strict score above 0.5 and a preference for one answer were required. Missing routing context, ties and low scores produced an abstention. Neither reader received the role keys, business outcomes, prior approval receipts, delivery records or later actions. The original lines can be recovered from the pinned inputs using the recorded excerpt hashes and support line numbers. The model quotes the entire routing block because an omitted role and the exclusivity clause can both matter. [Frozen protocol](../benchmarks/dispatch-role-text/protocol.json) · [Paired scores and evidence pointers](../benchmarks/dispatch-role-text/predictions.csv)

We retained the existing dispatch split. It groups each base task with all its stages, related policy topics and multistage pipeline families. The integration partition has 42 bases and 77 stages. Confirmation has 58 bases, each with one stage, across 43 topic groups. The publisher uses the same routing grammar on both sides, and the parser already recognized that grammar. The fixed protocol, candidate roles and two model hypotheses were written down before generating role predictions. The commit order that shows this is not part of this release. There was no tuning on confirmation. [Dispatch partition](../benchmarks/dispatch-workflows/protocol.json) · [Text protocol](../benchmarks/dispatch-role-text/protocol.json)

The source stores stage-level role participation. A reviewer of one document might be excluded from another document in the same stage. We therefore also projected the original routing lines onto the specific file used in the office. In this release, all routing lines within each of the 135 stages listed that stage's selected file. The two views and their scores were identical. The replay withholds document-specific reference metrics when the source clauses disagree on document membership. [Source-stage manifest](../benchmarks/dispatch-workflows/sources.csv)

## Which recipients did the readers identify?

| Held-out role | Requested | Absent | Parser correctly designated / correctly excluded | DeBERTa correctly designated / correctly excluded | DeBERTa false designations | DeBERTa abstentions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Legal specialist | 35 | 23 | 35 / 23 | 35 / 6 | 1 | 16 |
| Procurement specialist | 24 | 34 | 24 / 34 | 24 / 0 | 0 | 34 |
| Finance specialist | 23 | 35 | 23 / 35 | 23 / 2 | 0 | 33 |
| Three specialist roles | 82 | 92 | 82 / 92 | 82 / 8 | 1 | 83 |
| Unlisted records clerk | 0 | 58 | 0 / 58 | 0 / 20 | 0 | 38 |

On the 174 real specialist queries, the parser's designation precision and recall were both 100%. DeBERTa's precision was 82/83 (98.8%) and recall was 82/82. It gave a definite answer on 91/174 (52.3%), compared with the parser's 174/174. Across all four candidates, the model gave a definite answer on 111/232 (47.8%). On the integration partition the parser recovered all 77 complete sets and DeBERTa recovered eight. [Per-role precision, recall, confusion counts and coverage](../benchmarks/dispatch-role-text/results/role-metrics.csv) · [Exact sets by partition](../benchmarks/dispatch-role-text/results/stage-metrics.csv)

All four queries share the same ticket. Counting independent stages, at least one absent role was falsely designated on 0/58 parser stages and 1/58 model stages. Their one-sided exact 95% upper bounds are 5.03% and 7.92%, respectively. The observed rates are below 5%, but these 58 stages do not establish that ceiling at 95% confidence even for the parser. Some stages also share a policy topic. [Stage-level counts and bounds](../benchmarks/dispatch-role-text/results/stage-metrics.csv)

## Reading a ticket versus verifying a dispatch

The execution comparison uses the actual recipient and selected document on each of 61 deliveries across the 58 confirmation tasks. An excluded reading becomes an alert at the comparison point. A designated reading becomes clear. An abstention remains unknown. The local office records the authority in force at dispatch and can distinguish an accepted review that consumed the delivered version from an unused copy. The source ticket alone has neither of those witnesses. It supplies no measured alert arrival time. [Dispatch execution and timing](public-dispatch.md) · [Per-delivery comparison](../benchmarks/dispatch-role-text/results/primary-dispatches.csv)

| Per-delivery outcome | Ticket parser | DeBERTa | Structured dispatch check |
| --- | ---: | ---: | ---: |
| Warned on an actually excluded recipient | 50/50 | 16/50 | 41/50 |
| Warned on an actually authorized recipient | 0/11 | 0/11 | 0/11 |
| Flagged a completed unapproved use | 32/32 | 9/32 | 23/32 |
| Missed a completed use through abstention | 0/32 | 23/32 | 9/32 |
| False alerts on deliveries without a completed unapproved use | 18/29 | 7/29 | 18/29 |
| Flagged unused deliveries | 18/18 | 7/18 | 18/18 |

All 50 excluded primary deliveries targeted the single literal `unlisted_records_clerk`, whose name both readers saw in the role query. All 11 authorized deliveries went to requested specialists, six legal, three procurement and two finance. The primary comparison therefore benefits from an unusually informative role name. The source uses a common routing grammar throughout, and the office does not revoke approvals after ticket creation.

## What changes with an ordinary recipient name?

After seeing the primary results, we reran the same schedules with an ordinary
legal, procurement or finance specialist who was absent from the document's
routing list. We chose the replacement by a hash of the task ID, independently
of predictions and outcomes. Forty-three tasks had an eligible replacement,
covering 46 excluded deliveries. Eleven authorized tasks served as unchanged
controls. Four other tasks named all three specialists and had no eligible
replacement. They accounted for three completed effects and one unused copy.
Each eligible pair used the same source bytes, sequence of office operations,
transport schedule and commit outcome. This post hoc check reuses the original
tickets and the published role scores. It adds zero independent swarm rounds.
[Matched deliveries](../benchmarks/dispatch-role-text/sensitivity/deliveries.csv)

| Among the same 46 excluded deliveries | Clerk name | Ordinary specialist name |
| --- | ---: | ---: |
| DeBERTa warnings before considering the outcome | 13 | 2 |
| DeBERTa abstentions | 33 | 43 |
| DeBERTa warnings on completed unapproved uses | 7/29 | 1/29 |
| DeBERTa warnings on unused copies | 6/17 | 1/17 |
| Parser warnings on completed unapproved uses | 29/29 | 29/29 |
| Parser warnings on unused copies | 17/17 | 17/17 |

DeBERTa incorrectly designated one ordinary recipient. It abstained on all
16 finance and 19 procurement deliveries. Neither reader warned on any of
the 11 authorized deliveries. The structured dispatch and commit checks both
detected 21 of the 29 completed effects under either name. Eight lacked an
approval receipt. Dispatch also warned on all 17 unused copies. Checking the
input version at commit cleared all 17. The parser reads this release's fixed
grammar accurately, while determining whether someone used the copy still
requires execution evidence. [Paired scorecard](../benchmarks/dispatch-role-text/sensitivity/summary.json)

Even with complete text matching, the parser warned on every unused excluded copy. DeBERTa reduced that count by abstaining and missed 23 completed uses. Each method exceeded the 5% false-alert budget for completed effects. Verifying use requires observing what the recipient actually consumed. These role and delivery results contribute zero qualifying swarm rounds. [Execution counts and exact upper bounds](../benchmarks/dispatch-role-text/results/summary.json)

## Reproduction

The ordinary offline replay requires the published prediction tables and dispatch benchmark. It runs without model weights, external task text or network access.

Two full CPU inferences of 1,080 premise-hypothesis pairs produced identical
raw predictions and scorecards. The longest sequence occupied 363 tokens.
Two Windows executions and a Linux execution of the matched-recipient office
comparison also reproduced its delivery table and summary byte for byte.
[Inference manifest](../benchmarks/dispatch-role-text/manifest.json)

```sh
uv run --frozen python -m swarmtrace.reproduce.dispatch_role_text replay --out results-replay/dispatch-role-scorecard
uv run --frozen python -m swarmtrace.reproduce.dispatch_recipient_sensitivity --out results-replay/dispatch-recipient-pairs
```

Full inference uses the three original hash-pinned approval assets and the same local DeBERTa checkpoint used for the transfer-necessity experiment. To recover an excerpt, specify the source directory, stage, role and reader. The publisher's data card at this revision supplies no dataset license identifier. Only role membership keys, identifiers, hashes, model outputs and derived counts are published here. Original ticket prose, file contents, business decisions and model weights remain in their upstream distributions. [Dispatch source setup](public-dispatch.md#reproduction) · [CPU inference environment](../benchmarks/dispatch-role-text/manifest.json) · [Model card](https://huggingface.co/MoritzLaurer/deberta-v3-large-zeroshot-v2.0/tree/cf44676c28ba7312e5c5f8f8d2c22b3e0c9cdae2)

```sh
python -m swarmtrace.reproduce.dispatch_role_text rebuild --source results-replay/public-dispatch-inputs --snapshot /path/to/pinned/model --out results-replay/dispatch-role-inputs
uv run --frozen python -m swarmtrace.reproduce.dispatch_recipient_sensitivity --source results-replay/public-dispatch-inputs --out results-replay/dispatch-recipient-fresh
uv run --frozen python -m swarmtrace.reproduce.dispatch_role_text replay --study results-replay/dispatch-role-inputs --out results-replay/dispatch-role-rebuilt
uv run --frozen python -m swarmtrace.reproduce.dispatch_role_text quote --source results-replay/public-dispatch-inputs --stage appr_multi_1_1 --role legal_approval_specialist --method parser
```
