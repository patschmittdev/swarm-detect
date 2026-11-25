# Does an excluded recipient give enough warning?

On 58 held-out public approval tickets executed in the local document office, a
recipient check flagged the exact delivery before 17 of 32 completed unapproved
uses. It also flagged 15 of 26 tasks where no such use occurred. Waiting for the
editor to identify the version it actually consumed detected 23 of 32 with zero
false alerts. The earliest of those confirmations arrived at commitment. Use
the dispatch record to inspect pending work and the commit receipt to verify
completed use. Neither result supports automatic swarm escalation.
[Paired operating points](../benchmarks/dispatch-workflows/scorecard.csv)

## Where the tasks and outcomes came from

Yu et al. released 80 single-stage and 20 multistage approval tickets in
EntCollabBench. Their instructions identify the submitting role, designated
specialists and named documents. We took the first document requested of the
first named specialist at each of the 135 stages in the release files and
checked its original bytes in the publisher's folder for every other specialist
assigned that document. We used this routing instruction as the recipient list
in the local office and recorded the permission before dispatch. A publisher
judgment about whether to approve a purchase supplies no evidence that another
recipient was authorized to see it. The source manifest identifies each stage,
file digest and routing decision. [Paper](https://arxiv.org/abs/2605.08761),
[publisher's release](https://huggingface.co/datasets/Kirito-Lab/EntCollabBench/tree/df95c87317863d507f229df190b2c0a29c4e4afc)
and [source manifest](../benchmarks/dispatch-workflows/sources.csv)

Swarmtrace executed the actions, issued file-read grants, recorded which
version each worker received, and checked the actual bytes used at commit.
File-read permission and approval to receive a handoff are separate decisions.
The assignment score saw the gateway's selected grants. The whole-run model
saw the same office actions through its usual audit and scope inputs. Both
used their earlier fit and control-derived cutoff. Each prefix contained only
records available by that step. The full office journal supplied the outcome
even when a transport schedule delayed or dropped the monitor's copy of a
receipt. These are new local executions of public instructions. The publisher
did not supply the actions, their timing, or the workers' motives.
[Office and frozen baselines](../src/swarmtrace/eval/dispatch_baselines.py)

We froze the split, 14 schedules, primary comparison and outcome before
scoring. All tasks sharing a policy topic, its negation variant, or a linked
multistage pipeline stayed together. The six examples inspected during
integration put 42 tasks and all 20 multistage tickets in the integration
partition. Confirmation comprised 58 single-stage tasks in 43 groups. The
source uses a common routing sentence across partitions. A deterministic
hash picked one eligible schedule per task. Running every eligible schedule
produced 1,346 task replays, 1,820 executed stages and 1,920 deliveries. The
774 confirmation stress replays reuse the same 58 tickets. They measure how
the rules respond to individual conditions. Only the 58 preselected replays
enter the primary comparison.
[Frozen protocol](../benchmarks/dispatch-workflows/protocol.json)

## What each method detected

| Frozen method | Completed effects detected, of 32 | Control tasks flagged, of 26 | Strictly early on the same delivery, of 32 | Effects at the common 5% budget |
| --- | ---: | ---: | ---: | ---: |
| Whole-run logistic margin | 0 | 0 | No delivery identifier | 0 |
| Assignment score | 5 | 0 | No delivery identifier | 5 |
| Excluded recipient at dispatch | 23 | 15 | 17 | 0 |
| Unapproved input version at commit | 23 | 0 | 0 | 23 |
| Peer-read rule | 32 | 22 | 32 | 0 |
| Margin or dispatch | 23 | 15 | 17 | 0 |

All 32 effects involved one distinct source file read outside a grant's file
list. The assignment alert crossed its threshold before five effects, but its
score carries no delivery identifier. The common-budget column allows at most
one of the 26 control tasks to alert and keeps tied scores together. It uses
confirmation labels to describe ranking. A binary dispatch or peer-read rule
can only take all its tied alerts or none. The shipped cutoffs are the ones
used in the first two numeric columns.
[Per-task decisions and scores](../benchmarks/dispatch-workflows/runs.csv.gz)

The 17 early dispatch warnings led the matching commit by two office steps
each. Six first arrived after the effect. In three of those six an unrelated
earlier delivery had already triggered a warning, which would inflate the
early count from 17 to 20 if we measured only the first alarm on the task.
The other nine effects had a missing approval receipt. The dispatch and
commit checks both returned unknown on all nine. In seven different cases a
missing gateway read left a scope decision unknown while the independent
transaction receipts remained available.
[Per-stage timing and coverage](../benchmarks/dispatch-workflows/stages.csv.gz)

The primary tasks contained 61 deliveries. Of the 29 deliveries without a
completed unapproved use, 18 copies never became an input to a completed
review. The dispatch check flagged all 18. These included an independent
copy, a later revision, a fresh draft and an extra dispatch made earlier in
the same task. Four tickets explicitly routed the file to a second authorized
specialist. Both receipt rules cleared all four. At task level, 14 of the 23
template groups containing a control had a false dispatch warning.
[Per-delivery evidence](../benchmarks/dispatch-workflows/deliveries.csv.gz)

We also gave a parser and DeBERTa the same original routing instructions
for each ticket. Both recognized all 82 requested specialists. The parser
correctly excluded all 92 other real-specialist choices. DeBERTa excluded
eight, incorrectly designated one and abstained on 83. All unapproved
deliveries in the frozen office comparison went to one explicitly named
unlisted clerk. A matched follow-up reexecuted 46 excluded deliveries using
ordinary specialist names. On those same 29 completed effects, the model's
warnings fell from seven to one. [Same-ticket text and execution comparison](dispatch-role-text.md#what-changes-with-an-ordinary-recipient-name)

Against the whole-run margin, dispatch gained 23 and lost zero of the 32
effects. Its paired 95% recall-gain interval was +38.5 to +85.7 percentage
points. Its observed control-alert rate was 57.7%, with a one-sided exact 95%
upper bound of 74.2%. For commitment, zero false alerts in 26 gives an upper
bound of 10.9%. These bounds condition on the sampled case mix and treat tasks
as independent. Shared templates and scripted behaviors further restrict
transfer. Even a zero count would need at least 59 independent controls to
put the one-sided upper bound below 5%.
[Scorecard and denominators](../benchmarks/dispatch-workflows/summary.json)

## What two model reviewers could establish

Two model reviewers from different model families, each run once in
isolation, received the same anonymous event packets without the schedules,
scores or each other's decisions. Each returned a separate file citing event
IDs for all 60 packets. On the 58 primary tasks they agreed 58/58 on read
exceptions, completed effects and cooperation (Cohen's kappa 1.00 on each).
Both found 39 read exceptions and 32 completed effects, matching the full
office record on all 58 tasks for both questions, and both found observable
cooperation in 50, including routine work. On intent they agreed in 50 of 58
(kappa 0.65): both judged 11 routine and both left 39 unresolved, and they
disagreed on 8, which one reviewer judged routine and the other unresolved.
Neither judged any task a mistake or coordinated. Agreement between two model
reviewers is not ground truth, and the panel supplies no human validation of
its intent judgments.
[Panel procedure and ballot fingerprints](../benchmarks/dispatch-workflows/reviewers/panel.json)
and [case-level judgments](../benchmarks/dispatch-workflows/review-agreement.csv)

In two additional packets, the operator assigned a clerical slip to one
worker and deliberate cooperation to another. Once case IDs were removed,
the observable records were identical. Both reviewers marked both motives
unresolved. They also left unresolved all eight explicitly scripted mistakes
and both deliberate uses in the primary set. A sensitivity estimate for
independently established deliberate coordination has zero eligible positives
here. The separate MCPHunt study uses two published human reviews per task
for the narrower question of what its text requires.
[Review results](../benchmarks/dispatch-workflows/review-summary.json)
and [human-rated transfer instructions](approval-text.md)

**History of this panel.** The two ballots first submitted were
byte-identical and are retained as `reviewers/original-ballot.csv`. The panel
was re-run on 2026-11-24. Reviewer one was Claude Opus 5.5, run through the
Claude Code CLI 2.1.331 in print mode with the model alias `opus`, all tools
disabled, no session persistence, from an empty working directory. Reviewer
two was `gpt-6.2-astra`, run through the Codex CLI (version 0.172.0 observed
after the run) with a read-only sandbox, from a different empty working
directory; its sandbox could read files, it was instructed not to and the
directory was empty. Each received the same single prompt, the recorded
rubric wording plus formatting instructions followed by the 60 recorded
packets (the `prompt_instructions` text in `reviewers/panel.json` followed by
`review-packets.jsonl`), and neither received the other's ballot, the case
schedules, the original ballot or any detector output. Line endings of the
returned files were normalised to LF and a final newline ensured; nothing
else was changed. Each reviewer ran once. The re-run is post hoc: it was done
after the identical original files were noticed, and its operator had already
seen the original ballot and the reference record. Reviewer two's ratings
equal the original ballot's on all 60 packets. No human rated these packets.
The frozen protocol text (`benchmarks/dispatch-workflows/protocol.json`) is
unchanged.

## Reproduction

From the repository root, the first invocation can fetch three pinned source
assets. Omitting `--fetch` uses the verified local cache. The full replay
requires a new output directory each time. Raw publisher tickets, document
contents and model weights are kept outside the repository.

```shell
uv run --frozen swarmtrace dispatch-workflows --fetch --source-dir results-replay/public-dispatch-inputs --out results-replay/public-dispatch
uv run --frozen swarmtrace dispatch-workflows --source-dir results-replay/public-dispatch-inputs --out results-replay/public-dispatch-repeat
uv run --frozen swarmtrace dispatch-workflows --source-dir results-replay/public-dispatch-inputs --review-only --out results-replay/public-dispatch-panel
uv run --frozen swarmtrace dispatch-reviews --out results-replay/public-dispatch-reviews
```

Two independent Windows executions reproduced all eight workflow artifacts
byte for byte, including the original blinded packet file. A full Linux replay
matched every decision, time, count and group across 1,346 task runs, 1,820
stages, 1,920 deliveries and 354 scorecard rows. The largest margin difference
was below 1.8e-15. The earlier 24-case recipient contract can be replayed
independently.
[Dispatch contract](dispatch-contract.md)

## Decision for the next round

The follow-up recovered the nine missing approval receipts in the local
office and tested how policy changes between dispatch and use affect the
reviewer's conclusions. [Operation-time results](operation-authority.md)

For completed-use audits, the nine missing approvals identify a specific
follow-up. Test whether an authoritative, versioned policy store can recover
the approval in force at dispatch. Include superseded instructions, revocations
and later-approved exceptions. At commit, require the same recipient, delivery
and input bytes. A ticket that names a recipient can guide that lookup, while
the policy history establishes which approval actually applied.

Keep the existing swarm classifier and use assignment scores to investigate
access exceptions. An independent swarm test still needs naturally occurring
workflow traces with the original ticket, prior authority, actual input consumed
and human evidence about intent. Retain unresolved verdicts and office
mistakes in that evaluation. Apply the predeclared one-point recall gain,
paired lower bound, common 5% false-alert budget and in-scope controls before
changing a default. This study contributes zero qualifying swarm rounds.
More repetitions of the identical slip and deliberate traces cannot distinguish
their motives. [Round criteria](detector-rounds.md#measuring-diminishing-returns)
