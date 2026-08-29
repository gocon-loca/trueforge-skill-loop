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
minted_from: research                  # research | manual
exercised: false                       # see the exercise gate below
exercised_at: null                     # ISO-8601 UTC when it first passed
exercised_by: null                     # command that constituted the passing run
citations: 3                           # count in citations.md, 0 for manual skills
```

## The exercise gate

A minted skill is **untrusted until it has completed one successful run.**
`exercised: false -> true` happens only on a passing run, and nothing else may flip it.

This is the mechanism that prevents built-never-run skills from entering the trusted set.
The offline fixture path is what a skill is exercised against first:

```sh
make exercise      # runs the test suite, then the deterministic offline fixture path
```

Live execution comes second, and only after the offline run passes. A skill that has
never been exercised may be proposed and committed, but it must not be used to perform
work.

Re-minting a skill (because the method changed, or because a site drifted) resets
`exercised` to `false`. The skill re-earns trust the same way it earned it the first time.
