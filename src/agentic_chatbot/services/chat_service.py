"""Chat orchestration: streaming replies, history, and state access."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.types import Command

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
        context_provider: Callable[[], str] | None = None,
    ):
        self._chatbot = chatbot
        self._thread_service = thread_service
        self._title_service = title_service
        self._system_message = SystemMessage(content=system_prompt)
        self._context_provider = context_provider

    def _system_content(self) -> str:
        """Return the system prompt plus any current knowledge-base context."""
        if self._context_provider is None:
            return self._system_message.content

        context = self._context_provider().strip()

        if not context:
            return self._system_message.content

        return f"{self._system_message.content}\n\n{context}"

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
            new_messages.append(SystemMessage(content=self._system_content()))

        new_messages.append(HumanMessage(content=user_message))

        for chunk in self._chatbot.stream(
            {"messages": new_messages},
            config=config,
            stream_mode=["messages", "updates"],
            version="v2",
        ):
            yield from self._events_from_chunk(chunk)

        if is_first_message:
            title = self._title_service.generate_title(user_message)
            self._thread_service.rename_thread(thread_id, title)
            yield TurnEvent(type="done", title=title)

        else:
            self._thread_service.touch_thread(thread_id)
            yield TurnEvent(type="done")

    def resume_turn(self, thread_id: str, decision: dict) -> Iterator[TurnEvent]:
        """Continue a graph run that paused on an approval interrupt."""
        config = self.get_config(thread_id)

        for chunk in self._chatbot.stream(
            Command(resume=decision),
            config=config,
            stream_mode=["messages", "updates"],
            version="v2",
        ):
            yield from self._events_from_chunk(chunk)

        self._thread_service.touch_thread(thread_id)
        yield TurnEvent(type="done")

    def get_pending_interrupt(self, thread_id: str) -> dict | None:
        """Return the pending interrupt for a thread, or ``None``.

        Reading graph state does not resume anything, so this is safe to call on
        startup to restore a pending approval after a process restart.
        """
        try:
            state = self._chatbot.get_state(self.get_config(thread_id))
        except Exception:  # noqa: BLE001 - an unknown thread simply has no interrupt
            return None

        for task in getattr(state, "tasks", None) or ():
            for item in getattr(task, "interrupts", None) or ():
                return {
                    "interrupt_id": getattr(item, "id", None),
                    "value": getattr(item, "value", None),
                }

        return None

    def _events_from_chunk(self, chunk: dict) -> Iterator[TurnEvent]:
        if chunk["type"] == "messages":
            message_chunk, metadata = chunk["data"]

            node = metadata.get("langgraph_node")

            if node not in (None, "chat_node"):
                return

            if isinstance(message_chunk.content, str) and message_chunk.content:
                yield TurnEvent(type="token", content=message_chunk.content)

        elif chunk["type"] == "updates":
            data = chunk.get("data") or {}

            interrupts = (
                data.get("__interrupt__") if isinstance(data, dict) else None
            )
            for item in interrupts or ():
                yield TurnEvent(
                    type="interrupt",
                    name="approval",
                    payload=getattr(item, "value", None),
                )

            for node, update in data.items():
                if node == "__interrupt__":
                    continue

                for message in (update or {}).get("messages", []):
                    if node == "chat_node":
                        for call in getattr(message, "tool_calls", None) or []:
                            yield TurnEvent(
                                type="tool_call",
                                name=call["name"],
                                content=json.dumps(call.get("args", {})),
                            )
                    elif node in {"tools", "approval"}:
                        yield TurnEvent(
                            type="tool_result",
                            name=getattr(message, "name", None),
                            content=str(message.content),
                        )
