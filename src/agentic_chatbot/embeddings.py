"""Embeddings model factory."""

from langchain_openai import OpenAIEmbeddings

from agentic_chatbot.config import Settings


def create_embeddings(
    settings: Settings,
    dimensions: int | None = None,
) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embeddings_model,
        api_key=settings.openai_api_key,
        dimensions=dimensions or settings.embedding_dimensions,
    )
