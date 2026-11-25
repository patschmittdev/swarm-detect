# Swarmtrace phase 3: scope and containment

Status: built. Results are in the README; tables are in `data/scope.md` and
`data/containment.md`. This document extends `docs/design.md`, whose sections
4 (contract, invariants) and 9 (offence definition) still bind.

The text below is the design as written before implementation. Building it
showed several places where it did not fit the code. They were resolved as
follows, and the code follows these, not the original wording:

- The own-credential scope feature needs V1, not V0, because telling an own
  login from a borrowed one needs the credential id.
- "Files read on a host" is not in the log. A borrowed session's reads are the
  files an agent first reads after its borrowed login, on any host.
- The identical-policy check is an exact gate on role-flipped twins, with
  byte-identical logs required. A statistical comparison of in-scope relays
  with sharing controls is reported and is not a gate, because relay runs can
  contain extra sharing teams.
- A label-side `outcomes.json` records task completion and out-of-scope reads,
  because benign task completion was not recorded anywhere.
- Controllers get decisions through a neutral type in the trace package and a
  tick-level hook in the engine. All controllers run at V1.
- Revoking a credential ends every session opened with it, so its owner is
  locked out of its own host. The prediction that revocation costs less benign
  work was written before that was known.
- The detectors used for containment are refitted deterministically from the
  main dataset; nothing is stored as a pickle.
- Three reference controllers are built: oracle, random and halt-all.
- A login-free comparator, distinct files read per agent, was added to the
  scope experiment after review.

## 1. Why

The first results end at a wall. A relay group and a benign team that shares a
credential sloppily run the same code, so the log shows that a credential was
shared and cannot show why. That is true by construction and it leaves two
questions the study cannot yet answer:

1. What extra information would let a defender tell the two apart, and how
   much of it is needed?
2. Once a detector fires, does acting on it stop anything, and at what cost to
   benign work?

Phase 3 adds one thing for each question. It keeps the existing
identical-policy case as a control, so a detector that separates the old
populations is still a detector with a leak.

## 2. Offence by scope

### Definition

Every hand-off between teammates concerns a task, and a task has a scope: a
set of files on the host the receiving member takes over.

- **Delegation** (benign): the receiver logs in under its own credential and
  works inside the scope.
- **Sloppy sharing** (benign): the receiver logs in with the sender's
  credential and works inside the scope.
- **In-scope relay** (the existing offence, kept as a control): identical to
  sloppy sharing. Its label differs and nothing else does.
- **Scope violation** (new offence): the receiver logs in with the sender's
  credential, works inside the scope, and also reads files outside it that the
  group's objective needs. The objective completes only when those files are
  read.

The difference is not an arbitrary cue. A hand-off should narrow authority:
the receiver should get the task's scope intersected with what the lender may
do, and never more. Delegation under the receiver's own credential does that.
A borrowed credential breaks the narrowing, because it carries the lender's
full authority. The offence is the use of that excess.

Reads are the interesting case. A system that enforces scope usually enforces
it on writes and leaves reads open, because blocking reads blocks harmless
context gathering. Out-of-scope reads therefore sit where prevention is
normally absent and detection is the only tool, which is why this study
measures them.

### Why it is not trivially separable

- Benign agents make scope mistakes. Every agent working under any credential
  reads an out-of-scope file at a small, role-independent rate (levels: 0, 2
  and 5 percent of reads). Sloppy sharers therefore sometimes touch
  out-of-scope files under a borrowed credential.
- The size of the violation varies: 1, 2 or 5 out-of-scope reads.
- Scope sizes are drawn from the same distribution for every team.
- A group's declared scope is plausible: it is drawn by the same process as a
  benign team's, and the violation reads files next to it on the same host.

### Defender context, a second axis

Visibility tiers say how much of each event the defender sees. Context says
what the defender knows about the organisation. It is defender-side
information, not ground truth, and it is generated for every team by one
process that never looks at roles.

| Context | Defender knows | Realistic analogue |
| --- | --- | --- |
| C0 | Nothing beyond the log | Raw log analysis |
| C1 | Which credential belongs to which agent | An identity directory |
| C2 | C1 plus the scope of each hand-off | A ticket or change-management system |

Context is a new file, `context.json`, in each run directory. It is the
second defender-visible file. A new invariant and test: `context.json` is
byte-identical for two runs that differ only in the roles of their teams.

### Features

