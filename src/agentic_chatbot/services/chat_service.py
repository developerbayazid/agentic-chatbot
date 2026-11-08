"""Chat orchestration: streaming replies, history, and state access."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agentic_chatbot.models import TurnEvent

if TYPE_CHECKING:
    from agentic_chatbot.services.thread_service import ThreadService
    from agentic_chatbot.services.title_service import TitleService


class ChatService:
    def __init__(
        self,
        chatbot: Any,
        thread_service: ThreadService,
        title_service: TitleService,
        system_prompt: str,
    ):
        self._chatbot = chatbot
        self._thread_service = thread_service
        self._title_service = title_service
        self._system_message = SystemMessage(content=system_prompt)

    def get_config(self, thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def get_messages(self, thread_id: str) -> list[BaseMessage]:
        state = self._chatbot.get_state(self.get_config(thread_id))
        return state.values.get("messages", [])

    def stream_turn(self, thread_id: str, user_message: str) -> Iterator[TurnEvent]:
        config = self.get_config(thread_id)

        is_first_message = len(self.get_messages(thread_id)) == 0

        new_messages: list[BaseMessage] = []

        if is_first_message:
            new_messages.append(self._system_message)

        new_messages.append(HumanMessage(content=user_message))

        for chunk in self._chatbot.stream(
            {"messages": new_messages},
            config=config,
            stream_mode="messages",
            version="v2",
        ):
            if chunk["type"] != "messages":
                continue

            message_chunk, _metadata = chunk["data"]

            if isinstance(message_chunk.content, str) and message_chunk.content:
                yield TurnEvent(type="token", content=message_chunk.content)

        if is_first_message:
            title = self._title_service.generate_title(user_message)
            self._thread_service.rename_thread(thread_id, title)
            yield TurnEvent(type="done", title=title)

        else:
            self._thread_service.touch_thread(thread_id)
            yield TurnEvent(type="done")
