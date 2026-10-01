"""Le chemin LangGraph suit la même orchestration que le runner."""
import json
from pathlib import Path

import pytest

pytest.importorskip("langgraph")

from kaldera.graph import run_graph  # noqa: E402
from kaldera.runner import run_scenario  # noqa: E402

SCENARIOS = json.loads(
    (Path(__file__).resolve().parents[1] / "scenarios" / "scenarios_test.json").read_text(
        encoding="utf-8"
    )
)["scenarios"]


def _trace(state):
    return [(e["agent_id"], e["step"]) for e in state.log]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_graph_matches_runner(scenario):
    by_runner = run_scenario(scenario)
    by_graph = run_graph(scenario)
    assert by_graph.status == by_runner.status == "done"
    assert _trace(by_graph) == _trace(by_runner)
    assert by_graph.step_count == by_runner.step_count


class _StuckAgent:
    name = "researcher"

    def run(self, state):
        return


def test_graph_stops_stuck_agent():
    scenario = {"initial_context": {"topic": "x", "required_steps": ["RESEARCH"]}}
    state = run_graph(scenario, agents_by_name={"researcher": _StuckAgent()})
    assert state.status == "aborted"
    assert state.step_count <= 1
