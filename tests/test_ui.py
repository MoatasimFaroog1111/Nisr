from pathlib import Path

from fastapi.testclient import TestClient

from api.app import app


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"


def test_root_serves_nisr_interface():
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "Nisr" in response.text
    assert "/ui/js/app.js" in response.text


def test_gold_white_design_contract():
    css = (UI / "styles.css").read_text(encoding="utf-8")
    assert "--gold: #ffd200" in css
    assert "--page: #ffffff" in css
    assert "border-color: var(--gold)" in css


def test_components_do_not_call_backend_directly():
    components = list((UI / "js" / "components").glob("*.js"))
    assert components
    for component in components:
        source = component.read_text(encoding="utf-8")
        assert "fetch(" not in source, f"{component.name} bypasses the API client"

    api_client = (UI / "js" / "services" / "api-client.js").read_text(encoding="utf-8")
    assert "fetch(" in api_client


def test_ui_has_separate_state_and_service_layers():
    assert (UI / "js" / "state" / "store.js").is_file()
    assert (UI / "js" / "services" / "api-client.js").is_file()
    assert len(list((UI / "js" / "components").glob("*.js"))) >= 8
