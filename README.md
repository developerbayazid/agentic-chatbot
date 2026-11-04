# Agentic Chatbot

A hands-on project to learn and build an **Agentic AI Chatbot** using Python, LangChain, and LangGraph.

This repository follows a practical learning series and focuses on implementing the chatbot's functionalities step by step, from basic conversational capabilities to more advanced agentic features.

The goal is to understand how an AI chatbot works internally and how different components come together to create an intelligent, interactive AI agent.

## 🎯 Project Goals

- Build an AI-powered conversational chatbot.
- Understand the fundamentals of Agentic AI.
- Explore LangChain and LangGraph in a practical project.
- Implement different chatbot functionalities step by step.
- Understand state management and conversation flow.
- Explore tool calling and external tool integration.
- Learn how an AI agent makes decisions and executes tasks.
- Gradually develop a more capable and intelligent chatbot.

## 🛠️ Tech Stack

- **Python** — Primary programming language
- **LangChain** — LLM application framework
- **LangGraph** — Agent and workflow orchestration
- **OpenAI** — Language models
- **Pydantic** — Structured output and data validation
- **python-dotenv** — Environment variable management
- **Streamlit** — Chatbot interface (if used)
- **Git & GitHub** — Version control

## 📂 Repository Structure

```text
agentic-chatbot/
│
├── README.md
├── .gitignore
├── requirements.txt
├── .env.example
│
├── app.py
│
├── chatbot/
│   ├── __init__.py
│   ├── ...
│
├── tools/
│   └── ...
│
└── ...
```

_The repository structure will evolve as new functionalities are implemented._

## 📚 Learning Progress

This project is being developed incrementally by following the video series.

### Implemented Features

- [ ] Initial chatbot setup
- [ ] Basic LLM integration
- [ ] Conversational interface
- [ ] Chat history management
- [ ] State management
- [ ] LangGraph integration
- [ ] Tool calling
- [ ] Agentic decision-making
- [ ] Memory and persistence
- [ ] Additional chatbot functionalities

_The checklist will be updated as each feature is implemented._

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

Activate on Windows:

```powershell
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_openai_api_key
```

Never commit your `.env` file or expose your API key.

## ▶️ Running the Project

The execution command will depend on the chatbot interface and project structure.

For example, if the project uses Streamlit:

```bash
streamlit run app.py
```

## 📖 Learning Resource

**YouTube Learning Series:**

[Agentic Chatbot — Complete Learning Playlist](https://www.youtube.com/playlist?list=PLkz_y24mlSJZ9SFlc9O4Q4Grli5SQDbrB)

[Current Video — Agentic Chatbot](https://www.youtube.com/watch?v=_BVsXOC46wQ)

## 💡 Learning Approach

I am following a practical, project-based learning approach:

1. Watch and understand each lesson.
2. Implement the functionality using Python.
3. Understand how each component works internally.
4. Test the chatbot with different inputs.
5. Document the implementation.
6. Gradually improve the chatbot with new capabilities.

The objective is not just to build a chatbot, but to understand the engineering concepts behind Agentic AI systems.

---

**This project is continuously evolving as I learn and implement new Agentic AI concepts.**
