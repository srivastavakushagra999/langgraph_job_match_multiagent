from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph
from langchain_core.messages import AIMessage

from job_matcher.nodes import dreamer_agent, merge, orchestrator, score_agent
from job_matcher.state import OrchestratorState

# Loaded once at import time, before any node runs — nodes no longer call this
# per-invocation.
load_dotenv()

def route(state: OrchestratorState) -> str:
    if not state.get("chat_history"):
        return "search"
    return state["intent"]


def chat_node(state: OrchestratorState) -> dict:
    return {"chat_history": [AIMessage(content="(chat node stub)")]}


# --- wiring ---

graph = StateGraph(OrchestratorState)
graph.add_node("orchestrator", orchestrator)
graph.add_node("score_agent", score_agent)
graph.add_node("dreamer_agent", dreamer_agent)
graph.add_node("merge", merge)

graph.add_node("chat_node", chat_node)
graph.add_conditional_edges(START, route, {"search": "orchestrator", "chat": "chat_node"})
graph.add_edge("chat_node", END)
graph.add_edge("orchestrator", "score_agent")
graph.add_edge("orchestrator", "dreamer_agent")
graph.add_edge("score_agent", "merge")
graph.add_edge("dreamer_agent", "merge")
graph.add_edge("merge", END)

app = graph.compile()
