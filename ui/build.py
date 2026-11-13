"""Deterministic stdlib packaging; both SDKs share content views; only Dashboard adds read-only profile selection.

The Dashboard SDK has no chat composer, so its page passes no draft and every in-chat button shows the message to copy.
Run: python ui/build.py (writes dashboard/dist/index.js and desktop/plugin.js)."""

from pathlib import Path

root = Path(__file__).resolve().parents[1]
page = (root / "ui/page.js").read_text()
(root / "dashboard/dist/index.js").write_text(
    """(function () {
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
"""
    + page
    + "\nwindow.__HERMES_PLUGINS__.register('hermes-muse',makeMusePage(React,useScope,request,null,profileAdmin));\n})();\n"
)
(root / "desktop/plugin.js").write_text(
    """import React from 'react';
import {host, useValue, ROUTES_AREA, SIDEBAR_NAV_AREA} from '@hermes/plugin-sdk';
"""
    + page
    + """
export default {
 id:'hermes-muse',name:'Muse',
 register(ctx) {
  if (!ctx.rest || !host.state.profile || !host.state.connectionId) {
   ctx.register({id:'page',area:ROUTES_AREA,data:{path:'/muse'},render:()=>React.createElement('p',null,'Update Hermes Desktop to a build with scoped plugin REST and connection identity to view Muse safely.')});
   return;
  }
  function useScope() {
   const profile=useValue(host.state.profile), connection=useValue(host.state.connectionId);
   return {key:connection+':'+profile,profile,connection,label:(connection || 'Local')+' · '+profile,
    current:()=>host.state.profile.get()===profile && host.state.connectionId.get()===connection};
  }
  async function request(path,scope) {
   if (!scope.current()) throw new Error('Connection changed; refresh Muse');
   return ctx.rest(path+(path.includes('?')?'&':'?')+'profile='+encodeURIComponent(scope.profile));
  }
  // Chat drafts only where this Desktop can address a session's composer; makeMusePage shows the text to copy otherwise.
  const draft=typeof host.composer?.insertText==='function' && host.state.focusedSessionOwner && host.state.focusedStoredSessionId ?
   (text,scope)=>museComposerDraft(host,text,scope) : null;
  const Page=makeMusePage(React,useScope,request,draft);
  ctx.register({id:'page',area:ROUTES_AREA,data:{path:'/muse'},render:()=>React.createElement(Page)});
  ctx.register({id:'nav',area:SIDEBAR_NAV_AREA,data:{path:'/muse',label:'Muse',codicon:'sparkle'}});
 }
};
"""
)
