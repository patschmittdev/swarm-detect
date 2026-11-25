# Can a ticket establish that a transfer needs the original values?

Keep the zero-shot reader out of the swarm detector. On 71 held-out MCPHunt tasks, both readers missed all six transfers that two independent human reviewers judged to require the original protected values. The deterministic parser recognized 23 cases where redaction was possible. DeBERTa recognized three, including one the parser missed. Neither reader supplied evidence of who approved a recipient or what a worker actually delivered. [Paired results](../benchmarks/approval-text/results/summary.json)

## What the humans reviewed

MCPHunt defines *completion requires secret* as an instruction that requires using the original protected values to complete a task. Its rubric considers the transfer language, whether the source contains protected values, and whether removing them would violate the request. Under that rubric, a task that permits a derived result or leaves transfer ambiguous can be completed without disclosing those values. [Publisher rubric](https://github.com/lihaonan0716/MCPHunt/blob/48e0f42f0820f15c9e88edb0ba461c615b908ecb/src/mcphunt/taxonomy.py#L152-L170)

The authors released a post-submission audit in which two people outside the author team reviewed every task independently, blind to trace outcomes and to each other's decisions. The audit description says the reviewers could see the task registry, description and prompt. The released response sheets contain the description and decision but omit the prompt column, so their exact presentation cannot be reconstructed. We reconstructed the complete original instructions from the separately pinned task definitions and joined the two human answers by task ID. The earlier author-assigned labels play no part in scoring. [Independent audit and both response sheets](https://huggingface.co/datasets/lihaonan0716/mcphunt-agent-traces/tree/8f05fed6face78aa48b10edcf3357c9aadfe71f5/crs_audit) · [Original instructions](https://github.com/lihaonan0716/MCPHunt/blob/48e0f42f0820f15c9e88edb0ba461c615b908ecb/src/mcphunt/prompts.py)

| Independent human decisions | All tasks | Calibration | Confirmation |
| --- | ---: | ---: | ---: |
| Both said original values were required | 13 | 7 | 6 |
| Both said redaction was possible | 125 | 63 | 62 |
| Disagreed | 9 | 6 | 3 |
| Agreement | 138/147 | 70/76 | 68/71 |
| Cohen's kappa | 0.710 | 0.659 | 0.776 |

The reviewers assessed transfer necessity. The release supplies no reviewer decisions for Swarmtrace cases, named-recipient authority, downstream acceptance of a particular file version, or deliberate multi-worker coordination. These results contribute zero qualifying swarm rounds.

Two related 2026 releases support different questions about recipients. AgentCIBench provides synthetic receiver-specific disclosure scenarios and predefined items that must or must not be shared. AgentCIScope synthesizes contextual disclosure contracts and reports a human check on 50 sampled tasks. Either could test whether a reader follows a recipient-specific disclosure policy. To measure swarm accuracy we would still need the source authorization decision, the actual downstream worker and version used, and independently assigned coordination labels on the same workflows. [AgentCIBench](https://arxiv.org/abs/2606.23189v2) · [AgentCIScope human validation](https://arxiv.org/html/2610.19158v1#A4)

## How the comparison was held out

The unit is one externally authored task. We kept whole publisher workflow families, linked base tasks and their paired variants, and exact or closely matching normalized instruction templates together. For near duplicates we required word-trigram Jaccard similarity of at least 0.75, then joined overlapping groups transitively. The 43 workflow families formed 42 groups. Thirteen examples already discussed in the published research and their entire groups went to calibration. A deterministic hash assigned the remaining groups. Calibration contained 76 tickets in 17 groups spanning 18 families. Confirmation contained 71 tickets from 25 other groups and families. This measures generalization across workflows within one publisher. [Frozen protocol and example IDs](../benchmarks/approval-text/protocol.json) · [Individual assignments](../benchmarks/approval-text/predictions.csv)

The rules, hypotheses, template split and threshold policy were fingerprinted before reading the individual reviewer assignments. The upstream aggregate agreement and published examples were already public. The readers both received the same complete task instructions with two runtime substitutions rendered as inert placeholders. Neither received task IDs, descriptions, mechanisms, reviewer decisions or execution records as features.

The parser uses explicit transfer or derivation phrases, checks immediate negation, and abstains when the phrases conflict or supply no answer. DeBERTa scores two fixed statements about the ticket. Its full-ticket preference must match the preference for a specific sentence. Its evidence score is the smaller of the full-ticket and sentence entailment probabilities. The stored offsets identify the parser's literal match or the model's strongest supporting sentence. Across all 147 tickets, all 188 nonempty spans and all 106 empty spans were verified against their source. The reviewers labeled answers only and did not grade these excerpts. [Source and inference implementation](../src/swarmtrace/reproduce/approval_text_source.py) · [Frozen scores and evidence offsets](../benchmarks/approval-text/predictions.csv)

## Confirmation at a 5% false-necessity budget

Both readers started with a strict evidence cutoff above 0.5. Calibration could raise the cutoff for claiming the original values were required until at most 5% of agreeing negative controls received a false necessity claim. Neither threshold needed to move. Both readers may return *unclear*. Unresolved positives stay in the recall denominator. Unresolved controls stay in the false-necessity denominator. The three human disagreements stay outside both denominators.

| Held-out result | Parser | Zero-shot DeBERTa |
| --- | ---: | ---: |
| Correctly identified required transfers | 0/6 | 0/6 |
| Incorrectly claimed a redactable transfer was required | 0/62 | 0/62 |
| Correctly identified redactable transfers | 23/62 | 3/62 |
| Incorrectly called a required transfer redactable | 0/6 | 0/6 |
| Resolved among agreeing human decisions | 23/68 (33.8%) | 3/68 (4.4%) |
| Abstained among agreeing human decisions | 45/68 | 65/68 |
| Abstained among human disagreements | 3/3 | 3/3 |

The two readers recognized two of the same redactable controls. The parser alone recognized 21, DeBERTa alone recognized one, and both abstained on the other 38. Retrospectively allowing any required-transfer cutoff consistent with the same observed 5% control budget still recovered zero positives for either method. That ranking diagnostic uses the confirmation labels and has no deployment cutoff. [Counts by family, split and threshold](../benchmarks/approval-text/results/operating-points.csv) · [Per-task decisions](../benchmarks/approval-text/results/decisions.csv)

Zero false necessity claims in 62 controls gives a one-sided 95% Clopper-Pearson upper bound of 4.72% if tickets are independent. All 25 held-out workflow groups included controls. Zero groups had a false claim, giving an upper bound of 11.29% for a group having any false claim under independent group sampling. The six positives came from four families. At the frozen thresholds the model gained zero positives and lost zero positives relative to the parser. With only six paired positives, an exact one-sided 95% bound on their discordance rate still allows 39.30% under independent ticket sampling. This benchmark cannot establish equivalence between the readers. [Uncertainty and paired counts](../benchmarks/approval-text/results/summary.json)

## Reproduction and attribution

The offline replay verifies the published protocol, prediction and reviewer hashes and writes the scorecard to a new directory. It runs with the standard project dependencies.

```sh
uv run --frozen swarmtrace approval-text --study benchmarks/approval-text --out results-replay/approval-text
```

For full inference, use Python 3.12 with PyTorch 2.6.0 CPU, Transformers 5.5.4, Tokenizers 0.22.2 and SentencePiece 0.2.1. Supply a local checkpoint directory at the revision in the protocol. The rebuild reads and verifies seven checkpoint files and four public source files. It decodes the original instructions as literals, replaces only the workspace and service placeholders, and scores 407 unique full-ticket or sentence inputs against two hypotheses. The 814 entailment scores are computed locally in FP32 on CPU. Two independent full runs with eight threads gave byte-identical predictions, reviewer tables and scorecards on the recorded runtime. [Inference manifest and file hashes](../benchmarks/approval-text/manifest.json) · [Pinned model card](https://huggingface.co/MoritzLaurer/deberta-v3-large-zeroshot-v2.0/tree/cf44676c28ba7312e5c5f8f8d2c22b3e0c9cdae2)

```sh
python -m swarmtrace.reproduce.approval_text_source rebuild --source results-replay/mcphunt-text --fetch --snapshot /path/to/pinned/model --out results-replay/approval-text-inputs
uv run --frozen swarmtrace approval-text --study results-replay/approval-text-inputs --out results-replay/approval-text-rebuilt
uv run --frozen python -m swarmtrace.reproduce.approval_text_source quote --source results-replay/mcphunt-text --task ca_data_inventory --method parser
```

The task IDs and paired reviewer responses are adapted from *MCPHunt*, by Haonan Li, Tianjun Sun, Yongqing Wang and Qisheng Zhang. The dataset uses CC BY 4.0. The public benchmark preserves both answers, converts their spelling to `yes` and `no`, and omits descriptions and original task text. Splits, scores, hashes, offsets and evaluation reports were added for this study. MCPHunt source code and the DeBERTa checkpoint use the MIT license. The offline replay reads only the published prediction and label tables, protocol and hashes. [MCPHunt paper](https://arxiv.org/abs/2604.27819v2) · [Pinned data release](https://huggingface.co/datasets/lihaonan0716/mcphunt-agent-traces/tree/8f05fed6face78aa48b10edcf3357c9aadfe71f5) · [CC BY 4.0 terms](https://creativecommons.org/licenses/by/4.0/) · [MCPHunt source license](https://github.com/lihaonan0716/MCPHunt/blob/48e0f42f0820f15c9e88edb0ba461c615b908ecb/LICENSE)
