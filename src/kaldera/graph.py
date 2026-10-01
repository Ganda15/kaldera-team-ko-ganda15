"""Construction du graphe d'agents (LangGraph) pour l'exécution « live ».

Le graphe réutilise la décision du superviseur (`next_agent`) et l'appel contrôlé
(`call_agent`) du runner : une seule orchestration pour les deux chemins.
"""
from __future__ import annotations

from typing import TypedDict

from .orchestrator import END, AGENTS_BY_NAME, route
from .runner import _abort, call_agent, load_context, next_agent, step_budget
from .state import TeamState


class GraphState(TypedDict):
    team: TeamState
    next: str


def build_graph(budget: int, agents_by_name: dict | None = None):
    from langgraph.graph import END as GRAPH_END
    from langgraph.graph import StateGraph

    registry = agents_by_name if agents_by_name is not None else AGENTS_BY_NAME
    graph = StateGraph(GraphState)

    def supervisor(state: GraphState) -> dict:
        return {"team": state["team"], "next": next_agent(state["team"], budget)}

    def agent_node(agent):
        def node(state: GraphState) -> dict:
            call_agent(state["team"], agent)
            return {"team": state["team"]}

        return node

    graph.add_node("supervisor", supervisor)
    for name, agent in registry.items():
        graph.add_node(name, agent_node(agent))
        graph.add_edge(name, "supervisor")  # chaque agent rend la main au superviseur

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        lambda state: state["next"],
        {**{name: name for name in registry}, END: GRAPH_END},
    )
    return graph.compile()


def run_graph(
    scenario: dict, max_iterations: int | None = None, agents_by_name: dict | None = None
) -> TeamState:
    from langgraph.errors import GraphRecursionError

    state = TeamState()
    load_context(state, scenario)
    budget = step_budget(scenario, max_iterations)
    app = build_graph(budget, agents_by_name)
    try:
        # Un tour = superviseur + agent ; +3 pour l'entrée et le dernier passage vers END.
        out = app.invoke({"team": state, "next": ""}, config={"recursion_limit": 2 * budget + 3})
    except GraphRecursionError:
        _abort(state, "recursion_limit atteint")
        return state
    return out["team"]


__all__ = ["build_graph", "run_graph", "route", "END", "TeamState"]
