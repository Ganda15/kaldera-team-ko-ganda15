"""Vérifications en direct des 4 points du brief (phase DÉVELOPPEMENT).

Chaque contrôle exécute le vrai code de l'équipe et compare le résultat à la
spécification (`specs/flow_spec.md`). Rien n'est écrit en dur dans le verdict.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from .agents.base import Agent
from .agents.reviewer import Reviewer
from .orchestrator import AGENTS, AGENTS_BY_NAME, END, STEP_TO_AGENT, build_routing_table, route
from .runner import run_scenario
from .state import TeamState
from .steps import STEP_BY_NAME, Step

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_FILE = ROOT / "scenarios" / "scenarios_test.json"

# Responsable de chaque étape selon la spec (l. 17-20), recopié de la spec et non du code.
SPEC_OWNER = {"RESEARCH": "researcher", "DRAFT": "writer", "REVIEW": "reviewer", "FINALIZE": "finalizer"}

# Les 14 tests fournis avec le dépôt (non modifiés), puis nos tests de trace.
PROVIDED_TESTS = [
    "tests/test_observability.py",
    "tests/test_orchestration.py",
    "tests/test_roles.py",
    "tests/test_runner.py",
    "tests/test_scenarios.py",
    "tests/test_steps.py",
]
TRACE_TESTS = ["tests/test_trace.py"]


def _check(label: str, ok: bool, detail: str = "") -> dict:
    return {"label": label, "ok": bool(ok), "detail": detail}


def _scenarios() -> list[dict]:
    return json.loads(SCENARIOS_FILE.read_text(encoding="utf-8"))["scenarios"]


def _owners(state: TeamState) -> list[str]:
    return [entry["agent_id"] for entry in state.log]


class _StuckWriter:
    """Panne simulée : un writer qui ne fait jamais avancer le flux."""

    name = "writer"

    def run(self, state: TeamState) -> None:
        return


def roles() -> list[dict]:
    owners: dict[str, list[str]] = {}
    for agent in AGENTS:
        for step in agent.handles:
            owners.setdefault(step.value, []).append(agent.name)
    single = {s: names for s, names in owners.items() if len(names) == 1}

    expected_refusals = sum(len(Step) - len(a.handles) for a in AGENTS)
    refusals = [(a.name, s.value) for a in AGENTS for s in Step if s not in a.handles and not a.accepts(s)]

    foreign = run_scenario(
        {}, agents_by_name={"writer": Reviewer()}, initial_state=TeamState(topic="x", required_steps=[Step.DRAFT])
    )

    class _Intruder(Agent):
        name = "intrus"
        handles = {Step.REVIEW}

    try:
        build_routing_table(AGENTS + [_Intruder()])
        duplicate = "acceptée"
    except ValueError as exc:
        duplicate = f"refusée au démarrage : {exc}"

    try:

        class _Greedy(Agent):
            def accepts(self, step):
                return True

        override = "acceptée"
    except TypeError as exc:
        override = f"refusée : {exc}"

    descriptions = {a.name: a.description for a in AGENTS}
    return [
        _check(
            "Chaque étape a un seul responsable (spec l. 27)",
            len(single) == len(Step) and all(single[s] == [SPEC_OWNER[s]] for s in single),
            ", ".join(f"{s} → {names[0]}" for s, names in sorted(single.items())),
        ),
        _check(
            "Chaque agent refuse les étapes des autres (spec l. 22)",
            len(refusals) == expected_refusals,
            f"{len(refusals)} refus sur {expected_refusals} étapes étrangères testées",
        ),
        _check(
            "Une étape étrangère confiée à un agent arrête le flux proprement",
            foreign.status == "aborted" and "ne traite pas" in (foreign.stop_reason or ""),
            f"statut {foreign.status} · raison : {foreign.stop_reason}",
        ),
        _check("Deux responsables pour une étape : bloqué au démarrage", duplicate.startswith("refusée"), duplicate),
        _check("Un sous-agent ne peut pas élargir son périmètre (accepts verrouillé)", override.startswith("refusée"), override),
        _check(
            "Quatre descriptions distinctes (pas de confusion pour un routeur LLM)",
            len(set(descriptions.values())) == len(descriptions),
            " · ".join(f"{n} : {d}" for n, d in descriptions.items()),
        ),
    ]


def orchestration() -> list[dict]:
    arbitration = {s.value: route(TeamState(required_steps=[s])) for s in Step}

    happy = next(s for s in _scenarios() if s["id"] == "happy_path")
    done = run_scenario(happy)

    registry = dict(AGENTS_BY_NAME)
    registry["writer"] = _StuckWriter()
    stuck = run_scenario(happy, agents_by_name=registry)

    budget = run_scenario(
        {"initial_context": {"topic": "x", "required_steps": list(SPEC_OWNER)}, "expected": {"max_steps": 2}}
    )

    class _Expensive(Agent):
        name = "researcher"
        handles = {Step.RESEARCH}
        token_budget = 50
        step_cost = 100

        def act(self, state, step):
            state.artifacts["research"] = "ok"

    tokens = run_scenario(
        {}, agents_by_name={"researcher": _Expensive()}, initial_state=TeamState(topic="x", required_steps=[Step.RESEARCH])
    )

    return [
        _check(
            "Arbitrage : chaque étape va à son responsable (spec l. 26)",
            arbitration == SPEC_OWNER,
            ", ".join(f"{s} → {a}" for s, a in arbitration.items()),
        ),
        _check(
            "Délégation : happy_path traité par les 4 agents, dans l'ordre",
            _owners(done) == [SPEC_OWNER[s] for s in happy["initial_context"]["required_steps"]],
            " → ".join(_owners(done)),
        ),
        _check(
            "Fin de boucle : END atteint après la dernière étape (spec l. 28)",
            done.status == "done" and route(done) == END,
            f"statut {done.status} en {done.step_count} étapes",
        ),
        _check(
            "Fin de boucle : un agent bloqué est arrêté au premier tour sans progrès",
            stuck.status == "aborted" and stuck.step_count == 2,
            f"statut {stuck.status} après {stuck.step_count} tours (pas 50) · raison : {stuck.stop_reason}",
        ),
        _check(
            "Budget d'étapes jamais dépassé (spec l. 29)",
            budget.status == "aborted" and budget.step_count == 2,
            f"4 étapes demandées, budget 2 : arrêt après {budget.step_count} · raison : {budget.stop_reason}",
        ),
        _check(
            "Budget de tokens : dépassement interrompu (spec l. 33-34)",
            tokens.status == "aborted" and "budget de tokens" in (tokens.stop_reason or ""),
            f"raison : {tokens.stop_reason}",
        ),
    ]


def spec() -> list[dict]:
    checks = [
        _check(
            "Libellés de la spec reconnus : REVIEW (l'ancien PROOFREAD n'existe plus)",
            set(STEP_BY_NAME) == set(SPEC_OWNER) and "PROOFREAD" not in STEP_BY_NAME,
            ", ".join(sorted(STEP_BY_NAME)),
        )
    ]
    for scenario in _scenarios():
        state = run_scenario(scenario)
        expected = scenario["expected"]
        steps = scenario["initial_context"]["required_steps"]
        missing = [k for k in expected["artifacts"] if k not in state.artifacts]
        ok = (
            state.status == expected["final_status"]
            and state.step_count <= expected["max_steps"]
            and not missing
            and _owners(state) == [SPEC_OWNER[s] for s in steps]
            and all(e.get("agent_id") for e in state.log)
        )
        checks.append(
            _check(
                f"Scénario {scenario['id']} conforme",
                ok,
                f"statut {state.status} · {state.step_count}/{expected['max_steps']} étapes · "
                f"trace {' → '.join(_owners(state))} · artefacts {sorted(state.artifacts)}",
            )
        )
    no_final = run_scenario({"initial_context": {"topic": "x", "required_steps": ["RESEARCH", "DRAFT"]}})
    checks.append(
        _check(
            "Pas de faux succès : sans FINALIZE, le flux ne se déclare pas « done »",
            no_final.status == "aborted",
            f"statut {no_final.status} · raison : {no_final.stop_reason}",
        )
    )
    return checks


def _pytest(files: list[str]) -> tuple[bool, str]:
    missing = [f for f in files if not (ROOT / f).exists()]
    if missing:
        return False, f"fichiers de test absents de cette installation : {missing}"
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider", *files],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    lines = [l for l in out.stdout.strip().splitlines() if l.strip()]
    summary = next((l for l in reversed(lines) if re.search(r"\d+ (passed|failed)", l)), lines[-1] if lines else "")
    return out.returncode == 0, summary.strip("= ")


def regression(run: bool = True) -> tuple[list[dict], bool]:
    if not run:
        return [], True
    provided_ok, provided = _pytest(PROVIDED_TESTS)
    trace_ok, trace = _pytest(TRACE_TESTS)
    return [
        _check("Les 14 tests fournis passent, sans modification", provided_ok and "14 passed" in provided, provided),
        _check("Tests de trace (qui, dans quel ordre, combien de fois)", trace_ok, trace),
    ], False


def all_sections(run_regression: bool = True) -> list[dict]:
    regression_checks, skipped = regression(run_regression)
    return [
        {"id": "roles", "title": "1. Rôles et frontières des sous-agents",
         "brief": "clarifier les rôles et frontières des sub-agents", "checks": roles(), "skipped": False},
        {"id": "orchestration", "title": "2. Orchestration : fin de boucle, arbitrage, délégation",
         "brief": "corriger l'orchestration (fin de boucle, arbitrage, délégation)", "checks": orchestration(),
         "skipped": False},
        {"id": "spec", "title": "3. Flux réaligné sur la spécification métier",
         "brief": "réaligner le flux sur la spécification métier", "checks": spec(), "skipped": False},
        {"id": "regression", "title": "4. Non-régression sur les scénarios fournis",
         "brief": "vérifier la non-régression sur les scénarios de test fournis", "checks": regression_checks,
         "skipped": skipped},
    ]
