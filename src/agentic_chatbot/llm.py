"""Chat model factory."""

from langchain_openai import ChatOpenAI

from agentic_chatbot.config import Settings


def create_llm(settings: Settings) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        api_key=settings.openai_api_key,
    )
