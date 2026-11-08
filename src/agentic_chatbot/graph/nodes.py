"""LangGraph node implementations."""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from agentic_chatbot.graph.state import ChatState


def create_chat_node(llm: BaseChatModel):
    def chat_node(state: ChatState) -> dict[str, list[BaseMessage]]:
        response = llm.invoke(state["messages"])
        return {"messages": [response]}

    return chat_node
