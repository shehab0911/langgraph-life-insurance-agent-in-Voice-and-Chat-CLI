# backend/langgraph_agent.py
import os
import json
from typing import Annotated, Dict, Any, List
from typing_extensions import TypedDict
from dotenv import load_dotenv

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langchain_openai import ChatOpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Set OPENAI_API_KEY in environment")

KB_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge_base.json")

def load_kb() -> Dict[str, Any]:
    try:
        with open(KB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

KB = load_kb()

def query_kb(query: str) -> str:
    q = query.lower()
    out = []
    if "term" in q: out.append(KB.get("policy_types", {}).get("term_life", ""))
    if "whole" in q: out.append(KB.get("policy_types", {}).get("whole_life", ""))
    if "claim" in q or "file" in q:
        out.append(KB.get("claims", {}).get("how_to_file", ""))
        out.append(KB.get("claims", {}).get("required_docs", ""))
    if "eligib" in q: out.append(KB.get("eligibility", {}).get("general", ""))
    if "benefit" in q: out.append(KB.get("benefits", {}).get("general", ""))
    return " ".join([s for s in out if s])

# --- 🏎️ SPEED CONFIGURATION ---

llm = ChatOpenAI(
    model="gpt-4o-mini", 
    temperature=0.0, 
    # We give it 150 space so it never cuts off mid-sentence...
    max_tokens=150,
    api_key=OPENAI_API_KEY
)

# ...But we ORDER it to only use about 30-50 tokens.
SYSTEM_PROMPT = (
    "You are a lightning-fast life insurance assistant. "
    "Answer in exactly 1 or 2 short sentences. "  # <--- FORCES SPEED (0.5s generation)
    "Do not use lists or bullet points. "         # <--- PREVENTS LONG ANSWERS
    "Be direct and conversational."
)

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    kb_snippet: str

async def retrieve_knowledge_node(state: AgentState) -> dict:
    last_message = state["messages"][-1]
    kb_text = query_kb(last_message.content)
    return {"kb_snippet": kb_text}

async def call_llm_node(state: AgentState) -> dict:
    kb_text = state.get("kb_snippet", "")
    sys_msg = SYSTEM_PROMPT
    if kb_text:
        sys_msg += f" Context: {kb_text}"
    
    messages = [SystemMessage(content=sys_msg)] + state["messages"]
    response = await llm.ainvoke(messages)
    return {"messages": [response]}

workflow = StateGraph(AgentState)
workflow.add_node("retrieve_knowledge", retrieve_knowledge_node)
workflow.add_node("call_llm", call_llm_node)

workflow.set_entry_point("retrieve_knowledge")
workflow.add_edge("retrieve_knowledge", "call_llm")
workflow.add_edge("call_llm", END)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "chat_history.db")

async def run_agent(user_text: str, session_id: str) -> str:
    async with AsyncSqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        app = workflow.compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": session_id}}
        inputs = {"messages": [HumanMessage(content=user_text)]}
        final_state = await app.ainvoke(inputs, config=config)
        return final_state["messages"][-1].content