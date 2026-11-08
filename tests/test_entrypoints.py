import agentic_chatbot


def test_package_exposes_main():
    assert callable(agentic_chatbot.main)


def test_main_delegates_to_cli(monkeypatch):
    from agentic_chatbot import cli

    calls = []
    monkeypatch.setattr(cli, "main", lambda: calls.append(True))

    agentic_chatbot.main()

    assert calls == [True]
