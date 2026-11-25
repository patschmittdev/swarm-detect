# Evidence for improving swarm detection

Research cutoff **November 23, 2026**. The question is whether a monitor can
distinguish deliberate coordination from ordinary collaboration and genuine
mistakes at a small false-alert budget. This review examined original papers
and release schemas on multi-agent collusion, authorization, data provenance
and detector transfer. Reported figures below belong to the named studies.
The local test of a proposed change has its own fixed protocol and paired
scores. [Swarmtrace grant-count experiment](grant-scope-round.md)

## Which additional evidence is worth collecting

**1. Record the authority actually used at the decision.** An actor can work
under two assignments on the same host. A login timestamp places both in the
same session, even if each file belongs to just one assignment. A study of
object-centric logs from Angular development found missing object links and
explained why inferring them from co-occurrence could introduce errors. Laws et al.
made the delegation path independently verifiable in a four-worker system.
Their November 18 preprint evaluated attribution on 20 tasks with five trials
per task. Some integrity checks narrowed responsibility to two agents. Its
reported attribution rate addresses a different question from false swarm
alerts on routine teamwork. Swarmtrace can test the more modest change of
joining a read to a selected, validated grant without introducing a graph
model. [Object-centric event-log study, June 2026](https://link.springer.com/article/10.1007/s44311-026-00043-x) and [Laws et al., auditor evaluation](https://arxiv.org/html/2611.25056v1)

**2. Obtain the original approval for the action and recipient.** Copty
et al. supplied a monitor with a trusted description of an agent's mission
and constraints. On more than 10,000 executed AgentDojo trajectories,
post-execution AUROC was 0.843 without context, 0.897 with raw configuration
and 0.949 with a structured intent profile. This supports testing a new
information source. The paper's separate improvement in out-of-scope F1
came from a synthetic input-classification task. For Swarmtrace, record an
approved recipient or exception before execution, parse its structured fields
first, and measure how often a human can independently resolve the case.
A zero-shot text model has a concrete comparison if the approval is expressed
only in prose. Give both methods the same ticket, an explicit unknown answer
and a required reference to the supporting passage.
[Intent-aware security study, November 12](https://arxiv.org/html/2611.16122v1)

**3. Verify the downstream action.** A read, a message that proposes an
action and a confirmed effect answer different questions. The November 17
revision of Colosseum found that agents can discuss collusion and then choose
cooperative actions. In the accepted SCHEME study, trusted monitors with
access to both code and communications caught at least 93% of successful
sabotage from each of ten tested models; the
[arXiv v1 preprint](https://arxiv.org/abs/2605.29178v1) reports two models.
That endpoint is conditional on a successful outcome and uses evidence that
may arrive after the damage. For an offline detector, first test whether a
separately identified recipient performed an observable operation with the
same object or version. Include an authorized transfer, a read with no
subsequent use, and an unrelated recipient acting on a different version as
matched controls. For an early detector, report the first alert strictly
before the effect and the proportion of control runs ever alerted.
[Colosseum](https://arxiv.org/abs/2602.15198v3), [SCHEME, accepted NeurIPS record](https://openreview.net/forum?id=4f5ZeIKhaC) and [NeurIPS poster page](https://neurips.cc/virtual/2026/poster/155561)

**4. Keep benign violations in the control population.** MasDrift's 600
benign productivity tasks crossed authorization boundaries in 2.7% to 19.8%
of generic hierarchical tasks and 0.6% to 0.8% of generic peer tasks.
In MCPHunt's risky-environment tasks where redaction was allowed, five
instruction-following models propagated protected data in 11.5% to 41.3%
of runs. Even the same observed transfer could be required on another task.
A confirmed policy exception therefore belongs
in access review even when evidence of deliberate group behavior is weak.
Include mistaken reads, legitimate sharing, approved exceptions and incomplete
records in both calibration and confirmation. Split by base task for any
dataset containing matched variants. [MasDrift](https://arxiv.org/abs/2608.07556v3) and [MCPHunt](https://arxiv.org/abs/2604.27819v2)

## Models and evaluation choices

- **Keep unrelated work out of an assignment's score.** In our primary
  paired study, merely adding an independent office job reduced logistic's
  one-file detections from 437 to 183 at a common false-alert ceiling. Try
  computing evidence per observable assignment and alerting on the largest
  assignment score. Use only recorded grants, actors and object links to
  identify assignments. Simulator role labels and office-specific identifiers
  would disclose the experimental construction. Calibrate the maximum on
  whole control runs so that a team with ten tickets gets the same run-level
  false-alert target as a team with one. Test unrelated jobs, legitimate
  cross-ticket sharing, incomplete linkage and tickets that genuinely overlap
  inside the focal team. The previous graph count measured shared-login
  groups and tied on single-group cases. [Paired grant study](grant-scope-round.md#first-confirmation-results) and [previous graph-count benchmark](detector-accuracy.md#what-the-candidates-measure)
- **For audit logs alone, account for shared schedules and popular files.**
  On 26 labelled social-media datasets, Iannucci et al. found that the
  expected activity of the accounts and items changed which groups could be
  recovered. Dense clusters appeared even where recovery was poor. A
  Swarmtrace timing benchmark could preserve each job's fan-out, file
  popularity and worker activity rate when measuring unusual co-access.
  Report it against ordinary teams on scheduled jobs, with the existing
  sharing-pair count as the baseline. On the 108 pairs with identical events,
  any such statistic must tie. New results would apply to workflows with
  observable timing differences. [Statistical Detectability of Coordination, October 27](https://arxiv.org/html/2610.37970v1) and [local identical-policy control](../data/scope-identical.md)
- **A graph is useful when an edge has a verified meaning.** CASPIAN reports
  86.8% true-positive rate at a 5% false-positive rate on AutoGen and 84.2%
  on LLM Debate. Its fixed-FPR comparison uses a retrospective ROC over
  full-trace scores. Its early-detection measure is a separate experiment.
  Those labels concern cascades. Compare a verified path from a grant through
  an object to its recipient with counts of the same events. Make the
  comparison at a pre-calibrated run-level threshold. [CASPIAN, including Appendix E](https://arxiv.org/html/2605.19240v1)
- **Hidden-state probes require different observations and better negatives.**
  HELIOS found strong transfer on instructed collusion in open-weight models.
  In a November follow-up that included agents given the same instruction
  who subsequently refused, a probe's AUROC dropped from 1.00 to 0.61 when
  the instruction was removed. A vote-only rule reached 0.990 after the vote
  and found nothing beforehand. Swarmtrace has tool observations from scripted
  agents. Validate any future activation or language monitor against refusals
  and matched benign instructions, with final decisions hidden at prediction
  time. [HELIOS](https://arxiv.org/abs/2604.01151v5) and [What Do Collusion Probes Read?, November 7](https://arxiv.org/html/2611.10620v1)
- **Decide which everyday failures count as negatives.** Skynet trained a
  workflow graph model on benign executions and reported 0.89% false alerts
  on its held-out benign split. Its target includes intrinsic failures such
  as plan errors. An accidental appendix read is a negative for deliberate
  swarm activity in our study. A graph model would therefore need a fresh
  comparison on the same clerical mistakes that the frozen assignment score
  flagged. Published anomaly recall cannot supply that comparison.
  [Skynet, evaluation and target labels](https://arxiv.org/html/2609.06835v1)
  and [local mistake-control replay](assignment-round.md#what-happens-when-the-clerk-makes-a-mistake)
- **Measure false reviews and cross-workflow transfer.** Abbasi et al. found
  that a detector with AUROC 0.879 produced only 7.6% precision at 2%
  prevalence. Varying the benign mix moved that precision between 3.9% and
  11.7%. Models trained on AgentDrift scored 0.47 to 0.52 AUROC on AgentDojo.
  A re-evaluation of provenance detectors found a training-only
  allowlist matched or exceeded selected learned baselines on operating-point
  metrics across four primary datasets. Use a simple baseline, count false
  reviews per 1,000 runs at explicit prevalence assumptions, and reserve new
  workflow families for promotion. [Tool-trace transfer study, October 30](https://arxiv.org/html/2610.41803v1) and [provenance benchmark re-evaluation](https://arxiv.org/abs/2608.01454v4)

## Can an external release validate this detector today?

The two frozen models require actor, host, credential owner, login and
post-receipt access features as well as handoff scopes. The candidate also
requires the grant actually selected for each read. The following publisher
inventories establish what could be tested with their released data.

| Release inspected | Available evidence | Appropriate external test |
| --- | --- | --- |
| WeClawArena, Findings of EMNLP 2026 | 124 base tasks across six domains, each with one benign and four modified scenarios. The public snapshot contains scenarios, manifests and evaluation contracts. It excludes the paper's runtime records. | Collect new execution logs from benign cross-user tasks with permission to instrument the gateway. Hold out whole base tasks. [Paper](https://aclanthology.org/2026.findings-emnlp.1424/) and [release card](https://huggingface.co/datasets/kingofspace0wzz/WeClawArena/blob/cb103b49200821c47ba3f6440940e50a1b683396/README.md) |
| MCPHunt | 3,615 main traces across 147 tasks and five models. One acting agent uses multiple servers. Labels describe propagation and required or prohibited use. | Validate the narrower downstream-flow measure. A server is a resource boundary and supplies no second-agent intent label. [Release card](https://huggingface.co/datasets/lihaonan0716/mcphunt-agent-traces/blob/8f05fed6face78aa48b10edcf3357c9aadfe71f5/README.md) |
| SALT agent collusion | Episode IDs, rounds, senders, recipients, mutual acceptance and conditional collusion labels in paired-agent work. Its schema has no host login, credential owner or selected file grant. | Evaluate a separate peer-review detector on observable prefixes. Preserve real round ordering and the published conditions for valid labels. [Official schema](https://huggingface.co/datasets/SALT-NLP/agent-collusion/blob/2eba8f3771e8fbcc0f49f6cbbfd2111b939a117a/SCHEMA.md) |
| SCHEME | Accepted paper and authors' study materials document code changes, communication and outcomes. We could not verify a public credential-and-grant trace schema. | Use its distinction between attempted, completed and detected actions to design labels. [Accepted paper](https://openreview.net/forum?id=4f5ZeIKhaC) and [authors' project summary](https://pbernabeup.github.io/projects/multi-agent/) |

None of these four inventories supports a faithful external replay of the two
frozen classifiers. For external validation, collect a read-only audit export
from a separately instrumented workflow and freeze task-level splits before
fitting. Ask reviewers to label the file-scope exception and the evidence for
coordinated use separately. Record disagreement and permit an unresolved
intent label. A synthetic or reconstructed grant ID would change the input
being validated.

The released MCPHunt labels make one narrower check possible now. We joined
two independent reviewers' answers by task ID on whether completion required
transferring the original protected value. They agreed on 138 of 147 tasks
(93.9%, Cohen's kappa 0.710). Both answered yes for 13 tasks and no for 125.
They disagreed on nine even though they used the same written rubric and
were blind to the outcome. This gives a reason to measure reviewer agreement
before using ticket text as ground truth in Swarmtrace. [Audit protocol and raw labels](https://huggingface.co/datasets/lihaonan0716/mcphunt-agent-traces/tree/8f05fed6face78aa48b10edcf3357c9aadfe71f5/crs_audit)

## Comparisons selected from the research

The assignment study tested the proposed grouping. The recipient study used
a separate document office because the archived traces lacked recipient
approvals and committed input versions. Its results establish what those
receipts can verify on the labelled office cases. The improvement over the
existing swarm detector on independently collected workflows remains open.
[Assignment study](assignment-round.md) and [recipient-use study](recipient-approval.md)

EntCollabBench released specialist routing instructions and approval documents
for 100 tasks. They provided independent task inputs for the local dispatch
experiment. The publisher's named roles fixed the request and our office
recorded pre-dispatch permission, selected file grants and exact downstream
inputs. The same-record comparison exposed both the cost of warning on unused
copies and the ambiguity of clerical slips. The external human transfer ratings
from MCPHunt supplied a separate test of what ticket text establishes.
[EntCollabBench paper](https://arxiv.org/abs/2605.08761),
[public dispatch results](public-dispatch.md) and [human-rated text results](approval-text.md)

1. **Assignment-level scoring.** Freeze the assignment-linking rule on
   development data. Compare the default whole-run logistic model with a
   maximum over assignment scores, and report a whole-run verified-grant
   score to isolate the effect of grouping. Keep run-level labels at the
   run level. A positive run can contain several legitimate tickets. Reserve
   two new focal workflow families, with shared reviewers and objects in at
   least one, and include controls with varying numbers of concurrent tickets.
   Target 540 one-file cases and 2,160 controls across the new families.
   Calibrate on disjoint complete runs and report family-specific results as
   well as pooled paired recall, false alerts and the in-scope relay count.
2. **Recipient approval and confirmed use.** On separately labelled runs,
   compare the incumbent with one additional verified fact about whether the
   recipient's use of the object version matched the prior approval. Include
   missing authorizations, authorized exceptions and a worker acting alone.
   Report how often the evidence resolves the case, how many false reviews
   it adds, and the first alert before the downstream action. A model using
   ticket text gets a separate comparison with a plain parser on identical
   inputs. Hold out ticket templates and entire base tasks together.

For both comparisons, use the established one-point gain for one-file recall,
positive paired lower bound, better ranking at the common 5% budget and no
increase in in-scope relay alarms. For a local deployment candidate, also
require the one-sided 95% upper false-alert bound to meet that budget. Two
consecutive independent comparisons whose upper recall gain and matched-budget
gain both fall below one point on the same evidence would shift effort to
better observations or scoring cost. A budget failure or uncertain estimate
leaves that stopping criterion unmet. [Benchmark decisions](detector-rounds.md#measuring-diminishing-returns)
