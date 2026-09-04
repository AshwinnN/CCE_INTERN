#!/usr/bin/env python3
import os
import shutil
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from cce.ingestion.checkpoint import IngestionCheckpointStore  # noqa: E402


class IngestionCheckpointStoreTests(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = IngestionCheckpointStore(store_path=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_returns_none_when_nothing_saved(self):
        self.assertIsNone(self.store.load("src-1", "obj-1"))

    def test_save_then_load_round_trips(self):
        checkpoint_id = self.store.save("src-1", "obj-1", {"status": "partial", "errors": ["x"]})
        self.assertEqual(checkpoint_id, "src-1__obj-1")
        loaded = self.store.load("src-1", "obj-1")
        self.assertEqual(loaded, {"status": "partial", "errors": ["x"]})

    def test_object_id_with_path_separators_is_escaped_into_a_safe_filename(self):
        checkpoint_id = self.store.save("src-1", "folder/sub/doc.pdf", {"status": "complete"})
        self.assertNotIn("/", checkpoint_id)
        self.assertEqual(self.store.load("src-1", "folder/sub/doc.pdf"), {"status": "complete"})

    def test_mark_complete_stores_status_and_revision(self):
        self.store.mark_complete("src-1", "obj-1", "rev-9")
        loaded = self.store.load("src-1", "obj-1")
        self.assertEqual(loaded, {"status": "complete", "revision": "rev-9"})

    def test_different_source_ids_do_not_collide_on_the_same_object_id(self):
        self.store.save("src-A", "obj-1", {"status": "complete"})
        self.store.save("src-B", "obj-1", {"status": "partial"})
        self.assertEqual(self.store.load("src-A", "obj-1")["status"], "complete")
        self.assertEqual(self.store.load("src-B", "obj-1")["status"], "partial")

    def test_store_path_defaults_to_env_var_when_not_passed(self):
        os.environ["CCE_CHECKPOINT_STORE_PATH"] = os.path.join(self.tmpdir, "from_env")
        try:
            store = IngestionCheckpointStore()
            self.assertEqual(store.store_path, os.path.join(self.tmpdir, "from_env"))
            self.assertTrue(os.path.isdir(store.store_path))
        finally:
            del os.environ["CCE_CHECKPOINT_STORE_PATH"]


if __name__ == "__main__":
    unittest.main()
