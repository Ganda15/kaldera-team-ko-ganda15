"""Superviseur : routage des étapes vers les sous-agents."""
from __future__ import annotations

from .agents.finalizer import Finalizer
from .agents.researcher import Researcher
from .agents.reviewer import Reviewer
from .agents.writer import Writer
from .state import TeamState
from .steps import Step

END = "__end__"

AGENTS = [Researcher(), Writer(), Reviewer(), Finalizer()]
AGENTS_BY_NAME = {a.name: a for a in AGENTS}


def build_routing_table(agents: list) -> dict[Step, str]:
    """Table dérivée des `handles` : exactement un responsable par étape, sinon erreur au démarrage."""
    table: dict[Step, str] = {}
    for agent in agents:
        for step in agent.handles:
            if step in table:
                raise ValueError(f"{step.value} revendiquée par {table[step]} et {agent.name}")
            table[step] = agent.name
    missing = [s.value for s in Step if s not in table]
    if missing:
        raise ValueError(f"étape(s) sans responsable : {missing}")
    return table


STEP_TO_AGENT: dict[Step, str] = build_routing_table(AGENTS)


def route(state: TeamState) -> str:
    if state.step_index >= len(state.required_steps):
        return END
    current = state.required_steps[state.step_index]
    return STEP_TO_AGENT[current]
