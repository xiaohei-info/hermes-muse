# Changelog

## 0.1.13

- Return remaining review batches directly so hourly/nightly work can finish its snapshot in one run; preserve timestamp ties and truthful partial progress.
- Explain pending notification blockers and earliest eligibility; allow evidence-backed urgency reassessment without bypassing user snoozes or inventing promises.
- Bind verified tool aliases to existing source IDs and archive duplicate observations without transferring success checkpoints.


## 0.1.12

- Preserve all recorded real-user context from the last day for patrols, removing the 0.1.11 eight-message/1,000-character excerpt cap. Earlier context remains available through native memory/session retrieval.
- Make coverage, timely follow-through and user experience the priority; reuse tools and source records only without reducing useful checks or context. The 0.1.11 source, signal and receipt fixes remain.

## 0.1.11

- Exclude native async-completion envelopes from user signals and signal-backed actions. Preserve historical misclassified messages as background audit evidence.
- Derive source IDs from connection/account/resource identity; track expected and checked resources separately. Incomplete coverage cannot advance the successful checkpoint. Archive old free-form source records without guessing their identities.
- Read the native same-profile Bot Chat receipt by its execution-specific key. Repair finalized unknown outcomes when that exact receipt settles, even after later patrols overwrite the latest-job pointer; never resend.
- Give each Cron only its relevant signal context. Patrols reuse tested read recipes, batch independent reads and use source checkpoints while continuing live source inspection on every tick.

## 0.1.10

- Run all six fixed jobs on schedule instead of treating empty local goals/interests as proof there is no work. Patrols discover connected services/devices, inspect changes and upcoming deadlines, then stay silent when nothing merits a notice. This increases scheduled model usage.
- Record per-source coverage and successful watermarks; partial or failed reads preserve the previous successful position. Retire stale unsent notices from verified source evidence.
- Add weather/travel changes, interest news and relevant local opportunities to the existing patrol/Feed procedures, with current context, original sources, expiry and the same attention budget. No extra Cron or service dependency.
- Give nightly review its own signal cursor; keep pending notices visible, fix interest snooze/resumption and a nested SQLite transaction during interest-notice finalization.
- Allow evidence-backed completion of accepted goals across days, verified external cancellation and expiring Ideas without a fabricated goal. New commitments and scope changes still require user evidence.
- Use one native asynchronous coordinator for new research batches, with host result callbacks and durable status. No user-driven wave advancement for new work; legacy batches remain inspectable.
- Keep one Skill, seven prompts, four hooks and six fixed jobs. Preserve user templates, native identity/memory and job schedule/model/pause choices.

## 0.1.9

- Expand proactive behavior instructions: notice concrete conversational plans, prepare useful work before interrupting, select one strongest ordinary item, and avoid status chasing or repeated offers.
- Connect memory, goal research, patrol selection and feedback/expiry rules without new Skills, hooks or Cron jobs. Existing execution and permission checks are unchanged.
- Add natural conversation and evidence-first follow-through guidance, plus bounded working lessons maintained in the companion workspace AGENTS.md during nightly review. Existing user instructions and SOUL are preserved.

## 0.1.8

- Fix the live-acceptance failure in 0.1.7 where the model returned a dispatch-status summary instead of the notice body. A narrowly scoped native transform_llm_output hook now finalizes patrol/watch output from approved records.
- Recheck lifecycle and attention conditions at final output; require that finalization before recognizing a direct notice as sent. Other conversations and review reports are unchanged.
- Registers four hooks; still one Skill, seven prompt files and six fixed Cron jobs. No delivery-only Cron is created.

## 0.1.7

- Deliver selected reminders in the patrol/watch Cron's own final response; no additional delivery-only Cron is created. Deferred candidates remain for the next patrol.
- Keep lifecycle, freshness, deduplication and attention checks; bind native receipts to the exact preparing execution instead of the recurring job's latest run.
- Migrate the old silent patrol and unchanged generated monitoring instructions once; preserve schedules, pauses and user-selected destinations. Existing delivery-only jobs can finish through their original path.

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
