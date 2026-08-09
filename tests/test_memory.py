from adapters.storage.memory_sqlite import SqliteMemoryAdapter

def test_memory_round_trip(tmp_path):
    memory = SqliteMemoryAdapter(tmp_path / "memory.sqlite3")
    memory.upsert("project.language", "Python")
    assert any("Python" in row for row in memory.search("Python"))
