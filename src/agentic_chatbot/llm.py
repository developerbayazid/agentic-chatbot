"""Chat model factory."""

from collections.abc import Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from agentic_chatbot.config import Settings


def create_llm(
    settings: Settings,
    tools: Sequence[BaseTool] | None = None,
) -> BaseChatModel | Runnable:
    llm = ChatOpenAI(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        api_key=settings.openai_api_key,
    )

    if tools:
        return llm.bind_tools(list(tools))

    return llm
