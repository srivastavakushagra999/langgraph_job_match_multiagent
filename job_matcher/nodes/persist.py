from langchain_core.runnables import RunnableConfig

from job_matcher.memory.memory import save_run
from job_matcher.state import OrchestratorState


def persist(state: OrchestratorState, config: RunnableConfig) -> dict:
    """Writes the finished search run to memory.sqlite. Side effect only —
    the checkpoint is the source of truth for graph state, so this returns
    nothing back to it. LangGraph passes `config` because the signature
    declares it; `thread_id` lives in config, not in state."""
    thread_id = config["configurable"]["thread_id"]
    save_run(state, thread_id)
    return {}
