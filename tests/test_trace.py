"""Tests de trace : rejouer un scénario et vérifier qui a fait quoi, dans quel ordre, combien de fois."""
import json
from pathlib import Path

import pytest

from kaldera.runner import run_scenario
from kaldera.state import TeamState
from kaldera.steps import Step

SCENARIOS = json.loads(
    (Path(__file__).resolve().parents[1] / "scenarios" / "scenarios_test.json").read_text(
        encoding="utf-8"
    )
)["scenarios"]

# Responsable de chaque étape, recopié de specs/flow_spec.md (l. 17-20), pas du code.
SPEC_OWNER = {
    "RESEARCH": "researcher",
    "DRAFT": "writer",
    "REVIEW": "reviewer",
    "FINALIZE": "finalizer",
}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_trace_matches_spec(scenario):
    steps = scenario["initial_context"]["required_steps"]
    state = run_scenario(scenario)

    owners = [entry.get("agent_id") for entry in state.log]
    assert owners == [SPEC_OWNER[s] for s in steps]  # bon ordre, bon agent (S1, S3)
    assert state.step_count == len(steps)  # un passage par étape, pas de boucle (S2)
    assert state.status == "done"
    assert "final" in state.artifacts  # pas de faux succès (S4)


class _StuckAgent:
    """Agent qui ne fait jamais avancer l'état."""

    name = "researcher"

    def run(self, state: TeamState) -> None:
        return


def test_stuck_agent_aborts_on_first_non_progress():
    state = TeamState(topic="x", required_steps=[Step.RESEARCH])
    result = run_scenario({}, agents_by_name={"researcher": _StuckAgent()}, initial_state=state)

    assert result.status == "aborted"
    assert result.step_count <= 1  # arrêt au premier tour sans progrès, pas après 50
