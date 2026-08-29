"""Tests for the interconnection graph.

The property under test is the method rule the graph is built on: a link below the
confidence floor must not merge two entities, because one false positive taken
transitively chains records that share nothing.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from pipeline.graph import DEFAULT_FLOOR, build

FIXTURE = json.loads(Path("fixtures/entities.json").read_text(encoding="utf-8"))


class GraphTests(unittest.TestCase):
    def test_weak_links_do_not_merge_entities(self) -> None:
        graph = build(FIXTURE, DEFAULT_FLOOR)
        self.assertEqual(graph["cluster_count"], 5)

    def test_naive_closure_would_collapse_them(self) -> None:
        """If this stops collapsing, the fixture no longer shows why the floor exists."""
        naive = build(FIXTURE, 0.0)
        self.assertLess(
            naive["cluster_count"],
            build(FIXTURE, DEFAULT_FLOOR)["cluster_count"],
            "a floor of zero must over-merge; otherwise the fixture proves nothing",
        )

    def test_declined_links_are_retained_not_discarded(self) -> None:
        graph = build(FIXTURE, DEFAULT_FLOOR)
        declined = [e for e in graph["edges"] if not e["verified"]]
        self.assertTrue(declined, "a link the method declined is a finding, not noise")
        for edge in declined:
            self.assertIn("confidence", edge)
            self.assertIn("provenance", edge)

    def test_every_record_lands_in_exactly_one_cluster(self) -> None:
        graph = build(FIXTURE, DEFAULT_FLOOR)
        members = [m for c in graph["clusters"] for m in c["members"]]
        self.assertEqual(sorted(members), sorted(r["id"] for r in FIXTURE["records"]))
        self.assertEqual(len(members), len(set(members)))

    def test_relations_are_rewritten_onto_clusters(self) -> None:
        graph = build(FIXTURE, DEFAULT_FLOOR)
        ids = {c["id"] for c in graph["clusters"]}
        for edge in graph["edges"]:
            self.assertIn(edge["source"], ids)
            self.assertIn(edge["target"], ids)

    def test_raising_the_floor_never_merges_more(self) -> None:
        counts = [build(FIXTURE, f)["cluster_count"] for f in (0.0, 0.5, 0.9, 0.99)]
        self.assertEqual(counts, sorted(counts), f"monotonic in the floor, got {counts}")
