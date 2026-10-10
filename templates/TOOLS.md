# Available sources and tools

No external source is assumed connected. Check the current Hermes tool list and actual connection/permission state before using a service. Record confirmed source scope, last verification and relevant limitations here; never store passwords, tokens or private connection URLs. Reuse the user's existing tools and memory provider. An unavailable connector is a gap to report, not a reason to invent data or request a mandatory backend.

Keep short tested read recipes here: tool/CLI, account discovery, collection queries and pagination, without credentials. Reuse them while checking live availability and source data each patrol. Stable connection/account/resource identities, resource coverage, cursors and failures are maintained through muse_manage source_check in state.db. Discover current connections and devices each patrol; an empty inventory does not suppress checking. Only completed source reads advance their successful watermark.

Record confirmed tool-call conventions alongside the recipe. On hosts restricting local tool_call to one entry, use separate invocations for local/MCP tools; independent invocations may share a turn. Do not infer batching support from an array-shaped argument. Save a successful correction immediately so the next run starts with the working method.
