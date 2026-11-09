from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from agentic_chatbot.graph.workflow import build_chatbot
from agentic_chatbot.tools import calculator


class StubLLM:
    def __init__(self):
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1

        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "calculator",
                        "args": {"expression": "2+2"},
                        "id": "call-1",
                    }
                ],
            )

        return AIMessage(content="The answer is 4.")


def test_tool_loop_executes_tool_and_returns_final_answer():
    graph = build_chatbot(StubLLM(), InMemorySaver(), [calculator])

    result = graph.invoke(
        {"messages": [HumanMessage(content="what is 2+2?")]},
        config={"configurable": {"thread_id": "thread-1"}},
    )

    messages = result["messages"]
    tool_messages = [message for message in messages if isinstance(message, ToolMessage)]

    assert len(tool_messages) == 1
    assert tool_messages[0].name == "calculator"
    assert tool_messages[0].content == "4"
    assert messages[-1].content == "The answer is 4."
    assert not messages[-1].tool_calls


def test_graph_without_tools_has_no_tool_node():
    graph = build_chatbot(StubLLM(), InMemorySaver())

    nodes = set(graph.get_graph().nodes)

    assert "chat_node" in nodes
    assert "tools" not in nodes
