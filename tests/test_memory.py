from super_agent.core.memory import MemoryStore


def test_memory_round_trip(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.upsert("project.language", "Python")
    assert any("Python" in row for row in store.search("Python"))
