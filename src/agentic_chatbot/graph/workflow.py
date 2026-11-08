"""Build and compile the chat LangGraph."""

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from agentic_chatbot.graph.nodes import create_chat_node
from agentic_chatbot.graph.state import ChatState


def build_chatbot(llm: BaseChatModel, checkpointer):
    graph = StateGraph(ChatState)
    graph.add_node("chat_node", create_chat_node(llm))
    graph.add_edge(START, "chat_node")
    graph.add_edge("chat_node", END)
    return graph.compile(checkpointer=checkpointer)
