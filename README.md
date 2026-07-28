# HR Onboarding Agent

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent-0A0D14)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Qdrant](https://img.shields.io/badge/Qdrant-FF6F61?logo=qdrant&logoColor=white)](https://qdrant.tech/)
[![Poetry](https://img.shields.io/badge/Poetry-60A5FA?logo=poetry&logoColor=white)](https://python-poetry.org/)

HR onboarding assistant for NordTech Solutions, a distributed company with offices in Tallinn, Porto, and Tampere. It helps employees find clear answers from internal policy documents, reduces repetitive HR support, and escalates uncertain or out-of-scope questions to HR.

## Architecture

Single LangGraph agent, multiple tools.

```mermaid
flowchart TD
  E[Employee] --> UI[Streamlit UI]
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
  Q[Question] --> CI[classify_intent]
  CI --> RD[retrieve_docs]
  RD --> GA[generate_answer]
  GA --> SC[score_confidence]
  SC -->|High confidence| RU[respond_to_user]
  RU --> LI[log_interaction]
  SC -->|Low confidence| EH[escalate_to_hr]
  EH --> LU[log_unanswered]
```

## Documents

The knowledge base lives in `docs/` and includes:

- Employee Handbook
- Onboarding Checklist
- IT Setup Guide
- Leave & Absence Policy
- Benefits & Perks Guide
- Expense & Reimbursement Policy
- Org Chart & Team Directory
- GDPR Employee Data Policy
- EU AI Act Compliance Summary
- HR FAQ Log

## About NordTech Solutions

NordTech Solutions is the fictional company behind this knowledge base. It operates across three offices in Tallinn, Porto, and Tampere, with policies shaped for a distributed team. The content in this repository covers the employee questions that typically come up during onboarding and day-to-day work: how to set up devices, where to request leave, what benefits are available, who to contact, and how internal policies work.

## What It Is For

This system is designed to give employees a fast, grounded way to get HR answers without forcing them to search across multiple documents or wait for manual replies. It is meant to answer routine policy questions directly, cite the right internal sources, and route edge cases to HR when the documents are incomplete or the confidence score is low.

## Tech Stack

- LangGraph for orchestration
- LangChain for document and retrieval primitives
- Qdrant for vector search
- FastAPI for the API
- Streamlit for the UI
- APScheduler for weekly digests
- SQLite and SQLAlchemy for interaction logging
