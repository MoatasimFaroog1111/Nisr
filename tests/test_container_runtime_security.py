from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_docker_entrypoint_bootstraps_volume_then_drops_privileges():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")

    assert 'ENTRYPOINT ["/app/docker-entrypoint.sh"]' in dockerfile
    assert "apt-get install -y --no-install-recommends gosu" in dockerfile
    assert "USER nisr" not in dockerfile, "Entrypoint must start with enough privilege to repair mounted volume ownership"

    assert "prepare_runtime_dir /app/data" in entrypoint
    assert "chown -R nisr:nisr" in entrypoint
    assert 'exec gosu nisr "$@"' in entrypoint
    assert entrypoint.rstrip().endswith('exec "$@"')


def test_sqlite_runtime_paths_live_under_persistent_mount():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for variable in (
        "AGENT_MEMORY_DB=/app/data/agent_memory.sqlite3",
        "AGENT_APPROVAL_DB=/app/data/approvals.sqlite3",
        "AGENT_SESSION_DB=/app/data/sessions.sqlite3",
        "AGENT_AUDIT_LOG=/app/data/audit.jsonl",
    ):
        assert variable in dockerfile
