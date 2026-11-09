"""Build and compile the chat LangGraph."""

from collections.abc import Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agentic_chatbot.graph.nodes import create_chat_node
from agentic_chatbot.graph.state import ChatState


def build_chatbot(
    llm: BaseChatModel,
    checkpointer,
    tools: Sequence[BaseTool] | None = None,
):
    graph = StateGraph(ChatState)
    graph.add_node("chat_node", create_chat_node(llm))
    graph.add_edge(START, "chat_node")

    if tools:
        graph.add_node("tools", ToolNode(list(tools)))
        graph.add_conditional_edges("chat_node", tools_condition)
        graph.add_edge("tools", "chat_node")
    else:
        graph.add_edge("chat_node", END)

    return graph.compile(checkpointer=checkpointer)
