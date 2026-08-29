# TrueForge Skill Loop

An orchestration layer that makes [TrueForge](https://github.com/truefoundry/trueforge)
sessions verifiable and self-extending.

TrueForge provides the runtime an agent needs to do work: MCP tools, skills, sandboxed
execution, approvals, subagents, and persistent sessions. This project adds a loop around
that runtime so the agent can extend its own skill set during a task, and so no skill is
trusted before it has run.

## Start here

The problem: an agent executing a work step is limited to the methods it already knows. If
the literature has moved, the agent applies a stale method and the output looks fine.

The loop this project runs, per work step:

1. **Work.** The agent receives a task.
2. **Method-gap check.** Before executing, it asks whether current literature changes how
   this step should be done.
3. **Research.** If yes, it dispatches a research task and produces a digest with full
   citations and extracted method rules.
4. **Mint.** The digest becomes a `SKILL.md` pack with its citations, committed to the
   skill registry. The registry is laid out as a git-backed skill source in the format
   TrueForge reads.
5. **Exercise gate.** The minted skill is untrusted. `exercised: false -> true` happens
   only on a passing run.
6. **Execute.** The work runs using the now-trusted skill.

The exercise gate is the part worth looking at. A skill can be proposed, written, and
committed without ever having run, and a registry full of skills in that state is a
liability. Here a skill earns trust by executing against a deterministic offline fixture
before it is allowed near live work, and re-minting resets it to untrusted.

See [`registry/README.md`](registry/README.md) for the schema and the gate.

## Run

Requires Python 3.9 or newer and Node.js 22.14 or newer.

```sh
# Start the harness. UI at http://localhost:8790
npx @truefoundry/trueforge

# Deterministic offline pipeline run. No network, no credentials.
make fixture

# Unit tests
make test

# The exercise gate: tests, then the offline path
make exercise

# The loop end to end, offline. No credentials and no operator keys.
make demo

# Render the output
make serve   # then open http://localhost:8000/map/board.html
```

Copy `.env.example` to `.env` for live acquisition. Never commit `.env`.

## Repository contents

| Path | What it is |
|---|---|
| `pipeline/` | Acquisition, normalization, and scoring. Standard library only. |
| `orchestrator/` | The loop: gap check, research adapter, registry, exercise gate. |
| `registry/` | Git-backed skill packs in the format TrueForge reads, with the gate schema. |
| `config/` | Collector behaviour and drift thresholds, versioned rather than passed ad hoc. |
| `fixtures/` | Deterministic payloads the offline path and the exercise gate run against. |
| `map/` | Rendered output view. |
| `docs/` | Setup runbook. |

## Qodo Code Review Evidence

Every meaningful change in this repository goes through a pull request reviewed by
[Qodo](https://www.qodo.ai) before merge. Direct pushes to `main` do not count as reviewed
work. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the workflow.

**Representative merged PR:
[#1, Scaffold the public repo](https://github.com/gocon-loca/trueforge-skill-loop/pull/1).**
Qodo returned four findings. Three were correctness bugs in code lifted from an earlier
project: a Make target that could not run because it dropped a required argument, a
rendered view that fetched a path one directory above where the data was written, and a
SQLite writer that only upserted, so its table and its JSON snapshot described different
runs once a later scrape returned fewer records. All three were fixed before merge.

The fourth finding is the one worth reading, because it landed on the centerpiece. Qodo
observed that the exercise gate was an alias for two existing targets: nothing read a
skill's metadata, nothing ran a skill's declared verification, nothing promoted the trust
flag, and nothing rejected an unexercised skill at the point of use. The repository
documented a mechanism it did not yet implement. That finding was dismissed in thread with
its reasoning and a pointer to the pull request that implements the enforcement path,
rather than closed silently.

### The finding worth reading twice

On [#2](https://github.com/gocon-loca/trueforge-skill-loop/pull/2), which carries the
fullest review trail, Qodo reported that the trust type had a public constructor, so any
caller could assert a passing run without performing one, **and that the test suite was
itself obtaining trust that way.** The tests were green while asserting a guarantee they
had bypassed. Green was evidence of nothing.

That is this project's own thesis occurring one level up. The exercise gate exists because
work that has never run should not be trusted, and the tests for the gate had never
exercised the path they claimed to verify. Review caught it; we did not.

The fix replaces asserted evidence with a registry-issued ticket, single use, bound to the
skill version and body hash observed before the run and consumed on completion, so a
re-mint while a run is in flight invalidates the ticket rather than inheriting its trust.
The tests now go through the gate. What the change does not do is make trust unforgeable
in process, and the code says so where it would otherwise be tempting to imply otherwise.
The durable property is narrower and honest: what ran is recorded, and every change to
trust state is a reviewable diff.

Review also found, on the same trail, that skill names could escape the registry root
because only one write path validated them, that `exercised: "false"` read as trusted
because a non-empty string is truthy in Python, that re-minting wrote new content before
revoking trust so an interrupted write could leave new content under old passing evidence,
and that an unlaunchable verifier aborted the caller instead of failing the gate.

### What review cost, not only what it caught

Two of the three correctness bugs in #1 were introduced by this project, not inherited
from the code it was lifted from. Moving the rendered view into its own directory broke
the path it fetched, and rewriting a Make target dropped a required argument so the target
could not run at all. The drift-check division was written here too. Only the SQLite
writer predates this repository.

That distinction matters for reading the rest of this section. A review record where every
finding is an inherited flaw invites the conclusion that the review was staged against a
straw target. The more credible and more useful account is that we introduced defects at a
normal rate while moving quickly, and that the process caught them before they merged.

### The same pattern, found twice

The pattern in both cases is an invariant enforced at a distance from where it is relied
on. It recurred on
[#3](https://github.com/gocon-loca/trueforge-skill-loop/pull/3): the drift check divided by
a count that its configuration loader guaranteed to be non-zero, which held for the
intended path and not for a public function taking a plain dictionary. It was raised as a
review question rather than asserted as safe, then falsified by executing it rather than
by reading it. The fix moved validation to each point of use.

That sequence is the gate applied to a claim instead of to a skill, and it is why the
mechanism in this repository is worth more than the wording that describes it.

### PR history

| PR | State | What review changed |
|---|---|---|
| [#1](https://github.com/gocon-loca/trueforge-skill-loop/pull/1) | merged | Three lifted correctness bugs fixed; the unenforced gate identified and routed to #4 |
| [#2](https://github.com/gocon-loca/trueforge-skill-loop/pull/2) | superseded by #4 | Forgeable trust evidence, path traversal, truthy `"false"`, write ordering, launch failures |
| [#3](https://github.com/gocon-loca/trueforge-skill-loop/pull/3) | open | Division guarded at each point of use rather than only at load |
| [#4](https://github.com/gocon-loca/trueforge-skill-loop/pull/4) | open | The enforcement path for #1's fourth finding |


## License

MIT. See [`LICENSE`](LICENSE).
