# Swarmtrace: design and architecture

This document fixes the architecture and the contracts between parts. It is
the specification the code was built against. The README reports what was
measured.

## 1. Decisions

| Decision | Choice | Reason |
| --- | --- | --- |
| Language and tooling | Python 3.12, `uv`, src layout, pytest, ruff | Common, pinned tooling |
| Runtime dependencies | numpy, pandas, scikit-learn only | Installs and reproduces with one command |
| Simulation style | Discrete-event, logical clock, in-memory world | Deterministic and has no network surface |
| Agent order | Scripted policies first, LLM agents behind an optional extra later | The first results need no API key |
| Contract between halves | Versioned trace schema plus a separate labels file | Lets generation and analysis be built and tested independently |

## 2. Scope

The question is whether a defender who can read only the tool-call log of a
shared environment can tell an offensive group of agents from ordinary
teamwork, at three levels of logging detail.

In scope for the first milestone: a deterministic simulator with scripted
agents, a versioned trace contract, features, baseline detectors, attribution,
online detection, and one command that regenerates every table.

Built since this was first written: one evasion, a scope-based offence and a
containment study (see `docs/design-phase3.md` and the README). Still not
built, and described here only as planned work: other evasive agents,
LLM-driven agents, and the attested-identity tier in section 8. The README states what was measured and its limits.

## 3. Threat model

- **Defender** owns the environment and reads its log. It cannot read agent
  prompts, model activations, or agent memory.
- **Adversary** controls the policies of a subset of agents. It knows the
  detector's feature family and may shape behaviour to evade it. It cannot
  alter or suppress log records.
- **Benign population** shares the same hosts and tools, and some benign agents
  legitimately work in teams. Coordination alone is therefore not the signal;
  the detector must separate offensive coordination from ordinary teamwork.

The last point is the main design risk. Without benign teams in the population
the task collapses into "find the agents that talk to each other".

## 4. Architecture

```
            config + seed
                 |
        +--------v---------+
        |   sim.engine     |   discrete-event loop, logical clock
        |  world  agents   |
        +--------+---------+
                 | tool calls (the only way agents touch the world)
        +--------v---------+        +-------------------+
        | sim.recorder     |------->| trace.jsonl       |  defender-visible
        +------------------+        +-------------------+
                 |                  +-------------------+
                 +----------------->| labels.json       |  ground truth, held apart
                                    +-------------------+
   ---------------------- contract boundary ----------------------
        trace.jsonl --> features --> detect --> eval --> report
```

### Packages

| Package | Responsibility |
| --- | --- |
| `swarmtrace.trace` | Event and label types, JSON Schema, reader and writer, schema version |
| `swarmtrace.world` | Hosts, services, files, credentials, permission zones; seeded generator; tool API |
| `swarmtrace.agents` | Agent protocol; benign solo and benign team policies; coordinated offensive policies; channels |
| `swarmtrace.objectives` | Multi-step objectives that need more than one agent's permissions; completion referee |
| `swarmtrace.sim` | Engine, single-run runner, condition sweep |
| `swarmtrace.features` | Per-agent, pairwise and run-level features, each computable on a time prefix |
| `swarmtrace.detect` | Baselines, attribution from pair scores, online detection |
| `swarmtrace.eval` | Splits, metrics with intervals, results tables |
| `swarmtrace.contain` | Defender-side controllers that act on a detector's flag. Imports only `trace`, `features` and `detect` |
| `swarmtrace.reproduce` | End-to-end pipeline, controls, the follow-up experiments, recorded datasets, `verify` |
| `swarmtrace.cli` | `synthetic`, `sweep`, `features`, `eval`, `reproduce`, `sharing-sweep`, `evasion`, `scope`, `containment`, `verify` |

### The contract: trace and labels

A run is a directory with three files.

- `trace.jsonl`, one event per line: `schema_version`, `run_id`, `seq`,
  `tick`, `agent`, `tool`, `target`, `args`, `result`, `provenance`.
- `labels.json`: for each agent, its role (benign solo, benign team, offensive)
  and group id; the objective outcome and the tick it completed.
- `manifest.json`: the condition (channel, topology, sizes), seed, and
  code version.

Only `trace.jsonl` is defender-visible. `labels.json` and `manifest.json` are
both label-side: the manifest states group size, so feature and
detector code never opens it. `run_id` is an opaque random token.

Runs made with task scope enabled (see `docs/design-phase3.md`) carry up to
three more files. Runs without it keep exactly the three above.

- `context.json`, defender-visible: which agent each credential belongs to,
  and the file scope of each hand-off. It is organisational context, not
  ground truth, and is generated by a process that never looks at roles. A
  context level (C0, C1, C2) is a projection applied when it is loaded, like
  a tier.
- `interventions.jsonl`, defender-visible: the interventions a containment
  controller applied, one per line. Written only when a controller is
  attached.
- `outcomes.json`, label-side: per-task completion and out-of-scope reads.
  Read only inside `eval`.

