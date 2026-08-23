"""Generate and record a recovery action."""

from app.agents.orchestrator import AgentService


def execute(service: AgentService, **kwargs):
    return service.recover(**kwargs)
