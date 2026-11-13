(function () {
const SDK = window.__HERMES_PLUGIN_SDK__;
if (!SDK?.React || typeof SDK.fetchJSON !== 'function') return;
const React = SDK.React;
function key() { return location.origin + ':' + (new URLSearchParams(location.search).get('profile') || ''); }
function useScope() {
  const [value, setValue] = React.useState(key());
  React.useEffect(() => { const check=()=>setValue(key()); const timer=setInterval(check,100); window.addEventListener('popstate',check); return ()=>{clearInterval(timer);window.removeEventListener('popstate',check);}; }, []);
  const profile = new URLSearchParams(location.search).get('profile');
  return {key:value, profile, label:location.host + ' · ' + (profile || 'Serving profile'), current:()=>key()===value};
}
function request(path,scope) { return SDK.fetchJSON('/api/plugins/hermes-muse'+path+(path.includes('?')?'&':'?')+'profile=default&selected_profile='+encodeURIComponent(scope.profile)); }
const profileAdmin={list:()=>SDK.fetchJSON('/api/plugins/hermes-muse/profiles?profile=default')};
const MUSE_CSS = `
.muse-root{--muse-fg:var(--color-foreground,var(--dt-foreground,currentColor));--muse-card:color-mix(in srgb,var(--muse-fg) 4%,transparent);--muse-soft:color-mix(in srgb,var(--muse-fg) 86%,transparent);--muse-muted:color-mix(in srgb,var(--muse-fg) 70%,transparent);--muse-border:var(--color-border,var(--dt-border,color-mix(in srgb,currentColor 18%,transparent)));--muse-accent:var(--color-primary,var(--dt-primary,currentColor));--muse-accent-fg:var(--color-primary-foreground,var(--dt-primary-foreground,Canvas));--muse-tint:color-mix(in srgb,var(--muse-accent) 16%,transparent);--muse-ring:var(--color-ring,var(--dt-ring,currentColor));--muse-danger:var(--color-destructive,var(--dt-destructive,currentColor));--muse-warn:var(--color-warning,var(--dt-warning,currentColor));--muse-ok:var(--color-success,var(--dt-success,currentColor));--muse-hover:color-mix(in srgb,var(--muse-fg) 7%,transparent);--muse-radius:var(--radius-lg,var(--theme-radius,8px));--muse-ctl:36px;box-sizing:border-box;width:100%;max-width:880px;margin:0 auto;padding:clamp(16px,4vw,24px);font:inherit;line-height:1.55;color:var(--muse-fg);overflow-wrap:anywhere;word-break:break-word}
.muse-root *,.muse-root *::before,.muse-root *::after{box-sizing:border-box}
.muse-root :where(button,input,select){font:inherit;color:inherit}
.muse-root :focus-visible{outline:2px solid var(--muse-ring);outline-offset:2px}
.muse-root a{color:var(--muse-accent);text-decoration:underline;text-underline-offset:2px}
.muse-header{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 16px}
.muse-title{margin:0;font-size:1.5rem;line-height:1.3;font-weight:700}
.muse-meta{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;color:var(--muse-muted);font-size:.85rem}
.muse-profile{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px}
.muse-profile>*{margin:0}
.muse-pill{display:inline-flex;align-items:center;height:22px;line-height:1;padding:0 10px;border:1px solid var(--muse-border);border-radius:999px;color:var(--muse-muted);font-size:.75rem;white-space:nowrap}
.muse-select,.muse-input{height:var(--muse-ctl);padding:0 12px;border:1px solid var(--muse-border);border-radius:var(--muse-radius);background:var(--muse-card);max-width:100%}
.muse-search{position:relative;flex:1 1 220px;min-width:0;display:block}
.muse-search svg{position:absolute;left:12px;top:50%;width:16px;height:16px;margin-top:-8px;color:var(--muse-muted);pointer-events:none}
.muse-search .muse-input{width:100%;padding-left:36px}
.muse-input::placeholder{color:var(--muse-muted);opacity:1}
.muse-tabs{display:flex;flex-wrap:wrap;gap:2px;margin:16px 0;padding:2px;border:1px solid var(--muse-border);border-radius:calc(var(--muse-radius) + 2px);width:fit-content;max-width:100%}
.muse-tab,.muse-btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:var(--muse-ctl);padding:0 14px;border:1px solid transparent;border-radius:var(--muse-radius);background:transparent;cursor:pointer}
.muse-tab{height:30px;gap:6px;color:var(--muse-muted)}
.muse-tab:hover{background:var(--muse-hover);color:var(--muse-fg)}
.muse-tab[aria-pressed=true]{background:var(--muse-tint);color:var(--muse-accent);font-weight:600}
.muse-count{font-size:.72rem;font-weight:400;color:var(--muse-muted);font-variant-numeric:tabular-nums}
.muse-tab[aria-pressed=true] .muse-count{color:var(--muse-accent)}
.muse-btn:hover:not(:disabled){background:var(--muse-hover)}
.muse-btn.primary{background:var(--muse-accent);color:var(--muse-accent-fg)}
.muse-btn.primary:hover:not(:disabled){background:var(--muse-accent);filter:brightness(1.1)}
.muse-btn.secondary{border-color:var(--muse-border)}
.muse-btn.text{padding:0 8px;color:var(--muse-muted)}
.muse-btn.text:hover:not(:disabled){color:var(--muse-fg)}
.muse-btn:disabled{opacity:.5;cursor:default}
.muse-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0 0 16px}
.muse-chip{display:inline-flex;align-items:center;gap:4px;height:var(--muse-ctl);padding:0 4px 0 12px;border:1px solid var(--muse-border);border-radius:var(--muse-radius);background:var(--muse-card)}
.muse-list{margin:0;padding:0;list-style:none;border-top:1px solid var(--muse-border)}
.muse-list>li{border-bottom:1px solid var(--muse-border)}
.muse-list>li.dim{opacity:.6}
.muse-row{display:grid;grid-template-columns:minmax(0,1fr) auto;column-gap:16px;align-items:start;width:100%;padding:16px 8px;border:0;background:transparent;text-align:left;cursor:pointer;border-radius:var(--muse-radius)}
.muse-row:hover{background:var(--muse-hover)}
.muse-row.static{cursor:default}
.muse-row.static:hover{background:transparent}
.muse-compose{margin-top:12px;padding:12px 16px;border:1px solid var(--muse-border);border-radius:var(--muse-radius);background:var(--muse-card);font-size:.9rem}
.muse-compose p{margin:0 0 8px}
.muse-compose textarea{display:block;width:100%;min-height:4.5em;padding:8px 12px;border:1px solid var(--muse-border);border-radius:var(--muse-radius);background:transparent;resize:vertical;font:inherit;color:inherit}
.muse-compose .muse-idea-actions{margin-top:8px}
.muse-row-main{display:block;min-width:0}
.muse-row-side{display:block;min-width:4.5rem;text-align:right;color:var(--muse-muted);font-size:.8rem;white-space:nowrap}
.muse-row-title{display:block;font-weight:600;font-size:1rem}
.muse-row-text{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin-top:4px;color:var(--muse-soft);font-size:.9rem}
.muse-row-text.one{-webkit-line-clamp:1}
.muse-row-text.faint{color:var(--muse-muted)}
.muse-row-meta{display:block;margin-top:6px;color:var(--muse-muted);font-size:.8rem;min-height:1.2em}
.muse-badge{display:inline-flex;align-items:center;height:22px;padding:0 10px;border:1px solid var(--muse-border);border-radius:999px;font-size:.75rem;font-weight:600;white-space:nowrap;color:var(--muse-soft)}
.muse-badge.warn{background:var(--muse-warn);border-color:var(--muse-warn);color:var(--muse-accent-fg)}
.muse-badge.danger{background:var(--muse-danger);border-color:var(--muse-danger);color:var(--muse-accent-fg)}
.muse-badge.ok{color:var(--muse-ok);border-color:currentColor}
.muse-sect,.muse-fold{display:flex;align-items:center;gap:8px;width:100%;min-height:var(--muse-ctl);margin:0 0 8px;padding:0 8px;font-weight:600;font-size:.95rem}
.muse-fold{margin:24px 0 0;padding:0 7px;border:1px solid var(--muse-border);border-radius:var(--muse-radius);background:var(--muse-card);cursor:pointer;text-align:left}
.muse-fold:hover{background:var(--muse-hover)}
.muse-fold[aria-expanded=true]{border-bottom-left-radius:0;border-bottom-right-radius:0}
.muse-fold svg{width:16px;height:16px;flex:none;transition:transform .15s}
.muse-fold[aria-expanded=true] svg{transform:rotate(90deg)}
.muse-fold .muse-hint{margin-left:auto;font-weight:400;font-size:.8rem;color:var(--muse-muted)}
.muse-fold svg{margin-left:4px}
.muse-card{margin:0 0 16px;padding:4px 16px;border:1px solid var(--muse-border);border-radius:calc(var(--muse-radius) + 2px);background:var(--muse-card)}
.muse-card-head{margin:12px 0 0;font-size:.95rem;font-weight:600;text-transform:none;letter-spacing:normal}
.muse-for{display:block;margin-bottom:2px;color:var(--muse-muted);font-size:.8rem}
.muse-idea{padding:12px 0;border-bottom:1px solid var(--muse-border)}
.muse-idea:last-child{border-bottom:0}
.muse-idea-actions{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:12px}
.muse-empty{margin:24px 0;padding:24px;border:1px dashed var(--muse-border);border-radius:var(--muse-radius);text-align:center;color:var(--muse-soft)}
.muse-empty strong{display:block;margin-bottom:4px;color:var(--muse-fg)}
.muse-empty .muse-btn{margin-top:12px}
.muse-alert{border-style:solid;border-color:var(--muse-danger)}
.muse-health{margin:12px 0;padding:12px 16px;border:1px solid var(--muse-border);border-radius:var(--muse-radius);background:var(--muse-card)}
.muse-health.high{border-color:var(--muse-danger)}
.muse-health.medium{border-color:var(--muse-warn)}
.muse-health summary{display:flex;flex-wrap:wrap;align-items:center;gap:8px;cursor:pointer}
.muse-health ul{margin:8px 0 0;padding-left:20px;font-size:.85rem;color:var(--muse-soft)}
.muse-article-head{margin:0 0 24px;padding-bottom:16px;border-bottom:1px solid var(--muse-border)}
.muse-detail-title{margin:16px 0 8px;font-size:1.5rem;line-height:1.3}
.muse-detail-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:24px;padding-top:16px;border-top:1px solid var(--muse-border)}
.muse-prose{max-width:68ch}
.muse-section{margin:24px 0 0}
.muse-sh{margin:0 0 8px;font-size:.8rem;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--muse-muted)}
.muse-plain{margin:0;padding-left:20px;list-style:disc}
.muse-src-path{color:var(--muse-muted);font-size:.85rem}
.muse-md>:first-child{margin-top:0}.muse-md>:last-child{margin-bottom:0}
.muse-md h1,.muse-md h2,.muse-md h3,.muse-md h4,.muse-md h5,.muse-md h6{margin:24px 0 8px;line-height:1.3;font-weight:700;text-transform:none;letter-spacing:normal}
.muse-md h1{font-size:1.4rem}.muse-md h2{font-size:1.2rem}.muse-md h3{font-size:1.05rem}.muse-md h4,.muse-md h5,.muse-md h6{font-size:1rem}
.muse-md p,.muse-md ul,.muse-md ol,.muse-md blockquote,.muse-md pre,.muse-md table{margin:0 0 12px}
.muse-md ul,.muse-md ol{padding-left:24px}
.muse-md ul{list-style:disc}.muse-md ol{list-style:decimal}.muse-md ul ul{list-style:circle}.muse-md li::marker{color:var(--muse-muted)}
.muse-md li>ul,.muse-md li>ol{margin:4px 0 0}
.muse-md blockquote{padding:4px 12px;border-left:3px solid var(--muse-border);color:var(--muse-soft)}
.muse-md code{color:var(--muse-fg);padding:1px 5px;border-radius:4px;background:var(--muse-hover);font-family:var(--theme-font-mono,var(--dt-font-mono,ui-monospace,monospace));font-size:.875em}
.muse-md pre{padding:12px;border:1px solid var(--muse-border);border-radius:var(--muse-radius);background:var(--muse-card);overflow-x:auto;max-width:100%}
.muse-md pre code{padding:0;background:none;white-space:pre;color:var(--muse-fg)}
.muse-md hr{border:0;border-top:1px solid var(--muse-border);margin:16px 0}
.muse-tablewrap{overflow-x:auto;max-width:100%;margin:0 0 12px}
.muse-md table{border-collapse:collapse;margin:0}
.muse-md th,.muse-md td{padding:6px 10px;border:1px solid var(--muse-border);text-align:left}
.muse-md th{background:var(--muse-hover)}
.muse-admin{margin:16px 0;padding:12px 16px;border:1px solid var(--muse-border);border-radius:var(--muse-radius);background:var(--muse-card);font-size:.9rem}
.muse-admin p{margin:8px 0 0}
.muse-sub{margin:4px 0 0;color:var(--muse-muted);font-size:.85rem}
`;

const MUSE_MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function museTime(value, withTime) {
  if (typeof value !== 'number' || !isFinite(value)) return '';
  const d = new Date(value * 1000), p = n => String(n).padStart(2, '0');
  return MUSE_MONTHS[d.getMonth()] + ' ' + d.getDate() + (withTime ? ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) : '');
}

function museSafeUrl(url) { return /^(https?:|mailto:)/i.test(url) ? url : null; }

// Inline Markdown to React nodes. Raw HTML is never interpreted: React escapes every string.
function museInline(h, text, key) {
  const re = /(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)|!?\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)|\*\*([\s\S]+?)\*\*|~~([\s\S]+?)~~|\*([^*\s][^*]*?)\*|(https?:\/\/[^\s<>)\]]+)/g;
  const out = [];
  let last = 0, m, n = 0;
  const link = (label, url, k) => {
    const safe = museSafeUrl(url);
    return safe ? h('a', {key:k, href:safe, target:'_blank', rel:'noopener noreferrer'}, label) : label;
  };
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const k = key + ':' + n++;
    if (m[2] !== undefined) out.push(h('code', {key:k}, m[2].trim()));
    else if (m[4] !== undefined) out.push(link(museInline(h, m[3] || m[4], k), m[4], k));
    else if (m[5] !== undefined) out.push(h('strong', {key:k}, museInline(h, m[5], k)));
    else if (m[6] !== undefined) out.push(h('del', {key:k}, museInline(h, m[6], k)));
    else if (m[7] !== undefined) out.push(h('em', {key:k}, museInline(h, m[7], k)));
    else out.push(link(m[8], m[8], k));
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const museNorm = t => String(t || '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
// Drop a leading H1 that repeats the title; Feed files also end with a "## Sources" list shown separately.
function museBody(body, title, feed) {
  let text = String(body || '');
  const b = museNorm(title);
  for (let first, a; (first = /^\s*#\s+(.+?)\s*#*\s*(?:\n+|$)/.exec(text)) && b && ((a = museNorm(first[1])) === b || (Math.min(a.length, b.length) >= 8 && (a.includes(b) || b.includes(a))));) text = text.slice(first[0].length);
  if (!feed) return text;
  const marker = '\n\n## Sources\n', at = text.lastIndexOf(marker);
  if (at >= 0 && text.slice(at + marker.length).split('\n').every(line => !line || line.startsWith('- '))) text = text.slice(0, at);
  return text;
}

function museSource(h, source, key) {
  const safe = museSafeUrl(source);
  let url;
  try { url = safe && new URL(safe); } catch (e) { url = null; }
  if (!url || url.protocol === 'mailto:') return safe ? h('a', {href:safe, target:'_blank', rel:'noopener noreferrer'}, source.replace(/^mailto:/i, '')) : source;
  let path = url.pathname === '/' ? '' : url.pathname + url.search;
  try { path = decodeURIComponent(path); } catch (e) {}
  return [h('a', {key:key + 'a', href:safe, target:'_blank', rel:'noopener noreferrer'}, url.hostname.replace(/^www\./, '')), path && h('span', {key:key + 'p', className:'muse-src-path'}, ' ' + path.slice(0, 60))];
}

function museMarkdown(h, source) {
  const lines = String(source || '').replace(/\r\n?/g, '\n').split('\n');
  const item = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
  const cells = line => line.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
  let key = 0;
  function list(i, indent) {
    const ordered = /\d/.test(item.exec(lines[i])[2]);
    const items = [];
    while (i < lines.length) {
      const m = item.exec(lines[i]);
      if (!m || m[1].length < indent || (m[1].length > indent)) break;
      if (/\d/.test(m[2]) !== ordered) break;
      const children = [museInline(h, m[3], 'li' + key++)];
      i++;
      while (i < lines.length) {
        const next = item.exec(lines[i]);
        if (next && next[1].length > indent) { const sub = list(i, next[1].length); children.push(sub.node); i = sub.next; }
        else if (lines[i].trim() && !next && /^\s{2,}\S/.test(lines[i])) { children.push(' ', museInline(h, lines[i].trim(), 'lc' + key++)); i++; }
        else break;
      }
      items.push(h('li', {key:'i' + key++}, ...children));
    }
    return {node:h(ordered ? 'ol' : 'ul', {key:'l' + key++}, ...items), next:i};
  }
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    let m;
    if (!line.trim()) { i++; continue; }
    if ((m = /^\s*(`{3,}|~{3,})/.exec(line))) {
      const body = [];
      for (i++; i < lines.length && !lines[i].trim().startsWith(m[1]); i++) body.push(lines[i]);
      i++;
      blocks.push(h('pre', {key:'b' + key++}, h('code', null, body.join('\n'))));
    } else if ((m = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line))) {
      blocks.push(h('h' + m[1].length, {key:'b' + key++}, museInline(h, m[2], 'h' + key)));
      i++;
    } else if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) { blocks.push(h('hr', {key:'b' + key++})); i++; }
    else if (/^\s*>/.test(line)) {
      const quote = [];
      for (; i < lines.length && /^\s*>/.test(lines[i]); i++) quote.push(lines[i].replace(/^\s*> ?/, ''));
      blocks.push(h('blockquote', {key:'b' + key++}, museMarkdown(h, quote.join('\n'))));
    } else if (line.includes('|') && i + 1 < lines.length && /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/.test(lines[i + 1])) {
      const head = cells(line), rows = [];
      for (i += 2; i < lines.length && lines[i].trim() && lines[i].includes('|'); i++) rows.push(cells(lines[i]));
      blocks.push(h('div', {key:'b' + key++, className:'muse-tablewrap'}, h('table', null,
        h('thead', null, h('tr', null, ...head.map((c, j) => h('th', {key:j}, museInline(h, c, 'th' + j))))),
        h('tbody', null, ...rows.map((r, j) => h('tr', {key:j}, ...head.map((_, k) => h('td', {key:k}, museInline(h, r[k] || '', 'td' + j + k)))))))));
    } else if (item.test(line)) {
      const sub = list(i, item.exec(line)[1].length);
      blocks.push(sub.node); i = sub.next;
    } else {
      const para = [];
      for (; i < lines.length && lines[i].trim() && !/^\s*(#{1,6}\s|>|`{3,}|~{3,})/.test(lines[i]) && !item.test(lines[i]); i++) para.push(lines[i].trim());
      blocks.push(h('p', {key:'b' + key++}, museInline(h, para.join(' '), 'p' + key)));
    }
  }
  return blocks;
}

// The message a button asks the user to send to Muse in chat; the change itself goes through muse_manage there.
const MUSE_ASKS = {discuss:'I want to discuss or change {}.', feedback:'I have feedback on {}.', cancel:'Please cancel {}.',
  accept:'I accept {}; please take it on.', dismiss:'Please dismiss {} as not useful.', useful:'Please mark {} as useful.'};
function museDraftText(item, kind, intent) {
  const name = String(item.title || item.metadata?.title || '').replace(/\s+/g, ' ').trim();
  const label = 'Muse ' + kind + ' ' + item.id + (name ? ' "' + (name.length > 120 ? name.slice(0, 119) + '…' : name) + '"' : '');
  return (MUSE_ASKS[intent] || MUSE_ASKS.discuss).replace('{}', () => label) + ' Read its current state before changing anything.';
}

// Desktop only: put the text into the message box of the focused chat, when that chat belongs to the profile and
// connection shown here. insertText reaches a mounted composer by session address and fails closed.
async function museComposerDraft(host, text, scope) {
  if (!scope.current()) return {ok:false, reason:'The connection or profile changed.'};
  const owner = host.state.focusedSessionOwner.get(), stored = host.state.focusedStoredSessionId.get();
  const same = (a, b) => (a || 'default') === (b || 'default');
  if (!stored || !owner || !same(owner.profile, scope.profile) || owner.connectionId !== scope.connection)
    return {ok:false, reason:'No chat of this profile is open next to this page.'};
  return await host.composer.insertText(stored, text) ? {ok:true} : {ok:false, reason:'The chat did not accept the text.'};
}

const MUSE_JOBS = {intake:'Intake', patrol:'Patrol', nightly:'Nightly review', feed:'Feed research'};
const MUSE_RUN_STATES = {running:['Running',''], ok:['Completed','ok'], degraded:['Partly done','warn'], failed:['Failed','danger'], abandoned:['Lost','danger']};
const MUSE_RULES = {claim_without_write:'claimed done without a write', tool_failure_unretried:'failed tool not retried',
  user_correction:'user corrected the agent', unrecorded_need:'need not recorded'};

function makeMusePage(React, useScope, request, draft, profileAdmin) {
  const h = React.createElement;
  return function MusePage() {
    const hostScope = useScope();
    const [profiles, setProfiles] = React.useState([]);
    const [selected, setSelected] = React.useState(null);
    const [managementMessage, setManagementMessage] = React.useState('');
    const selectionRef = React.useRef(selected);
    selectionRef.current = selected;
    const selectedRow = profiles.find(row=>row.name===selected);
    const scope = profileAdmin ? {...hostScope, profile:selected, key:hostScope.key+':'+selected,
      label:selected ? hostScope.label+' · '+selected : 'Select a profile on this Hermes host',
      current:()=>hostScope.current() && selectionRef.current===selected} : hostScope;
    React.useEffect(()=>{
      if (!profileAdmin) return;
      let active=true;setSelected(null);setProfiles([]);setManagementMessage('');
      profileAdmin.list().then(value=>{if(active)setProfiles(value.profiles);}).catch(e=>{if(active)setManagementMessage(String(e.message||e));});
      return ()=>{active=false;};
    },[hostScope.key]);
    const [tab, setTab] = React.useState('feed');
    const [draftQuery, setDraftQuery] = React.useState('');
    const [query, setQuery] = React.useState('');
    const [topic, setTopic] = React.useState('');
    const [topicLabel, setTopicLabel] = React.useState('');
    const [page, setPage] = React.useState(null);
    const [closed, setClosed] = React.useState(null);
    const [closedOpen, setClosedOpen] = React.useState(false);
    const [titles, setTitles] = React.useState({});
    const [counts, setCounts] = React.useState({});
    const [article, setArticle] = React.useState(null);
    const [error, setError] = React.useState('');
    const [busy, setBusy] = React.useState(false);
    const [health, setHealth] = React.useState(null);
    const [composed, setComposed] = React.useState(null);
    const generation = React.useRef(0);
    const identity = scope.key + ':' + tab + ':' + query + ':' + topic;
    const active = React.useRef(identity);
    active.current = identity;
    const ready = !profileAdmin || (selectedRow && selectedRow.enabled);
    React.useEffect(()=>{const timer=setTimeout(()=>setQuery(draftQuery.trim()),250);return ()=>clearTimeout(timer);},[draftQuery]);
    async function fetchList(path, extra, cursor) {
      const params = new URLSearchParams({limit: '25', ...extra});
      if (cursor) params.set('cursor', cursor);
      return request(path + '?' + params, scope);
    }
    async function load(cursor) {
      if (!ready) {setBusy(false);return;}
      const token = ++generation.current, captured = identity;
      setBusy(true); setError('');
      try {
        const extra = {};
        if (tab === 'feed') { if (query) extra.query = query; if (topic) extra.topic = topic; }
        if (tab === 'goals') extra.status = 'open';
        const value = await fetchList('/' + tab, extra, cursor);
        if (tab === 'ideas') {
          // Titles only label the groups; a failure here must not hide the ideas.
          try {const goals = await fetchList('/goals', {status:'open'}); setTitles(Object.fromEntries(goals.items.map(g=>[g.id,g.title])));} catch (e) {}
        }
        if (generation.current !== token || active.current !== captured || !scope.current()) return;
        setPage({ ...value, identity: captured, items: cursor ? [...(page?.items || []), ...value.items] : value.items });
        if (!cursor && !(tab === 'feed' && (query || topic))) setCounts(c=>({...c,[tab]:value.total}));
      } catch (e) { if (active.current === captured && scope.current()) setError(String(e.message || e)); }
      finally { if (generation.current === token) setBusy(false); }
    }
    async function loadClosed(cursor) {
      const captured = identity;
      setBusy(true); setError('');
      try {
        const value = await fetchList('/goals', {status:'closed'}, cursor);
        if (active.current !== captured || !scope.current()) return;
        setClosed(prev=>({...value, identity: captured, items: cursor ? [...(prev?.items || []), ...value.items] : value.items}));
      } catch (e) { if (active.current === captured && scope.current()) setError(String(e.message || e)); }
      finally { if (active.current === captured) setBusy(false); }
    }
    React.useEffect(() => { setPage(null); setClosed(null); setClosedOpen(false); setArticle(null); setComposed(null); load(); return () => { generation.current++; }; }, [identity, ready]);
    React.useEffect(() => {
      if (!ready) return;
      let live = true;
      setCounts({});
      Promise.all([['feed',{}],['ideas',{}],['goals',{status:'open'}],['closed',{status:'closed'}],['runs',{}],['findings',{}]].map(([name,extra])=>
        request('/'+(name==='closed'?'goals':name)+'?'+new URLSearchParams({limit:'1',...extra}), scope).then(v=>live&&scope.current()&&setCounts(c=>({...c,[name]:v.total}))).catch(()=>{})));
      return ()=>{live=false;};
    }, [scope.key, ready]);
    React.useEffect(() => {
      if (!ready) return;
      let live = true;
      setHealth(null);
      request('/health', scope).then(v=>live&&scope.current()&&setHealth(v)).catch(()=>{});
      return ()=>{live=false;};
    }, [scope.key, ready]);
    async function open(item, continuation) {
      const captured = identity, token = ++generation.current;
      setBusy(true); setError('');
      try {
        const params = new URLSearchParams();
        if (continuation) { params.set('offset', article.next_offset); params.set('revision', article.revision); }
        const value = await request('/' + tab + '/' + encodeURIComponent(item.id) + '?' + params, scope);
        if (generation.current !== token || active.current !== captured || !scope.current()) return;
        setArticle({...value, identity: captured, body: continuation ? article.body + value.body : value.body});
      } catch (e) { if (active.current === captured && scope.current()) setError(String(e.message || e)); }
      finally { if (active.current === captured) setBusy(false); }
    }
    // Every "in chat" button: the host's draft writes into a chat where it can; otherwise, or when that fails, the
    // message is shown here to copy. Either way the click shows its result on this page.
    async function compose(item, kind, intent) {
      const text = museDraftText(item, kind, intent), id = item.id;
      setComposed({id, text, working:Boolean(draft)});
      let result = {ok:false, reason:''};
      if (draft) {
        try { result = (await draft(text, scope)) || result; } catch (e) { result = {ok:false, reason:String(e.message || e)}; }
      }
      setComposed(c => c && c.id === id && c.text === text ? {id, text, ok:Boolean(result.ok), reason:result.reason || ''} : c);
    }
    async function copy(text) {
      let note = 'Copied. Paste it into your conversation with Muse.';
      try { await globalThis.navigator.clipboard.writeText(text); } catch (e) { note = 'Copying is not available here: select the text above and copy it.'; }
      setComposed(c => c && c.text === text ? {...c, copied:note} : c);
    }
    const currentPage = page?.identity === identity ? page : null;
    const currentClosed = closed?.identity === identity ? closed : null;
    const currentArticle = article?.identity === identity ? article : null;
    const button = (label, onClick, disabled=false, variant='secondary', extra) => h('button', {type:'button', className:'muse-btn '+variant, onClick, disabled, ...extra}, label);
    const badge = (label, tone) => h('span', {className:'muse-badge'+(tone ? ' '+tone : '')}, label);
    const empty = (title, text, action, alert) => h('div', {className:'muse-empty'+(alert ? ' muse-alert' : ''), role:alert ? 'alert' : undefined}, h('strong', null, title), text, action);
    const goalState = g => g.status === 'done' ? ['Done','ok'] : g.status === 'cancelled' ? ['Cancelled',''] : g.waiting_user ? ['Needs you','warn'] : g.blocked ? ['Blocked','danger'] : ['In progress',''];
    const plural = (n, word) => n + ' ' + word + (n === 1 ? '' : 's');
    const icon = (paths, extra) => h('svg', {viewBox:'0 0 16 16', fill:'none', stroke:'currentColor', strokeWidth:2, strokeLinecap:'round', strokeLinejoin:'round', 'aria-hidden':'true', ...extra}, ...paths);
    // Two-column row: text on the left, a fixed right column (date or status) aligned to the top.
    const row = (item, index, side, text, meta, onOpen, style={}) => {
      const id = 'muse-' + tab + '-' + index;
      return h('li', {key:item.id, className:style.dim ? 'dim' : undefined},
        h('button', {type:'button', className:'muse-row', onClick:onOpen, 'aria-labelledby':id+'-t', 'aria-describedby':id+'-d'},
          h('span', {className:'muse-row-main'},
            h('span', {id:id+'-t', className:'muse-row-title'}, item.title || item.id),
            text && h('span', {id:id+'-d', className:'muse-row-text'+(style.one ? ' one' : '')+(style.faint ? ' faint' : '')}, text),
            h('span', {className:'muse-row-meta'}, meta)),
          h('span', {className:'muse-row-side'}, side)));
    };
    const composePanel = id => composed && composed.id === id && h('div', {className:'muse-compose', role:'status'},
      h('p', null, composed.working ? 'Adding the message to your chat…' : composed.ok ?
        [h('strong', {key:'t'}, 'Added to your chat. '), 'It is waiting in the message box of the chat you last used in this profile: switch to that chat to review and send it.'] :
        [h('strong', {key:'t'}, 'Send this message to Muse in chat. '), composed.reason ? composed.reason + ' ' : '', 'Copy it and paste it into your conversation with Muse in this profile.']),
      h('textarea', {readOnly:true, value:composed.text, rows:3, 'aria-label':'Message for Muse', onFocus:e=>e.target.select()}),
      h('div', {className:'muse-idea-actions'},
        !composed.ok && !composed.working && button('Copy message', ()=>copy(composed.text), false, 'primary'),
        button('Close', ()=>setComposed(null), false, 'text'),
        composed.copied && h('span', {className:'muse-sub'}, composed.copied)));
    const goalRow = (g, i) => {
      const [label, tone] = goalState(g), isOpen = g.status === 'active';
      const meta = isOpen ? [g.next_check_at ? 'Next check ' + museTime(g.next_check_at, true) : '', g.deadline ? (g.next_check_at ? ' · ' : '') + 'Due ' + museTime(g.deadline) : ''] :
        (g.status === 'done' ? 'Completed ' : 'Cancelled ') + museTime(g.updated);
      const text = g.blocked ? 'Blocked: ' + g.blocked : g.latest_progress ? 'Latest: ' + g.latest_progress.text : 'No updates yet';
      return row(g, i, badge(label, tone), text, meta, ()=>open(g), {one:true, dim:!isOpen, faint:!g.blocked && !g.latest_progress});
    };

    let content;
    if (currentArticle) {
      const md = currentArticle.metadata || {};
      const goal = currentArticle.kind === 'goal';
      const [label, tone] = goalState(md);
      const sources = (md.sources || []).filter(s => typeof s === 'string');
      content = h('article', null,
        h('div', {className:'muse-article-head'},
          button('← Back to list', ()=>setArticle(null), false, 'text'),
          h('h2', {className:'muse-detail-title'}, md.title || currentArticle.id),
          h('div', {className:'muse-meta'}, ...(goal ?
            [badge(label, tone), md.owner && badge('Owner: ' + md.owner.kind), md.deadline && h('span',null,'Due ' + museTime(md.deadline)), md.next_check_at && md.status === 'active' && h('span',null,'Next check ' + museTime(md.next_check_at, true))] :
            [md.created && h('span',null,museTime(md.created)), sources.length > 0 && h('span',null,plural(sources.length, 'source'))]))),
        h('div', {className:'muse-prose'},
          goal && md.blocked && h('section', {className:'muse-section'}, h('h3', {className:'muse-sh'}, 'Blocked'), h('div', {className:'muse-md'}, museMarkdown(h, md.blocked))),
          h('div', {className:'muse-md'}, museMarkdown(h, museBody(currentArticle.body, md.title, !goal))),
          currentArticle.next_offset != null && h('div', {className:'muse-detail-actions'}, button('Continue article',()=>open(currentArticle,true),busy)),
          goal && md.owner && h('section', {className:'muse-section'}, h('h3', {className:'muse-sh'}, 'Owner'), h('div', null, md.owner.kind + ' · ' + md.owner.id)),
          goal && Array.isArray(md.progress) && md.progress.length > 0 && h('section', {className:'muse-section'}, h('h3', {className:'muse-sh'}, 'Progress'),
            h('ul', {className:'muse-plain'}, ...[...md.progress].reverse().map((p,i)=>h('li',{key:i},h('span',{className:'muse-sub'},museTime(p.at,true)+' — '),p.text)))),
          sources.length > 0 && h('section', {className:'muse-section'}, h('h3', {className:'muse-sh'}, 'Sources'),
            h('ul', {className:'muse-plain'}, ...sources.map((s,i)=>h('li',{key:i}, museSource(h, s, 's'+i))))),
          h('div', {className:'muse-detail-actions'},
            button(goal?'Discuss or change this goal':'Give feedback in chat',()=>compose(currentArticle,currentArticle.kind,goal?'discuss':'feedback'),busy),
            goal && md.status === 'active' && button('Cancel goal in chat',()=>compose(currentArticle,'goal','cancel'),busy)),
          composePanel(currentArticle.id)));
    } else if (!currentPage) {
      content = error ? null : busy ? h('p', {role:'status', className:'muse-sub'}, 'Loading…') : null;
    } else if (tab === 'feed') {
      content = currentPage.items.length === 0 ?
        empty(query || topic ? 'No matching articles' : 'No articles yet', query || topic ? 'Try a different search or clear the filters.' : 'New Feed articles will appear here.') :
        h('ul', {className:'muse-list', 'aria-label':'Items'}, ...currentPage.items.map((item,i)=>row(item, i, museTime(item.created), item.why, item.source_count ? plural(item.source_count, 'source') : '', ()=>open(item))));
    } else if (tab === 'ideas') {
      const groups = [];
      for (const item of currentPage.items) {
        const name = item.goal_id ? (titles[item.goal_id] || 'Related goal') : '';
        const group = groups.find(g=>g.name === name) || (groups.push({name, items:[]}), groups.at(-1));
        group.items.push(item);
      }
      content = currentPage.items.length === 0 ?
        empty('No ideas yet', 'Ideas are suggested by the nightly review from your active goals. New suggestions will appear here.' + (currentPage.last_review_at ? ' Last review: ' + museTime(currentPage.last_review_at, true) + '.' : ' The nightly review has not run yet.')) :
        groups.map(group=>{
          const single = group.items.length === 1;
          return h('section', {key:group.name || 'independent', className:'muse-card', 'aria-label':group.name || 'Independent ideas'},
            !single && h('h3', {className:'muse-card-head'}, group.name || 'Independent ideas'),
            ...group.items.map(item=>h('div', {key:item.id, className:'muse-idea'},
              single && group.name && h('span', {className:'muse-for'}, 'For: ' + group.name),
              h('span', {className:'muse-row-title'}, item.title),
              h('span', {className:'muse-row-text'}, item.rationale || item.why),
              item.source_count > 0 && h('span', {className:'muse-row-meta'}, plural(item.source_count, 'source')),
              h('div', {className:'muse-idea-actions'},
                item.goal_id && button('Explore topic',()=>{setTab('feed');setTopic(item.goal_id);setTopicLabel(group.name);}),
                button('Discuss idea in chat',()=>compose(item,'idea','discuss')),
                button('Accept idea in chat',()=>compose(item,'idea','accept'),false,'primary')),
              composePanel(item.id))));
        });
    } else if (tab === 'runs') {
      content = currentPage.items.length === 0 ?
        empty('No runs in the last ' + currentPage.days + ' days', 'Background jobs (intake, patrol, nightly review, Feed research) are listed here when they had work. A check with nothing to do leaves no record.') :
        h('ul', {className:'muse-list', 'aria-label':'Recent runs'}, ...currentPage.items.map(r=>{
          const [label, tone] = MUSE_RUN_STATES[r.state] || [r.state, ''];
          const kinds = Object.entries(r.item_kinds || {}).map(([k,n])=>plural(n, k)).join(', ');
          const did = r.items === undefined ? 'No work packet recorded.' :
            (r.items ? 'Handled ' + r.handled + ' of ' + r.items + (kinds ? ' (' + kinds + ')' : '') + '.' : 'Checked sources.') +
            (r.observed ? ' Observed ' + plural(r.observed, 'source item') + (r.found?.length ? ': ' + r.found.join('; ') : '') + '.' : '');
          return h('li', {key:r.id}, h('div', {className:'muse-row static'},
            h('span', {className:'muse-row-main'},
              h('span', {className:'muse-row-title'}, MUSE_JOBS[r.job] || r.job || 'Run'),
              h('span', {className:'muse-row-text'}, did),
              h('span', {className:'muse-row-meta'}, (r.started ? 'Started ' + museTime(r.started, true) : '') + (r.ended ? (r.started ? ' · ' : '') + 'ended ' + museTime(r.ended, true) : ''))),
            h('span', {className:'muse-row-side'}, badge(label, tone))));
        }));
    } else if (tab === 'findings') {
      content = currentPage.items.length === 0 ?
        empty('No open findings', 'The nightly review files a finding when a recent conversation turn shows the assistant missed something. Open findings are listed here until you resolve or dismiss them, or for 14 days.') :
        h('ul', {className:'muse-list', 'aria-label':'Open findings'}, ...currentPage.items.map(f=>h('li', {key:f.id}, h('div', {className:'muse-row static'},
          h('div', {className:'muse-row-main'},
            h('span', {className:'muse-row-title'}, f.title || f.id),
            h('span', {className:'muse-row-text'}, (f.tag === 'friction' ? 'Friction (a suggestion)' : 'Agent gap') + (f.rules?.length ? ' · ' + f.rules.map(r=>MUSE_RULES[r] || r).join(', ') : '')),
            h('span', {className:'muse-row-meta'}, (f.turn ? 'Turn ' + f.turn : '') + (f.expires ? (f.turn ? ' · ' : '') + 'dismissed automatically ' + museTime(f.expires) : '')),
            h('div', {className:'muse-idea-actions'},
              button('Dismiss in chat',()=>compose(f,'finding','dismiss')),
              button('Mark useful in chat',()=>compose(f,'finding','useful')),
              button('Discuss in chat',()=>compose(f,'finding','discuss'),false,'text')),
            composePanel(f.id)),
          h('span', {className:'muse-row-side'}, museTime(f.created))))));
    } else {
      content = h(React.Fragment, null,
        h('h3', {className:'muse-sect'}, 'Active', h('span', {className:'muse-count'}, currentPage.total)),
        currentPage.items.length === 0 ? empty('No open goals', 'Goals you agree on with Muse appear here while they are in progress.') :
          h('ul', {className:'muse-list', 'aria-label':'Open goals'}, ...currentPage.items.map(goalRow)),
        h('button', {type:'button', className:'muse-fold', 'aria-expanded':closedOpen, onClick:()=>{const next=!closedOpen;setClosedOpen(next);if(next&&!closed)loadClosed();}},
          h('span',null,'Done and cancelled'), counts.closed !== undefined ? h('span',{className:'muse-count'},counts.closed) : null,
          h('span', {className:'muse-hint'}, closedOpen ? 'Hide' : 'Show'), icon([h('path',{key:'p',d:'M6 3l5 5-5 5'})])),
        closedOpen && currentClosed && (currentClosed.items.length === 0 ? empty('Nothing here yet', 'Completed and cancelled goals will be listed here.') :
          h('ul', {className:'muse-list', 'aria-label':'Closed goals'}, ...currentClosed.items.map(goalRow))),
        closedOpen && currentClosed?.next_cursor && button('Load more closed goals',()=>loadClosed(currentClosed.next_cursor),busy,'text'));
    }
    // Last health check (muse/health.json); Dashboard and Desktop never run one.
    const healthPanel = report => {
      if (report.available === false) return h('section', {className:'muse-health', 'aria-label':'Muse health'}, h('span', {className:'muse-sub'}, 'Health: no check has run in this profile yet.'));
      const items = (report.invariants || []).filter(f=>f.level !== 'ok').sort((a,b)=>['info','low','medium','high'].indexOf(b.level)-['info','low','medium','high'].indexOf(a.level));
      const tone = {high:'danger', medium:'warn', ok:'ok'}[report.level] || '';
      return h('section', {className:'muse-health '+(report.level||''), 'aria-label':'Muse health'},
        h('details', {open:report.level === 'high'},
          h('summary', null, h('strong', null, 'Health'), badge(report.level || 'unknown', tone),
            h('span', {className:'muse-sub'}, 'checked ' + new Date(report.generated_at).toLocaleString() + (items.length ? ' · ' + plural(items.length, 'health item') : ''))),
          items.length > 0 && h('ul', null, ...items.map(f=>h('li', {key:f.id}, h('strong', null, f.level + ' ' + f.id), ': ' + f.detail + (f.fix ? ' — Fix: ' + f.fix : ''))))));
    };
    const label = {feed:'Feed', ideas:'Ideas', goals:'Goals', runs:'Runs', findings:'Findings'};
    const state = selectedRow && (selectedRow.enabled ? 'Enabled' : selectedRow.installed ? 'Disabled' : 'Not installed');
    return h('main', {className:'muse-root'},
      h('style', null, MUSE_CSS),
      h('header', {className:'muse-header'},
        h('h1', {className:'muse-title'}, 'Muse'),
        h('div', {className:'muse-profile'}, ...(profileAdmin ? [
          h('select',{className:'muse-select','aria-label':'Profile',value:selected||'',onChange:e=>{setSelected(e.target.value||null);setDraftQuery('');setQuery('');setTopic('');setManagementMessage('');}},
            h('option',{value:''},'Choose a profile…'),
            ...profiles.map(row=>h('option',{key:row.name,value:row.name},row.name))),
          selectedRow && h('span',{className:'muse-pill',title:'Managed by Hermes plugin management'},(selectedRow.version?selectedRow.version+' · ':'')+state)] :
          [h('span',{className:'muse-meta'},scope.label)]))),
      profileAdmin && managementMessage && h('section',{'aria-label':'Muse profiles',className:'muse-admin'},
        h('p',{role:'status'},managementMessage)),
      profileAdmin && !ready && empty(selectedRow ? 'Muse is not enabled for this profile' : 'No profile selected', selectedRow ? 'Install and enable Muse in that profile with Hermes plugin management (hermes -p <profile> plugins), then browse its Feed, Ideas, Goals, Runs and Findings here.' : 'Choose a profile to browse its Feed, Ideas, Goals, Runs and Findings.'),
      ready && h('nav', {'aria-label':'Muse sections', className:'muse-tabs'},
        ...Object.keys(label).map(name => h('button', {key:name, type:'button', className:'muse-tab', 'aria-pressed':tab===name, 'aria-label':label[name], onClick:()=>setTab(name)}, label[name], counts[name] !== undefined && h('span', {className:'muse-count'}, counts[name])))),
      ready && health && healthPanel(health),
      ready && tab === 'feed' && !currentArticle && h('form', {className:'muse-toolbar', onSubmit:e=>{e.preventDefault(); setQuery(draftQuery.trim());}},
        h('label', {className:'muse-search'}, icon([h('circle',{key:'c',cx:7,cy:7,r:4.5}), h('path',{key:'p',d:'M10.5 10.5L14 14'})]),
          h('input', {className:'muse-input', type:'search', 'aria-label':'Search articles', value:draftQuery, placeholder:'Search title or keyword', onChange:e=>setDraftQuery(e.target.value)})),
        topic && h('span', {className:'muse-chip'}, 'Topic: ' + (topicLabel || 'selected'), button('✕',()=>{setTopic('');setTopicLabel('');},false,'text',{'aria-label':'Clear topic filter'})),
        (draftQuery || topic) && button('Clear',()=>{setDraftQuery('');setQuery('');setTopic('');setTopicLabel('');},false,'text')),
      ready && error && empty('Something went wrong', error, button('Retry',()=>currentArticle?open(currentArticle):load(),busy), true),
      ready && (currentPage || currentArticle) && busy && h('p', {role:'status', className:'muse-sub'}, 'Loading…'),
      ready && content,
      ready && !currentArticle && currentPage?.next_cursor && h('div', {className:'muse-toolbar'}, button('Load more',()=>load(currentPage.next_cursor),busy)));
  };
}

window.__HERMES_PLUGINS__.register('hermes-muse',makeMusePage(React,useScope,request,null,profileAdmin));
})();
