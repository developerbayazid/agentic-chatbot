import sqlite3
import uuid

from typing import TypedDict, Annotated
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import (BaseMessage, HumanMessage, AIMessage,SystemMessage)

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver


# ============================================================
# 1. Environment Setup
# ============================================================

load_dotenv()


# ============================================================
# 2. LLM Setup
# ============================================================

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
)


# ============================================================
# 3. LangGraph State
# ============================================================

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# ============================================================
# 4. Chat Node
# ============================================================

def chat_node(state: ChatState):
    messages = state["messages"]

    response = llm.invoke(messages)

    return {
        "messages": [response]
    }


# ============================================================
# 5. SQLite Database Setup
# ============================================================

db_connect = sqlite3.connect(
    "chatbot_memory.db",
    check_same_thread=False,
)

cursor = db_connect.cursor()


# Thread metadata table
cursor.execute("""
CREATE TABLE IF NOT EXISTS threads (
    thread_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New chat',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

db_connect.commit()


# ============================================================
# 6. LangGraph Checkpointer
# ============================================================

checkpointer = SqliteSaver(db_connect)

# Initialize LangGraph checkpoint tables
checkpointer.setup()


# ============================================================
# 7. Build LangGraph
# ============================================================

graph = StateGraph(ChatState)

graph.add_node("chat_node", chat_node)

graph.add_edge(START, "chat_node")
graph.add_edge("chat_node", END)

chatbot = graph.compile(
    checkpointer=checkpointer
)


# ============================================================
# 8. System Message
# ============================================================

SYSTEM_MESSAGE = SystemMessage(
    content="You are a helpful AI assistant."
)


# ============================================================
# 9. Thread Management Functions
# ============================================================

def create_thread():
    """Create a new conversation thread."""

    thread_id = str(uuid.uuid4())

    cursor.execute(
        """
        INSERT INTO threads (thread_id, title)
        VALUES (?, ?)
        """,
        (thread_id, "New chat"),
    )

    db_connect.commit()

    print("\nNew conversation created.")

    return thread_id


def get_all_threads():
    """Get all conversations from SQLite."""

    cursor.execute("""
        SELECT thread_id, title, created_at, updated_at
        FROM threads
        ORDER BY updated_at DESC, created_at DESC
    """)

    return cursor.fetchall()


def thread_exists(thread_id: str):
    """Check whether a thread exists."""

    cursor.execute(
        "SELECT 1 FROM threads WHERE thread_id = ?",
        (thread_id,),
    )

    return cursor.fetchone() is not None


def get_thread_config(thread_id: str):
    """Return LangGraph configuration for a thread."""

    return {
        "configurable": {
            "thread_id": thread_id
        }
    }


def update_thread_title(thread_id: str, title: str):
    """Update conversation title."""

    cursor.execute(
        """
        UPDATE threads
        SET title = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE thread_id = ?
        """,
        (title, thread_id),
    )

    db_connect.commit()


def update_thread_activity(thread_id: str):
    """Update last activity timestamp."""

    cursor.execute(
        """
        UPDATE threads
        SET updated_at = CURRENT_TIMESTAMP
        WHERE thread_id = ?
        """,
        (thread_id,),
    )

    db_connect.commit()


def generate_title(user_message: str):
    """Generate a ChatGPT-style conversation title."""

    try:
        response = llm.invoke([
            SystemMessage(
                content=(
                    "Generate a short and meaningful title for a "
                    "conversation based on the user's first message. "
                    "Use 3 to 6 words. "
                    "Return only the title without quotation marks "
                    "or explanation."
                )
            ),
            HumanMessage(content=user_message),
        ])

        title = response.content.strip()

        if not title:
            raise ValueError("Empty title generated.")

        return title[:100]

    except Exception as error:
        print(f"\nTitle generation failed: {error}")

        # Fallback: use the first part of the user's message
        return user_message[:50].strip() or "New chat"


def delete_thread(thread_id: str):
    """Delete a thread and its LangGraph checkpoints."""

    if not thread_exists(thread_id):
        print("\nThread not found.")
        return False

    try:
        # Delete LangGraph checkpoint data
        checkpointer.delete_thread(thread_id)

        # Delete thread metadata
        cursor.execute(
            "DELETE FROM threads WHERE thread_id = ?",
            (thread_id,),
        )

        db_connect.commit()

        print("\nThread deleted successfully.")

        return True

    except Exception as error:
        db_connect.rollback()

        print(f"\nFailed to delete thread: {error}")

        return False


# ============================================================
# 10. Display Functions
# ============================================================

def show_threads(current_thread_id: str):
    """Display all available conversations."""

    threads = get_all_threads()

    if not threads:
        print("\nNo conversations found.")
        return

    print("\n========== YOUR CONVERSATIONS ==========")

    for index, thread in enumerate(threads, start=1):

        thread_id, title, created_at, updated_at = thread

        active = (
            "  <-- Active"
            if thread_id == current_thread_id
            else ""
        )

        print(f"\n{index}. {title}{active}")
        print(f"   Thread ID: {thread_id}")
        print(f"   Updated: {updated_at}")

    print("\n========================================")


def show_history(thread_id: str):
    """Display conversation history."""

    if not thread_exists(thread_id):
        print("\nThread not found.")
        return

    config = get_thread_config(thread_id)

    state = chatbot.get_state(config)

    messages = state.values.get("messages", [])

    if not messages:
        print("\nNo conversation history found.")
        return

    print("\n========== CONVERSATION HISTORY ==========")

    for message in messages:

        if isinstance(message, HumanMessage):
            role = "You"

        elif isinstance(message, AIMessage):
            role = "Assistant"

        elif isinstance(message, SystemMessage):
            continue

        else:
            role = message.type.capitalize()

        content = message.content

        if isinstance(content, str):
            print(f"\n{role}: {content}")

        else:
            print(f"\n{role}: {content}")

    print("\n==========================================")


def show_help():
    """Display available CLI commands."""

    print("""
        ========== AVAILABLE COMMANDS ==========

        /new       - Create a new conversation
        /threads   - Show all conversations
        /switch    - Switch conversation
        /history   - Show current conversation history
        /rename    - Rename current conversation
        /delete    - Delete a conversation
        /help      - Show available commands
        /exit      - Exit chatbot

        =======================================
    """)


# ============================================================
# 11. Conversation Functions
# ============================================================

def process_message(
    user_message: str,
    thread_id: str,
):
    """Process user message and stream the AI response."""

    config = get_thread_config(thread_id)

    # Check whether this is the first message in the thread
    state = chatbot.get_state(config)

    existing_messages = state.values.get("messages", [])

    is_first_message = len(existing_messages) == 0

    # Prepare messages
    new_messages = []

    if is_first_message:
        new_messages.append(SYSTEM_MESSAGE)

    new_messages.append(
        HumanMessage(content=user_message)
    )

    print("\nAssistant: ", end="", flush=True)

    # Stream LLM response
    try:
        for chunk in chatbot.stream(
            {"messages": new_messages},
            config=config,
            stream_mode="messages",
            version="v2",
        ):

            if chunk["type"] != "messages":
                continue

            message_chunk, metadata = chunk["data"]

            if isinstance(message_chunk.content, str):
                print(
                    message_chunk.content,
                    end="",
                    flush=True,
                )

        print("\n")

    except Exception as error:
        print(f"\n\nError while generating response: {error}")
        return

    # Generate title after the first successful conversation turn
    if is_first_message:

        print("Generating conversation title...")

        title = generate_title(user_message)

        update_thread_title(
            thread_id,
            title,
        )

        print(f"Conversation title: {title}")

    else:
        update_thread_activity(thread_id)


# ============================================================
# 12. Main CLI Application
# ============================================================

def main():

    # Restore the most recently active thread
    threads = get_all_threads()

    if threads:
        current_thread_id = threads[0][0]

        print("\nPrevious conversation restored.")

    else:
        current_thread_id = create_thread()

    print("\n======================================")
    print("       AGENTIC AI CHATBOT")
    print("======================================")

    print(f"\nActive Thread ID: {current_thread_id}")

    show_help()

    while True:

        try:
            user_input = input("\nYou: ").strip()

            if not user_input:
                continue

            # --------------------------------------------
            # Exit
            # --------------------------------------------

            if user_input == "/exit":
                print("\nGoodbye!")
                break

            # --------------------------------------------
            # Help
            # --------------------------------------------

            elif user_input == "/help":
                show_help()

            # --------------------------------------------
            # Create New Thread
            # --------------------------------------------

            elif user_input == "/new":
                current_thread_id = create_thread()

                print(
                    f"Active Thread ID: {current_thread_id}"
                )

            # --------------------------------------------
            # Show All Threads
            # --------------------------------------------

            elif user_input == "/threads":
                show_threads(current_thread_id)

            # --------------------------------------------
            # Switch Thread
            # --------------------------------------------

            elif user_input == "/switch":

                show_threads(current_thread_id)

                thread_id = input(
                    "\nEnter Thread ID: "
                ).strip()

                if thread_exists(thread_id):

                    current_thread_id = thread_id

                    print("\nConversation switched successfully.")

                else:
                    print("\nThread not found.")

            # --------------------------------------------
            # Show Conversation History
            # --------------------------------------------

            elif user_input == "/history":
                show_history(current_thread_id)

            # --------------------------------------------
            # Rename Current Thread
            # --------------------------------------------

            elif user_input == "/rename":

                new_title = input(
                    "\nEnter new conversation title: "
                ).strip()

                if new_title:

                    update_thread_title(
                        current_thread_id,
                        new_title[:100],
                    )

                    print("\nConversation renamed successfully.")

                else:
                    print("\nTitle cannot be empty.")

            # --------------------------------------------
            # Delete Thread
            # --------------------------------------------

            elif user_input == "/delete":

                show_threads(current_thread_id)

                thread_id = input(
                    "\nEnter Thread ID to delete: "
                ).strip()

                if not thread_exists(thread_id):
                    print("\nThread not found.")
                    continue

                confirm = input(
                    "\nAre you sure you want to delete "
                    "this conversation? (y/n): "
                ).strip().lower()

                if confirm == "y":

                    deleted = delete_thread(thread_id)

                    if deleted and thread_id == current_thread_id:

                        current_thread_id = create_thread()

                        print(
                            "A new conversation is now active."
                        )

                else:
                    print("\nDeletion cancelled.")

            # --------------------------------------------
            # Normal Chat Message
            # --------------------------------------------

            else:

                process_message(
                    user_input,
                    current_thread_id,
                )

        except KeyboardInterrupt:
            print("\n\nUse /exit to close the chatbot.")

        except Exception as error:
            print(f"\nUnexpected error: {error}")


# ============================================================
# 13. Application Entry Point
# ============================================================

if __name__ == "__main__":

    try:
        main()

    finally:
        db_connect.close()
        print("\nDatabase connection closed.")
