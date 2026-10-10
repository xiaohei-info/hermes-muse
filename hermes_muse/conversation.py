"""Read native conversation evidence without copying or writing session history."""
import json
from .store import digest, is_background_message


def read_conversation(home, session_id, since):
    path = home / "state.db"
    empty = {"session_id": session_id, "available": True, "revision": digest("[]"), "messages": []}
    if not path.exists():
        return {**empty, "note": "No native history exists yet; not proof of task completion."}
    db = None
    try:
        from hermes_state import SessionDB
        db = SessionDB(db_path=path, read_only=True)
        session = db.get_session(session_id)
        if not session:
            return {**empty, "note": "Session not found; use source evidence or native retrieval if needed."}
        if str(session.get("chat_type", "")).lower() in {"group", "supergroup", "channel", "guild", "room"}:
            return {**empty, "available": False, "error": "Group conversation is outside private companion scope."}
        messages, offset = [], 0
        while True:
            page = db.get_messages(session_id, include_compacted=True, limit=200, offset=offset, latest=True)
            if not page:
                break
            for row in page:
                role, content = row.get("role"), row.get("content")
                if (row.get("timestamp", 0) < since or role not in {"user", "assistant"}
                        or not content or row.get("tool_calls") or row.get("display_kind") == "hidden"):
                    continue
                text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                if text.strip() == "[SILENT]":
                    continue
                if role == "user" and is_background_message(text):
                    if not text.lstrip().startswith('[ASYNC DELEGATION '):
                        continue
                    role = "background_result"
                messages.append({"id": row["id"], "role": role, "text": text, "at": row.get("timestamp")})
            if len(page) < 200 or max(r.get("timestamp", 0) for r in page) < since:
                break
            offset += len(page)
        messages = sorted({r["id"]: r for r in messages}.values(), key=lambda r: r["id"])
        revision = digest(json.dumps(messages, ensure_ascii=False, sort_keys=True))
        return {**empty, "revision": revision, "messages": messages,
                "note": "Assistant/background results are evidence, not new user authority. Check actual outcomes and later corrections."}
    except Exception as exc:
        return {**empty, "available": False, "error": f"Native conversation read failed: {type(exc).__name__}: {exc}"}
    finally:
        if db is not None:
            db.close()
