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
   - Asks the employee first, and only sends questions they agree to; those wait in the HR inbox and reach HR in one email at the end of the day, with who asked. HR's answer goes back to the employee's chat and into the knowledge base.
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
  SC -->|Medium or high| RN[read_neighbours]
  SC -->|Low| NF[answer_not_found]
  RN --> GA[generate_answer]
  RN -.->|CORRECTIVE_SEARCH=1| GD[grade_documents]
  GD -.->|Sections answer it| GA
  GD -.->|Partly or not at all| SA[search_again]
  SA -.->|Found more| GA
  SA -.->|Still nothing relevant| NF
  GA -->|Draft| CA[check_answer]
  GA -->|Declined| NF
  CA -->|Answers, nothing to fix| RU[respond_to_user]
  CA -->|Unsupported or missing details| RA[revise_answer]
  CA -->|Doesn't really answer| NF
  RA -->|Rewritten| RU
  RA -->|Declined| NF
  CH --> LI[log_interaction]
  RU --> LI
  NF --> LI
```

- `understand_message` sorts greetings, thanks and other small talk from HR questions, and rewrites follow-ups ("and in Finland?") into standalone questions using the last few turns of the chat.
- `resolve_filters` searches the employee's own country, unless the question names another one.
- Searches add the policies' own words for everyday ones ("vacation" also searches "annual leave"), see `retrieval/vocabulary.py`.
- `read_neighbours`: documents are split into ~500-character pieces, and the condition that matters (an approver, the day a rule changes) is often in the next piece of the same section. Each found piece is read with the pieces either side of it, joined into one passage without the repeated overlap (`retrieval/context.py`). Citations still open the piece search found.
- `grade_documents` and `search_again` are corrective RAG, off unless `CORRECTIVE_SEARCH=1`. `gpt-4.1-mini` grades whether the passages answer the whole question; if not, one more search runs for what's missing, in the policies' own words, and adds the passages that help. If neither search finds anything relevant, the employee is offered HR without an answer being written. Grading never removes passages: dropping the ones graded unhelpful cost more answers than it saved. It's off by default because, on the evaluation set, it added about a second per answer without changing the results: the first search already finds the right document for every test question, and reading neighbours brings in what was missing. It's there for real employees' phrasing, which is harder than the FAQ log's.
- `check_answer` reviews each draft before the employee sees it (the critique step of Self-RAG, with `gpt-4.1`): a draft that talks around the question ("not covered", "case by case") becomes an offer to ask HR, and one with unsupported claims or a missing condition is rewritten once by `revise_answer`. Because of this, answers aren't streamed while they're written; the progress steps show the check instead.
- `respond_to_user` turns the answer's citations into numbered sources. The answer model marks each sentence or list item with the passage it came from; these are renumbered in the order the answer first uses them, and a source keeps its number every time it's cited, so the employee sees [1], [2], ... for exactly the sources used, however many there are (`agent/citations.py`). Earlier answers are given to the models without their numbers, since those point to another search's passages.
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
- SQLite and SQLAlchemy for interaction logging, accounts and sign-in sessions

## Run It Locally

Create a `.env` file from `.env.example` and set at least:

```bash
OPENAI_API_KEY=sk-...
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=nordtech_hr
```

`COHERE_API_KEY` is optional. The API runs without Cohere reranking unless `USE_COHERE_RERANK=true` (the trial key is limited to 10 calls a minute). Corrective RAG (grading the found sections and searching again) is off unless `CORRECTIVE_SEARCH=true`.

**1. Start Qdrant and Mailpit, and ingest the corpus**

```bash
docker compose up -d
PYTHONPATH=. poetry run python scripts/ingest.py
```

Mailpit catches the HR digest email locally, so nothing real is sent; its inbox is at http://localhost:8025.

**2. Start the API** (port 8010)

```bash
PYTHONPATH=. poetry run uvicorn api.main:app --port 8010
```

On first start, with no accounts in the database, the API adds the [demo accounts](#demo-accounts). `scripts/seed_users.py` does the same on demand and adds any that are missing.

Every route except `GET /health` and `POST /auth/sign-in` needs a signed-in session, and answers `401` without one.

- `POST /auth/sign-in` checks `{"email": "...", "password": "..."}` and sets the session cookie; `POST /auth/sign-out` ends the session; `GET /auth/me` returns the signed-in user's profile
- `POST /chat/stream` answers a question as server-sent events: `status` updates while it searches, `token` events as the answer is written, then `done` with the full answer and sources
- `POST /chat` answers in one response: `{"message": "...", "session_id": "..."}`. Where the employee works (country, office, department, role) comes from their account, not the request
- `POST /interactions/{interaction_id}/hr-request` records whether the employee wants an unanswered question sent to HR: `{"ask_hr": true}`
- `GET /sessions` lists the signed-in user's chats, newest first, with the number of unread HR replies in each
- `GET /sessions/{session_id}/messages` returns one of the user's chats, including HR's replies, and marks those replies as read. Other users' chats answer `404`
- `GET /sources/{chunk_id}` returns the source document of a cited chunk with the chunk's character span, so the UI can open it with that part highlighted
- `GET /health`

HR team only (`403` for employees):

- `GET /hr/overview`: open questions, questions answered this week, and the most common unanswered topics of the last 30 days
- `GET /hr/questions?status=requested|answered`: questions sent to HR, with who asked
- `GET /hr/questions/{interaction_id}`: one question with why the assistant couldn't answer, the documents it checked, and the earlier turns of the chat
- `POST /hr/questions/{interaction_id}/answer`: `{"answer": "...", "applies_to": "country" | "everyone"}` sends HR's answer to the employee and adds it to the knowledge base

Every question is logged to `data/interactions.db` with the user who asked (`user_id`). Questions the documents can't answer have `answered = 0` and `escalation_status` set to `offered`, then `requested` or `declined` once the employee chooses, or `dismissed` if they ask something else without choosing; the ones sent to HR also have `escalated = 1`, and become `answered` when HR replies from the HR inbox (`hr_answer`, `hr_answered_by`, `hr_answered_at`).

Declined and dismissed questions stay anonymous. Questions sent to HR also store who asked (`employee_name`, `employee_email`), taken from the signed-in account, so HR can reply.

**HR digest email.** Once a day at `HR_DIGEST_TIME` (default 18:00, `Europe/Tallinn`) the API emails `HR_DIGEST_TO` every question sent to HR since the last digest: the question, who asked and their email, where they work, why the assistant couldn't answer, which documents it checked, and a link to answer it in the HR inbox (`HR_INBOX_URL`). Questions HR already answered in the inbox are left out. Nothing is sent on days without new questions. Each question is marked with `hr_notified_at` once the email is accepted, so a failed send is retried next time and nothing is sent twice. SMTP settings are in `.env.example`; set `HR_DIGEST_TIME=` (empty) to turn it off. To send it now, or from cron instead:

```bash
PYTHONPATH=. poetry run python scripts/send_hr_digest.py            # send now
PYTHONPATH=. poetry run python scripts/send_hr_digest.py --dry-run  # print it, send nothing
```

**3. Start the web app** (port 3000)

```bash
cd web
npm install
npm run dev
```

Open http://localhost:3000 and sign in with one of the [demo accounts](#demo-accounts). The web app proxies `/api/*` to the API; set `HR_API_URL` if the API runs somewhere other than `http://localhost:8010`.

Answers mark their sources inline as numbers after each sentence; clicking a number opens that document beside the chat, with the part the answer used highlighted. When the documents don't cover a question, the assistant says so and asks whether to send it to HR; nothing goes to HR unless the employee says yes. HR's answer appears in that chat, and the chat is marked in the sidebar until the employee opens it. The profile page shows the employee's details as the assistant sees them.

### Sign-in

Nobody can use the app or the API without signing in. Accounts live in the same SQLite database as the interactions (`users` table), with passwords hashed with scrypt and a per-user salt. Signing in creates a row in `auth_sessions` and sets an HttpOnly, SameSite=Lax cookie holding a random token; only a hash of the token is stored, and signing out deletes the row, so the cookie stops working everywhere. Sessions last 7 days. The web app reaches the API through its own `/api` proxy, so the cookie is first-party. Set `SESSION_COOKIE_SECURE=true` when serving over HTTPS.

There are two roles: `employee` uses the chat, `hr` also has the HR platform. After signing in, HR lands in the HR inbox and employees in the chat.

### Demo accounts

All demo accounts share the password `nordtech-demo`. **It is for local demos only**: change or remove these accounts anywhere else. Everyone is fictional; all addresses use the `nordtech.test` domain.

| Role | Name | Email | Job title | Office | Started | Pronouns |
|---|---|---|---|---|---|---|
| HR | Marju Ilves | marju.ilves@nordtech.test | HR Business Partner | Tallinn, Estonia | Feb 2021 | she/her |
| Employee | Kertu Vaher | kertu.vaher@nordtech.test | Junior Backend Engineer | Tallinn, Estonia | 19 Oct 2026 | she/her |
| Employee | Joonas Laaksonen | joonas.laaksonen@nordtech.test | Senior Account Executive | Tampere, Finland | 26 Oct 2026 | he/him |
| Employee | Mariana Lopes | mariana.lopes@nordtech.test | Product Designer | Porto, Portugal | Mar 2025 | she/her |
| Employee | Alex Rinne | alex.rinne@nordtech.test | Site Reliability Engineer | Remote (employed in Finland) | Sep 2026 | they/them |
| Employee | Duarte Mendes | duarte.mendes@nordtech.test | Marketing Lead | Porto, Portugal | May 2023 | he/him |

Managers are the team leads from the org chart. The assistant uses each person's country for country-specific rules; remote work doesn't change it.

### HR platform

`/hr` is for the HR team only. The inbox lists the questions employees sent to HR, oldest first, with an overview of open questions, questions answered this week, and the most common unanswered topics (the closest document section, over the last 30 days). Each question shows who asked (name, email, job title, office), when, why the assistant couldn't answer, which documents it checked, and the earlier turns of the chat.

HR writes an answer and chooses who it applies to: employees in the asker's country, or everyone. Sending it:

1. adds the question and answer to the knowledge base as a new chunk (`source_doc: hr_answers`, `doc_type: faq_log`, `category: FAQ`, `country` set to that choice): it is embedded and written to Qdrant, and added to the running BM25 index, so the assistant can use it for similar questions straight away, without a restart
2. marks the question `answered`, with who answered and when
3. shows the answer in the employee's chat

The answered list keeps every question HR has answered. Answers cited by the assistant open in the source viewer like any other source.

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

### Evaluating answers

`scripts/eval_answers.py` runs the real agent on every question in `corpus/hr_faq_log.csv` and on the multi-turn conversations in `evaluation/conversations.yaml` (greetings, follow-ups, other countries, everyday words, off-topic, questions the documents don't cover), then checks each reply:

- **Behaviour**: answered, offered to ask HR, or chatted, as expected
- **Cited the right document** and **searched the right country**
- **Answers with citations**: how many answers mark their sources (reported, not part of passing)
- **Correctness** against the expected answer, and **grounding** (every claim backed by the sections the answer was written from), both graded by a stronger model (`gpt-4.1` by default)

```bash
PYTHONPATH=. poetry run python scripts/eval_answers.py                      # everything, about 6 minutes
PYTHONPATH=. poetry run python scripts/eval_answers.py --cases conversations --limit 3
PYTHONPATH=. poetry run python scripts/eval_answers.py --answer-model gpt-4.1-mini --out-dir data/evaluations/gpt-4.1-mini
PYTHONPATH=. poetry run python scripts/eval_answers.py --corrective-search  # with corrective RAG switched on
PYTHONPATH=. poetry run python scripts/eval_answers.py --no-judge          # free checks only
```

Each run prints a summary next to the previous run's numbers and saves a JSON and a Markdown report to `data/evaluations/`; the Markdown lists every failing turn with what was expected, what the agent said, and why it failed. Evaluation runs don't write to the interactions database.
