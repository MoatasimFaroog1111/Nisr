from adapters.storage.artifact_filesystem import FileSystemArtifactAdapter

def test_artifact_round_trip(tmp_path):
    artifacts = FileSystemArtifactAdapter(tmp_path / "artifacts")
    record = artifacts.write_text("x.txt", "hello")
    assert record["size"] == 5
    assert artifacts.read_text("x.txt") == "hello"
    assert artifacts.list()[0]["name"] == "x.txt"
