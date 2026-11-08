"""Test doubles for the graph, services, and checkpointer."""

from types import SimpleNamespace


def message_chunk(content):
    return {"type": "messages", "data": (SimpleNamespace(content=content), {})}


class FakeChatbot:
    def __init__(self, chunks=None, messages=None, error=None):
        self.chunks = (
            list(chunks)
            if chunks is not None
            else [message_chunk("Hel"), message_chunk("lo")]
        )
        self.messages = list(messages) if messages is not None else []
        self.error = error
        self.last_config = None
        self.last_inputs = None
        self.last_stream_kwargs = None

    def get_state(self, config):
        self.last_config = config
        return SimpleNamespace(values={"messages": list(self.messages)})

    def stream(self, inputs, config, stream_mode, version):
        self.last_inputs = inputs
        self.last_stream_kwargs = {
            "config": config,
            "stream_mode": stream_mode,
            "version": version,
        }

        if self.error is not None:
            raise self.error

        for chunk in self.chunks:
            yield chunk


class FakeThreadService:
    def __init__(self, threads=None):
        self.renamed = []
        self.touched = []
        self._threads = threads if threads is not None else []

    def rename_thread(self, thread_id, title):
        self.renamed.append((thread_id, title))

    def touch_thread(self, thread_id):
        self.touched.append(thread_id)

    def list_threads(self):
        return self._threads


class FakeTitleService:
    def __init__(self, title="Generated Title", error=None):
        self.title = title
        self.error = error
        self.calls = []

    def generate_title(self, user_message):
        self.calls.append(user_message)

        if self.error is not None:
            raise self.error

        return self.title


class FakeCheckpointer:
    def __init__(self):
        self.deleted = []

    def delete_thread(self, thread_id):
        self.deleted.append(thread_id)
