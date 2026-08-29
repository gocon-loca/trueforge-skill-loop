# Skill Registry

Git-backed skill packs that TrueForge consumes as a skill source. Each skill is a
directory containing:

| File | Required | Purpose |
|---|---|---|
| `SKILL.md` | yes | The instructions the agent loads when the skill applies. |
| `meta.yaml` | yes | Provenance and trust state, including the `exercised` flag. |
| `citations.md` | yes when minted from research | Full citations for the method rules the skill encodes. |
| `references/` | no | Supporting material the skill can pull in. |

## meta.yaml schema

```yaml
name: competitor-site-interpretation   # directory name, kebab-case
version: 1                             # integer, bumped on re-mint
minted_from: research                  # research | incident | manual
exercised: false                       # see the exercise gate below
exercised_at: null                     # ISO-8601 UTC when it passed
exercised_by: null                     # command that constituted the passing run
exercised_hash: null                   # digest of the files that passed
citations: 3                           # count in citations.md, 0 for manual skills
```

## The exercise gate

A minted skill is **untrusted until it has completed one successful run.**
`exercised: false -> true` happens only on a passing run, and nothing else may flip it.

A skill is verified by its own `verify.py`, invoked as `make verify-skill SKILL=<name>`.
A skill that declares no verification, or ships no `verify.py`, cannot be exercised and so
cannot become trusted. Verification that exercises the surrounding machinery rather than
the skill's own method is not verification of that skill.

`minted_from: incident` marks a skill whose rules were extracted from an operational
record rather than from literature. It carries the same obligation as `research`: every rule
traces to a cited source, and here the source is a logged event rather than a paper. A skill
that claims either provenance and cites nothing is rejected.

`exercised_hash` is what makes the flag mean something. Recording that a run passed,
without recording what passed, lets an edit keep the flag: the metadata still says trusted
while the files it was earned against are gone. The hash covers every file in the skill
directory except `meta.yaml`, so the body, the citations and the verifier are all inside
the binding, and a skill whose files no longer match is refused at the point of use.

This is the mechanism that keeps built-never-run skills out of the trusted set.
The offline fixture path is what a skill is exercised against first:

```sh
make exercise      # runs the test suite, then the deterministic offline fixture path
```

Live execution comes second, and only after the offline run passes. A skill that has
never been exercised may be proposed and committed, but it must not be used to perform
work.

Re-minting a skill (because the method changed, or because a site drifted) resets
`exercised` to `false`. The skill re-earns trust the same way it earned it the first time.
