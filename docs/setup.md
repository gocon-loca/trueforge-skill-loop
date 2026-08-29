# Setup

A runbook for someone who has just cloned this repository and wants to see it work.

Every command here is one you can run and check. Where something is not yet true, this
document says so rather than describing an intention in the present tense.

## The short version

You can evaluate this repository without credentials, without an account, and without
asking anyone for a key:

```sh
make exercise   # tests plus the offline pipeline path. No install, no credentials.
```

To also run the full loop, which needs one dependency:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
make demo PYTHON=.venv/bin/python
```

`make exercise` needs nothing installed and no credentials at all. `make demo` runs the
whole loop, gap through research, mint, exercise gate, and execution, and needs one
dependency but still no credentials.

**The offline path is the whole system minus live acquisition.** Credentials add real data
sources; they do not add capability you cannot otherwise inspect.

## Prerequisites

| Requirement | Why | How to check |
|---|---|---|
| Python 3.9 or newer | The pipeline and its tests. Standard library only, nothing to install. | `python3 --version` |
| Python 3.10 or newer | The orchestrator, and therefore `make demo`. | `python3 --version` |
| Node.js 22 or newer | TrueForge, the agent harness. | `node --version` |
| `make` | Entry point for every task below. | `make --version` |

Two different floors, because two parts of the repository have different needs, and it is
worth knowing which you are subject to.

The pipeline floor is 3.9, confirmed by running its full suite and the offline path under
3.9.6. It imports nothing outside the standard library.

The orchestrator floor is 3.10. Under 3.9 it fails at import with
`TypeError: unsupported operand type(s) for |`, because `orchestrator/loop.py` declares a
type alias using `X | None` union syntax, and a type alias is evaluated eagerly even with
`from __future__ import annotations` in the file. `requirements.txt` states 3.11 or newer;
nothing was found that requires 3.11 specifically, but 3.10 was not available here to test,
so treat 3.11 as the safe number and 3.10 as probable.

The orchestrator needs PyYAML. The pipeline needs nothing.

Install into a virtual environment, then point `make` at it:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
make demo PYTHON=.venv/bin/python
```

There is a `make deps` target, but on a recent macOS or Homebrew Python it fails with
`error: externally-managed-environment`, because PEP 668 forbids installing into a system
Python. The virtual environment above is the portable route and works regardless.
`.venv/` is already gitignored.

## Running the pipeline offline

```sh
make test       # unit tests, no network
make fixture    # deterministic pipeline run against a committed fixture
make exercise   # both, in the order the trust gate requires
make serve      # then open http://localhost:8000/map/board.html
make demo       # the full loop, after the virtual environment step above
```

`make fixture` reads `fixtures/brightdata-papers.json` and publishes to `data/papers.json`
and `data/papers.db`. It makes no network calls and reads no credentials. Running it twice
produces the same result, which is what makes it usable as a verification step rather than
just a smoke test.

## Running TrueForge

```sh
npx @truefoundry/trueforge
```

The harness serves on `http://localhost:8790` and stores its data in a local SQLite file.

**Running is not the same as configured.** A fresh instance starts with no model provider,
no connectors, no skills, and no sandbox provider. You can confirm what yours has:

```sh
curl -s http://localhost:8790/api/v1/models
curl -s http://localhost:8790/api/v1/skills
```

An empty `{"data":[]}` means the harness is up and has nothing configured yet. Configuring
it is a UI task, described below, and it needs credentials.

Two things worth knowing before you expose it anywhere. It logs `Auth is disabled; browser
login is off` at warn level and serves anyway, so treat a local instance as trusted-network
only. And it binds IPv6 loopback, so a client pinned to IPv4 will not reach it on
`127.0.0.1` even though `localhost` works; `lsof -nP -iTCP:8790 -sTCP:LISTEN` shows the
actual bind address.

## What needs credentials, and what they unlock

Nothing below is required to evaluate the offline path.

| Credential | Unlocks | Without it |
|---|---|---|
| Model provider API key | The harness can run an agent. Settings, then Models. | The harness runs; no agent executes. |
| Daytona API key | Sandboxed execution of generated code. Settings, then Sandbox providers. | No isolated execution target. |
| `BRIGHTDATA_API_KEY`, `BRIGHTDATA_COLLECTOR_ID` | Live acquisition via `make scrape`. | `make fixture` covers the same pipeline offline. |

Copy `.env.example` to `.env` and fill in what you need. `.env` is gitignored and must stay
that way. `make scrape` fails with a configuration message when the collector id is unset,
rather than a confusing argument error.

## The trust gate

A skill in `registry/` is untrusted until it has completed a passing run. `exercised` moves
from `false` to `true` only on that run, and re-minting a skill resets it. The reasoning and
the schema are in [`registry/README.md`](../registry/README.md).

Run the gate before trusting anything:

```sh
make exercise
```

## Contributing

Every meaningful change goes through a pull request. Direct pushes to `main` do not count as
reviewed work. Qodo reviews automatically; if it does not, comment `/agentic_review`. Fix
valid high-severity findings, or dismiss them in the thread with a reason. The pre-commit
checklist is in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Seeing the whole loop

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
make demo PYTHON=.venv/bin/python
```

`make demo` mints two skills from two different method gaps, exercises each against its own
verification, and then attempts work. It is worth watching for what it refuses: a skill
whose verification fails stays untrusted, and execution is blocked rather than proceeding on
an unexercised skill. The run prints that refusal as an outcome, because a gate that is
never seen to reject is not evidence of a gate.

## Not yet on `main`

Nothing from the previous edition of this list. Collector configuration, drift detection,
the orchestrator, and the enforced gate have all landed.

Still open: registering the skill packs with a running TrueForge instance
(`make trueforge-skills`).

If you are reading this and it lists something that has since landed, the runbook is stale
and that is a bug.
