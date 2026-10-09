# Changelog

## 0.1.6

- Exclude all native Cron deliveries from user-signal collection, including existing jobs outside Muse. Keeps background results from creating or renewing interests as if the user had spoken. No change to allowed background state operations.
- Resolve macOS temporary-directory aliases in the native integration test.
- Document explicit profile selection, Cron model defaults and the `muse` toolset requirement when platform tool lists are configured.

## 0.1.5

- Add weekly outcome/cost review and monthly instruction/workflow audit, using the shared Skill and current-profile Bot Chat. Reports propose changes, save summaries for follow-up, and exclude a separate Skill audit.

- Rebuild runtime behavior, background prompts and Skill procedures from v0.1.2, then reapply the current-profile Bot Chat delivery changes.
- Remove the 0.1.3 blanket Cron state-write restrictions, the plugin's 30-minute/4000-character watch limits and its extra schedule validator.
- Remove the 0.1.4 read-only restriction on Bot Chat receiving turns. Keep the original user-evidence checks and exclude delivered results from new user signals.
- Retain Bot Chat receipts, exact-notice deduplication and the README's Bot Chat workflow.


## 0.1.4

- Send selected Cron results to the current profile's Bot Chat by default. The bot reads the result and replies in that chat.
- Remove the separate source-session injection step; notification_handoff uses the same delivery queue.
- Track live-owner and deferred Bot Chat receipts, without treating admission as a completed reply.
- Exclude incoming delivery turns from user-signal collection and prevent recursive notification creation.
- Document Bot Chat as the recommended workflow, native missing-chat creation and the installer's static after-install notes.


## 0.1.3

- Refuse user-decision state operations from Cron, including use of saved user signals; keep research progress, reminder preparation and watch stopping available.
- Limit new watch prompts to 4000 characters and recurring clock slots to at least 30 minutes, including midnight. One-off reminders can be sooner.
- Exclude Hermes bot-chat targets from the single-home notification fallback.
- Use Hermes's read-only configuration loader.
- Add real-Hermes regressions for these boundaries and align the Skill/background prompts with them.
- Include the revised bilingual feature comparisons and bundled Skill, prompt and hook documentation.

## 0.1.2

Reorganized both READMEs as a project reference and added feature coverage tables. The tables distinguish implemented code, configured model procedures, partial support and missing features. Runtime behavior is unchanged.

## 0.1.1

Rewrote the English and Chinese READMEs around the project's inspiration from Meta Muse and the everyday follow-up behavior it aims to bring to Hermes. Installation and runtime behavior are unchanged.

## 0.1.0

Initial independent companion assembly: one Skill, four script-gated recurring jobs, five prompts, transactional operational state, goals/subgoals and expiring interests, reminder preparation and native delivery tracking, quiet upkeep, reflection/relationships, silent Feed operations, bounded research, profile-scoped initialization and documented native-remove cleanup. No mandatory external provider or core patch.
