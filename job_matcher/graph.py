import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from job_matcher.nodes import chat, dreamer_agent, merge, orchestrator, persist, score_agent
from job_matcher.nodes.chat import CHAT_TOOLS
from job_matcher.state import OrchestratorState


# Loaded once at import time, before any node runs — nodes no longer call this
# per-invocation.
load_dotenv()

CHECKPOINT_DB = Path(__file__).parent / "data" / "checkpoints.sqlite"

CHECKPOINT_DB.parent.mkdir(exist_ok=True)
conn = sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)
serde = JsonPlusSerializer(allowed_msgpack_modules=[
    ("job_matcher.schemas", "Preferences"),
    ("job_matcher.schemas", "JobListing"),
    ("job_matcher.schemas", "ScoredJob"),
])


def route(state: OrchestratorState) -> str:
    if not state.get("chat_history"):
        return "search"
    return state.get("intent", "search")


# --- wiring ---

graph = StateGraph(OrchestratorState)
graph.add_node("orchestrator", orchestrator)
graph.add_node("score_agent", score_agent)
graph.add_node("dreamer_agent", dreamer_agent)
graph.add_node("merge", merge)
graph.add_node("persist", persist)

graph.add_node("chat_node", chat)
graph.add_conditional_edges(START, route, {"search": "orchestrator", "chat": "chat_node"})
graph.add_node("chat_tools", ToolNode(CHAT_TOOLS, messages_key="chat_history"))
graph.add_conditional_edges(
    "chat_node",
    lambda state: tools_condition(state, messages_key="chat_history"),
    {"tools": "chat_tools", "__end__": END},
)
graph.add_edge("chat_tools", "chat_node")
graph.add_edge("orchestrator", "score_agent")
graph.add_edge("orchestrator", "dreamer_agent")
graph.add_edge("score_agent", "merge")
graph.add_edge("dreamer_agent", "merge")
graph.add_edge("merge", "persist")
graph.add_edge("persist", END)

app = graph.compile(checkpointer=SqliteSaver(conn, serde=serde))
