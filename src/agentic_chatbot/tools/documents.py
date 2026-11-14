"""Tools for searching the ingested document knowledge base.

Retrieval is scoped to the authenticated user. The identity arrives through the
LangGraph run config (``configurable["rag_owner_id"]``) exactly like the notes
tools; it is never an argument, so the model cannot choose whose documents it
reads.
"""

import json
from dataclasses import asdict

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from agentic_chatbot.services.document_service import (
    DocumentService,
    RetrievalError,
)


def _to_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _owner_id(config: RunnableConfig | None) -> str | None:
    if not config:
        return None

    configurable = config.get("configurable") or {}
    owner_id = configurable.get("rag_owner_id")

    return str(owner_id) if owner_id else None


def create_document_tools(service: DocumentService) -> list[BaseTool]:
    """Build the retrieval tools bound to a document service."""

    @tool
    def search_documents(
        query: str, namespace: str = "", k: int = 4, config: RunnableConfig = None
    ) -> str:
        """Search the user's ingested documents: Markdown, text, and PDF files.

        Call this when the user refers to their own documents, an uploaded or
        provided file or PDF, a handbook, or asks to search or summarize their
        documents. Also call it before answering questions about a specific
        person, the user's background, role, projects, or technologies when the
        documents may describe them — including "Who is <name>?" even when the
        question does not mention documents. Do not call it for general
        knowledge topics unrelated to the user's documents. Never use web_search
        for private personal information. namespace must be one of the values in
        the namespaces array returned by list_documents, never a document title;
        leave it empty to search every namespace. Cite the document title and
        source, and the page number for PDF results.
        """
        if not query.strip():
            return "Error: query is required."

        owner_id = _owner_id(config)
        candidate = namespace.strip()
        available = service.list_namespaces(owner_id=owner_id)

        if candidate and candidate not in available:
            return _to_json(
                {
                    "query": query,
                    "namespace": candidate,
                    "count": 0,
                    "results": [],
                    "error": "Unknown namespace.",
                    "namespaces": available,
                }
            )

        try:
            hits = service.search(query, candidate or None, k, owner_id=owner_id)
        except RetrievalError as exc:
            return _to_json(
                {
                    "query": query,
                    "namespace": candidate or None,
                    "count": 0,
                    "results": [],
                    "error": f"Retrieval failed: {exc}",
                }
            )

        if not hits:
            return _to_json(
                {
                    "query": query,
                    "namespace": candidate or None,
                    "count": 0,
                    "results": [],
                    "message": "No matching documents were found.",
                }
            )

        return _to_json(
            {
                "query": query,
                "namespace": candidate or None,
                "count": len(hits),
                "results": [asdict(hit) for hit in hits],
            }
        )

    @tool
    def list_documents(namespace: str = "", config: RunnableConfig = None) -> str:
        """List the user's ingested documents and namespaces available for search.

        Use this when you need to know which documents or namespaces exist, or
        when the user asks what documents are available.
        """
        owner_id = _owner_id(config)

        documents = service.list_documents(namespace or None, owner_id=owner_id)

        return _to_json(
            {
                "namespaces": service.list_namespaces(owner_id=owner_id),
                "count": len(documents),
                "documents": [
                    {
                        "doc_id": document.doc_id,
                        "title": document.title,
                        "source": document.source,
                        "namespace": document.namespace,
                        "size_bytes": document.size_bytes,
                        "updated_at": document.updated_at,
                    }
                    for document in documents
                ],
            }
        )

    return [search_documents, list_documents]
