from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AnyMessage, HumanMessage

from job_matcher.prompts import CHAT_SYSTEM_PROMPT, build_chat_context
from job_matcher.state import OrchestratorState


def _from_first_human(history: list[AnyMessage]) -> list[AnyMessage]:
    """Anthropic requires the first message to be from the user, but
    chat_history starts with the orchestrator's search-run marker (an
    AIMessage). Drop everything before the first HumanMessage."""
    for i, msg in enumerate(history):
        if isinstance(msg, HumanMessage):
            return history[i:]
    return []


def chat(state: OrchestratorState) -> dict:
    llm = ChatAnthropic(model="claude-haiku-4-5-20251001")

    context = build_chat_context(
        state["preferences"],
        state["resume_text"],
        state["candidate_profile"],
        state["realistic_matches"],
        state["stretch_matches"],
        state.get("chat_summary", ""),
    )
    system = CHAT_SYSTEM_PROMPT + "\n\n" + context
    history = _from_first_human(state["chat_history"])

    response = llm.invoke([("system", system)] + history)
    return {"chat_history": [response]}
