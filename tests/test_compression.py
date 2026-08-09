from super_agent.core.compression import ContextCompressor

def test_context_compression_preserves_recent():
    c=ContextCompressor(10000,preserve_recent=2); rows=[{'tool':'x','ok':True,'output':'a'*5000} for _ in range(5)]
    out=c.compress_tool_results(rows); assert len(out)==5 and out[-1]['output']==rows[-1]['output'] and '[compressed]' in out[0]['output']