Rules the schema enforces:

- Agent ids are random per run and carry no role information. Spawn order is
  shuffled.
- The total number of agents in a run is drawn independently of whether an
  offensive group is present, so agent count carries no label.
- Every tool call is logged, including calls that fail or are denied. `result`
  carries a status (`ok`, `denied`, `not_found`, `error`) and a size, never
  free text from the agent.
- `provenance` is the `seq` of the most recent event in which this agent
  received content written by another agent (a `recv` or a `read` of a file
  another agent wrote), or null. It is instrumentation a real defender may not
  have, so every feature declares the visibility tier it needs.

Serialization is fixed so that "byte-identical" holds across Windows and CI:
UTF-8, LF newlines, keys sorted, no insignificant whitespace, integer ticks,
no floats in the trace.

Tool vocabulary (closed list, pinned by a test):

| Tool | `target` | `args` | Notes |
| --- | --- | --- | --- |
| `scan` | host id | none | Lists services on a host |
| `login` | host id | credential id | Grants a session on success |
| `list` | host id | path prefix | Lists file ids |
| `read` | file id | none | Size in `result` |
| `write` | file id | size, content digest | Creates or overwrites |
| `send` | recipient agent id | size, content digest | Recipient visible from V0 |
| `recv` | sender agent id | size, content digest | Logged when the message is consumed |

The `content` field holds the text for `send`, `recv`, `write` and `read`. In
a full record it is a string (possibly empty) on every such call that returns
`ok`, and null on every other event. It is visible only at V2.

A receipt, for `provenance`, is an `ok` `recv` from another agent or an `ok`
`read` of a file whose most recent `ok` `write` was by another agent. Whether
`content` is present plays no part in that definition.

Validation is tier-aware: `validate_trace(events, tier)` enforces the shape of
that tier, so a projected trace validates at its own tier and fails at a higher
one. Files on disk are always full V2 records.

| Tier | Defender sees | Realistic analogue |
| --- | --- | --- |
| V0 | agent, tick, tool, target, result status | Access logs |
| V1 | V0 plus `args` and result size | Audit logs |
| V2 | V1 plus `content` and `provenance` | Full instrumentation |

The recorder always writes the full V2 record. A tier is a projection applied
when a trace is loaded for analysis, so one dataset serves all three.

Results are reported per tier. A detector that only works at V2 is a weaker
finding than one that works at V0, and the tables should show that.

### Invariants, each with a test

1. **Single writer.** Only the recorder appends to the trace; agents hold no
   reference to it.
2. **Label isolation.** Feature code accepts a trace type that has no labels.
   Labels join only inside `eval`.
3. **Determinism.** The same config and seed give a byte-identical trace.
4. **No network.** A full run passes with socket creation patched to raise.
5. **Honest splits.** Train and test are split by run, never by agent pair.
   Held-out conditions hold out the focal group's channel or topology; other
   teams in training runs draw their own and may still use the held-out value.
6. **Positive and negative controls.** An all-benign sweep measures the false
   positive rate; a deliberately loud offensive group must be caught, or the
   pipeline is broken.
7. **Context is role-invariant.** `context.json` is byte-identical for two
   runs on one seed that differ only in the roles of their teams.
8. **Identical policies give identical logs.** A control whose teams all share
   credentials and an in-scope relay of the same shape on the same seed
   produce byte-identical `trace.jsonl` and `context.json`. Only the labels
   differ. Any detector that separates them has a leak.

## 5. Experimental grid

| Factor | Levels |
| --- | --- |
| Offensive group size | 0 (control), 2, 3, 5 |
| Total agents | drawn from 12 to 28 regardless of group size; benign agents fill the remainder |
| Coordinated groups | 1, 2 or 3 per run, drawn independently of the label; a positive run has one offensive group and the rest benign teams, a control has only benign teams; sizes 2, 3 or 5 |
| Benign credential sharing | 10 percent of benign teams by default (section 9) |
| Channel | explicit messages, shared files only, pre-agreed plan |
| Topology | hub-and-spoke, peer-to-peer |
| Agent implementation | scripted |

Outputs per detector and tier: detection AUROC and false-positive rate,
per-agent attribution precision and recall, time to detection as a fraction of
the objective, each with bootstrap intervals over runs. Held-out results are
reported beside in-distribution ones, never merged.

## 6. How the two halves are kept apart

Trace generation (world, agents, simulator) and trace analysis (features,
detectors, evaluation) were built separately against the contract in section
4. Neither half imports the other.

The analysis half never imports the simulator. It is tested against two things
that ship with the trace package: a handful of hand-written fixture traces for
exact feature values, and a small planted-signal generator
(`swarmtrace.trace.synthetic`) that emits hundreds of schema-valid runs with a
known, tunable statistical signal and no world model behind them. Detector
fitting, splits and metrics are tested on that. The `reproduce` command is the
first point where the two halves meet.

## 7. Risks

