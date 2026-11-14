"""Tools for searching the ingested document knowledge base."""

import json
from dataclasses import asdict

from langchain_core.tools import BaseTool, tool

from agentic_chatbot.services.document_service import DocumentService


def _to_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def create_document_tools(service: DocumentService) -> list[BaseTool]:
    """Build the retrieval tools bound to a document service."""

    @tool
    def search_documents(query: str, namespace: str = "", k: int = 4) -> str:
        """Search the user's ingested documents: Markdown, text, and PDF files.

        Call this when the user refers to their own documents, an uploaded or
        provided file or PDF, a handbook, or asks to search or summarize their
        documents. Do not call it for general-knowledge questions. namespace
        must be one of the values in the namespaces array returned by
        list_documents, never a document title; leave it empty to search every
        namespace. Cite the document title and source, and the page number for
        PDF results.
        """
        if not query.strip():
            return "Error: query is required."

        candidate = namespace.strip()
        available = service.list_namespaces()

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

        hits = service.search(query, candidate or None, k)

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
    def list_documents(namespace: str = "") -> str:
        """List the user's ingested documents and namespaces available for search.

        Use this when you need to know which documents or namespaces exist, or
        when the user asks what documents are available.
        """
        documents = service.list_documents(namespace or None)

        return _to_json(
            {
                "namespaces": service.list_namespaces(),
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
