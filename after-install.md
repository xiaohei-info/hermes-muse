# Hermes Muse

Recommended: use the current profile's **Bot Chat** for your goals, interests and follow-up.

Patrols deliver selected reminders themselves, without extra delivery Cron jobs. Scheduled weekly/monthly reports also go to that profile's Bot Chat. The bot reads them and replies there, using the profile's model. Hermes can create a missing Bot Chat on first delivery.

First plugin load sets up one Skill, one state tool, three conversation hooks, seven prompts and six recurring Cron jobs. Start a new conversation to load the system prompt section; keep the Hermes scheduler running for background work.

No external messaging channel is required. This installer does not present a channel/session picker. See README.md or README.zh-CN.md for the workflow and uninstall instructions.

If this profile has explicit `platform_toolsets` lists, include `muse` in the relevant platform lists so the assistant can call `muse_manage`.
