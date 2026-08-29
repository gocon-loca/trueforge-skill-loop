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
   skill registry that TrueForge consumes.
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

# Render the output
make serve   # then open http://localhost:8000/map/board.html
```

Copy `.env.example` to `.env` for live acquisition. Never commit `.env`.

## Repository contents

| Path | What it is |
|---|---|
| `pipeline/` | Acquisition, normalization, and scoring. Standard library only. |
| `registry/` | Git-backed skill packs consumed by TrueForge, with the exercise gate schema. |
| `fixtures/` | Deterministic payloads the offline path and the exercise gate run against. |
| `map/` | Rendered output view. |
| `docs/` | Setup runbook. |

## Qodo Code Review Evidence

Every meaningful change in this repository goes through a pull request reviewed by
[Qodo](https://www.qodo.ai) before merge. Direct pushes to `main` do not count as reviewed
work. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the workflow.

Representative reviewed PR: _to be linked once the first review completes._

What Qodo found and what changed: _pending._

## License

MIT. See [`LICENSE`](LICENSE).
