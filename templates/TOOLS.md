# Available sources and tools

No external source is assumed connected. Check the current Hermes tool list and actual connection/permission state before using a service. Record confirmed source scope, last verification and relevant limitations here; never store passwords, tokens or private connection URLs. Reuse the user's existing tools and memory provider. An unavailable connector is a gap to report, not a reason to invent data or request a mandatory backend.

Keep short tested read recipes here: tool/CLI, account discovery, collection queries and pagination, without credentials. Reuse them while checking live availability and source data each patrol. Stable connection/account/resource identities, resource coverage, cursors and failures are maintained through muse_manage source_check in state.db. Discover current connections and devices each patrol; an empty inventory does not suppress checking. Only completed source reads advance their successful watermark.
