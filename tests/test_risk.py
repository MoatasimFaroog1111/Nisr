from domain.contracts import RiskPolicy
from domain.models import RiskLevel

def test_risk_policy_blocks_catastrophic_command(): assert RiskPolicy().classify_command("rm -rf /") == RiskLevel.BLOCKED
def test_risk_policy_marks_read_command_low(): assert RiskPolicy().classify_command("python --version") == RiskLevel.LOW
def test_risk_policy_recognizes_read_only_sql(): assert RiskPolicy().classify_sql("select 1") == RiskLevel.LOW
