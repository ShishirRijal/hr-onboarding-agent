# HR Onboarding Agent

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent-0A0D14)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![Qdrant](https://img.shields.io/badge/Qdrant-FF6F61?logo=qdrant&logoColor=white)](https://qdrant.tech/)
[![Poetry](https://img.shields.io/badge/Poetry-60A5FA?logo=poetry&logoColor=white)](https://python-poetry.org/)

HR onboarding assistant for NordTech Solutions, a fictional 200-person company with offices in Tallinn, Porto, and Tampere. It is scoped to HR onboarding and policy lookup: the agent answers common employee questions from the internal corpus, reduces repetitive HR support, and escalates uncertain or out-of-scope questions to HR.

## Architecture

Single LangGraph agent, multiple tools.

The system is built as one agent with five tools:

- RAG retrieval
- confidence scoring
- HR escalation
- interaction logging
- a weekly digest job

This keeps the system bounded and easy to reason about while still covering the full workflow from question to answer or handoff.

## What This Project Is

This is a single LangGraph agent for HR onboarding and internal policy support. It answers employee questions from a fixed knowledge base, uses retrieval to stay grounded, and escalates when the system is not confident enough to answer safely.

The goal is a production-style assistant that can handle the repetitive HR questions employees ask during onboarding and day-to-day work, while preserving a human handoff for edge cases.

## Company Context

NordTech Solutions is the fictional company behind the project. It is a ~200-person tech startup with offices in Tallinn, Porto, and Tampere.

That setup is deliberate. It gives the project a realistic but bounded domain, and the three-office, EU-based structure makes the HR content naturally include leave rules, benefits, compliance, and contact routing across multiple countries.

The documents in this repo are written for that context and are meant to feel like real internal policy material, not generic demo text.

## The Five Tools

The agent is built around five tools:

1. `RAG Retrieval Tool`
   - Takes the employee's question and retrieves the most relevant chunks from the HR knowledge base.
   - The knowledge base includes the handbook, leave policy, IT setup docs, benefits material, onboarding docs, and related policy references.
   - Uses hybrid search so it can combine keyword matching and semantic retrieval instead of relying on only one method.
   - Passes the top candidates through a reranking step before the answer is generated, so the model sees the strongest evidence first.
   - Returns the retrieved chunks with source attribution and relevance scores.

2. `Confidence Scorer`
   - Scores how confident the system should be that the retrieved context is enough to answer the question safely.
   - Exists because an HR assistant that confidently guesses wrong is worse than one that escalates.
   - Uses retrieval quality and groundedness signals to decide whether the answer should be returned or handed off.
   - Produces a confidence value that drives the agent's branching logic.
   - Low confidence triggers escalation instead of a speculative response.

3. `HR Escalation Tool`
   - Activates when confidence is too low or the question needs human judgment.
   - Routes the query to a human HR contact rather than letting the model invent an answer.
   - Handles sensitive or edge-case questions such as grievances, legal ambiguity, or anything outside the policy set.
   - Formats the question and context into a structured handoff so HR can review it quickly.
   - This is the system's safety valve and the main human-in-the-loop path.

4. `Interaction Logger`
   - Logs every interaction for traceability, debugging, and later analysis.
   - Records the question, retrieved context, confidence score, whether the query escalated, and the final answer.
   - Provides an audit trail for evaluating how the system behaves over time.
   - Supports later analysis of common question patterns and unanswered topics.
   - Feeds the weekly digest workflow.

5. `Weekly Digest Job`
   - Runs independently on a schedule rather than inside the chat loop.
   - Summarizes the week's unanswered or low-confidence questions.
   - Groups recurring topics and flags documentation gaps for HR.
   - Gives the system a background automation layer, not just a request/response chat flow.
   - Demonstrates that the assistant can support ongoing knowledge maintenance, not only live answers.

This setup keeps the agent simple: one brain, a few clearly separated responsibilities, and a safe fallback path when the answer is uncertain.

```mermaid
flowchart TD
  E[Employee] --> UI[Next.js web app]
  UI --> API[FastAPI POST /chat]
  API --> AG[LangGraph Agent]

  AG --> RET[RAG Retrieval Tool]
  RET --> QD[Qdrant Vector DB]
  AG --> GEN[Generate Answer]
  GEN --> SCO[Confidence Scorer]

  SCO -->|High confidence| RESP[Respond to User]
  RESP --> LOG[Interaction Logger]

  SCO -->|Low confidence| ESC[HR Escalation Tool]
  ESC --> UN[Unanswered Log]

  SCH[APScheduler weekly job] --> UN
  SCH --> DIG[HR digest]
```

## Data Flow

```mermaid
flowchart TD
  Q[Message + recent turns] --> UM[understand_message]
  UM -->|Small talk| CH[reply_in_chat]
  UM -->|HR question| RF[resolve_filters]
  RF --> RD[retrieve_documents]
  RD --> SC[score_confidence]
  SC -->|Medium or high| GA[generate_answer]
  SC -->|Low| NF[answer_not_found]
  GA -->|Answered| RU[respond_to_user]
  GA -->|Declined| NF
  CH --> LI[log_interaction]
  RU --> LI
  NF --> LI
```

- `understand_message` sorts greetings, thanks and other small talk from HR questions, and rewrites follow-ups ("and in Finland?") into standalone questions using the last few turns of the chat.
- `resolve_filters` searches the employee's own country, unless the question names another one.
- Searches add the policies' own words for everyday ones ("vacation" also searches "annual leave"), see `retrieval/vocabulary.py`.
- `answer_not_found` asks the employee whether to send the question to HR; nothing is sent until they say yes.

## Corpus

The knowledge base lives in `corpus/` and includes:

- Employee Handbook
- Onboarding Checklist
- IT Setup Guide
- Leave & Absence Policy
- Working Hours & Payroll Policy
- Benefits & Perks Guide
- Expense & Reimbursement Policy
- Org Chart & Team Directory
- GDPR Employee Data Policy
- EU AI Act Compliance Summary

`corpus/hr_faq_log.csv` is the HR FAQ Log. It is not ingested: it is kept as a held-out evaluation set of employee questions with expected answers and source documents, including questions the corpus deliberately cannot answer (`source_doc: NONE`), which the agent should escalate.

Project documentation lives in `docs/` and is reserved for architecture notes, ingestion and retrieval design, and ADRs.

## What It Is For

This system is designed to give employees a fast, grounded way to get HR answers without forcing them to search across multiple documents or wait for manual replies. It is meant to answer routine policy questions directly, cite the right internal sources, and route edge cases to HR when the documents are incomplete or the confidence score is low.

The build order is also intentional: document ingestion comes first, then retrieval, then the agent layer, then the API and UI.

## Tech Stack

- LangGraph for orchestration
- LangChain for document and retrieval primitives
- Qdrant for vector search
- FastAPI for the API
- Next.js (React, TypeScript, Tailwind CSS) for the web app
- APScheduler for weekly digests
- SQLite and SQLAlchemy for interaction logging

## Run It Locally

Create a `.env` file from `.env.example` and set at least:

```bash
OPENAI_API_KEY=sk-...
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=nordtech_hr
```

`COHERE_API_KEY` is optional. The API runs without Cohere reranking unless `USE_COHERE_RERANK=true` (the trial key is limited to 10 calls a minute).

**1. Start Qdrant and ingest the corpus**

```bash
docker compose up -d
PYTHONPATH=. poetry run python scripts/ingest.py
```

**2. Start the API** (port 8010)

```bash
PYTHONPATH=. poetry run uvicorn api.main:app --port 8010
```

- `POST /chat/stream` answers a question as server-sent events: `status` updates while it searches, `token` events as the answer is written, then `done` with the full answer and sources
- `POST /chat` answers in one response: `{"message": "...", "session_id": "...", "employee_context": {"employee_country": "Estonia"}}`
- `POST /interactions/{interaction_id}/hr-request` records whether the employee wants an unanswered question sent to HR: `{"ask_hr": true}`
- `GET /sessions/{session_id}/messages` returns a chat's history
- `GET /sources/{chunk_id}` returns the source document of a cited chunk with the chunk's character span, so the UI can open it with that part highlighted
- `GET /health`

Every question is logged to `data/interactions.db`. Questions the documents can't answer have `answered = 0` and `escalation_status` set to `offered`, then `requested` or `declined` once the employee chooses, or `dismissed` if they ask something else without choosing; the ones sent to HR also have `escalated = 1`.

**3. Start the web app** (port 3000)

```bash
cd web
npm install
npm run dev
```

Open http://localhost:3000. The web app proxies `/api/*` to the API; set `HR_API_URL` if the API runs somewhere other than `http://localhost:8010`.

Answers stream in with their sources. When the documents don't cover a question, the assistant says so and asks whether to send it to HR; nothing goes to HR unless the employee says yes.

### Command line

Ask the agent directly, without the API or web app:

```bash
PYTHONPATH=. poetry run python scripts/ask_agent.py "How much annual leave do I get?" --employee-country Estonia --no-rerank
```

The script prints the answer, confidence, sources, and for escalated questions the reason plus the draft answer that was withheld.

### Tests

```bash
PYTHONPATH=. poetry run pytest
```
