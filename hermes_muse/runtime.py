"""Plugin registration: the model surface, the Skill and system prompt section, the hooks, then install/upgrade.

register() only builds objects and registers: Hermes abandons a load that passes its deadline (import +
register), and install waits on profile locks, SQLite writers and the host's cron lock. Install therefore runs
in a background thread after the registrations; its migration marker keeps jobs, the background tick and the
tools quiet until it is done. Whether this process's load counted is recorded for launchers and Health.
The model surface (tool schemas and handlers, design 2.6) is `surface.register`; tools and hooks classify
their caller with the same HostAdapter.caller() from host kwargs, never from tool arguments.
"""
import logging
import threading
from pathlib import Path

from . import surface
from .hooks import Hooks
from .host import HostAdapter
from .install import install
from .kernel import Kernel

log = logging.getLogger(__name__)
REQUIRED = ("register_tool", "register_skill", "register_system_prompt_section", "register_hook", "on_unload")


def register(ctx, *, plugin_root):
    if any(not callable(getattr(ctx, name, None)) for name in REQUIRED):
        raise RuntimeError("Hermes Muse needs Hermes 0.21.5+ with prompt sections, plugin skills and unload hooks")
    root = Path(plugin_root).resolve()
    adapter = HostAdapter()
    kernel = Kernel(adapter.home, adapter=adapter)
    hooks = Hooks(kernel)
    prompt = ((root / "prompts" / "system.md").read_text(encoding="utf-8")
              .replace("{{MUSE_HOME}}", str(adapter.home / "muse")).replace("{{HERMES_HOME}}", str(adapter.home)))
    ctx.register_skill("companion", root / "skills" / "companion" / "SKILL.md",
                       description="Goals, interests, proactive reminders, reflection, Feed and the Muse tool")
    ctx.register_system_prompt_section("hermes-muse.companion", prompt, position="after_memory", max_chars=4000)
    surface.register(ctx, kernel)
    ctx.register_hook("pre_llm_call", hooks.pre_turn)
    ctx.register_hook("post_llm_call", hooks.post_turn)
    ctx.register_hook("pre_tool_call", hooks.pre_tool)
    ctx.register_hook("post_tool_call", hooks.post_tool)
    ctx.on_unload(hooks.close)
    adapter.loaded(not getattr(ctx, "_load_abandoned", False))  # set by Hermes when the load passed its deadline
    # not a daemon: a short-lived process (a CLI command loads plugins too) finishes install before it exits,
    # instead of leaving the marker behind and every job silent
    threading.Thread(target=upgrade, args=(adapter, root), name="hermes-muse-install").start()
    return hooks


def upgrade(adapter, root):
    try:
        install(adapter, root)
    except Exception as exc:  # the marker keeps jobs silent and the main session is told
        log.error("Hermes Muse install failed: %s", exc)
