from fastapi.testclient import TestClient

from api.app import app


def test_browser_session_issues_bound_token_and_authenticated_websocket():
    with TestClient(app) as client:
        created = client.post("/browser/sessions")
        assert created.status_code == 200
        payload = created.json()
        assert payload["session_id"]
        assert payload["token"].startswith("bs1.")
        assert payload["owner"] == "agent"
        assert payload["control_state"] == "AGENT_CONTROL"
        assert client.cookies.get("nisr_browser_user")

        with client.websocket_connect(
            payload["websocket_path"],
            subprotocols=["nisr-browser", payload["token"]],
        ) as websocket:
            event = websocket.receive_json()
            assert event["type"] == "browser.session_ready"
            assert event["session_id"] == payload["session_id"]


def test_browser_http_access_rejects_invalid_or_cross_session_token_before_runtime_use():
    with TestClient(app) as client:
        first = client.post("/browser/sessions").json()
        second = client.post("/browser/sessions").json()

        invalid = client.get(
            f"/browser/sessions/{first['session_id']}",
            headers={"x-nisr-browser-token": "invalid"},
        )
        assert invalid.status_code == 403

        cross_session = client.get(
            f"/browser/sessions/{second['session_id']}",
            headers={"x-nisr-browser-token": first["token"]},
        )
        assert cross_session.status_code == 403
