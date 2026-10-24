# Available sources and tools

No external source is assumed connected. Check the current Hermes tool list and actual connection/permission state before using a service. Record confirmed source scope, last verification and relevant limitations here; never store passwords, tokens or private connection URLs. Reuse the user's existing tools and memory provider. An unavailable connector is a gap to report, not a reason to invent data or request a mandatory backend.

Keep short tested read recipes here: tool/CLI, account discovery, collection queries and pagination, without credentials. Reuse them while checking live availability and source data each patrol. Stable connection/account/resource identities, resource coverage, cursors and failures are maintained through muse_manage source_check in state.db. Discover current connections and devices each patrol; an empty inventory does not suppress checking. Only completed source reads advance their successful watermark.

## Confirmed and Recommended Read Recipes

### Weather Forecast (Contextual & Extended)
- **Tool / Command**: Pure HTTP query to Open-Meteo (public, no API key or credentials required) via python or curl:
  `python3 -c "import urllib.request, json; print(json.dumps(json.loads(urllib.request.urlopen('https://api.open-meteo.com/v1/forecast?latitude=<lat>&longitude=<lon>&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,weather_code&timezone=auto&forecast_days=5').read().decode())['daily']))"`
  or via a local weather script / CLI tool if configured.
- **Output**: Daily min/max temperatures, precipitation probability/sum, and WMO weather codes.
- **Usage in Patrol**: Query during scheduled patrols (`proactive-watch`) when calendar events, trips, or recurring family routines occur in the 1–5 day rolling window, alerting on severe weather or sharp temperature drops.

Record confirmed tool-call conventions alongside the recipe. On hosts restricting local tool_call to one entry, use separate invocations for local/MCP tools; independent invocations may share a turn. Do not infer batching support from an array-shaped argument. Save a successful correction immediately so the next run starts with the working method.

Read and maintain this Muse-owned note through muse_manage content_read/content_write(kind=tools_note,id=current), with a current revision and evidence for changes. A recipe documents usage; it does not grant permissions or register tools.
