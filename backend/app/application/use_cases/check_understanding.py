"""Run the three-level understanding check."""

from app.agents.orchestrator import AgentService


def execute(service: AgentService, **kwargs):
    return service.check(**kwargs)
