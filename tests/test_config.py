import os

from agentic_chatbot.config import Settings, export_langsmith_env

LANGSMITH_KEYS = (
    "LANGSMITH_TRACING",
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
    "LANGSMITH_ENDPOINT",
)


def test_defaults_without_env(monkeypatch):
    for key in (
        "OPENAI_API_KEY",
        "DATABASE_PATH",
        "LLM_MODEL",
        "LLM_TEMPERATURE",
        "SYSTEM_PROMPT",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.openai_api_key is None
    assert settings.database_path == "chatbot_memory.db"
    assert settings.llm_model == "gpt-4o-mini"
    assert settings.llm_temperature == 0.0
    assert settings.system_prompt == "You are a helpful AI assistant."


def test_reads_environment_variables(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("DATABASE_PATH", "env.db")
    monkeypatch.setenv("LLM_MODEL", "env-model")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
    monkeypatch.setenv("SYSTEM_PROMPT", "Be brief.")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key == "env-key"
    assert settings.database_path == "env.db"
    assert settings.llm_model == "env-model"
    assert settings.llm_temperature == 0.7
    assert settings.system_prompt == "Be brief."


def test_reads_env_file(tmp_path, monkeypatch):
    for key in (
        "OPENAI_API_KEY",
        "DATABASE_PATH",
        "LLM_MODEL",
        "LLM_TEMPERATURE",
        "SYSTEM_PROMPT",
    ):
        monkeypatch.delenv(key, raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_PATH=file.db\n"
        "LLM_MODEL=file-model\n"
        "LLM_TEMPERATURE=0.3\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=str(env_file))

    assert settings.database_path == "file.db"
    assert settings.llm_model == "file-model"
    assert settings.llm_temperature == 0.3


def test_export_langsmith_env(monkeypatch):
    for key in LANGSMITH_KEYS:
        monkeypatch.delenv(key, raising=False)

    settings = Settings(
        langsmith_tracing=True,
        langsmith_api_key="ls-key",
        langsmith_project="my-project",
        langsmith_endpoint="https://example.com",
        _env_file=None,
    )

    export_langsmith_env(settings)

    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "ls-key"
    assert os.environ["LANGSMITH_PROJECT"] == "my-project"
    assert os.environ["LANGSMITH_ENDPOINT"] == "https://example.com"


def test_export_langsmith_env_does_not_override_existing(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGSMITH_PROJECT", "existing")

    settings = Settings(
        langsmith_tracing=True,
        langsmith_project="file-project",
        _env_file=None,
    )

    export_langsmith_env(settings)

    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert os.environ["LANGSMITH_PROJECT"] == "existing"


def test_explicit_arguments_override_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", "env.db")
    monkeypatch.setenv("LLM_MODEL", "env-model")

    settings = Settings(
        database_path="explicit.db",
        llm_model="explicit-model",
        _env_file=None,
    )

    assert settings.database_path == "explicit.db"
    assert settings.llm_model == "explicit-model"
