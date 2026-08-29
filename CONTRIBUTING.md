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
git diff --cached | grep -nEi 'sk-|gh[pous]_|xox[baprs]-|AKIA|BEGIN [A-Z ]*PRIVATE KEY|/Users/'
```

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
