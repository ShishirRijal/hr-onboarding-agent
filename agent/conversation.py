from __future__ import annotations

from typing import Any, Literal, Sequence

from pydantic import BaseModel, Field

from .answering import (
    DEFAULT_ANSWER_MODEL,
    _load_default_llm,
    conversation_text,
    describe_employee,
    first_name,
    history_messages,
)
from .state import ConversationTurn, EmployeeContext, MessageRoute

MESSAGE_CHAT = "chat"
MESSAGE_HR = "hr"

ROUTER_PROMPT = """You sort messages sent to NordTech Solutions' HR onboarding assistant.

kind "chat": the message is conversation rather than a request for information. Greetings, introductions, thanks, goodbyes, "how are you", reactions like "ok" or "great", questions about the assistant itself (who are you, what can you do), and requests that have nothing to do with work, like poems or general knowledge.

kind "hr": the message asks about anything to do with working at NordTech: policies, leave, pay, benefits, IT, accounts and equipment, expenses, teams, people, onboarding, rules, company facts, and the offices and office life, such as facilities, wifi, parking, lunch or the area around an office. Any message that asks for information about NordTech is "hr", even with a greeting in front: "who is the CTO?", "hi i'm new, what should I do on my first day?", "what's the wifi password?". Only pure conversation is "chat". When unsure, choose "hr".

search_query: for "hr", the question rewritten so it stands on its own, filling in anything a follow-up leaves out from the conversation so far. For example "and in Finland?" after a question about annual leave becomes "How much annual leave do employees in Finland get?". Add only details stated in the message or the conversation; never add a country, office or person that wasn't mentioned, because the search already knows where the employee works. If the message already stands on its own, copy it unchanged. For "chat", leave it empty.

follows_up: true when the message builds on the assistant's last answer: asks for more about it, refers back to it ("that", "those", "step 3", "the second one"), or asks the same thing for another country or case. False for a new topic."""

CHAT_PROMPT = """You are NordTech Solutions' HR onboarding assistant, chatting with an employee{employee}.

Be warm, friendly and brief, like a helpful colleague: one to three short sentences. Their first name is {name}: use it when greeting them and now and then after that, not in every reply.

You help with NordTech HR and onboarding: leave, pay, benefits, IT setup, expenses, offices and the first weeks at the company. You answer from NordTech's HR documents, and when they don't cover something you can pass the question to the HR team.

Don't state any NordTech policy, number, date or contact here. If they want facts, invite them to ask.
If they ask for something unrelated to working at NordTech, say kindly that you can only help with NordTech HR and onboarding, and suggest something you can help with."""


class _RouteDecision(BaseModel):
    kind: Literal["chat", "hr"]
    search_query: str = Field(default="")
    follows_up: bool = False


def route_message(
    question: str,
    history: Sequence[ConversationTurn] = (),
    *,
    summary: str = "",
    llm: Any | None = None,
    model: str = DEFAULT_ANSWER_MODEL,
) -> MessageRoute:
    """Decides whether a message is small talk or an HR question, and how to search for it."""
    router = (llm or _load_default_llm(model=model)).with_structured_output(_RouteDecision)
    conversation = conversation_text(history, summary)
    prompt = f"{conversation}\n\n" if conversation else ""
    decision = router.invoke([("system", ROUTER_PROMPT), ("human", f"{prompt}New message: {question}")])

    if decision.kind == MESSAGE_CHAT:
        return {"kind": MESSAGE_CHAT, "search_query": "", "follows_up": False}
    # A rewrite only helps a follow-up; the first question is searched exactly as asked.
    rewritten = decision.search_query.strip() if history or summary else ""
    return {
        "kind": MESSAGE_HR,
        "search_query": rewritten or question,
        "follows_up": decision.follows_up and bool(history),
    }


def generate_chat_reply(
    question: str,
    *,
    history: Sequence[ConversationTurn] = (),
    summary: str = "",
    employee_context: EmployeeContext | None = None,
    llm: Any | None = None,
    model: str = DEFAULT_ANSWER_MODEL,
) -> str:
    """A short conversational reply to small talk, without looking anything up."""
    client = llm or _load_default_llm(model=model, temperature=0.4)
    employee = describe_employee(employee_context or {})
    messages = [
        (
            "system",
            CHAT_PROMPT.format(
                employee=f" {employee}" if employee else "",
                name=first_name(employee_context or {}) or "not known",
            ),
        ),
        *history_messages(history, summary),
        ("human", question),
    ]
    response = client.invoke(messages)
    return str(getattr(response, "content", response)).strip()
