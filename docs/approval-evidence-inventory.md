# Public evidence for operation-time approvals

As of November 23, 2026, the closest public records answer two different questions. One release records which version of a ticket changed after an approval decision. Another has two human reviewers judge whether a pair agreed to relax a verification rule. Across the inspected sources, **zero cases** join a changing approval, the exact delivered document consumed by a recorded worker, and independent human judgments of mistake versus deliberate cooperation on that same operation. General swarm accuracy and its false-alert rate remain unmeasured on these records. [Recomputed results](../benchmarks/operation-authority/external-evidence.json)

## Which cases can be resolved

| Source and unit | Evidence available | Scope of the result |
| --- | --- | --- |
| Commit-Time Authorization, 28 ticket-service cases | Each constructed request names the ticket, requested status, observed ticket version, approval handle and approval epoch. Sink records give state before and after, whether a write applied and the service's authorization witness. | All 28 requested versions match the precommit ticket version. Twenty-four cases contain at least one recorded sink attempt. The request origin is a deterministic constructor. There is no worker-to-document delivery or human motive judgment. [Study](https://arxiv.org/abs/2607.10487v2) and [original cases](https://anonymous.4open.science/api/repo/commit-time-authorization/file/studies/local-specificity-v1/evidence/revocation-after-issuance-v1.json) |
| SALT agent-collusion, 100 dialogue and 100 reflection samples | Each sample joins to two anonymous reviewer IDs and a final human answer by sample ID and signal. The paper identifies the two reviewers as its first two authors, working independently. | Dialogue ratings concern a reciprocal agreement to accept or relax verification. Reflection ratings concern a single agent's stated willingness to relax its standard. The source episode references point to grading interactions. Neither panel has a corresponding document-consumption or changing recipient-approval record. [Human rating procedure](https://arxiv.org/html/2609.24967v2#A3) and [pinned tables](https://huggingface.co/datasets/SALT-NLP/agent-collusion/tree/2eba8f3771e8fbcc0f49f6cbbfd2111b939a117a/data) |
| CLIO, two upstream unit files | Real authorization and grant-store functions exercise one-use spending, path scope, denial, revocation, expiry and save/restore. Approvals in the path tests come from a callback. | Twenty-five path assertions and five grant-store subtests passed. These are implementation checks. Their denominator supplies neither observed user decisions nor independent workflow incidents. [Path tests](https://github.com/SyntheticAutonomicMind/CLIO/blob/4babd7be9dc15acc894d4089ff4eb840ad3e10cf/tests/unit/test_path_authorization_grants.pl#L58-L85) and [store tests](https://github.com/SyntheticAutonomicMind/CLIO/blob/4babd7be9dc15acc894d4089ff4eb840ad3e10cf/tests/unit/test_grant_store.pl#L44-L168) |

### Ticket effects

The replay checked every published row outcome against the recorded state change and the service's authorization verdict. Every applied write advanced the ticket version by one. Across 28 cases, 23 writes applied and five cases ended with the version unchanged. There were 25 recorded attempts because four cases stopped before a sink attempt and one case attempted consumption twice.

| Publisher group | Authorized write | Unauthorized write | Safe non-completion |
| --- | ---: | ---: | ---: |
| Main post-issuance revocation, five controls facing the same case | 1 | 4 | 0 |
| Expiry and repeat-consumption probes | 2 | 0 | 1 |
| Original service controls | 10 | 6 | 4 |

The source grant and the derived reservation have different lifetimes. Four recorded attempts applied a still-valid reservation after its source grant lost authority. In this release the independently authorized, unspent lease can survive until its stated expiry. One attempted consumption failed its expiry check. Another failed its unspent check on replay and also encountered a changed ticket version. An adapter needs the issuer's reservation semantics to interpret those outcomes. The five main controls repeatedly exercise one constructed transition, so they contribute one scenario and five enforcement observations. [Publisher specification](https://anonymous.4open.science/api/repo/commit-time-authorization/file/studies/local-specificity-v1/SPEC.md)

### Human coordination judgments

On the 100 dialogue samples, the reviewers agreed on all 100. They found 34 positive reciprocal agreements and 66 negatives. On a separate 100 reflections they agreed on 92 and disagreed on eight. The final reflection answers contain 50 positives. The publisher's automated judge matched the final human answers on 100 dialogue and 95 reflection samples. The agreement and judge-accuracy rates are the paper's, and the replay reproduces them; the positive and negative breakdowns and the reviewer and run/episode counts are derived here from the released dataset tables. They use identical sample-and-signal keys, with exactly two distinct reviewers per item. Each group contains 100 distinct run/episode pairs. The counts describe these selected items. A negative dialogue rating means the transcript lacked the specified agreement. It supplies no label of clerical error for a downstream operation. [Signal definitions](https://huggingface.co/datasets/SALT-NLP/agent-collusion/blob/2eba8f3771e8fbcc0f49f6cbbfd2111b939a117a/SCHEMA.md) and [paper](https://arxiv.org/abs/2609.24967v2)

## Other primary evidence

- The November 17 decision-receipts Internet-Draft provides an immutable test package with expected results for approval consumption and decision-to-outcome binding. These constructed vectors test verifier behavior. The draft distinguishes evidence of duplicate use within a receipt set from atomic enforcement by a live executor. [Verification rules and test package](https://www.ietf.org/archive/id/draft-gruszka-audit-decision-receipts-10.html#section-3.5)
- Deng and colleagues report paired approval decisions with native business-state witnesses. Four of 59 comparable n8n workflows executed the protected effect after rejection. The linked arXiv source package contains the paper and figures. It describes an offline toolkit but does not include the underlying run files. This inventory counts those findings as publisher-reported. [Paper, workflow section](https://arxiv.org/html/2611.19237v1#S5)
- TAMAS used two human reviewers and a third adjudicator on 120 representative logs. They scored how far a specified objective progressed. A multi-agent scenario label describes the assigned task or intervention. It does not show that a particular member of an office workflow knowingly committed an unapproved input. [Human verification rubric, appendix C.1](https://aclanthology.org/2026.acl-long.1442.pdf#page=16)
- MCPHunt's two human reviewers assessed whether a task required transferring a protected value. SwarmTrace's prior replay preserves that endpoint and its disagreements. [Transfer-requirement benchmark](approval-text.md)

## Reproducing the checks

Run from the repository root. The optional Parquet reader is used only for this source replay. The command verifies the original four file digests before scoring and writes only aggregate counts. Omit `--fetch` to use the same flat source cache offline.

```shell
uv run --frozen --with pyarrow==21.0.0 python -m swarmtrace.reproduce.authority_external --source-dir results-replay/public-authority-inventory --out results-replay/authority-evidence --fetch
```

For CLIO, use revision `4babd7be9dc15acc894d4089ff4eb840ad3e10cf`. From that checkout, run `prove tests/unit/test_path_authorization_grants.pl tests/unit/test_grant_store.pl`. We ran the original Git file bytes under Perl 5.40.5 on Linux with the network disabled and temporary storage for the test session. The runner reported two files, 30 top-level tests and zero failures. [Grant persistence rules](https://github.com/SyntheticAutonomicMind/CLIO/blob/4babd7be9dc15acc894d4089ff4eb840ad3e10cf/lib/CLIO/Security/GrantStore.pm#L303-L328)
