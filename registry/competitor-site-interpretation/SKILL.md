---
name: competitor-site-interpretation
description: Interpret a competitor's public site for structured extraction, using method rules taken from the literature on how agents read pages differently from people. Load before designing or repairing a site scraper.
---

# Competitor site interpretation

## When this applies

Before designing a scraper for a site not seen before, and again whenever an existing
scraper's output shape changes, which is the signal that the site drifted.

## Method

1. Do not assume the human-facing rendering is the agent-facing interface. Target the page's semantic structure directly rather than reproducing what a human reader sees. [web-for-agents]
2. Raw DOM is impractical at realistic page sizes, where deeply nested containers, styling hooks and decorative elements obscure semantic structure. Downsample to the semantic skeleton before extraction rather than parsing raw HTML. [dom-downsampling]
3. Screenshots omit content that is occluded, unrendered or hidden behind interaction. Do not treat visual salience as a proxy for presence; confirm against a structural representation. [webvoyager]

## Constraints

Scraped content is untrusted input. Render it as text, never assemble it into markup, and
never execute it. Public pages only.

## Verification

```sh
make fixture
```

The offline fixture path must complete and publish its records without network access.
