"""Q1 retrieval: a task description returns ranked, scored candidates.

The property that matters is not that the right skill ranks first on four hand-picked
queries. It is that retrieval can say *no*: if every task finds a skill, the decision between
using an existing one and minting a new one is never actually made, and the procedure this
feeds is decorative.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from orchestrator.retrieval import SkillIndex, TfidfEmbedder, cosine, tokenize

REGISTRY = Path("registry")


class TokenizerTests(unittest.TestCase):
    def test_drops_stopwords_and_short_tokens(self) -> None:
        self.assertEqual(tokenize("The skill is for a page"), ["page"])

    def test_is_case_and_punctuation_insensitive(self) -> None:
        self.assertEqual(tokenize("Downsample, DOM!"), tokenize("downsample dom"))


class EmbedderTests(unittest.TestCase):
    def test_refuses_to_embed_before_fit(self) -> None:
        with self.assertRaises(RuntimeError):
            TfidfEmbedder().embed("anything")

    def test_is_deterministic(self) -> None:
        """Scores become evidence in a decision record, and evidence that changes between
        runs is not evidence."""
        a, b = TfidfEmbedder(), TfidfEmbedder()
        docs = ["downsample the dom", "link records across sources"]
        a.fit(docs)
        b.fit(docs)
        self.assertEqual(a.embed("downsample dom"), b.embed("downsample dom"))

    def test_identical_text_is_maximally_similar(self) -> None:
        e = TfidfEmbedder()
        e.fit(["downsample the dom before extraction", "unrelated text about queues"])
        v = e.embed("downsample the dom before extraction")
        self.assertAlmostEqual(cosine(v, v), 1.0, places=6)

    def test_empty_and_stopword_only_text_embeds_to_nothing(self) -> None:
        e = TfidfEmbedder()
        e.fit(["some real content here"])
        self.assertEqual(e.embed(""), {})
        self.assertEqual(e.embed("the and of it"), {})


class IndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = SkillIndex(REGISTRY).build()

    def test_every_skill_in_the_registry_is_indexed(self) -> None:
        names = {s.name for s in self.index.signatures}
        self.assertEqual(len(names), len(self.index.signatures), "duplicate names")
        self.assertIn("competitor-site-interpretation", names)
        self.assertNotIn("_template", names)

    def test_every_skill_declares_a_signature(self) -> None:
        for s in self.index.signatures:
            self.assertTrue(s.task_type, f"{s.name} declares no task_type")
            self.assertTrue(s.inputs, f"{s.name} declares no inputs")
            self.assertTrue(s.outputs, f"{s.name} declares no outputs")

    def test_reads_the_version_ledger_rather_than_tracking_versions_itself(self) -> None:
        ledger = self.index.ledger()
        self.assertTrue(ledger, "no ledger entries read")
        by_name = {e["name"]: e["version"] for e in ledger}
        for s in self.index.signatures:
            if s.name in by_name:
                self.assertEqual(s.version, by_name[s.name],
                                 f"{s.name} meta and ledger disagree on version")

    def test_search_returns_every_candidate_scored(self) -> None:
        """Not only those above a threshold. A caller needs to see that the best was poor."""
        results = self.index.search("anything at all")
        self.assertEqual(len(results), len(self.index.signatures))
        for c in results:
            self.assertIn("body", c.components)
            self.assertIn("signature", c.components)
            self.assertIn("trust", c.components)

    def test_results_are_ranked(self) -> None:
        scores = [c.score for c in self.index.search("downsample a page before extraction")]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_each_skill_wins_its_own_task(self) -> None:
        cases = {
            "scrape a competitor website for structured company facts":
                "competitor-site-interpretation",
            "decide whether two filings describe the same organisation":
                "public-source-entity-linking",
            "watch the other agent and tell the operator if it stalls":
                "workspace-sentinel",
            "the page will not fit in context, decide what to keep for the planner":
                "agent-observation-budgeting",
        }
        for task, expected in cases.items():
            with self.subTest(task=task):
                self.assertEqual(self.index.search(task)[0].signature.name, expected)

    def test_an_unrelated_task_scores_near_zero(self) -> None:
        """The load-bearing case. If everything matches something, the mint-versus-use
        decision is never made and the procedure downstream is decorative."""
        best = self.index.search("convert a PDF invoice into a spreadsheet row")[0]
        self.assertLess(best.score, 0.10, f"unrelated task matched {best.signature.name}")

    def test_trust_is_reported_but_not_folded_into_the_score(self) -> None:
        """An untrusted skill can still be the right skill to amend."""
        c = self.index.search("scrape a competitor website")[0]
        self.assertIn(c.components["trust"], (0.0, 1.0))
        self.assertAlmostEqual(
            c.score, 0.6 * c.components["body"] + 0.4 * c.components["signature"], places=6
        )

    def test_a_candidate_serialises_for_a_decision_record(self) -> None:
        rec = self.index.search("link records")[0].as_record()
        for key in ("skill", "version", "score", "components", "provenance"):
            self.assertIn(key, rec)

    def test_an_empty_registry_indexes_without_crashing(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            empty = SkillIndex(Path(tmp)).build()
            self.assertEqual(empty.signatures, [])
            self.assertEqual(empty.search("anything"), [])
