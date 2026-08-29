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
   citations and extracted method rules. Two executors ship: a deterministic fixture-backed
   stub, which is what the offline paths use, and `ArxivResearchExecutor`, which queries the
   public arXiv API and extracts each method rule with a local model. Neither needs an
   account or an API key.
4. **Mint.** The digest becomes a `SKILL.md` pack with its citations, committed to the
   skill registry, which TrueForge reads as a git-backed skill source. See
   [Registering the registry with TrueForge](#registering-the-registry-with-trueforge).
5. **Exercise gate.** The minted skill is untrusted. `exercised: false -> true` happens
   only on a passing run.
6. **Execute.** The work runs using the now-trusted skill.

The exercise gate is the part worth looking at. A skill can be proposed, written, and
committed without ever having run, and a registry full of skills in that state is a
liability. Here a skill earns trust by executing against a deterministic offline fixture
before it is allowed near live work, and re-minting resets it to untrusted.

See [`registry/README.md`](registry/README.md) for the schema and the gate.

## Run

There are two Python floors, not one. The pipeline is standard library only and runs on
3.9, verified by executing its suite and the offline path under 3.9.6. The orchestrator
needs 3.11: `orchestrator/loop.py` declares a type alias using the `X | None` union, and a
type alias is evaluated eagerly even with `from __future__ import annotations`, which covers
annotations but not assignments. 3.10 is likely fine and is untested here, so it is not
claimed. Node.js 22.14 or newer for TrueForge.

```sh
# One-time: dependencies go in a venv, which every target then picks up automatically.
# A system Python refuses a direct pip install under PEP 668.
make deps

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

# Build the interconnection graph and render it
make map
make serve   # then open http://localhost:8000/map/board.html
```

Copy `.env.example` to `.env` for live acquisition. Never commit `.env`.

## Where skills come from

Two provenances, both cited, neither self-certifying.

`minted_from: research` marks a skill whose method rules were extracted from literature.
`minted_from: incident` marks one extracted from an operational record, where each rule
traces to a logged event rather than a paper. Both are rejected at mint time if they cite
nothing, and both land untrusted and earn trust the same way.

`competitor-site-interpretation` carries a rule amended from a **live** retrieval: real
papers, real identifiers, and author lists taken from the API rather than recorded as
unverified. Its rule 2 is prescribed by two sources for two different objectives, keeping the
semantic structure legible and bounding observation cost, and it states both because a change
satisfying one could otherwise destroy the other while the rule still read as satisfied.

`meta.yaml` records what prompted that amend: the gap question, the retrieval source, the
identifier and the date. That record exists because folding a live retrieval into an existing
skill would otherwise erase the evidence that live retrieval happened at all, leaving it only
in a commit message.

`agent-observation-budgeting` carries the rules from that same retrieval which had no
counterpart. Its rules were extracted from abstracts by a local model, which is a judgement
rather than a lookup, so its verification checks grounding rather than correctness: every
citation carries a well-formed arXiv identifier, a non-empty imperative rule, and a stated
objective. That is a weaker guarantee than the known-answer skills get, and the skill says so
in its own constraints: read the cited papers before relying on a rule.

`workspace-sentinel` is the second kind. Its rules come from the recorded behaviour of a
coordination agent, including two cases where the refined rule differs from the obvious one:
an unavailable liveness signal is missing evidence rather than evidence of failure, and
crossing an idle threshold is a reason to escalate only when the content would carry new
information. Its verification replays the situations that actually occurred and asserts the
encoded policy reproduces the decisions that were actually taken.

## Registering the registry with TrueForge

TrueForge reads skills as git-backed `SKILL.md` packs. This repository is public, so
registering it needs no credentials: the manifest carries an HTTPS URL, a path and a ref,
and TrueForge fetches the packs itself.

```sh
npx @truefoundry/trueforge     # starts the harness
make trueforge-skills          # registers every pack in registry/
```

TrueForge then reports them:

```sh
curl -s 'http://[::1]:8790/api/v1/skills'
```

```json
{"data": [
  {"name": "competitor-site-interpretation", "description": "Interpret a public site ..."},
  {"name": "public-source-entity-linking",   "description": "Link entities across ..."}
]}
```

Registration is idempotent, so re-running it after a re-mint is safe.

Note on the address. TrueForge binds IPv6 loopback, so `http://127.0.0.1:8790` returns
nothing while `http://[::1]:8790` works. `lsof -nP -iTCP:8790 -sTCP:LISTEN` shows the bind
address if you need to check.

### What this does and does not show

It shows that a skill this project minted, with its citations and its trust record, is
visible to TrueForge as a skill it could load. That is the part of the claim this
repository can demonstrate on its own.

It does not show an agent using one inside a session. A TrueForge session needs a
configured model provider, and skills additionally need a configured sandbox provider.
Both take operator credentials that are not in this repository and should not be. On an
instance without them, `/api/v1/settings/model-providers` returns an empty list and
`/api/v1/settings/sandbox-providers` reports that none is configured, while the skills
above still register and list correctly.

## Repository contents

| Path | What it is |
|---|---|
| `pipeline/` | Acquisition, normalization, and scoring. Standard library only. |
| `orchestrator/` | The loop: gap check, research adapter, registry, exercise gate. |
| `scripts/` | Registering the skill registry with a running TrueForge instance. |
| `registry/` | Git-backed skill packs in the format TrueForge reads, the gate schema, and the version ledger. |
| `config/` | Collector behaviour and drift thresholds, versioned rather than passed ad hoc. |
| `fixtures/` | Deterministic payloads the offline path and the exercise gate run against. |
| `map/` | Interconnection map, rendered from `data/graph.json`. |
| `docs/` | Setup runbook. |

## Qodo Code Review Evidence

Every meaningful change in this repository goes through a pull request reviewed by
[Qodo](https://www.qodo.ai) before merge. Direct pushes to `main` do not count as reviewed
work. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the workflow.

**Representative merged PR:
[#1, Scaffold the public repo](https://github.com/gocon-loca/trueforge-skill-loop/pull/1).**
Qodo returned four findings. Three were correctness bugs, and it is worth being exact
about where they came from, because this section's argument depends on it. Two were
introduced by this project while moving quickly: a Make target that could not run because
the rewrite dropped a required argument, and a rendered view that fetched a path one
directory above where the data was written, because the file had been moved without
updating it. The third was inherited: a SQLite writer that only upserted, so its table and
its JSON snapshot described different runs once a later scrape returned fewer records. All
three were fixed before merge.

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

Fifteen merged, one closed and superseded, none pushed directly to `main`. The table names the
ones where review changed the design rather than the wording.

| PR | What review changed |
|---|---|
| [#1](https://github.com/gocon-loca/trueforge-skill-loop/pull/1) | Three correctness bugs; the gate identified as an alias that enforced nothing, routed to #4 |
| [#2](https://github.com/gocon-loca/trueforge-skill-loop/pull/2) | Closed, superseded by #4. **Carries the fullest review trail**, including the forgeable-evidence exchange |
| [#3](https://github.com/gocon-loca/trueforge-skill-loop/pull/3) | Drift-check division guarded at each point of use rather than only at load |
| [#4](https://github.com/gocon-loca/trueforge-skill-loop/pull/4) | The enforcement path for #1's fourth finding: ticket-bound trust, path traversal, truthy `"false"`, write ordering, launch failures |
| [#10](https://github.com/gocon-loca/trueforge-skill-loop/pull/10) | `make deps` failed on any clean machine under PEP 668, at the first install step a reader runs |
| [#11](https://github.com/gocon-loca/trueforge-skill-loop/pull/11) | `main` was broken for 86 seconds by committed conflict markers, caught and repaired before anyone cloned it |
| [#15](https://github.com/gocon-loca/trueforge-skill-loop/pull/15) | Smoke tests replaced by known answers; fixtures moved inside the trust hash; a threshold that claimed to be a verified merge |
| [#16](https://github.com/gocon-loca/trueforge-skill-loop/pull/16) | Version injectivity made a check rather than a rule, after the same defect recurred three times |

The remaining merged PRs (#5, #6, #7, #8, #9, #12, #13, #14) add the runbook, the second and
third skills, TrueForge registration, the interconnection map, and the live arXiv executor.

### The check that found what review did not

`version` identifies which body of content a trust record referred to, so the mapping has to
be injective in both directions. Two contents sharing a version is ambiguous. Two versions
sharing a content is ambiguous in the same way, and is easier to create by accident, because
bumping a version feels like diligence.

That rule was written down twice, argued to a sharper form, and agreed explicitly. It then
recurred three times in four hours while two reviewers were watching for it. A rule that
survives that is a missing check, so it is one now: `registry/version-ledger.jsonl` records
`(name, version, content_hash)` on every passing exercise, and the registry refuses an entry
that makes either direction ambiguous, checked before the trust record is written so a
violation leaves the skill untrusted rather than trusted under an ambiguous version.

```sh
make check-versions
```

Turning it on immediately failed `make demo`, and the failure was correct: minting bumped the
version unconditionally, so re-minting identical content always produced two versions for one
content, and the demo re-mints on every run. It had been manufacturing that ambiguity every
time it ran, through three separate rounds of argument about versioning. Minting now keeps
the version when content is unchanged, while still revoking trust.

The ledger begins where it begins and cannot validate exercises that predate it.
`registry/README.md` says so, along with two limits it does not yet address.

## License

MIT. See [`LICENSE`](LICENSE).
