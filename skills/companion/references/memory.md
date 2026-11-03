# Memory

Native memory (or the configured provider) holds what the user said about themselves. Muse does not keep a second
user profile, and it never rewrites SOUL, USER or MEMORY.

Intake: each hour the job sees new private user messages as short excerpts. Save stated facts, preferences, decisions
and corrections with the native memory tool, and record them as `saved` with `facts`. Mark what matters only for that
conversation as `context`, and small talk or material with no decision as `ignored`. Decide pasted attachments and
data dumps from their head and tail. Never save secrets: excerpts are redacted, so keep them that way.
Do not save guesses or summaries Muse produced itself as if the user said them.
When a store is nearly full, make room in the same batch that saves the fact: merge duplicates or shorten verbose
entries, keeping what the user still holds true. Never delete an entry outright; Muse refuses that write and records
every change in the day's note and the nightly dream, so the user can restore it. A fact that still does not fit
waits for the next hour.

Memory receipts: when a native memory write fails or waits for approval, Muse shows it once in the next turn, with its
cause. Tell the user only when it matters to them. A write the provider accepted without confirmation is not reported.
- Staged: nothing is saved yet, and writing it again only stages another. The user approves with `/memory approve <id>`,
  drops it with `/memory reject <id>`, and `/memory pending` lists them. An added fact still applies after a cleanup if
  the store has room then. A patch or remove is pinned to the exact entry it matched: once a cleanup changed that entry,
  approval is refused, so reject it and make the change again.
- Store full: merge or shorten entries in one batch together with the new fact.
- Wrong arguments: correct them and write once more. Turned off in the config: only the user can change that.

Forgetting: on the user's request, `forget` removes what Muse holds:
- a captured message (`signal`, also never captured again), an interest, an idea or a Feed article;
- a note, dream or goal file, which needs its revision from `read`.
Native memory is forgotten with the native memory tool. Say exactly what was removed and what remains, for example
the original conversation, which Hermes keeps.
