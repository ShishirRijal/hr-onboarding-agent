from __future__ import annotations

import json
from typing import Any, Iterator

CHAT_NODE = "reply_in_chat"
# Only small talk streams as it's written. Answers from the documents are checked before the
# employee sees them, so they arrive whole and the web app types them out.
STREAMED_NODES = frozenset({CHAT_NODE})
NOT_FOUND_STATUS = {"stage": "not_found", "label": "Couldn't find this in the HR documents"}


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_agent(graph: Any, state: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Runs the graph and yields (event, payload) pairs: status updates, chat tokens,
    and a final "done" payload with the full result."""
    result = dict(state)

    for mode, chunk in graph.stream(state, stream_mode=["updates", "messages"]):
        if mode == "messages":
            message, metadata = chunk
            content = getattr(message, "content", "")
            if metadata.get("langgraph_node") in STREAMED_NODES and isinstance(content, str) and content:
                yield "token", {"text": content}
            continue

        for node, update in chunk.items():
            result.update(update or {})
            status = _status_for(node, update or {})
            if status is not None:
                yield "status", status

    yield "done", result


def _status_for(node: str, update: dict[str, Any]) -> dict[str, Any] | None:
    if node == "resolve_filters":
        country = (update.get("resolved_filters") or {}).get("country")
        label = f"Searching HR documents for {country}" if country else "Searching HR documents"
        return {"stage": "searching", "label": label}

    if node == "retrieve_documents":
        chunks = update.get("retrieved_chunks") or []
        documents = list(dict.fromkeys(
            (chunk.get("metadata") or {}).get("source_doc") for chunk in chunks
        ))
        documents = [document for document in documents if document]
        if not chunks:
            return {"stage": "reading", "label": "No matching sections found", "documents": []}
        noun = "section" if len(chunks) == 1 else "sections"
        return {"stage": "reading", "label": f"Reading {len(chunks)} relevant {noun}", "documents": documents}

    if node == "score_confidence":
        if update.get("confidence_label") == "low":
            return NOT_FOUND_STATUS
        return {"stage": "writing", "label": "Writing an answer from these sections"}

    if node == "generate_answer":
        if update.get("answer_declined"):
            return NOT_FOUND_STATUS
        return {"stage": "verifying", "label": "Double-checking it against the documents"}

    if node == "check_answer":
        check = update.get("answer_check") or {}
        if update.get("answer_declined"):
            return NOT_FOUND_STATUS
        if check.get("unsupported_claims") or check.get("missing_details"):
            return {"stage": "revising", "label": "Fixing details the first draft got wrong or left out"}
        return None

    if node == "revise_answer" and update.get("answer_declined"):
        return NOT_FOUND_STATUS

    return None
