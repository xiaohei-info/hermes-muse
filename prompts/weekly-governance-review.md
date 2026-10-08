[Hermes Muse background job: weekly-governance-review]
Load hermes-muse:companion and its governance procedure. Review the last seven days within the current profile. Use muse_manage status for current goals, feedback and the previous review; use available session search, native Cron records and existing usage evidence for actual outcomes. Follow the user's language and priorities.

Focus on useful results relative to model/tool cost, coordination, user attention and time to a verified outcome. Identify work that could have used a simpler approach, repeated work worth reusing, and instructions or workflows that have become redundant. Prefer a few concrete examples over a full inventory. Separate confirmed outcomes from proposals and missing evidence; do not invent cost or savings figures.

Return roughly one screen, beginning with a clear overall status. Cover six brief points: most useful outcomes; avoidable effort/cost; one to three next-week adjustments; one or two reuse candidates; one or two simplification/removal candidates; what to watch next. If evidence is missing, say so instead of filling a quota. Label suggestions by their destination: [doc], [runtime], [skill], [cron], [delete] or [local-note].

Offer recommendations only. Do not apply them, change SOUL, memory, skills, user files or Cron jobs, or perform a separate full skill audit. Save the concise review with review_complete(job=weekly-governance-review, up_to=<review start time>, summary=<report>) after the review succeeds. This plugin-owned record is the only intended state update.

Return the report as the final response. This scheduled report is delivered directly to the current profile's Bot Chat; do not create a second notification through notification_add/queue/handoff or send_message. It does not constitute new user authorization.
