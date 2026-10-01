"""Page de test : les vérifications des 4 points du brief (phase DÉVELOPPEMENT)."""
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from kaldera.web import app  # noqa: E402

client = TestClient(app)


def _sections(**params):
    response = client.get("/api/brief-checks", params=params)
    assert response.status_code == 200
    return {s["id"]: s for s in response.json()["sections"]}


def test_four_brief_points_are_checked():
    sections = _sections(regression="false")
    assert list(sections) == ["roles", "orchestration", "spec", "regression"]


@pytest.mark.parametrize("section_id", ["roles", "orchestration", "spec"])
def test_each_brief_point_passes(section_id):
    section = _sections(regression="false")[section_id]
    assert section["checks"], "une section sans contrôle ne prouve rien"
    assert all(c["ok"] for c in section["checks"]), [c for c in section["checks"] if not c["ok"]]


def test_regression_can_be_skipped():
    section = _sections(regression="false")["regression"]
    assert section["skipped"] is True


def test_regression_runs_the_provided_tests():
    section = _sections(regression="true")["regression"]
    assert section["skipped"] is False
    assert any("14 passed" in c["detail"] for c in section["checks"])
