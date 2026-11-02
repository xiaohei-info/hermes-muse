# Goals, interests, ideas and watches

- **Goal**: a clear request or promise the user accepted (the words "create a goal" are not needed). Write
  `criteria` as what done looks like in the user's terms. Before creating one, check `read(kind=goal, query=…)`.
  The same title in the same conversation returns the existing goal.
- **Interest**: something the user cares about for now (Feed and patrol use it). It lasts 14 days, or until
  `expires`. Only a new mention from the user renews it; an article Muse wrote does not.
- **Idea**: a suggestion for later. It authorizes nothing until the user accepts it.
- **Watch**: only on the user's explicit request to monitor something for an open goal. It needs a concrete stop
  condition and a schedule no tighter than the thing changes. A watch stops when its goal closes or it expires.
  A watch that has no `expires` renews while its goal is open.

Completion: check the actual result first, explain it to the user, then call `goal_update(status=done, evidence=…)`.
`evidence` is a link, commit, file path or one observation someone could check; code refuses done without it. When the
user says it is done, what they saw is the observation, so one call still closes it. A goal a rule made closes by code
once its executor shows evidence.
Cancel when the user drops the work. `waiting_user` marks a goal that waits on the user. `owner` records a native
delegation handle now working on it. An owner's finished result still needs your review before the goal is done.
Every update moves the next check to tomorrow. Nightly reviews due goals and records an assessment;
`done_suggested` there needs evidence and reaches the user as a question; when they agree, close the goal with that
evidence. It never closes anything by itself.

Dormancy (code-run): after `goal_dormant_days` (default 3) with no activity, Muse asks the user once whether they
still want the goal; `goal_fade_days` (default 3) after that question was really delivered with no answer, it cancels
the goal. Activity means the user or an executor moved it; a nightly assessment or a passed-on event does not count.
Goals waiting on the user fade too. A future deadline, an active watch, a live assignment, a running owner or `no_fade`
holds a goal. A cancelled goal revives with `goal_update(status=active)`. Set
`no_fade` only on the user's explicit wish for a standing goal. The question's text is the `fade_question`
preference: when the user does not write in English, set it once in their language with `{title}`, `{days}` and
`{date}`. If the user mentions a dormant goal, update it with a note; that revives it.
