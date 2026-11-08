"""Interactive command-line interface.

Presentation only: this module prints to the terminal and reads input. All
conversation, thread, and persistence logic lives in the services so a future
API layer can reuse it.
"""

from agentic_chatbot.config import get_settings
from agentic_chatbot.container import ChatbotContainer, build_container
from agentic_chatbot.models import Thread
from agentic_chatbot.services.chat_service import ChatService
from agentic_chatbot.services.thread_service import ThreadService


def show_help() -> None:
    print(
        """
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
    """
    )


def show_threads(threads: list[Thread], current_thread_id: str) -> None:
    if not threads:
        print("\nNo conversations found.")
        return

    print("\n========== YOUR CONVERSATIONS ==========")

    for index, thread in enumerate(threads, start=1):
        active = "  <-- Active" if thread.thread_id == current_thread_id else ""

        print(f"\n{index}. {thread.title}{active}")
        print(f"   Thread ID: {thread.thread_id}")
        print(f"   Updated: {thread.updated_at}")

    print("\n========================================")


def show_history(thread_service: ThreadService, chat_service: ChatService, thread_id: str) -> None:
    if not thread_service.thread_exists(thread_id):
        print("\nThread not found.")
        return

    messages = chat_service.get_messages(thread_id)

    if not messages:
        print("\nNo conversation history found.")
        return

    print("\n========== CONVERSATION HISTORY ==========")

    for message in messages:
        if message.type == "human":
            role = "You"
        elif message.type == "ai":
            role = "Assistant"
        elif message.type == "system":
            continue
        else:
            role = message.type.capitalize()

        print(f"\n{role}: {message.content}")

    print("\n==========================================")


def process_message(chat_service: ChatService, thread_id: str, user_message: str) -> None:
    print("\nAssistant: ", end="", flush=True)

    title: str | None = None

    try:
        for event in chat_service.stream_turn(thread_id, user_message):
            if event.type == "token":
                print(event.content, end="", flush=True)
            elif event.type == "done":
                title = event.title

        print("\n")

    except Exception as error:
        print(f"\n\nError while generating response: {error}")
        return

    if title:
        print(f"Conversation title: {title}")


def _run_interactive(container: ChatbotContainer) -> None:
    thread_service = container.thread_service
    chat_service = container.chat_service

    threads = thread_service.list_threads()

    if threads:
        current_thread_id = threads[0].thread_id
        print("\nPrevious conversation restored.")
    else:
        current_thread_id = thread_service.create_thread().thread_id
        print("\nNew conversation created.")

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

            if user_input == "/exit":
                print("\nGoodbye!")
                break

            elif user_input == "/help":
                show_help()

            elif user_input == "/new":
                current_thread_id = thread_service.create_thread().thread_id
                print("\nNew conversation created.")
                print(f"Active Thread ID: {current_thread_id}")

            elif user_input == "/threads":
                show_threads(thread_service.list_threads(), current_thread_id)

            elif user_input == "/switch":
                show_threads(thread_service.list_threads(), current_thread_id)

                thread_id = input("\nEnter Thread ID: ").strip()

                if thread_service.thread_exists(thread_id):
                    current_thread_id = thread_id
                    print("\nConversation switched successfully.")
                else:
                    print("\nThread not found.")

            elif user_input == "/history":
                show_history(thread_service, chat_service, current_thread_id)

            elif user_input == "/rename":
                new_title = input("\nEnter new conversation title: ").strip()

                if new_title:
                    thread_service.rename_thread(current_thread_id, new_title)
                    print("\nConversation renamed successfully.")
                else:
                    print("\nTitle cannot be empty.")

            elif user_input == "/delete":
                show_threads(thread_service.list_threads(), current_thread_id)

                thread_id = input("\nEnter Thread ID to delete: ").strip()

                if not thread_service.thread_exists(thread_id):
                    print("\nThread not found.")
                    continue

                confirm = (
                    input(
                        "\nAre you sure you want to delete "
                        "this conversation? (y/n): "
                    )
                    .strip()
                    .lower()
                )

                if confirm == "y":
                    deleted = thread_service.delete_thread(thread_id)

                    if deleted and thread_id == current_thread_id:
                        current_thread_id = thread_service.create_thread().thread_id
                        print("A new conversation is now active.")
                    elif deleted:
                        print("\nThread deleted successfully.")
                else:
                    print("\nDeletion cancelled.")

            else:
                process_message(chat_service, current_thread_id, user_input)

        except KeyboardInterrupt:
            print("\n\nUse /exit to close the chatbot.")

        except Exception as error:
            print(f"\nUnexpected error: {error}")


def main() -> None:
    container = build_container(get_settings())

    try:
        _run_interactive(container)
    finally:
        container.close()
        print("\nDatabase connection closed.")


if __name__ == "__main__":
    main()