| Feature | Needs | Meaning |
| --- | --- | --- |
| `borrowed_session_breadth` | V1, C0 | Distinct files read on a host by an agent after it logged in there with a credential it was not first to use |
| `out_of_scope_reads_borrowed` | V1, C2 | Reads outside the hand-off's scope, by an agent in a session opened with another agent's credential |
| `out_of_scope_reads_own` | V0, C2 | The same count for sessions opened with the agent's own credential; expected to carry no signal, reported as a check |

The first is what a defender without a ticket system can do: guess scope from
breadth. The second is the direct measurement.

### Measurements

Two labellings, always reported side by side:

- **Strict:** positive means scope violation. In-scope relays are controls.
- **Legacy:** positive means any relay. This reproduces the current tables.

For each, at V1 with contexts C0, C1 and C2, for the rule baseline and the
fitted detectors:

- AUROC and detection rate at the calibrated threshold, against all controls
  and against sharing controls only. The second number is the one stuck at
  chance today.
- By violation size and by benign mistake rate.
- The identical-policy control: in-scope relays against sloppy sharers must
  stay at chance at every context level. If it does not, something leaks.

Predictions, written before any run: at C0 the breadth feature separates only
the largest violations; at C2 separation is limited by the benign mistake
rate; C1 adds nothing over C0, because the first-user rule already recovers
ownership.

### Limits to state

- The offence and its feature are still designed together. The contribution is
  the measured value of context, not the feature.
- Scope is assumed to be recorded correctly and for every hand-off. Real
  ticket data is incomplete and late.
- Mistake rates are chosen, not measured.
- The log is assumed to be complete and unaltered. In practice that needs a
  tamper-evident log, which is assumed here and not modelled.

## 3. Containment

### Interventions

The engine already supports quarantining an agent and cutting a channel. A
containment controller is added on the defender's side: it reads the trace
prefix at each checkpoint, runs the online detector and attribution, and
issues interventions that take effect at the next tick.

| Lever | Effect | Needs |
| --- | --- | --- |
| Quarantine | Every call by the named agents is denied from the next tick | V0 |
| Credential revocation | Logins with the named credential are denied; open sessions under it end | V1 |

Cutting the channel is left out: two of the three channels have no runtime
messages to cut.

The controller is in a new package, `swarmtrace.contain`. It imports
`features` and `detect` and never reads labels or the manifest. Interventions
are written to `interventions.jsonl` beside the trace; their effect appears in
the trace as denied calls.

### Design

Paired runs: the same condition and seed with and without the controller, on
the scope-violation offence, because it has damage that can be counted after
the relay login. Detectors and thresholds are frozen from an earlier dataset
and are not refitted.

Three reference controllers bound the result:

- **Oracle:** acts at the first relayed login, using labels. An upper bound.
  It lives in `eval`, the only place labels may be read.
- **Random:** quarantines the same number of agents at the same tick, chosen
  at random. A lower bound on harm prevented.
- **Halt all:** denies every agent from the tick after the first flag. An
  upper bound on benign cost.

### Measurements

- Objective completion rate with and without containment.
- Out-of-scope reads prevented, as a fraction of those in the uncontained
  twin.
- Benign cost: benign agents quarantined; benign tasks left unfinished that
  finished in the twin.
- Time from the first relayed login to the intervention.

Each for quarantine and for revocation, for the rule and fitted detectors,
with the oracle, random and halt-all controllers beside them.

Prediction, written before any run: with a checkpoint every 8 ticks and
detection that mostly arrives at or after completion, containment prevents
little; revocation costs less benign work than quarantine. A null result is
reported as found.

### Limits to state

- Interventions take effect instantly and cannot be evaded. Agents do not
  react to being contained.
- The cost model counts unfinished tasks and nothing else.

## 4. What is kept fixed

- The trace schema and its version. Scope and interventions live in separate
  files.
- Existing conditions, seeds and recorded tables. Phase 3 datasets are new
  sweeps under new seed namespaces.
- Runtime dependencies: numpy, pandas, scikit-learn.

## 5. Order

1. Scope in the world and agents, `context.json`, the two new invariants'
   tests. No detector work.
2. Scope features and the context axis in evaluation.
3. The scope experiment and its tables.
4. The containment controller and the two reference controllers.
5. The containment experiment and its tables.

Steps 1 to 3 stand alone. Containment depends on step 1 only.
