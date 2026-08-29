"""A live research executor backed by the public arXiv API.

This is the first implementation of the `ResearchExecutor` protocol that reaches a real
source. It needs no credentials and no account: arXiv's export API is public.

Two steps, deliberately separated, because they fail differently.

**Retrieval** is deterministic and verifiable. A query returns real papers with real
identifiers, titles and author lists. Nothing here is inferred.

**Rule extraction** is not. Turning an abstract into the method rule a skill should encode
is a judgement, and this module makes it with a local model through an OpenAI-compatible
endpoint. A rule it cannot extract is left empty, which makes the citation ungrounded, which
makes the digest refuse to mint. That is the intended failure: a skill whose rules were
guessed is worse than no skill.

Offline by default in the sense that matters: nothing here runs during `make test` or
`make demo`. The fixture-backed stub remains what the deterministic paths use.
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from orchestrator.research_executor import Citation, Digest

ARXIV_API = "https://export.arxiv.org/api/query"
ATOM = {"a": "http://www.w3.org/2005/Atom"}


def _ssl_context() -> ssl.SSLContext | None:
    """Some Python builds ship without a usable CA bundle, so urllib fails cert
    verification on a host curl reaches fine. Prefer certifi's bundle when it is present
    and fall back to the default context rather than to an unverified one."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None
DEFAULT_MODEL_ENDPOINT = "http://localhost:11434/v1/chat/completions"
DEFAULT_MODEL = "qwen2.5:7b"

RULE_PROMPT = """You are extracting one method rule from a paper abstract.

A method rule is a single imperative sentence telling a practitioner what to do or avoid,
which the abstract actually supports. It is not a summary of the paper.

Good: "Downsample the DOM to its semantic skeleton before extraction, because raw HTML at
realistic page sizes buries structure in styling and container noise."

Bad: "This paper explores DOM downsampling for web agents."

If the abstract does not support a method rule, reply with exactly: NONE

Reply with the rule alone. No preamble, no quotes.

Title: {title}

Abstract: {abstract}"""


def _slug(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(words[:4]) or "citation"


def search_arxiv(query: str, max_results: int = 4, timeout: int = 30) -> list[dict]:
    """Retrieve real papers. Deterministic, verifiable, no credentials."""
    url = f"{ARXIV_API}?{urllib.parse.urlencode({'search_query': query, 'start': 0, 'max_results': max_results})}"
    with urllib.request.urlopen(url, timeout=timeout, context=_ssl_context()) as response:
        root = ET.fromstring(response.read())

    papers = []
    for entry in root.findall("a:entry", ATOM):
        raw_id = (entry.findtext("a:id", default="", namespaces=ATOM) or "").rstrip("/")
        identifier = raw_id.rsplit("/abs/", 1)[-1] if "/abs/" in raw_id else raw_id
        published = entry.findtext("a:published", default="", namespaces=ATOM) or ""
        authors = [
            (a.findtext("a:name", default="", namespaces=ATOM) or "").strip()
            for a in entry.findall("a:author", ATOM)
        ]
        papers.append({
            "identifier": f"arXiv:{identifier}",
            "title": " ".join((entry.findtext("a:title", default="", namespaces=ATOM) or "").split()),
            "abstract": " ".join((entry.findtext("a:summary", default="", namespaces=ATOM) or "").split()),
            "authors": [a for a in authors if a],
            "year": int(published[:4]) if published[:4].isdigit() else 0,
        })
    return papers


def extract_rule(
    paper: dict,
    endpoint: str = DEFAULT_MODEL_ENDPOINT,
    model: str = DEFAULT_MODEL,
    timeout: int = 180,
) -> str:
    """Ask a local model for the method rule. Returns "" when it will not commit to one.

    An empty rule is not an error to be papered over. It propagates into `is_groundable`
    and stops the mint, which is the behaviour we want when nothing was actually extracted.
    """
    body = json.dumps({
        "model": model,
        "messages": [{
            "role": "user",
            "content": RULE_PROMPT.format(title=paper["title"], abstract=paper["abstract"][:3000]),
        }],
        "temperature": 0,
    }).encode()

    request = urllib.request.Request(
        endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except Exception:
        return ""

    rule = (payload.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
    rule = rule.strip('"').strip()
    if not rule or rule.upper().startswith("NONE"):
        return ""
    return " ".join(rule.split())


class ArxivResearchExecutor:
    """Live `ResearchExecutor`. Retrieval is real; rule extraction is a model's judgement."""

    def __init__(
        self,
        max_results: int = 4,
        endpoint: str = DEFAULT_MODEL_ENDPOINT,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.max_results = max_results
        self.endpoint = endpoint
        self.model = model

    def run(self, question: str) -> Digest:
        papers = search_arxiv(question, max_results=self.max_results)
        citations = []
        for paper in papers:
            rule = extract_rule(paper, endpoint=self.endpoint, model=self.model)
            citations.append(Citation(
                key=_slug(paper["title"]),
                title=paper["title"],
                # Real author lists, from the API. The fixture-backed digests record
                # authorship as unverified because that dispatch confirmed identifiers and
                # titles but not authors; a live retrieval has no such excuse.
                authors=", ".join(paper["authors"][:6]) or "see arXiv record",
                venue="arXiv preprint",
                year=paper["year"],
                identifier=paper["identifier"],
                method_rule=rule,
            ))
        return Digest(question=question, citations=tuple(citations), source="arxiv-live")
