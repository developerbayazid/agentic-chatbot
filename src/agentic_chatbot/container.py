"""Application wiring: shared resources and services.

This is the single place that constructs the graph, database connection, and
services. A future FastAPI lifespan can call ``build_container`` and expose the
services through dependency injection without touching business logic.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from agentic_chatbot.config import Settings, get_settings
from agentic_chatbot.database import create_connection, init_schema
from agentic_chatbot.graph import build_chatbot
from agentic_chatbot.llm import create_llm
from agentic_chatbot.repository import ThreadRepository
from agentic_chatbot.services import ChatService, ThreadService, TitleService


class ChatbotContainer:
    def __init__(self, settings: Settings):
        self.settings = settings

        self.connection: sqlite3.Connection = create_connection(
            settings.database_path
        )
        init_schema(self.connection)

        self.checkpointer = SqliteSaver(self.connection)
        self.checkpointer.setup()

        self.llm = create_llm(settings)
        self.chatbot: Any = build_chatbot(self.llm, self.checkpointer)

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
            settings.system_prompt,
        )

    def close(self) -> None:
        self.connection.close()


def build_container(settings: Settings | None = None) -> ChatbotContainer:
    return ChatbotContainer(settings or get_settings())
