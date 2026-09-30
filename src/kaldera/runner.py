"""Boucle d'exécution d'un scénario par l'équipe."""
from __future__ import annotations

from .agents.base import BudgetExceeded, RoleViolation
from .orchestrator import END, AGENTS_BY_NAME, route
from .state import TeamState
from .steps import step_from_name

# Filet de sécurité dur : borne le nombre total d'itérations quoi qu'il arrive.
HARD_CAP = 50


def load_context(state: TeamState, scenario: dict) -> None:
    context = scenario["initial_context"]
    state.topic = context["topic"]
    state.required_steps = [step_from_name(name) for name in context["required_steps"]]


def step_budget(scenario: dict, max_iterations: int | None = None) -> int:
    limit = (
        max_iterations
        if max_iterations is not None
        else scenario.get("expected", {}).get("max_steps", HARD_CAP)
    )
    return min(limit, HARD_CAP)


def next_agent(state: TeamState, budget: int) -> str:
    """Décision du superviseur : l'agent à appeler, ou END si le flux est clos ou doit s'arrêter."""
    if state.status == "aborted":
        return END
    decision = route(state)
    if decision == END:
        # La fin est observée, pas déclarée : seul le finalizer met "done".
        if state.status != "done" or "final" not in state.artifacts:
            _abort(state, "END atteint sans résultat final")
        return END
    if state.step_count >= budget:
        _abort(state, f"budget d'étapes atteint ({budget})")
        return END
    return decision


def call_agent(state: TeamState, agent) -> None:
    """Délègue l'étape courante, puis vérifie que le flux a avancé d'une étape exactement."""
    before = state.step_index
    try:
        agent.run(state)
    except (RoleViolation, BudgetExceeded) as exc:
        state.step_count += 1
        _abort(state, str(exc))
        return
    state.step_count += 1
    if state.step_index != before + 1:
        _abort(state, f"{agent.name} n'a pas fait avancer le flux")


def run_scenario(
    scenario: dict,
    max_iterations: int | None = None,
    agents_by_name: dict | None = None,
    initial_state: TeamState | None = None,
) -> TeamState:
    state = initial_state if initial_state is not None else TeamState()
    if initial_state is None:
        load_context(state, scenario)
    registry = agents_by_name if agents_by_name is not None else AGENTS_BY_NAME
    budget = step_budget(scenario, max_iterations)
    while (decision := next_agent(state, budget)) != END:
        call_agent(state, registry[decision])
    return state


def _abort(state: TeamState, reason: str) -> None:
    state.status = "aborted"
    state.stop_reason = reason
