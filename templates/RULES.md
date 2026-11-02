<!-- hermes-muse {"executors": {}, "rules": []} -->
# Rules

What should happen on its own when an event arrives. The first line is the table Muse reads: `executors` (the command
templates of whatever does the work) and `rules` (which events go where). This text is only for you; no rule runs
until you add one to the first line.

A rule you write here is your authority: a matching event starts its executor without asking you. An event no rule
matches can at most become a notice to you, and can never start anything.

## Executors

`"my-agent": {"run": "my-agent start --cwd ~/code/app {brief}", "status": "my-agent inspect {handle}", "send": "my-agent send {handle} {message}", "stop": "my-agent stop {handle}"}`

`run` and `status` are required. The patrol runs them with the tools you authorized; Muse itself runs no command.
Real permissions belong in the executor's own configuration: `authority` only tells it what you expect.

## Rules

`{"name": "ci-fix", "when": {"source_id": "^github:", "title": "CI failed", "url": "/pull/"}, "thread": "(/pull/[0-9]+)", "do": "dispatch", "executor": "my-agent", "ask": "Find why CI failed on this PR and push a fix.", "authority": "write", "tell": "needed", "expect": "2h"}`

- `when`: regexes on `source_id`, `title`, `url`; all must match. The first matching rule wins.
- `thread`: a regex over the URL or upstream id. Its first group names the event thread: later events of one thread go to the same goal and executor.
- `do`: `dispatch` starts the executor; `ask` raises a question for you; `tell` raises a notice; `ignore` drops the event.
- `ask`: the one-sentence brief. The executor gets this and a link, never the event's text.
- `authority`: `read`, `draft` or `write`.
- `tell`: finished work is `never` told, told when `needed` (a goal you must close yourself), or `always`. Questions and failures always reach you.
- `expect`: `45m`, `2h`, `3d`. Past it with no progress, you are told.
- `goal`: `auto` (a goal per thread, closed by code once the executor shows evidence) or the id of an open goal of yours.

## Always ask me first

Whatever an executor must never do without you, for example deleting data, stopping a service, spending money, sending
anything outside, changing direction, credentials and permissions.
