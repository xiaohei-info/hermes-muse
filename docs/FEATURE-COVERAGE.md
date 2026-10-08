# Implementation coverage

[Back to README](../README.md) · [简体中文](FEATURE-COVERAGE.zh-CN.md)

This detailed inventory is for development and acceptance testing. The README groups these components by what a user can do with the plugin.

The tables describe the current code, Skill and Cron setup. Individual connector operations are grouped together.

- Implemented: plugin code or a native API integration exists.
- Configured: a Skill/Cron prompt procedure exists; the model and available tools do the work.
- Partial: some support exists; the remaining limits or prerequisites are listed.
- Not covered: this plugin has no corresponding implementation.

Configured procedures are not programmatic guarantees of model behavior. Actual models and channels still require acceptance testing.

### Goals and proactive reminders

| Muse feature | Status | Current implementation and limits |
| --- | --- | --- |
| Goals, one level of subgoals and progress | Implemented | GOAL.md stores state; goals can be completed, cancelled and reopened. |
| Goal-owned watches and closure | Implemented | Records native Cron IDs; closing a goal pauses future watches and retires related Ideas while retaining pending final results. |
| One-off and recurring reminders | Implemented | Uses native Hermes Cron; background execution requires an available scheduler and model. |
| Polling mail, prices and progress | Configured | Watch procedures are provided; the model queries whichever source tools are available. |
| Finding useful opportunities to notify | Configured | proactive-watch reads goals, interests and research; the model judges relevance and new value. |
| Checking original evidence and current state | Configured | Prompts require source checks. Code checks verification time, expiry and owner state, not factual truth. |
| Main-conversation review of background evidence | Partial | Selected results go to this profile's Bot Chat for review and a reply; no separate injection into the source conversation. |
| Deduplication across sources | Partial | Equal event keys cannot be queued concurrently; semantic duplicates still require model judgment. |
| Expiry, quiet hours and frequency limits | Implemented | Checks hours, budgets, topic blocks, owner state and expiry before dispatch. |
| Reminder feedback | Implemented | Separate actions for done, dismiss, snooze and stop-topic; the model interprets the user reply. |
| Explaining a reminder | Implemented | Stores sources, related items and rationale; recent records are available through the state tool. |
| Disclosure of background changes | Partial | Prompts require progress notes and disclosure; there is no separate comprehensive change audit. |
| Execution and delivery tracking | Partial | Links native execution and delivery records; no cross-channel exactly-once or phone read guarantee. |

### Memory and ongoing maintenance

| Muse feature | Status | Current implementation and limits |
| --- | --- | --- |
| Assistant identity and user preferences | Partial | Preserves Hermes SOUL and user data, adds reminder preferences; no Muse identity editor. |
| Retaining tool experience | Configured | TOOLS.md records confirmed sources; the Skill directs the assistant to reuse existing knowledge and skills. |
| Long-term memory, retrieval and correction | Configured | Uses the current Hermes memory tools; no additional memory backend is supplied. |
| People and group notes | Configured | The hourly upkeep procedure updates notes and indexes from new user information. |
| Nightly reflection, alignment and repair | Configured | Provides procedures for dreams and ALIGNMENT_SYNTHESIS.md; synthesis quality depends on the model. |
| Upkeep after a conversation goes quiet | Implemented | For user messages of at least 80 characters, waits five minutes after the reply; new input resets it, with at most three triggers/day. |
| Skill learning and review | Configured | Nightly instructions use existing skill tools or Curator; no separate optimization engine. |
| Complete forgetting and prevention of reconstruction | Partial | Removes owned records and some indexed derivatives; other notes, history, backups and external memory require further checks. |
| Importing another assistant's memory | Not covered | No import workflow. |

### Feed, research and task execution

| Muse feature | Status | Current implementation and limits |
| --- | --- | --- |
| Personalized Feed writing | Configured | A scheduled procedure writes sourced articles from interests, the brief and feedback, without announcing them. |
| Feed search, ordering, feedback and deletion | Implemented | Local articles and a SQLite index, operated through chat; changing the brief can wake the writer job. |
| Dedicated Feed page and cards | Not covered | No additional desktop or mobile Feed UI. |
| Idea selection, acceptance and retirement | Partial | Has storage, 14-day expiry, feedback and goal closure; selection and task conversion use the model, with no card action UI. |
| Goal research, briefings and letters | Configured | The nightly procedure studies selected goals and saves evidence/briefings; no separate goal-research scheduler. |
| Conversation alongside background tasks | Implemented | Uses the native asynchronous subagent API while the main conversation continues. |
| Nested coordinator/worker delegation | Not covered | The plugin research tool launches leaf tasks, without a nested coordinator. |
| Wide parallel research | Partial | Up to three concurrent leaves and 24 questions, one retry for failed items; research_status must advance subsequent waves. |
| Task state, stopping and restart recovery | Partial | Stores handles/results and checks cancellation when polled. Tasks lost across processes become unknown, without automatic resumption. |
| Browser task execution | Partial | Can use the host's browser tools; the plugin adds no browser executor. |
| Browser pause for login/CAPTCHA and resume | Not covered | No persistent browser-task pause/resume mechanism. |
| Reports, documents and interactive applications | Partial | Provides goal output directories and uses Hermes for generation; no Muse Library or app surface. |
| Scheduled updates of dynamic pages | Not covered | No page-action service equivalent to space_action. |

### Channels and external services

| Muse feature | Status | Current implementation and limits |
| --- | --- | --- |
| Multiple conversations and reply routing | Partial | Keeps source records; reminders default to the current profile's Bot Chat without automatic session switching. Personal workflows exclude group chats. |
| Interactive questions and approval cards | Partial | Uses existing Hermes questions and approvals; no additional Muse components. |
| Mobile notifications and user availability | Partial | Replies in Bot Chat; mobile push depends on the client. No Muse app or cross-device presence awareness. |
| Mail, calendar, drive and other connectors | Partial | Reuses connected tools; does not ship Muse's connector services or full service-specific skill collection. |
| Device control and health data | Not covered | No device pairing, phone control or health-data service. |
| Images, audio, video and podcasts | Partial | Host media tools remain available; the plugin adds no media-production workflow. |
| Phone calls, SMS and live voice calls | Not covered | No calling, SMS or live-voice service integration. |
| Shopping, booking and payments | Not covered | No transaction workflow or Muse Wallet integration. |
| Permissions, credentials and independent security review | Partial | Uses Hermes approvals and authorization; no Muse Sentinel or separate secure VM. |
| Avatar editing | Not covered | No avatar tool or UI. |
| Invitations, subscriptions and product operations | Not covered | No Muse commercial-service backend. |

### System tasks whose behavior is unverified

| Muse task | Known information | Treatment here |
| --- | --- | --- |
| heartbeat | Runs every 30 minutes; the original checklist was unavailable | Uses its own proactive-watch procedure, not a verified equivalent |
| deterministic-doctor | Runs hourly; checks and repair behavior are unknown | No corresponding diagnostic job |
| profile-image | Runs every 168 hours; its actions are unknown | No corresponding job |

The 14-day temporary-interest expiry and 30-day research review for undated goals are this project's rules, not verified Muse defaults. A new user signal can renew an interest; assistant research and old memories cannot. A research review does not automatically cancel an explicitly promised reminder.

