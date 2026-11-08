"""Automatic conversation title generation."""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

_TITLE_PROMPT = (
    "Generate a short and meaningful title for a conversation based on the "
    "user's first message. Use 3 to 6 words. Return only the title without "
    "quotation marks or explanation."
)


class TitleService:
    def __init__(self, llm: BaseChatModel):
        self._llm = llm

    def generate_title(self, user_message: str) -> str:
        try:
            response = self._llm.invoke(
                [
                    SystemMessage(content=_TITLE_PROMPT),
                    HumanMessage(content=user_message),
                ]
            )

            title = response.content.strip()

            if not title:
                raise ValueError("Empty title generated.")

            return title[:100]

        except Exception:
            return user_message[:50].strip() or "New chat"
