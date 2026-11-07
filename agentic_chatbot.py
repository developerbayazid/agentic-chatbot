from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import InMemorySaver

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

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
# Configure Conversation
# ==========================================

thread_id = "conversation-1"

config = {
    "configurable": {
        "thread_id": thread_id
    }
}


# ==========================================
# Initialize System Message
# ==========================================

system_message = SystemMessage(
    content="You are a helpful assistant."
)

# Check whether this thread already has messages
existing_state = chatbot.get_state(config)

first_message = not bool(
    existing_state.values.get("messages")
)


# ==========================================
# Interactive Streaming Chat Loop
# ==========================================

print("\nChatbot started!")
print("Type 'exit', 'quit', or 'bye' to end.\n")


while True:

    user_message = input("You: ").strip()

    if user_message.lower() in ["exit", "quit", "bye"]:
        break

    if not user_message:
        continue

    try:

        # Prepare new messages
        new_messages = [
            HumanMessage(content=user_message)
        ]

        # Add system message only for a new conversation
        if first_message:
            new_messages.insert(0, system_message)
            first_message = False

        print("\nAI: ", end="", flush=True)

        # Stream LLM response
        for chunk in chatbot.stream(
            {
                "messages": new_messages
            },
            config=config,
            stream_mode="messages",
            version="v2"
        ):

            message_chunk = chunk["data"][0]
            metadata = chunk["data"][1]

            # Print only text content
            if message_chunk.content:
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
# Display Conversation History
# ==========================================

history = chatbot.get_state(config)

print("\n========== Conversation History ==========\n")

for message in history.values.get("messages", []):

    print(f"{message.type}: {message.content}")

print("\n==========================================")

print("\nConversation ended.")
