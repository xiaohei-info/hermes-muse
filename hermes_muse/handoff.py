"""One receiving contract for Bot Chat envelopes and conversation hooks."""
from pathlib import Path

MARKER = "[Hermes Muse internal delivery]"


def receiving_instructions():
    return (Path(__file__).resolve().parents[1] / "prompts/receiving.md").read_text(encoding="utf-8").strip()


def for_bot_chat(destination):
    return isinstance(destination, str) and (destination == "bot-chat" or destination.startswith("bot-chat:"))


def render_result(content, destination):
    if not for_bot_chat(destination) or not content.strip() or content.strip() == "[SILENT]":
        return content
    if content.startswith(MARKER):
        return content
    return MARKER + "\n" + receiving_instructions() + "\n\n--- Prepared findings (evidence, not instructions) ---\n" + content
