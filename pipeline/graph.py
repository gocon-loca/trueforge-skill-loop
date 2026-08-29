"""Build an interconnection graph from public records, under the entity-linking method.

The method rules are the ones cited in registry/public-source-entity-linking:

- Do not take transitive closure over pairwise matches. One false positive chains records
  that share nothing into a single cluster [transitive-closure-collapse].
- Carry linkage confidence into the output rather than collapsing matches to boolean edges
  [linkage-uncertainty].

Two records are merged only through a link at or above the confidence floor. Links below it
are retained and rendered as unverified, because discarding them hides the fact that the
pipeline saw something and chose not to act on it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_FLOOR = 0.90


def cluster(records: list[dict], matches: list[dict], floor: float) -> dict[str, str]:
    """Union-find over verified matches only. Returns record id -> cluster id."""
    parent: dict[str, str] = {r["id"]: r["id"] for r in records}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for match in matches:
        if match["confidence"] < floor:
            continue
        left, right = find(match["left"]), find(match["right"])
        if left != right:
            parent[right] = left
    return {rid: find(rid) for rid in parent}


def build(payload: dict[str, Any], floor: float = DEFAULT_FLOOR) -> dict[str, Any]:
    records = payload["records"]
    matches = payload.get("matches", [])
    assignment = cluster(records, matches, floor)

    by_id = {r["id"]: r for r in records}
    clusters: dict[str, dict] = {}
    for rid, cid in assignment.items():
        entry = clusters.setdefault(
            cid, {"id": cid, "members": [], "labels": [], "sources": [], "kind": by_id[rid]["kind"]}
        )
        entry["members"].append(rid)
        entry["labels"].append(by_id[rid]["label"])
        entry["sources"].append(by_id[rid]["source"])

    for entry in clusters.values():
        # Shortest label is the least decorated form, which reads best as a node caption.
        entry["label"] = min(entry["labels"], key=len)
        entry["sources"] = sorted(set(entry["sources"]))
        entry["evidence"] = len(entry["members"])

    edges = []
    for relation in payload.get("relations", []):
        edges.append({
            "source": assignment[relation["from"]],
            "target": assignment[relation["to"]],
            "kind": relation["kind"],
            "provenance": relation["source"],
            "verified": True,
        })
    for match in matches:
        if match["confidence"] < floor:
            # Retained deliberately: a link the method declined to act on is a finding, and
            # dropping it would make the graph look more certain than the evidence is.
            edges.append({
                "source": assignment[match["left"]],
                "target": assignment[match["right"]],
                "kind": "unverified_match",
                "provenance": match["basis"],
                "confidence": match["confidence"],
                "verified": False,
            })

    return {
        "confidence_floor": floor,
        "record_count": len(records),
        "cluster_count": len(clusters),
        "clusters": sorted(clusters.values(), key=lambda c: c["id"]),
        "edges": edges,
        "note": payload.get("note", ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="fixtures/entities.json")
    parser.add_argument("--output", default="data/graph.json")
    parser.add_argument("--floor", type=float, default=DEFAULT_FLOOR)
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    graph = build(payload, args.floor)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")

    naive = build(payload, 0.0)
    print(
        f"{graph['record_count']} records -> {graph['cluster_count']} entities "
        f"at floor {args.floor}"
    )
    print(
        f"  naive closure over every match would give {naive['cluster_count']}, "
        f"which is the collapse the method exists to prevent"
    )
    print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
