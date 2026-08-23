from langgraph.graph import StateGraph, START, END

from job_matcher.state import OrchestratorState


# --- node stubs — replace each body with real logic one at a time ---

def orchestrator(state: OrchestratorState) -> dict:
    return {"job_listings": [], "expanded_keywords": [], "context_signals": ""}


def score_agent(state: OrchestratorState) -> dict:
    return {"realistic_matches": []}


def dreamer_agent(state: OrchestratorState) -> dict:
    return {"stretch_matches": []}


def merge(state: OrchestratorState) -> dict:
    return {}


# --- wiring ---

graph = StateGraph(OrchestratorState)
graph.add_node("orchestrator", orchestrator)
graph.add_node("score_agent", score_agent)
graph.add_node("dreamer_agent", dreamer_agent)
graph.add_node("merge", merge)

graph.add_edge(START, "orchestrator")
graph.add_edge("orchestrator", "score_agent")
graph.add_edge("orchestrator", "dreamer_agent")
graph.add_edge("score_agent", "merge")
graph.add_edge("dreamer_agent", "merge")
graph.add_edge("merge", END)

app = graph.compile()
