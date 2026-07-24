from datetime import datetime, timezone
import tempfile
from pathlib import Path
import unittest

from models import Item
from pipeline.dedup import cosine_similarity, deduplicate_items
from store.db import connect, init_db, recent_embedding_memory, upsert_items


def make_item(title: str, embedding: list[float]) -> Item:
    item = Item.from_source(
        title=title,
        url=f"https://example.test/{title.replace(' ', '-')}",
        source_type="test",
        source_name="Example",
        tier="A",
    )
    item.embedding = embedding
    item.status = "included"
    return item


class DedupTests(unittest.TestCase):
    def test_cosine_similarity_handles_matching_vectors(self):
        self.assertAlmostEqual(cosine_similarity([1, 0], [1, 0]), 1.0)
        self.assertEqual(cosine_similarity([1, 0], [0, 0]), 0.0)

    def test_deduplicate_items_drops_against_memory(self):
        item = make_item("Crosslinked polyolefin tubing update", [1.0, 0.0])
        config = {"dedup": {"similarity_threshold": 0.85, "on_duplicate": "drop"}}

        deduplicate_items(
            [item],
            [{"id": "existing", "embedding": [0.99, 0.01]}],
            config,
        )

        self.assertEqual(item.status, "dropped_dup")
        self.assertEqual(item.dup_of, "existing")

    def test_deduplicate_does_not_self_collide_with_memory(self):
        # A re-fetched item whose own id is already in the 30-day memory must NOT be dropped as a
        # duplicate of itself (regression: this demoted included items to dropped_dup on re-runs).
        item = make_item("Recurring soft robot item", [1.0, 0.0])
        config = {"dedup": {"similarity_threshold": 0.85, "on_duplicate": "drop"}}

        deduplicate_items([item], [{"id": item.id, "embedding": [1.0, 0.0]}], config)

        self.assertEqual(item.status, "included")
        self.assertIsNone(item.dup_of)

    def test_deduplicate_items_tracks_current_run_memory(self):
        first = make_item("First polymer item", [1.0, 0.0])
        second = make_item("Second polymer item", [1.0, 0.0])
        config = {"dedup": {"similarity_threshold": 0.85, "on_duplicate": "drop"}}

        deduplicate_items([first, second], [], config)

        self.assertEqual(first.status, "included")
        self.assertEqual(second.status, "dropped_dup")
        self.assertEqual(second.dup_of, first.id)

    def test_recent_embedding_memory_reads_stored_embeddings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "tracker.db"
            item = make_item("Stored polymer item", [0.5, 0.5])
            item.fetched_date = datetime.now(timezone.utc).date().isoformat()

            with connect(db_path) as db:
                init_db(db)
                upsert_items(db, [item])
                memory = recent_embedding_memory(db, window_days=30)

        self.assertEqual(memory, [{"id": item.id, "embedding": [0.5, 0.5]}])


if __name__ == "__main__":
    unittest.main()
