from agentic_chatbot.config import Settings


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
