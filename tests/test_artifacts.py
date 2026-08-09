from super_agent.core.artifacts import ArtifactManager

def test_artifact_manager(tmp_path):
    m=ArtifactManager(tmp_path/'artifacts'); rec=m.write_text('x.txt','hello'); assert rec['size']==5; assert m.read_text('x.txt')=='hello'; assert m.list()[0]['name']=='x.txt'
