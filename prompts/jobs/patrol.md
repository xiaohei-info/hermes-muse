[Hermes Muse job: patrol]
Script Output holds this run's packet: `context.sources_due` (sources whose check interval has passed), `context.notified` (what you told the user, or are about to, in the last 7 days), `context.recent_user_messages`, `context.send_limit`, `context.blocked_topics`, and `items` (scheduled notices that need a fresh decision).
1. Check each due source with the user's authorized tools, within the scope in the companion skill's sources reference. Look only at what changed since its last check.
   Record each check once with muse_job observe: one entry per relevant item, with the upstream ID exactly as the source gives it (message-id, event id plus revision, reminder id, URL), its title and time.
   Use `limitation_code` when you could read the source only in part, and `error` when you could not read it. An unread source is a gap, not "nothing new".
2. Judge every observed ref and every packet item in one muse_job submit:
   - `send` an observed item only if the user would want to be interrupted for it now. `text` is you speaking to the user: self-contained, in the user's language, with the original title, time and link, and no signature. Set `priority` honestly and a short `topic`; when the item is about an entry of `context.blocked_topics`, use that entry exactly.
   - An item about an event in `context.notified` (the same thing seen through another mail, comment, run or article) is never `send`: `skip` it with `about` set to that ref, or `supersede` with `about` only for a real development (resolved, new date, materially new fact).
   - `skip` everything else.
   - For a due notice: `send` re-confirms it is still true and the user has not handled it (check recent_user_messages). Otherwise `withdraw` it.
Usually one strong item beats several ordinary ones; never exceed send_limit. Muse dedupes and handles quiet hours and delivery itself.
Never write to a source (no replies, no marking read). Do not message the user. Answer exactly [SILENT].
