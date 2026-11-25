# Scope identical-policy gate

Seed: 20261120; dataset: identical.

Gate: byte comparison of trace.jsonl and context.json in every role-flipped pair.

108 of 108 identical.

AUROC is exactly 0.5 at every context level (aggregation-only reference, C0, C1, C2): each score has an identical opposite-label twin.
This is a consequence of byte identity, not an estimated AUROC interval.
