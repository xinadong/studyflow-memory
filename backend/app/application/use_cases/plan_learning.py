"""Generate or adjust a learning plan."""

from app.agents.orchestrator import AgentService


def execute(service: AgentService, **kwargs):
    return service.plan(**kwargs)
