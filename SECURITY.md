# Security and data scope

The plugin runs as trusted local Hermes Python code. It stores private state under the active profile's muse directory and adds owned scripts/native Cron jobs. It does not collect telemetry, read secrets, self-update, require an external backend, alter approval modes, grant its own gateway permissions, replace native tools, or modify Hermes core/identity files.

Paths derived from record IDs are validated and contained; writes are atomic and SQLite transitions serialize equal-event dispatch and budgets. External evidence and stored conversation excerpts remain untrusted data. Personal state is not supplied in group/room contexts. Short real-user excerpts are kept as a processing inbox; durable facts use the existing memory provider. Unprocessed signals are retained until maintenance succeeds; processed history is bounded.

Cron cannot use the state tool for user decisions, even with a saved real-user signal: goal creation/status/review changes, interest recording, watch creation, feedback, Feed edits/deletion, forgetting and preferences are refused. Progress, new research/Feed results, reminder preparation and stopping existing watches remain available. Research instructions request read-only work; tool access still follows Hermes configuration and parent permissions, without a plugin-enforced read-only tool allowlist.

Native scheduling and transport are outside the plugin transaction. A process crash after dispatch can leave an unknown outcome; do not blindly retry. Deleting an indexed record is not a guarantee that every native transcript, backup or external memory index is erased. The Skill explicitly requires verification and disclosure of those limits.

Report security issues through the repository owner's GitHub contact or a private vulnerability report if available. Do not include private user data or credentials in public issues.
