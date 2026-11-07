from typing import TypedDict, Annotated
import uuid

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import InMemorySaver

from langchain_core.messages import (BaseMessage, HumanMessage,SystemMessage)

from langchain_openai import ChatOpenAI
from dotenv import load_dotenv


# ==========================================
# Load Environment Variables
# ==========================================

load_dotenv()


# ==========================================
# Initialize LLM
# ==========================================

llm = ChatOpenAI(
    temperature=0,
    model="gpt-4o-mini",
)


# ==========================================
# Define Chat State
# ==========================================

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# ==========================================
# Define Chat Node
# ==========================================

def chat_node(state: ChatState):

    # Get conversation messages from state
    messages = state["messages"]

    # Send messages to LLM
    response = llm.invoke(messages)

    # Return AI response
    return {
        "messages": [response]
    }


# ==========================================
# Initialize Checkpointer
# ==========================================

checkpointer = InMemorySaver()


# ==========================================
# Build LangGraph
# ==========================================

graph = StateGraph(ChatState)

graph.add_node("chat_node", chat_node)

graph.add_edge(START, "chat_node")
graph.add_edge("chat_node", END)


# ==========================================
# Compile Graph
# ==========================================

chatbot = graph.compile(
    checkpointer=checkpointer
)


# ==========================================
# Multiple Thread Management
# ==========================================

SYSTEM_MESSAGE = SystemMessage(
    content="You are a helpful assistant."
)

# Store thread information for CLI display
threads = {}

# Create initial conversation
def create_thread():

    thread_id = str(uuid.uuid4())

    threads[thread_id] = {
        "name": f"Conversation {len(threads) + 1}"
    }

    return thread_id


# Get config for a specific thread
def get_thread_config(thread_id):

    return {
        "configurable": {
            "thread_id": thread_id
        }
    }


# Set initial conversation
current_thread_id = create_thread()


# ==========================================
# Thread History
# ==========================================

def show_history():

    config = get_thread_config(current_thread_id)

    history = chatbot.get_state(config)

    messages = history.values.get("messages", [])

    print("\n========== Conversation History ==========\n")

    if not messages:
        print("No conversation history yet.")

    for message in messages:
        print(f"{message.type}: {message.content}")

    print("\n==========================================\n")


# ==========================================
# Display All Threads
# ==========================================

def show_threads():

    print("\n========== Available Conversations ==========\n")

    for index, (thread_id, details) in enumerate(
        threads.items(), start=1
    ):

        active = (
            " [ACTIVE]"
            if thread_id == current_thread_id
            else ""
        )

        print(f"{index}. {details['name']}{active}")
        print(f"   Thread ID: {thread_id}\n")

    print("=============================================\n")


# ==========================================
# Interactive Chat Loop
# ==========================================

print("\nAgentic Chatbot Started!")
print("Type /help to see available commands.\n")


while True:

    user_message = input("You: ").strip()

    if not user_message:
        continue

    # --------------------------------------
    # Exit Command
    # --------------------------------------

    if user_message.lower() in ["exit", "quit", "bye", "/exit"]:
        break

    # --------------------------------------
    # Help Command
    # --------------------------------------

    if user_message.lower() == "/help":

        print("""
            Available Commands:

            /new       - Create a new conversation
            /threads   - Show all conversations
            /switch    - Switch conversation
            /history   - Show current conversation history
            /help      - Show available commands
            /exit      - Exit chatbot
            """)
        continue

    # --------------------------------------
    # Create New Thread
    # --------------------------------------

    if user_message.lower() == "/new":

        current_thread_id = create_thread()

        print("\nNew conversation created!")
        print("Thread ID:", current_thread_id, "\n")

        continue

    # --------------------------------------
    # Show All Threads
    # --------------------------------------

    if user_message.lower() == "/threads":

        show_threads()

        continue

    # --------------------------------------
    # Switch Thread
    # --------------------------------------

    if user_message.lower() == "/switch":

        show_threads()

        selected_thread = input(
            "Enter conversation number or thread ID: "
        ).strip()

        selected_thread_id = None

        # Select using conversation number
        if selected_thread.isdigit():

            thread_index = int(selected_thread) - 1

            thread_ids = list(threads.keys())

            if 0 <= thread_index < len(thread_ids):
                selected_thread_id = thread_ids[thread_index]

        # Select using thread ID
        elif selected_thread in threads:

            selected_thread_id = selected_thread

        if selected_thread_id:

            current_thread_id = selected_thread_id

            print(
                "\nSwitched to:",
                threads[current_thread_id]["name"],
                "\n"
            )

        else:

            print("\nInvalid conversation selection.\n")

        continue

    # --------------------------------------
    # Show Current Conversation History
    # --------------------------------------

    if user_message.lower() == "/history":

        show_history()

        continue

    # --------------------------------------
    # Chat Execution
    # --------------------------------------

    try:

        config = get_thread_config(current_thread_id)

        # Check current thread state
        existing_state = chatbot.get_state(config)

        messages = existing_state.values.get("messages", [])

        # Prepare new user message
        new_messages = [
            HumanMessage(content=user_message)
        ]

        # Add system message only for a new thread
        if not messages:

            new_messages.insert(0, SYSTEM_MESSAGE)

        print("\nAI: ", end="", flush=True)

        # Stream response
        for chunk in chatbot.stream(
            {
                "messages": new_messages
            },
            config=config,
            stream_mode="messages",
            version="v2"
        ):

            message_chunk, metadata = chunk["data"]

            if isinstance(message_chunk.content, str):

                print(
                    message_chunk.content,
                    end="",
                    flush=True
                )

        print("\n")

    except Exception as error:

        print(f"\nError: {error}\n")


# ==========================================
# Exit
# ==========================================

print("\nChatbot session ended.")