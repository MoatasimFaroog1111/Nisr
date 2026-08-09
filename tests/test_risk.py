from super_agent.core.risk import RiskGate
from super_agent.models import RiskLevel


def test_risk_gate_blocks_catastrophic_command():
    gate = RiskGate()
    assert gate.classify_command("rm -rf /") == RiskLevel.BLOCKED


def test_risk_gate_marks_normal_read_command_low():
    gate = RiskGate()
    assert gate.classify_command("python --version") == RiskLevel.LOW
