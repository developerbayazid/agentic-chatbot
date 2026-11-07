# Agentic Chatbot

A hands-on project focused on learning and building an **Agentic AI Chatbot** using Python, LangChain, and LangGraph.

This repository follows a practical, project-based learning approach, implementing chatbot capabilities step by step — from basic LLM interactions and conversation management to advanced agentic workflows.

The primary goal is to understand how AI agents work internally, how their components interact, and how to build intelligent systems capable of reasoning, making decisions, and executing tasks.

## 🎯 Project Goals

- Build an AI-powered conversational chatbot.
- Understand the fundamentals of Agentic AI.
- Explore LangChain and LangGraph through practical implementation.
- Implement chatbot functionalities incrementally.
- Understand state management and conversation flow.
- Explore tool calling and external tool integration.
- Learn how AI agents make decisions and execute tasks.
- Experiment with memory, persistence, and agentic workflows.

## 🛠️ Tech Stack

| Technology        | Purpose                                           |
| ----------------- | ------------------------------------------------- |
| **Python**        | Primary programming language                      |
| **LangChain**     | LLM application development                       |
| **LangGraph**     | Agent and workflow orchestration                  |
| **OpenAI**        | Large language models                             |
| **Pydantic**      | Structured output and data validation             |
| **python-dotenv** | Environment variable management                   |
| **SQLite**        | Conversation metadata and persistent storage      |
| **Git & GitHub**  | Version control and project management            |
| **Streamlit**     | Optional chatbot interface for future development |

## 📂 Repository Structure

```text
agentic-chatbot/
│
├── README.md
├── .gitignore
├── .env.example
├── agentic_chatbot.py
├── chatbot_memory.db
│
├── tools/
│   └── ...
│
└── ...
```

_The repository structure will evolve as new concepts and functionalities are implemented._

**Note:** `chatbot_memory.db` is generated locally when the application runs. It should not be committed to GitHub.

## 📚 Learning Progress

This project is being developed incrementally through hands-on implementation.

### Implementation Checklist

- [x] Initial project setup
- [x] Basic LLM integration
- [x] Chatbot implementation
- [x] Conversation history management
- [x] State management
- [x] LangGraph integration
- [x] Checkpointing and persistence
- [x] SQLite database integration
- [x] Multiple conversation thread support
- [x] Automatic conversation title generation
- [x] Conversation history restoration
- [x] Thread switching
- [x] Thread renaming
- [x] Thread deletion
- [x] Streaming LLM responses
- [ ] Tool calling and integration
- [ ] Agentic decision-making
- [ ] Cross-thread memory management
- [ ] Advanced agentic workflows
- [ ] FastAPI backend integration
- [ ] Frontend integration

_This checklist will be updated as new features are implemented._

## ⚙️ Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/agentic-chatbot.git

cd agentic-chatbot
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate the environment on Windows:

```powershell
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Required packages include:

```bash
pip install langchain langchain-openai langgraph langgraph-checkpoint-sqlite python-dotenv
```

### 4. Configure environment variables

Create a `.env` file in the project root and add your OpenAI API key:

```env
OPENAI_API_KEY=your_openai_api_key
```

**Important:** Never commit your `.env` file or expose your API key. Use `.env.example` to document the required environment variables.

## ▶️ Running the Project

Run the chatbot using:

```bash
python agentic_chatbot.py
```

### Available CLI Commands

| Command    | Description                       |
| ---------- | --------------------------------- |
| `/new`     | Create a new conversation         |
| `/threads` | Display all conversations         |
| `/switch`  | Switch between conversations      |
| `/history` | View current conversation history |
| `/rename`  | Rename the current conversation   |
| `/delete`  | Delete a conversation             |
| `/help`    | Display available commands        |
| `/exit`    | Exit the chatbot                  |

## 💾 Conversation Persistence

The chatbot uses **LangGraph SQLite Checkpointing** to persist conversation state.

Key capabilities include:

- Save conversation history in a local SQLite database.
- Restore previous conversations after restarting the application.
- Maintain separate histories using unique thread IDs.
- Automatically generate conversation titles based on the first user message.
- Rename and delete existing conversations.
- Track conversation activity and metadata.

Each conversation is associated with a unique `thread_id`, allowing multiple independent conversations to be maintained.

## 💡 Learning Approach

I follow a practical, project-based learning process:

1. Study each concept and understand its purpose.
2. Implement the functionality using Python.
3. Explore how the underlying components work.
4. Test implementations with different inputs.
5. Document important concepts and observations.
6. Refactor and improve the implementation.
7. Gradually introduce more advanced agentic capabilities.

The objective is not simply to build a chatbot, but to understand the engineering principles behind modern Agentic AI systems.

## 🚀 Project Status

**Ongoing** — new concepts and functionalities are added as the learning journey progresses.

---

**This project is a continuous learning journey toward understanding and building practical Agentic AI systems.**
