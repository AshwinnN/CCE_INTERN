import unittest

from integrations.agenticplane import AgenticPlaneMemory


class FakeMemory:
    def __init__(self):
        self.calls = []

    def store(self, **kwargs):
        self.calls.append(("store", kwargs))
        return {"memory_id": "mem-1"}

    def store_batch(self, **kwargs):
        self.calls.append(("store_batch", kwargs))
        return {"stored": 2}

    def search(self, **kwargs):
        self.calls.append(("search", kwargs))
        return {"results": []}


class FakePlane:
    def __init__(self):
        self.memory = FakeMemory()


class AgenticPlaneMemoryTests(unittest.TestCase):
    def test_store_delegates_directly(self):
        plane = FakePlane()
        result = AgenticPlaneMemory(plane).store(metadata={"document_id": "x"})
        self.assertEqual(result, {"memory_id": "mem-1"})
        self.assertEqual(plane.memory.calls[0], ("store", {"metadata": {"document_id": "x"}}))

    def test_store_batch_delegates_directly(self):
        plane = FakePlane()
        AgenticPlaneMemory(plane).store_batch(items=[{"content": "a"}, {"content": "b"}])
        self.assertEqual(plane.memory.calls[0][0], "store_batch")

    def test_search_delegates_directly(self):
        plane = FakePlane()
        result = AgenticPlaneMemory(plane).search(query="delivery SLA", limit=5)
        self.assertEqual(result, {"results": []})
        self.assertEqual(
            plane.memory.calls[0],
            ("search", {"query": "delivery SLA", "limit": 5}),
        )
