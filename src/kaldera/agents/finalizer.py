"""Agent de finalisation : assemble le résultat et clôt le flux."""
from __future__ import annotations

from ..state import TeamState
from ..steps import Step
from .base import Agent


class Finalizer(Agent):
    name = "finalizer"
    description = "Assemble le résultat final et clôt le traitement."
    handles = {Step.FINALIZE}

    def act(self, state: TeamState, step: Step) -> None:
        # Décision de conception : assembler le dernier artefact produit (la spec ne dit rien
        # du cas research_only, sans étape REVIEW).
        last = next(
            (state.artifacts[k] for k in ("review", "draft", "research") if k in state.artifacts), ""
        )
        state.artifacts["final"] = f"final:{last}"
        state.status = "done"
