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

TOOL_GUIDANCE = (
    "\n\nTool selection:\n"
    "- Decide for each user message whether a tool is needed. Do not call tools "
    'for ordinary general-knowledge questions (for example "What is RAG?" or '
    '"Why use RAG?").\n'
    "- Call search_documents when the user refers to their own documents, an "
    "uploaded or provided file or PDF, a handbook, or asks to search or "
    "summarize their documents. Leave namespace empty unless you know the exact "
    "ingest namespace.\n"
    "- Treat personal identity and profile questions as document questions when "
    "the indexed knowledge base may describe the user or the person named — for "
    'example "Who is <name>?", "What does <name> do?", or questions about the '
    "user's background, role, projects, or technologies. Call search_documents "
    "before answering, even when the question does not mention documents.\n"
    "- Never use web_search for private personal information or for questions "
    "about the user; use search_documents instead.\n"
    "- If several people share a name, rely on the retrieved evidence to tell "
    "them apart. If no relevant document exists, say so or ask for clarification "
    "instead of guessing.\n"
    "- Call search_notes or list_notes when the user refers to their saved, "
    "personal notes.\n"
    "- Call calculator for arithmetic instead of computing mentally.\n"
    "- Use tool results as the source of truth for the final answer, and cite "
    "document titles and sources (plus pages for PDFs).\n"
    "- Never claim to have searched, read, or opened something unless the "
    "matching tool was called. If a tool returns an error or no relevant "
    "information, say so plainly instead of guessing."
)


def _knowledge_catalog(document_service: DocumentService) -> str:
    """Describe what is indexed so the model can judge when to retrieve."""
    documents = document_service.list_documents()

    if not documents:
        return ""

    lines = ["Indexed knowledge base (searchable with search_documents):"]

    for document in documents[:20]:
        lines.append(
            f"- {document.title} — namespace {document.namespace} "
            f"({document.source})"
        )

    if len(documents) > 20:
        lines.append(f"- ...and {len(documents) - 20} more")

    return "\n".join(lines)


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
            settings.system_prompt + TOOL_GUIDANCE,
            context_provider=lambda: _knowledge_catalog(self.document_service),
        )

    def close(self) -> None:
        self.connection.close()


def build_container(settings: Settings | None = None) -> ChatbotContainer:
    return ChatbotContainer(settings or get_settings())
