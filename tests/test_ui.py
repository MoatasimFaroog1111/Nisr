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
    assert ".computer-panel" in css
    assert ".browser-viewer" in css


def test_components_do_not_call_backend_or_websocket_directly():
    components = list((UI / "js" / "components").glob("*.js"))
    assert components
    for component in components:
        source = component.read_text(encoding="utf-8")
        assert "fetch(" not in source, f"{component.name} bypasses the API client"
        assert "new WebSocket" not in source, f"{component.name} bypasses the realtime client"

    api_client = (UI / "js" / "services" / "api-client.js").read_text(encoding="utf-8")
    socket_client = (UI / "js" / "services" / "browser-socket.js").read_text(encoding="utf-8")
    assert "fetch(" in api_client
    assert "new WebSocket" in socket_client


def test_ui_has_separate_state_service_and_computer_components():
    assert (UI / "js" / "state" / "store.js").is_file()
    assert (UI / "js" / "services" / "api-client.js").is_file()
    assert (UI / "js" / "services" / "browser-socket.js").is_file()
    for name in (
        "computer-panel.js",
        "browser-viewer.js",
        "browser-controls.js",
        "browser-status.js",
        "browser-activity.js",
    ):
        assert (UI / "js" / "components" / name).is_file()


def test_private_browser_input_is_masked_and_activity_avoids_chain_of_thought():
    controls = (UI / "js" / "components" / "browser-controls.js").read_text(encoding="utf-8")
    assert 'type="password"' in controls
    assert 'autocomplete="off"' in controls
    activity = (UI / "js" / "components" / "browser-activity.js").read_text(encoding="utf-8")
    assert "chain-of-thought" in activity