| Risk | Mitigation |
| --- | --- |
| Scripted offensive agents are trivially separable, so every detector scores 1.0 | Benign teams, shared-file channel, and the pre-agreed-plan condition; report the trivial volume baseline beside real features |
| The detector learns the simulator's quirks, not coordination | Held-out channel and topology; LLM-driven agents are planned work |
| Result is null (nothing beats the volume baseline when held out) | A null result is reported as found |

## 8. Planned work: attested identity

Not built. A separate goal that extends the baseline; the baseline must stand
without it.

### Question

What does requiring attestation at the tool gateway buy a defender against a
coordinated group?

Sections 3 to 5 assume the log is truthful about which agent made each call and
that agent identities are free. Attribution in practice fails on exactly that:
an adversary can mint new identities, and the tooling says little about who
operates them. A gateway that accepts calls only from attested workloads binds
each call to a measured agent definition, which is what TRACE receipts, Agent
Manifest and cMCP provide.

### Additions

- **Tier V3.** Each event carries an `attested` field: a workload identity
  (a digest standing for the measured agent definition) and an operator key
  id. Simulated values only; no hardware and no real attestation library in the
  core package. V3 is a projection like the other tiers, so earlier results are
  unaffected.
- **Identity cost.** A condition in which the adversary may rotate agent
  identities mid-run. Without the gateway, rotation is free. With it, each new
  identity must present a distinct measured definition or reuse one, and reuse
  is visible in V3.
- **Features.** Shared workload identity and shared operator key across agents,
  available only at V3.
- **Containment lever.** Revoking an attested lease, modelled on WCM's
  wipe-on-lapse: the revoked workload's calls are denied from the next tick and
  it cannot return under the same measured definition. Compared against
  quarantining an agent id and cutting the channel.

### Measurements

- Attribution precision and recall at V3 against V0 to V2, with and without
  identity rotation.
- Objective completion and benign collateral for each containment lever, with
  and without rotation. The expected finding is that agent-id quarantine fails
  under rotation and lease revocation does not; report whichever is observed.

### Limits to state in the write-up

- An adversary's own swarm does not volunteer attestation. This applies only
  where the defender's environment requires attestation to act.
- Attestation shows which measured definition ran, not that its behaviour is
  benign. An attested agent can still be instructed to coordinate offensively.
- The simulated identity stands in for a verifier that works. Verifier flaws,
  such as evidence not bound to the platform that produced it, are out of
  scope here.

### Optional follow-on

An adapter that emits real TRACE claims for recorded runs, kept in a separate
optional package so the core stays at three dependencies.

## 9. What the offence is

An early version of the agent policies gave an offensive group no logged
behaviour that differed in kind from a benign team, so any detector would have
been measuring team size. Coordination is not the offence; this section says
what is.

### Offence studied: credential relay

A separation-of-duties violation. Each member has legitimate permissions of its
own. The group reaches something no single member is authorized for because one
member hands its credential to another, who then logs in with it. Everything
else the group does is ordinary hand-off work.

### What benign teams do that looks the same

- **Delegation.** A member asks a teammate to take over work on a host in the
  first member's zone. The teammate is granted access under its own credential
  (an administrative grant, not an agent tool call, not logged) and logs in
  with its own credential. Delegation is as frequent as offensive cross-zone
  logins.
- **Sloppy sharing.** A stated fraction of benign teams delegate by passing a
  credential, exactly as a relay would look. They are still benign. The default
  is 10 percent and it is a reported condition, not a hidden constant.

### What each tier can see

| Tier | Delegation versus relay |
| --- | --- |
| V0 | Same in kind: a first login to a new host after receiving something from a teammate who used it |
| V1 | Differ: the credential id in the login belongs to another agent |
| V2 | As V1, plus the relayed credential id appears in message or file content |

So V0 is expected to sit near chance on offence versus teamwork, and V1 is
expected to separate them up to the sloppy-sharing rate. That is a prediction,
not a result; the tables report what is measured.

### Confounds removed

Offensive groups and benign teams draw sizes from the same set and use the same
channels and topologies, including the pre-agreed plan. Control runs contain
benign teams at the same rate as positive runs. Denied calls happen at one
role-independent rate.

### Features this requires

Two pairwise features in a separate family, so results can be reported with and
without them:

- access expansion after receipt (V0): the first successful login by an agent
  to a host, shortly after a receipt from an agent that had already logged in
  there
- shared credential use (V1): two agents logging in with the same credential id

Generic coordination features (timing, overlap, messaging) are expected not to
separate offence from teamwork. Showing that, beside what the aggregation
features add at each tier, is the first result.

### Limits

- One offence class. A group that colludes by relaying content, not
  credentials, differs from a benign hand-off only in what the content is, and
  is not studied here.
- The sloppy-sharing rate is chosen, not measured from real organizations.
- Shared credential use is a known bad practice a defender can already alert
  on. The contribution is measuring it against teamwork at stated visibility.
  Evasion has not been tested.
