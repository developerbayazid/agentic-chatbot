"""Build and compile the chat LangGraph."""

from collections.abc import Callable, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agentic_chatbot.graph.approval import (
    create_approval_node,
    route_after_approval,
    route_after_chat,
)
from agentic_chatbot.graph.nodes import create_chat_node
from agentic_chatbot.graph.state import ChatState


def build_chatbot(
    llm: BaseChatModel,
    checkpointer,
    tools: Sequence[BaseTool] | None = None,
    *,
    sensitive_tools: dict[str, str] | None = None,
    preview_operation: Callable[[str, dict], dict] | None = None,
    record_decision: Callable[[dict, dict, str], None] | None = None,
):
    """Compile the chat graph.

    Without ``sensitive_tools`` the graph is exactly the previous
    ``chat_node``/``tools`` loop. Supplying them adds an ``approval`` node that
    calls ``interrupt()`` before the named tools execute.
    """
    graph = StateGraph(ChatState)
    graph.add_node("chat_node", create_chat_node(llm))
    graph.add_edge(START, "chat_node")

    if tools:
        tool_list = list(tools)
        graph.add_node("tools", ToolNode(tool_list))

        if sensitive_tools:
            graph.add_node(
                "approval",
                create_approval_node(
                    tool_list,
                    sensitive_tools,
                    preview_operation,
                    record_decision,
                ),
            )
            graph.add_conditional_edges(
                "chat_node",
                lambda state: route_after_chat(state, sensitive_tools),
                {"tools": "tools", "approval": "approval", "end": END},
            )
            graph.add_conditional_edges(
                "approval",
                route_after_approval,
                {"approval": "approval", "chat_node": "chat_node"},
            )
        else:
            graph.add_conditional_edges("chat_node", tools_condition)

        graph.add_edge("tools", "chat_node")
    else:
        graph.add_edge("chat_node", END)

    return graph.compile(checkpointer=checkpointer)
