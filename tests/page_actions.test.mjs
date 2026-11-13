// Run: node --test tests/page_actions.test.mjs (no Hermes or React needed).
// The page's "in chat" buttons (#21) and the Runs/Findings views, rendered with a minimal hook runtime.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8');
const source = read('../ui/page.js');
const {makeMusePage, museDraftText, museComposerDraft} =
  new Function(source + '\nreturn {makeMusePage, museDraftText, museComposerDraft};')();

// Just enough React to render MusePage, run its effects and click its buttons.
function mount(request, draft) {
  const states = [], refs = [], effects = [];
  let index = 0, refIndex = 0, effectIndex = 0, dirty = true, tree = null;
  const React = {
    Fragment: 'fragment',
    createElement: (tag, props, ...children) => ({tag, props: props || {}, children: children.flat(Infinity)}),
    useState(init) {
      const k = index++;
      if (!(k in states)) states[k] = typeof init === 'function' ? init() : init;
      return [states[k], v => { const next = typeof v === 'function' ? v(states[k]) : v; if (next !== states[k]) { states[k] = next; dirty = true; } }];
    },
    useRef(init) { const k = refIndex++; if (!(k in refs)) refs[k] = {current: init}; return refs[k]; },
    useEffect(fn, deps) {
      const k = effectIndex++, old = effects[k];
      if (!old || !deps || deps.some((d, i) => d !== old.deps[i])) {
        old?.cleanup?.();
        effects[k] = {deps, cleanup: null, pending: fn};
      }
    },
  };
  const scope = {key: 'host:p', profile: 'p', connection: 'local', label: 'Local · p', current: () => true};
  const Page = makeMusePage(React, () => scope, request, draft);
  async function settle() {
    for (let round = 0; round < 50 && dirty; round++) {
      dirty = false; index = refIndex = effectIndex = 0;
      tree = Page();
      for (const e of effects) if (e?.pending) { const fn = e.pending; e.pending = null; e.cleanup = fn() || null; }
      await new Promise(resolve => setTimeout(resolve, 0));
    }
    return tree;
  }
  return {settle, unmount: () => effects.forEach(e => e?.cleanup?.())};
}

const nodes = (tree, found = []) => {
  for (const n of [tree].flat(Infinity)) if (n && typeof n === 'object') { found.push(n); nodes(n.children, found); }
  return found;
};
const text = node => node.children.map(c => typeof c === 'object' && c ? text(c) : (c === false || c == null ? '' : String(c))).join('');
const buttons = tree => nodes(tree).filter(n => n.tag === 'button');
const click = (tree, label) => {
  const b = buttons(tree).find(n => n.props['aria-label'] === label || text(n) === label);
  assert.ok(b, 'button ' + label + ' among ' + buttons(tree).map(text).join(' | '));
  return b.props.onClick({preventDefault() {}});
};
const panel = tree => nodes(tree).find(n => n.props.className === 'muse-compose');

const IDEA = {id: 'idea-1', title: 'Try a standing desk', rationale: 'Long sitting', created: 1};
const FINDING = {id: 'finding-1', kind: 'finding', title: 'Claimed it was sent without sending', tag: null,
  rules: ['claim_without_write'], turn: 's1:7', created: 1, expires: 2};
const RUN = {id: 'run-1', job: 'patrol', state: 'degraded', started: 1, ended: 2, items: 2, handled: 1,
  item_kinds: {notice: 2}, observed: 1, found: ['Build failed on main']};
function api(overrides = {}) {
  const data = {feed: [], ideas: [IDEA], goals: [], runs: [RUN], findings: [FINDING], ...overrides};
  return async path => {
    const name = path.slice(1).split(/[/?]/)[0];
    if (name === 'health') return {available: false};
    const items = data[name] || [];
    return {items, total: items.length, next_cursor: null, days: 7};
  };
}

test('the message names the object and asks Muse to read it first', () => {
  assert.equal(museDraftText({id: 'g1', metadata: {title: 'Ship  it'}}, 'goal', 'cancel'),
    'Please cancel Muse goal g1 "Ship it". Read its current state before changing anything.');
  assert.equal(museDraftText({id: 'f1', title: 'costs $& more'}, 'finding', 'dismiss'),
    'Please dismiss Muse finding f1 "costs $& more" as not useful. Read its current state before changing anything.');
  assert.match(museDraftText({id: 'x'}, 'idea', 'unknown'), /^I want to discuss or change Muse idea x\./);
});

