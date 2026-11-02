"""muse/RULES.md: the user's rule table and executor command templates, in the file's first-line JSON metadata.

Shared layer, so Health can check the file without calling kernel business. Nothing here runs a command, reads a
source or writes state. Matching belongs to code: the model does not judge whether a rule applies, it follows it.
`thread` is the rule author's regex for the event thread (PR, ticket); Muse owns no connectors, so only the author
can say how to read one from a URL, and a thread key must be globally unique (include the repository). Without a rule, whether two items are one event stays the model's call (`about`).
"""
import json
import re

from .content_io import Files

REL = "RULES.md"
PREFIX = "<!-- hermes-muse "
NATIVE = "native"  # Hermes' own delegation: no templates, its state is read through HostAdapter.owners
DOES = ("dispatch", "ask", "tell", "ignore")
TELLS = ("never", "needed", "always")
AUTHORITIES = ("read", "draft", "write")
TEMPLATES = ("run", "status", "send", "stop")
WHEN = ("source_id", "title", "url")
EXPECT = "2h"
DURATION = re.compile(r"([1-9][0-9]*)([mhd])")
UNIT = {"m": 60, "h": 3600, "d": 86400}
LINK = re.compile(r"https?://[A-Za-z0-9._~:/?#=%+,@-]+")  # no whitespace or shell metacharacters: it goes into a command
EMPTY = {"executors": {}, "rules": []}


def seconds(text):
    found = DURATION.fullmatch(str(text))
    if not found:
        raise ValueError(f"expect must look like 45m, 2h or 3d, got {text!r}")
    return int(found.group(1)) * UNIT[found.group(2)]


def regex(where, text):
    try:
        re.compile(str(text))
    except re.error as exc:
        raise ValueError(f"{where} is not a valid regex: {exc}") from None


def one_of(where, value, allowed):
    if value not in allowed:
        raise ValueError(f"{where} must be one of {', '.join(allowed)}, got {value!r}")


def check_executors(executors):
    if not isinstance(executors, dict):
        raise ValueError("executors must be an object of name -> command templates")
    for name, templates in executors.items():
        if name == NATIVE:
            raise ValueError(f"executor name {NATIVE!r} is reserved for Hermes' own delegation")
        if not isinstance(templates, dict) or not all(isinstance(templates.get(t), str) for t in ("run", "status")):
            raise ValueError(f"executor {name!r} needs run and status command templates")
        extra = sorted(set(templates) - set(TEMPLATES))
        if extra:
            raise ValueError(f"executor {name!r} has unknown template {extra[0]!r}; templates: {', '.join(TEMPLATES)}")


def check_rule(rule, executors, seen):
    """The rule with its defaults filled in; ValueError naming the rule and field."""
    name = rule.get("name") if isinstance(rule, dict) else None
    if not name or not isinstance(name, str) or name in seen:
        raise ValueError(f"every rule needs a unique name, got {name!r}")
    where = f"rule {name!r}"
    when = rule.get("when")
    if not isinstance(when, dict) or not when or set(when) - set(WHEN):
        raise ValueError(f"{where}: when needs at least one of {', '.join(WHEN)}, and nothing else")
    for field, text in when.items():
        regex(f"{where}: when.{field}", text)
    if rule.get("thread"):
        regex(f"{where}: thread", rule["thread"])
    out = {"tell": "needed", "authority": "read", "expect": EXPECT, "goal": "auto", "thread": None, **rule}
    one_of(f"{where}: do", out.get("do"), DOES)
    one_of(f"{where}: tell", out["tell"], TELLS)
    one_of(f"{where}: authority", out["authority"], AUTHORITIES)
    seconds(out["expect"])
    if out["do"] == "dispatch":
        if out.get("executor") not in executors:
            raise ValueError(f"{where}: executor {out.get('executor')!r} is not in executors ({', '.join(executors) or 'none'})")
        if not str(out.get("ask") or "").strip():
            raise ValueError(f"{where}: a dispatch rule needs ask (the one-sentence brief)")
    return out


def parse(text):
    """{executors, rules} from the file's text; ValueError naming what is wrong."""
    first = text.partition("\n")[0].strip()
    if not (first.startswith(PREFIX) and first.endswith(" -->")):
        raise ValueError(f"RULES.md must start with {PREFIX}{{json}} -->")
    try:
        table = json.loads(first[len(PREFIX):-4])
    except ValueError as exc:
        raise ValueError(f"RULES.md metadata is not JSON: {exc}") from None
    if not isinstance(table, dict) or not isinstance(table.get("rules", []), list):
        raise ValueError("RULES.md metadata must be an object with executors and rules")
    executors = table.get("executors", {})
    check_executors(executors)
    rules, seen = [], set()
    for rule in table.get("rules", []):
        rules.append(check_rule(rule, executors, seen))
        seen.add(rule["name"])
    return {"executors": executors, "rules": rules}


def load(home):
    """The parsed file; an absent file is an empty table, a broken one raises ValueError (Health reports it)."""
    try:
        return parse(Files(home).read(REL).decode("utf-8"))
    except FileNotFoundError:
        return EMPTY


def match(rules, item):
    """The first rule whose every `when` regex finds its field in the observed item, or None."""
    for rule in rules:
        if all(re.search(text, str(item.get(field) or "")) for field, text in rule["when"].items()):
            return rule
    return None


def thread(rule, item):
    """The event-thread key: the rule's `thread` regex over the url and upstream id (its first group, else the match),
    else the item's own id; None when the item has neither."""
    fields = [item.get("url"), item.get("upstream_id")]
    if rule.get("thread"):
        for value in filter(None, fields):
            found = re.search(rule["thread"], str(value))
            if found:
                return found.group(1) if found.groups() else found.group(0)
    return next((str(value) for value in fields if value), None)


def link(item):
    """The item's URL if it is safe to hand to an executor, else None. An outsider writes this text too, so it must fully
    match LINK; a free-text upstream id never stands in for it."""
    return next((str(v) for v in (item.get("url"), item.get("upstream_id")) if v and LINK.fullmatch(str(v))), None)


def brief(rule, item):
    """What an executor gets, only for an item with a `link`: the rule's ask, its authority and that link. The only outside
    text in it is the checked link; the event's own text stays out, and the executor reads the original itself."""
    return f"{rule['ask']}\nAuthority: {rule['authority']}\nEvent: {link(item)}"


def forward_note(item):
    """What a running executor gets about a later event of its thread, or None without a `link`."""
    return link(item) and f"New event on this thread: {link(item)}"
