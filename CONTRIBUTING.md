# Contributing

## Pre-commit checklist

Run through this before every push. It is short on purpose.

- [ ] No tokens, API keys, or credentials. Secrets come from env vars only.
- [ ] No `.env` file staged. `.env.example` carries dummy values, never real ones.
- [ ] No absolute local paths (`/Users/...`).
- [ ] No account identifiers, collector IDs, channel IDs, or workspace references.
- [ ] No personal names or contact data.
- [ ] Scraped content is rendered as text, never assembled into markup.
- [ ] `make test` passes and `make fixture` runs offline with no credentials.

Quick scan:

```sh
# credentials and local paths: case-insensitive is fine, these all contain characters
# that do not occur in hex
git diff --cached | grep -nEi 'sk-|gh[pous]_|xox[baprs]-|AKIA|BEGIN [A-Z ]*PRIVATE KEY|/Users/'

# channel and workspace identifiers: case-SENSITIVE, deliberately
git diff --cached | grep -nE 'C0[A-Z0-9]{8}|T0[A-Z0-9]{8}'
```

The second scan must not take `-i`. A channel id is uppercase by construction, and
`C0[A-Z0-9]{8}` matched case-insensitively will hit any lowercase hex string containing `c0`
followed by eight hex characters. This repository stores content hashes in `meta.yaml`, so
that is not a rare coincidence: it has already produced two false boundary violations in two
independently written scanners, once on a commit hash and once on an `exercised_hash`.

A scan that cries wolf gets ignored, which is worse than not scanning, because the next
finding is real.

## Pull requests

Every meaningful change goes through a pull request. Direct pushes to `main` do not count
as reviewed work.

1. Branch, commit, open a PR.
2. Qodo reviews automatically. If it does not, comment `/agentic_review`.
3. Fix valid High-severity findings. If a finding is incorrect, deferred, or expected,
   dismiss it in the Qodo thread and say why.
4. Push fixes to the same PR and let the follow-up review run.
5. Merge once the review is addressed.

## Verification

```sh
make test       # unit tests, no network
make fixture    # deterministic offline pipeline run
make exercise   # both, in the order the exercise gate requires
```
