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

| Technology        | Purpose                                |
| ----------------- | -------------------------------------- |
| **Python**        | Primary programming language           |
| **LangChain**     | LLM application development            |
| **LangGraph**     | Agent and workflow orchestration       |
| **OpenAI**        | Large language models                  |
| **Pydantic**      | Structured output and data validation  |
| **python-dotenv** | Environment variable management        |
| **Streamlit**     | Optional chatbot interface             |
| **Git & GitHub**  | Version control and project management |

## 📂 Repository Structure

```text
agentic-chatbot/
│
├── README.md
├── .gitignore
├── requirements.txt
├── .env.example
│
├── chatbot/
│   ├── __init__.py
│   └── ...
│
├── tools/
│   └── ...
│
└── ...
```

_The repository structure will evolve as new concepts and functionalities are implemented._

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
- [ ] Tool calling and integration
- [ ] Agentic decision-making
- [ ] Memory management
- [ ] Advanced agentic workflows
- [ ] Additional functionalities

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

### 4. Configure environment variables

Create a `.env` file in the project root and add your OpenAI API key:

```env
OPENAI_API_KEY=your_openai_api_key
```

**Important:** Never commit your `.env` file or expose your API key. Use `.env.example` to document the required environment variables.

## ▶️ Running the Project

The execution command depends on the current implementation and project structure.

For a Python-based chatbot, you may run:

```bash
python agentic_chatbot.py
```

If a Streamlit interface is implemented later, it can be launched using:

```bash
streamlit run app.py
```

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

\<text>Ongoing — new concepts and functionalities are added as the learning journey progresses.\</text>

---

**This project is a continuous learning journey toward understanding and building practical Agentic AI systems.**
