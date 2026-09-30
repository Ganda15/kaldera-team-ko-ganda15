"""Étapes métier du flux Kaldera et résolution depuis les scénarios."""
from __future__ import annotations

from enum import Enum


class Step(str, Enum):
    RESEARCH = "RESEARCH"
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    FINALIZE = "FINALIZE"


# Correspondance entre les libellés employés dans les scénarios et les membres
# de l'énumération. Dérivée de l'énumération : le vocabulaire ne peut plus dériver de la spec.
STEP_BY_NAME: dict[str, Step] = {step.value: step for step in Step}


def step_from_name(name: str) -> Step:
    return STEP_BY_NAME[name]
