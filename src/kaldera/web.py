"""API et page de démonstration : rejouer un scénario et lire la trace de l'orchestration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .orchestrator import AGENTS_BY_NAME
from .runner import HARD_CAP, run_scenario, step_budget
from .state import TeamState
from .steps import STEP_BY_NAME

SCENARIOS_FILE = Path(__file__).resolve().parents[2] / "scenarios" / "scenarios_test.json"
PAGE_FILE = Path(__file__).resolve().parent / "static" / "index.html"

# Responsable de chaque étape selon specs/flow_spec.md (l. 17-20) : la référence des contrôles.
SPEC_OWNER = {"RESEARCH": "researcher", "DRAFT": "writer", "REVIEW": "reviewer", "FINALIZE": "finalizer"}

app = FastAPI(title="Kaldera · orchestration multi-agents", version="1.0.0")


class RunRequest(BaseModel):
    scenario_id: str | None = None
    topic: str = Field("demande libre", max_length=200)
    required_steps: list[str] = Field(default_factory=list, max_length=20)
    max_steps: int = Field(10, ge=1, le=HARD_CAP)
    engine: Literal["runner", "graph"] = "runner"
    fault: Literal["none", "stuck_writer"] = "none"


class _StuckWriter:
    """Panne simulée : un writer qui ne fait jamais avancer le flux."""

    name = "writer"

    def run(self, state: TeamState) -> None:
        return


def _load_scenarios() -> list[dict]:
    return json.loads(SCENARIOS_FILE.read_text(encoding="utf-8"))["scenarios"]


def _build_scenario(req: RunRequest) -> dict:
    if req.scenario_id is not None:
        for scenario in _load_scenarios():
            if scenario["id"] == req.scenario_id:
                return scenario
        raise HTTPException(status_code=404, detail=f"Scénario inconnu : {req.scenario_id}")
    if not req.required_steps:
        raise HTTPException(status_code=422, detail="Donner un scenario_id ou des required_steps.")
    unknown = [s for s in req.required_steps if s not in STEP_BY_NAME]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Étape(s) inconnue(s) : {unknown}. Étapes de la spec : {sorted(STEP_BY_NAME)}",
        )
    return {
        "id": "demande_libre",
        "initial_context": {"topic": req.topic, "required_steps": req.required_steps},
        "expected": {"max_steps": req.max_steps},
    }


def _checks(scenario: dict, state: TeamState, budget: int) -> list[dict]:
    steps = scenario["initial_context"]["required_steps"]
    owners = [entry["agent_id"] for entry in state.log]
    checks = [
        {"label": "Chaque étape traitée par son responsable (spec l. 17-20)",
         "ok": owners == [SPEC_OWNER[s] for s in steps[: len(owners)]]},
        {"label": f"Budget d'étapes respecté ({state.step_count} ≤ {budget})",
         "ok": state.step_count <= budget},
        {"label": "Pas de faux succès : done seulement avec l'artefact final",
         "ok": state.status != "done" or "final" in state.artifacts},
    ]
    expected = scenario["expected"]
    if "final_status" in expected:
        checks.append({"label": f"Statut attendu par le scénario : {expected['final_status']}",
                       "ok": state.status == expected["final_status"]})
        missing = [k for k in expected["artifacts"] if k not in state.artifacts]
        checks.append({"label": "Artefacts attendus présents" + (f" (manquants : {missing})" if missing else ""),
                       "ok": not missing})
    return checks


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return PAGE_FILE.read_text(encoding="utf-8")


@app.get("/api/brief-checks")
def brief_checks(regression: bool = True) -> dict:
    from .brief_checks import all_sections

    return {"sections": all_sections(regression)}


@app.get("/api/scenarios")
def scenarios() -> list[dict]:
    return _load_scenarios()


@app.post("/api/run")
def run(req: RunRequest) -> dict:
    scenario = _build_scenario(req)
    registry = dict(AGENTS_BY_NAME)
    if req.fault == "stuck_writer":
        registry["writer"] = _StuckWriter()
    if req.engine == "graph":
        from .graph import run_graph

        state = run_graph(scenario, agents_by_name=registry)
    else:
        state = run_scenario(scenario, agents_by_name=registry)
    budget = step_budget(scenario)
    return {
        "scenario": scenario["id"],
        "engine": req.engine,
        "status": state.status,
        "stop_reason": state.stop_reason,
        "step_count": state.step_count,
        "budget": budget,
        "trace": state.log,
        "artifacts": state.artifacts,
        "agent_tokens": state.agent_tokens,
        "checks": _checks(scenario, state, budget),
    }
