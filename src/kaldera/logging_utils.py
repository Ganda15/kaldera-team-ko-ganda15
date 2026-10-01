"""Journalisation des actions des agents."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import TeamState


def record(state: "TeamState", agent_id: str, message: str) -> dict:
    step = state.current_step()
    entry = {"agent_id": agent_id, "step": step.value if step else None, "message": message}
    state.log.append(entry)
    return entry
