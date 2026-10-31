# Proactivity

The patrol job runs every 30 minutes. It checks the sources that are due, records what it saw with `observe`, and
gives one verdict per item with `submit`. Code decides keys, dedupe against the last 7 days, quiet hours, daily
budgets, delivery and receipts. The model decides only what is worth the user's attention and how to say it.

## Coverage scope

Form the coverage plan before discovering any source. It comes from the user's explicit requirements and the
profile's declared responsibilities (SOUL, role instructions, and the free-text `## Coverage scope` section of
PROACTIVE_PREFERENCES.md, which `read(kind=preferences)` returns and `preferences.notes` sets). Read it at
the start of a patrol.
- A general assistant with no exclusions covers all authorized calendars over the next 30 local days, mail and
  reminders. A specialist role covers its declared sources fully and does not probe personal sources.
- A connector being installed is never permission to read it. Never narrow scope to save calls, and never infer
  responsibilities from a profile name.
- `notes` refines scope in prose; it grants no access.

Classify every source before you touch it:
- **Outside scope**: do not probe, read or observe it.
- **In scope, not connected**: `observe` it with `error` starting `not connected:` and naming the fix (see
  [sources](sources.md#connection-states)). Never trigger an authorization prompt.
- **In scope, partly readable**: `observe` with a stable `limitation_code`. After 5 identical codes in a row Muse
  treats the limitation as known, and it stops counting as a gap.
- **In scope, failing**: `observe` with `error`. After 3 failures in a row, Health raises it.

`source_id` is `<kind>:<account>`, for example `mail:work` or `calendar:family`. Keep it stable, because each kind has
its own check interval. Record every item that could matter, with the upstream ID exactly as the source gives it:
message-id or thread id, event id plus revision, reminder id, or URL. Use one form per source kind (for mail the
RFC Message-ID, not a provider's internal id), so the same item keeps the same ID across runs.

One event often arrives through several sources: the mail, the PR comment and a news item about the same reply, or
one CI failure per push. `context.notified` lists what the user was told, or is about to be, in the last 7 days. An
item about one of those events answers with `about` set to its ref: `skip` when it adds nothing, `supersede` only for
a real development. Muse then remembers the item's ID as part of that event and will not notify it again.

## What earns an interruption

- **Prepare before interrupting.** Give a checked answer, a short comparison, a ready draft or the exact deadline. A
  headline, a repeated inbox item or "I could look into it" is not enough.
- **Pick one strong item.** An ordinary unsolicited message carries one strong item. The others wait, or are skipped.
  The limits are ceilings, not targets, and an empty patrol is normal.
- **Read the user's situation.** Check `recent_user_messages` first, because the user may already have handled it.
  Silence or an unread mark is not a problem in itself. Never nag about a dismissed topic, and never invent urgency
  because nobody replied.
- **Write it so it stands alone.** `text` is self-contained and in the user's language. Give the original title and
  time, what changed, why it matters now, the work already done, and the source link. Say "prepared" when you did not
  act.
- **Supersede only on real change.** Use `supersede` only for an event Muse already notified about (its own item, or
  `about` a `context.notified` ref) that has a real new development, such as a moved date, a new deadline or a
  resolution. A re-crawl, another source repeating it, or another failed run of the same CI is not a development.
- **Re-confirm due notices.** A due notice comes back when its evidence is a day old or it has been stuck for 6 hours.
  `send` re-confirms it is still true; `withdraw` it if it is resolved, stale or already handled. A dormancy question
  belongs to Muse and never appears there.

## Priority

`ordinary` waits for waking hours and the daily allowance. `time_sensitive` matters today and has its own allowance.
`urgent` bypasses quiet hours: use it only for concrete evidence of ongoing harm, such as an account compromise, fraud,
a safety risk, or a deadline that passes before the next waking hour. The word "security" or an unread flag is not
urgent. A blocked topic or a user snooze still applies to urgent items.

## Small, timely help

When a known plan makes it useful, check a relevant opening, ticket window, travel disruption or (only with
`weather_context`, see [weather](weather.md)) the forecast. Prepare a short usable option; never book or operate
anything. Longer explanations belong in the silent Feed. None of this creates jobs, goals or subscriptions.

Interest news is the Feed's job, not the patrol's: the Feed researches the user's current interests once a day and
may raise one notice for a real development. When such a notice comes back as due, re-confirm it like any other.

## User feedback

- "Already handled" updates the related goal.
- "Not this time" is `feedback(value=not_useful)`.
- "Stop this" is `feedback(value=stop)`. For a whole topic, add it to the topics to avoid in the preferences
  `notes`, which the patrol reads.
- "Later" sets a real date on the goal.

Ask what the user meant instead of treating every reaction as a permanent opt-out.
