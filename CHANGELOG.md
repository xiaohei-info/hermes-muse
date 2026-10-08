# Changelog

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
