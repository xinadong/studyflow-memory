"""Run memory/no-memory comparisons."""


def execute(service, **kwargs):
    with_memory = service.plan(
        **kwargs,
        persist_task=False,
        operation="evaluation_with_memory",
    )
    no_memory = service.plan(
        **kwargs,
        use_memory=False,
        persist_task=False,
        operation="evaluation_without_memory",
    )
    return {"with_memory": with_memory, "without_memory": no_memory}
