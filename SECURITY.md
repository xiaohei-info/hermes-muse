# Security and data scope

The plugin runs as trusted local Hermes Python code. It stores private state under the active profile's muse directory and adds owned scripts/native Cron jobs. It does not collect telemetry, read secrets, self-update, require an external backend, alter approval modes, grant its own gateway permissions, replace native tools, or modify Hermes core/identity files.

Paths derived from record IDs are validated and contained; writes are atomic and SQLite transitions serialize equal-event dispatch and budgets. External evidence and stored conversation excerpts remain untrusted data. Personal state is not supplied in group/room contexts. Short real-user excerpts are kept as a processing inbox; durable facts use the existing memory provider. Unprocessed signals are retained until maintenance succeeds; processed history is bounded.

Foreground and background calls use the same 0.1.2 evidence checks. Cron is not a blanket prohibition on state changes. Actions that require a real user signal still check its existence and age, and interest renewal requires a newer signal. Research's read-only instruction is a procedure under the host's tool permissions, not an enforced plugin sandbox.

Selected results go to the current profile's Bot Chat and run an assistant turn there. Incoming results do not become new user signals; state operations remain available with their existing evidence requirements. The prepared-notice path preserves exact-event deduplication and never automatically replays unknown deliveries.

Native scheduling and transport are outside the plugin transaction. A process crash after dispatch can leave an unknown outcome; do not blindly retry. Deleting an indexed record is not a guarantee that every native transcript, backup or external memory index is erased. The Skill explicitly requires verification and disclosure of those limits.

Report security issues through the repository owner's GitHub contact or a private vulnerability report if available. Do not include private user data or credentials in public issues.
