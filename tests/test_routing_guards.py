"""Garde-fous de la table de routage et de la frontière des agents."""
import pytest

from kaldera.agents.base import Agent
from kaldera.agents.finalizer import Finalizer
from kaldera.agents.researcher import Researcher
from kaldera.agents.reviewer import Reviewer
from kaldera.agents.writer import Writer
from kaldera.orchestrator import build_routing_table
from kaldera.steps import Step


class _Intruder(Agent):
    name = "intruder"
    handles = {Step.REVIEW}


def test_two_owners_for_one_step_fail_at_startup():
    with pytest.raises(ValueError, match="REVIEW"):
        build_routing_table([Researcher(), Writer(), Reviewer(), Finalizer(), _Intruder()])


def test_step_without_owner_fails_at_startup():
    with pytest.raises(ValueError, match="FINALIZE"):
        build_routing_table([Researcher(), Writer(), Reviewer()])


def test_agent_cannot_override_accepts():
    with pytest.raises(TypeError):

        class _Greedy(Agent):
            def accepts(self, step):
                return True
