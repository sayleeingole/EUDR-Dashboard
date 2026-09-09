"""Floating 'ask about this' chatbot, shown on every page via a chat bubble
(templates/partials/chat_widget.html). Its context is always whatever record
is currently open in the right-hand reading pane — a legal requirement's
reference law, or an evidence claim — never the pane's own content, and the
answer appears only in the floating window, never written into the pane.

Same background-thread-plus-polling shape as core.runmanager's research
runs: the UI stays responsive while Claude answers. Conversation state lives
in memory only, keyed by a "{context_type}:{context_id}" string (e.g.
"requirement:412" or "evidence:819") — it's a reading aid, not part of the
audited record, so nothing here is persisted. It resets if the app restarts,
same as core.runmanager.RUNS."""

import threading

from . import researcher

_lock = threading.Lock()
CHATS = {}  # "type:id" -> {"turns": [...], "status": "idle"|"thinking", "error": None}


def _build_prompt(context_label, context_text, prior_turns, question):
    history = "\n\n".join(
        f"Q: {t['question']}\nA: {t['answer']}" for t in prior_turns if t.get("answer"))
    parts = [
        "You are helping a human reviewer on an EUDR (EU Deforestation "
        "Regulation) palm-oil legality/risk assessment understand ONE record "
        "currently open on their screen — a legal requirement's reference law, "
        "or a piece of evidence — before they decide whether to accept, "
        "reject, approve or reject it. Answer the reviewer's question "
        "directly and concisely (a few sentences, plain language — the "
        "reviewer is a sustainability expert, not a lawyer). If the question "
        "is about the underlying law or source, you may search the web to "
        "check it, but say what you found and where. Never fabricate a "
        "citation; say so if you can't verify something.",
        f"## Currently open: {context_label}\n" + context_text,
    ]
    if history:
        parts.append("## Conversation so far\n" + history)
    parts.append(f"## Reviewer's question\n{question}")
    return "\n\n".join(parts)


def state(key):
    with _lock:
        st = CHATS.get(key)
        return dict(st) if st else {"turns": [], "status": "idle", "error": None}


def ask(key, context_label, context_text, question, actor):
    question = (question or "").strip()
    with _lock:
        st = CHATS.setdefault(key, {"turns": [], "status": "idle", "error": None})
        if not question:
            st["error"] = "Ask something first."
            raise ValueError(st["error"])
        if st["status"] == "thinking":
            st["error"] = "Still answering the previous question — wait for it to finish."
            raise ValueError(st["error"])
        st["status"] = "thinking"
        st["error"] = None
        turn = {"question": question, "answer": None}
        st["turns"].append(turn)
        prompt = _build_prompt(context_label, context_text, st["turns"][:-1], question)

    def work():
        try:
            answer = researcher.ask(prompt)
        except Exception as err:
            with _lock:
                st["status"] = "idle"
                st["error"] = str(err)
                st["turns"].remove(turn)
            return
        with _lock:
            turn["answer"] = answer.strip()
            st["status"] = "idle"

    threading.Thread(target=work, daemon=True, name=f"chat-{key}").start()


def clear(key):
    with _lock:
        CHATS.pop(key, None)
