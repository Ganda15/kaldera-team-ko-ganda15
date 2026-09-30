"""Classe de base des sous-agents."""
from __future__ import annotations

from .. import logging_utils
from ..state import TeamState
from ..steps import Step


class RoleViolation(RuntimeError):
    """Un agent a reçu une étape hors de son périmètre."""


class BudgetExceeded(RuntimeError):
    """Un agent a dépassé son budget de tokens."""


class Agent:
    name: str = "agent"
    description: str = ""
    handles: set[Step] = set()
    token_budget: int = 1000
    step_cost: int = 100

    def __init_subclass__(cls, **kwargs):
        # La frontière est codée une seule fois, ici : un sous-agent ne peut pas l'élargir.
        super().__init_subclass__(**kwargs)
        if "accepts" in cls.__dict__:
            raise TypeError(f"{cls.__name__} ne doit pas redéfinir accepts()")

    @property
    def system_prompt(self) -> str:
        handled = ", ".join(sorted(s.value for s in self.handles))
        return (
            f"Tu es l'agent {self.name}. Tu traites uniquement : {handled}. "
            f"Ne traite pas les étapes des autres agents."
        )

    def accepts(self, step: Step | None) -> bool:
        return step in self.handles

    def run(self, state: TeamState) -> None:
        step = state.current_step()
        if not self.accepts(step):
            raise RoleViolation(f"{self.name} ne traite pas l'étape {step}")
        used = state.agent_tokens.get(self.name, 0) + self.step_cost
        if used > self.token_budget:
            raise BudgetExceeded(f"{self.name} dépasse son budget de tokens ({used} > {self.token_budget})")
        state.agent_tokens[self.name] = used
        assert step is not None
        self.act(state, step)
        logging_utils.record(state, self.name, f"a traité {step.value}")
        state.advance()

    def act(self, state: TeamState, step: Step) -> None:
        raise NotImplementedError
