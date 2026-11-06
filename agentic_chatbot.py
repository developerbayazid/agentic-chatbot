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

# First invocation only
chatbot.invoke(
    {
        "messages": [system_message]
    },
    config=config
)


# ==========================================
# Interactive Chat Loop
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

        response = chatbot.invoke(
            {
                "messages": [
                    HumanMessage(content=user_message)
                ]
            },
            config=config
        )

        ai_response = response["messages"][-1].content

        print("\nAI:", ai_response, "\n")

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
