"""Application wiring: shared resources and services.

This is the single place that constructs the graph, database connection, and
services. A future FastAPI lifespan can call ``build_container`` and expose the
services through dependency injection without touching business logic.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from agentic_chatbot.config import Settings, get_settings
from agentic_chatbot.database import create_connection, init_schema
from agentic_chatbot.embeddings import create_embeddings
from agentic_chatbot.graph import build_chatbot
from agentic_chatbot.llm import create_llm
from agentic_chatbot.repository import (
    DocumentsRepository,
    NotesRepository,
    ThreadRepository,
)
from agentic_chatbot.services import (
    ChatService,
    DocumentService,
    ThreadService,
    TitleService,
)
from agentic_chatbot.tools import get_tools
from agentic_chatbot.vector_store import VectorIndexStore

RAG_HINT = (
    "\n\nWhen a question could be answered by the user's ingested documents, "
    "call search_documents first and cite the document title and source "
    "(and page number for PDFs). If nothing is found, say so instead of guessing."
)


class ChatbotContainer:
    def __init__(self, settings: Settings):
        self.settings = settings

        self.connection: sqlite3.Connection = create_connection(
            settings.database_path
        )
        init_schema(
            self.connection,
            embedding_dimensions=settings.embedding_dimensions,
        )

        self.checkpointer = SqliteSaver(self.connection)
        self.checkpointer.setup()

        self.notes_repository = NotesRepository(self.connection)
        self.embeddings = create_embeddings(settings)
        self.documents_repository = DocumentsRepository(self.connection)
        self.vector_store = VectorIndexStore(
            Path(settings.rag_index_path),
            settings.embedding_dimensions,
        )
        self.document_service = DocumentService(
            self.documents_repository,
            self.vector_store,
            self.embeddings,
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
            top_k=settings.rag_top_k,
            min_score=settings.rag_min_score,
            max_text_bytes=settings.rag_max_text_bytes,
            max_pdf_bytes=settings.rag_max_pdf_bytes,
            max_pdf_pages=settings.rag_max_pdf_pages,
        )
        self.tools = get_tools(self.notes_repository, self.document_service)
        self.llm = create_llm(settings)
        self.chat_llm = create_llm(settings, self.tools)
        self.chatbot: Any = build_chatbot(
            self.chat_llm,
            self.checkpointer,
            self.tools,
        )

        self.thread_repository = ThreadRepository(self.connection)
        self.thread_service = ThreadService(
            self.thread_repository,
            self.checkpointer,
        )
        self.title_service = TitleService(self.llm)
        self.chat_service = ChatService(
            self.chatbot,
            self.thread_service,
            self.title_service,
            settings.system_prompt + RAG_HINT,
        )

    def close(self) -> None:
        self.connection.close()


def build_container(settings: Settings | None = None) -> ChatbotContainer:
    return ChatbotContainer(settings or get_settings())
