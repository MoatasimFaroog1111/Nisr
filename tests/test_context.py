from application.execution import ContextCompressor

def test_context_compressor_preserves_recent_rows():
    compressor = ContextCompressor(10_000, preserve_recent=2)
    rows = [{"output": "a" * 5000} for _ in range(5)]
    output = compressor.compress_rows(rows)
    assert output[-1]["output"] == rows[-1]["output"]
    assert "[compressed]" in output[0]["output"]
