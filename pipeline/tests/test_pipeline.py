import sqlite3
import tempfile
import unittest
from pathlib import Path

from pipeline.score import score_paper, score_records
from pipeline.scrape import extract_records, normalize_record, write_sqlite


class PipelineTests(unittest.TestCase):
    def test_extracts_nested_cli_envelope(self):
        records = [{"arxiv_id": "2608.1"}]
        self.assertEqual(extract_records({"data": {"results": records}}), records)

    def test_normalizes_aliases_and_lists(self):
        paper = normalize_record(
            {
                "id": "arXiv:2608.1",
                "title": " Example ",
                "authors": "Ada, Grace",
                "summary": "We propose a toy algorithm.",
                "categories": "cs.AI, cs.LG",
            },
            "2026-08-22T00:00:00Z",
        )
        self.assertEqual(paper["authors"], ["Ada", "Grace"])
        self.assertEqual(paper["arxiv_id"], "2608.1")
        self.assertEqual(paper["subjects"], ["cs.AI", "cs.LG"])
        self.assertEqual(paper["html_url"], "https://arxiv.org/html/2608.1")

    def test_rejects_incomplete_paper(self):
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            normalize_record({"title": "Incomplete"}, "2026-08-22T00:00:00Z")

    def test_scores_reproducible_signal(self):
        paper = {"title": "Toy algorithm", "abstract": "We propose a synthetic experiment."}
        self.assertGreaterEqual(score_paper(paper), 0.5)
        self.assertTrue(score_records([paper])[0]["reproducible"])

    def test_writes_sqlite(self):
        paper = {
            "arxiv_id": "2608.1", "title": "Example", "authors": ["Ada"],
            "abstract": "Toy algorithm", "subjects": ["cs.AI"], "score": 0.6,
            "reproducible": True, "scraped_at": "2026-08-22T00:00:00Z",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "papers.db"
            write_sqlite([paper], path)
            self.assertTrue(path.exists())

    def test_sqlite_matches_the_latest_run(self):
        """The JSON output is a snapshot of one run, so the table must be too.

        A record present in an earlier run and absent from a later one must not
        survive, or the two published outputs describe different datasets.
        """
        def paper(arxiv_id):
            return {
                "arxiv_id": arxiv_id, "title": "Example", "authors": ["Ada"],
                "abstract": "Toy algorithm", "subjects": ["cs.AI"], "score": 0.6,
                "reproducible": True, "scraped_at": "2026-08-22T00:00:00Z",
            }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "papers.db"
            write_sqlite([paper("2608.1"), paper("2608.2")], path)
            write_sqlite([paper("2608.2")], path)

            with sqlite3.connect(path) as connection:
                ids = {row[0] for row in connection.execute("SELECT arxiv_id FROM papers")}
            self.assertEqual(ids, {"2608.2"})

if __name__ == "__main__":
    unittest.main()
