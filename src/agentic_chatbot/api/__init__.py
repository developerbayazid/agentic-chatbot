"""REST API presentation layer.

A second adapter over the existing services: the CLI and these routers call the
same ``ChatbotContainer``, ``ChatService``, ``ThreadService``,
``DocumentService``, and compiled LangGraph. No business logic lives here.
"""

from agentic_chatbot.api.main import create_app

__all__ = ["create_app"]
