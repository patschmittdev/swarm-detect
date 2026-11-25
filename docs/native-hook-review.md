# Attributing a tool call to a worker

Two workers can be active when a tool call arrives. In nine scenarios recorded
by the nodeterm maintainers, the most recently started Claude worker made only
five of the ten calls observed during overlap. The native hook records identify
the worker for all ten. Swarmtrace now uses those identifiers in its offline
review command. [Claude capture provenance](https://github.com/eneskirca/nodeterm/blob/d6641fe94841110a2184dd5bb1a1b360666b342d/src/shared/agents/normalize.claude.subagent-capture.test.ts#L1-L25)

## What the captures establish

| Question | Records compared | Result |
| --- | --- | --- |
| Which Claude worker issued the request? | 21 requests with an explicit child ID, each with a result | Matching the session, call, tool name and worker joined 21 of 21. The most recently started open worker agreed on 16 of 21. |
| When did the latest-start rule fail? | 11 tagged requests with one open worker and 10 with multiple open workers | It agreed on 11 of 11 with one worker and 5 of 10 during overlap. Assigning only when one worker was open left 10 of 21 unanswered. |
| What about Claude calls without a worker ID? | 14 untagged requests | 12 matched a result by call identity. Two had no recorded result. The caller remains unknown for all 14. |
| Which Grok workers finished? | Two parallel workers, each with a start and a stop | Matching the child IDs recovered both lifecycles. Matching the session IDs on the start and stop recovered zero. |

Claude Code 2.1.284 supplied 169 events across nine scenarios and eight
distinct prompting sessions. We scored each scenario in its own recorded
order. Sixteen child starts had 14 matching stops. Two starts remained open,
and 13 stops lacked a preceding start in their scenario. A successful tool
result is evidence that the provider marked that call successful. The captures
supply no independent labels for document use, authorization or motive.
[Benchmark results by scenario](../benchmarks/native-hooks/summary.json)

Grok 1.0.13 supplied 15 selected events from September 1 and four child
lifecycle events from September 2. The latter name the parent session at
start and the child session at stop. Claude carries the same session ID on
both records. The review keeps the Grok selections separate and counts
ambiguous child IDs, missing starts and incomplete runs explicitly.
[Grok capture and field conventions](https://github.com/eneskirca/nodeterm/blob/d6641fe94841110a2184dd5bb1a1b360666b342d/src/shared/agents/normalize.grok.capture.test.ts#L97-L117)

## Review a local capture

Supply one chronologically ordered UTF-8 JSONL file from one provider.
Place one native hook object on each nonempty line. Run the command
separately for independent captures, even if they reuse session IDs.

```text
uv run --frozen swarmtrace review-hook-events --provider claude --events claude.jsonl
uv run --frozen swarmtrace review-hook-events --provider grok --events grok.jsonl --show-links
```

The default output contains the provider name and counts. With
`--show-links`, Claude reports the one-based positions of each matched child
request and result, plus the observed child start and the latest open start at
request time. An unavailable start is `null`. Grok reports the start and
stop positions of each matched child. Positions count nonempty records. The
output omits prompts, tool arguments, results, paths and identity strings.
The matches reflect IDs supplied by the producer. They do not authenticate
the actor or establish what a recipient later did.

## Reproduce the public benchmark

```text
uv run --frozen swarmtrace native-hook-benchmark --fetch --out results-replay/native-hooks-first
uv run --frozen swarmtrace native-hook-benchmark --out results-replay/native-hooks-offline
```

The first command downloads two missing files at a pinned nodeterm revision
and verifies their size and SHA-256. The second reuses the verified local
bytes. Both write `protocol.json` and `summary.json`. To use an existing
copy, supply `--source-dir` with the directory containing the two original
files. Swarmtrace distributes the protocol and derived counts. Nodeterm
publishes the original captures. [Source URLs, checksums and capture boundaries](../benchmarks/native-hooks/protocol.json)

This benchmark contributes zero independently labeled swarm-accuracy rounds.
The next useful case would link the same worker and call to the approval in
force and the document version a recipient actually consumed. The existing
recall and false-alert criteria apply when such cases have independent
coordination labels. [Round criteria](detector-rounds.md#measuring-diminishing-returns)
and [review of all nine repositories](external-repository-review.md)
