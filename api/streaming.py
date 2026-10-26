from __future__ import annotations

import json
from typing import Any, Iterator

from agent.answering import INSUFFICIENT_CONTEXT_MARKER

ANSWER_NODE = "generate_answer"


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class MarkerGate:
    """Holds streamed tokens back while they could still be the INSUFFICIENT_CONTEXT marker."""

    def __init__(self, marker: str = INSUFFICIENT_CONTEXT_MARKER) -> None:
        self._marker = marker
        self._buffer = ""
        self._open = False

    def feed(self, text: str) -> str:
        if self._open:
            return text
        self._buffer += text
        candidate = self._buffer.lstrip()
        if self._marker.startswith(candidate) or candidate.startswith(self._marker):
            return ""
        self._open = True
        released, self._buffer = self._buffer, ""
        return released


def stream_agent(graph: Any, state: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Runs the graph and yields (event, payload) pairs: status updates, answer tokens,
    and a final "done" payload with the full result."""
    result = dict(state)
    gate = MarkerGate()

    for mode, chunk in graph.stream(state, stream_mode=["updates", "messages"]):
        if mode == "messages":
            message, metadata = chunk
            content = getattr(message, "content", "")
            if metadata.get("langgraph_node") == ANSWER_NODE and isinstance(content, str) and content:
                released = gate.feed(content)
                if released:
                    yield "token", {"text": released}
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
            return {"stage": "not_found", "label": "Couldn't find this in the HR documents"}
        return {"stage": "checking", "label": "Checking these sections for an answer"}

    if node == ANSWER_NODE and update.get("answer_declined"):
        return {"stage": "not_found", "label": "Couldn't find this in the HR documents"}

    return None