test('Desktop drafts only into a focused chat of the same profile and connection, and reports failures', async () => {
  const calls = [];
  const host = (owner, stored, accepted = true) => ({
    state: {focusedSessionOwner: {get: () => owner}, focusedStoredSessionId: {get: () => stored}},
    composer: {insertText: async (id, value) => { calls.push([id, value]); return accepted; }},
  });
  const scope = {profile: 'p', connection: 'local', current: () => true};
  assert.deepEqual(await museComposerDraft(host({profile: 'p', connectionId: 'local'}, 'stored-1'), 'hi', scope), {ok: true});
  assert.deepEqual(calls, [['stored-1', 'hi']], 'addressed to the focused stored session');
  for (const [owner, stored] of [[{profile: 'other', connectionId: 'local'}, 's'], [{profile: 'p', connectionId: 'ssh'}, 's'],
    [{profile: 'p', connectionId: 'local'}, null], [null, 's']]) {
    const result = await museComposerDraft(host(owner, stored), 'hi', scope);
    assert.equal(result.ok, false); assert.ok(result.reason);
  }
  const refused = await museComposerDraft(host({profile: 'p', connectionId: 'local'}, 's', false), 'hi', scope);
  assert.equal(refused.ok, false); assert.ok(refused.reason);
  const moved = await museComposerDraft(host({profile: 'p', connectionId: 'local'}, 's'), 'hi', {...scope, current: () => false});
  assert.equal(moved.ok, false);
  assert.equal(calls.length, 2, 'nothing is inserted when the chat cannot be confirmed');
});

test('Dashboard (no composer): every in-chat button shows the message to copy', async () => {
  const page = mount(api(), null);
  let tree = await page.settle();
  click(tree, 'Ideas');
  tree = await page.settle();
  for (const label of ['Discuss idea in chat', 'Accept idea in chat']) assert.ok(buttons(tree).some(b => text(b) === label));
  await click(tree, 'Accept idea in chat');
  tree = await page.settle();
  const box = panel(tree);
  assert.ok(box, 'a click always shows a result');
  assert.match(text(box), /Copy it and paste it/);
  assert.equal(nodes(box).find(n => n.tag === 'textarea').props.value,
    'I accept Muse idea idea-1 "Try a standing desk"; please take it on. Read its current state before changing anything.');
  assert.ok(buttons(box).some(b => text(b) === 'Copy message'));
  page.unmount();
});

test('Desktop: a draft the chat accepted is confirmed; a refused one falls back to copy with the reason', async () => {
  for (const [result, expect] of [[{ok: true}, /Added to your chat/], [{ok: false, reason: 'No chat of this profile is open next to this page.'}, /No chat of this profile.*Copy it/]]) {
    const sent = [];
    const page = mount(api(), async value => { sent.push(value); return result; });
    let tree = await page.settle();
    click(tree, 'Findings');
    tree = await page.settle();
    await click(tree, 'Dismiss in chat');
    tree = await page.settle();
    assert.match(text(panel(tree)), expect);
    assert.equal(sent.length, 1);
    assert.match(sent[0], /^Please dismiss Muse finding finding-1 /);
    assert.equal(buttons(panel(tree)).some(b => text(b) === 'Copy message'), !result.ok);
    page.unmount();
  }
});

test('Runs and Findings list what background jobs did and what the review found; empty states explain', async () => {
  let page = mount(api(), null);
  let tree = await page.settle();
  click(tree, 'Runs');
  tree = await page.settle();
  const runs = text(nodes(tree).find(n => n.props['aria-label'] === 'Recent runs'));
  for (const part of ['Patrol', 'Partly done', 'Handled 1 of 2 (2 notices)', 'Observed 1 source item: Build failed on main']) assert.ok(runs.includes(part), part);
  click(tree, 'Findings');
  tree = await page.settle();
  const findings = text(nodes(tree).find(n => n.props['aria-label'] === 'Open findings'));
  for (const part of ['Claimed it was sent without sending', 'Agent gap', 'claimed done without a write', 'Turn s1:7']) assert.ok(findings.includes(part), part);
  page.unmount();
  page = mount(api({runs: [], findings: []}), null);
  tree = await page.settle();
  click(tree, 'Runs');
  tree = await page.settle();
  assert.match(text(nodes(tree).find(n => n.props.className === 'muse-empty')), /No runs in the last 7 days.*nothing to do/);
  click(tree, 'Findings');
  tree = await page.settle();
  assert.match(text(nodes(tree).find(n => n.props.className === 'muse-empty')), /No open findings.*14 days/);
  page.unmount();
});

test('both hosts are built from this page: Dashboard passes no draft, Desktop drafts only through museComposerDraft', () => {
  const dist = read('../dashboard/dist/index.js'), desktop = read('../desktop/plugin.js');
  assert.ok(dist.includes(source) && desktop.includes(source), 'run python ui/build.py');
  assert.ok(dist.includes('makeMusePage(React,useScope,request,null,profileAdmin)'));
  assert.match(desktop, /typeof host\.composer\?\.insertText==='function'[^]*museComposerDraft\(host,text,scope\)/);
  assert.deepEqual(source.match(/\bdraft\(/g), ['draft('], 'buttons go through compose(), never the host draft directly');
  assert.ok(source.includes('await draft(text, scope)'));
});
