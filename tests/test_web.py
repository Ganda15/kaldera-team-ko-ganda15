"""API de démonstration : rejouer un scénario et lire sa trace."""
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from kaldera.web import app  # noqa: E402

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_home_page_is_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "Kaldera" in response.text


def test_lists_provided_scenarios():
    ids = [s["id"] for s in client.get("/api/scenarios").json()]
    assert ids == ["happy_path", "research_only"]


@pytest.mark.parametrize("engine", ["runner", "graph"])
def test_provided_scenario_conforms_to_spec(engine):
    if engine == "graph":
        pytest.importorskip("langgraph")
    body = client.post("/api/run", json={"scenario_id": "happy_path", "engine": engine}).json()
    assert body["status"] == "done"
    assert [e["agent_id"] for e in body["trace"]] == ["researcher", "writer", "reviewer", "finalizer"]
    assert body["checks"] and all(c["ok"] for c in body["checks"])


def test_stuck_agent_is_stopped_with_a_reason():
    body = client.post(
        "/api/run", json={"scenario_id": "happy_path", "fault": "stuck_writer"}
    ).json()
    assert body["status"] == "aborted"
    assert body["step_count"] == 2
    assert "writer" in body["stop_reason"]


def test_custom_request_respects_step_budget():
    body = client.post(
        "/api/run",
        json={"topic": "test", "required_steps": ["RESEARCH", "DRAFT", "REVIEW", "FINALIZE"], "max_steps": 2},
    ).json()
    assert body["status"] == "aborted"
    assert body["step_count"] == 2
    assert "budget" in body["stop_reason"]


def test_unknown_step_label_is_rejected():
    response = client.post("/api/run", json={"topic": "x", "required_steps": ["PROOFREAD"]})
    assert response.status_code == 422
    assert "PROOFREAD" in response.text


def test_unknown_scenario_is_404():
    assert client.post("/api/run", json={"scenario_id": "nope"}).status_code == 404
