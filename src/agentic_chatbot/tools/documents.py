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
        """Search the ingested knowledge base of Markdown, text, and PDF files.

        Use this for questions about the user's documents, handbooks, notes, or
        specifications. Leave namespace empty to search every namespace, or pass
        one reported by list_documents. Cite the document title and source, and
        the page number for PDF results.
        """
        if not query.strip():
            return "Error: query is required."

        hits = service.search(query, namespace or None, k)

        if not hits:
            return _to_json(
                {
                    "query": query,
                    "namespace": namespace or None,
                    "count": 0,
                    "results": [],
                    "message": "No matching documents were found.",
                }
            )

        return _to_json(
            {
                "query": query,
                "namespace": namespace or None,
                "count": len(hits),
                "results": [asdict(hit) for hit in hits],
            }
        )

    @tool
    def list_documents(namespace: str = "") -> str:
        """List ingested documents and the namespaces available for search."""
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
