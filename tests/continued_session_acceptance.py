"""Native messaging reset/compression lineage is not task delegation; synthetic rows only."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from contextlib import closing
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hermes_muse.host import HostAdapter
from hermes_muse.kernel import Kernel, intake
from hermes_muse import surface


def main():
    from hermes_state import SessionDB
    from gateway.session_context import set_session_vars, clear_session_vars
    from agent.delegation_context import delegated_child_context
    for key in list(os.environ):
        if key.startswith('HERMES_SESSION_') or key in ('HERMES_CRON_SESSION', 'HERMES_DELEGATED_CHILD_CONTEXT'):
            os.environ.pop(key)
    with tempfile.TemporaryDirectory(prefix='muse-continuation-') as tmp:
        home = Path(tmp).resolve()
        os.environ['HERMES_HOME'] = str(home)
        SessionDB(db_path=home / 'state.db').close()
        with closing(sqlite3.connect(home / 'state.db')) as db, db:
            if 'created_source' not in {r[1] for r in db.execute('PRAGMA table_info(sessions)')}:
                db.execute('ALTER TABLE sessions ADD COLUMN created_source TEXT')
            def add(sid, parent=None, reason=None, config=None, **overrides):
                row = dict(id=sid, source='photon', created_source='photon', chat_type='dm', hidden=0,
                           session_key='agent:main:photon:dm:synthetic', chat_id='synthetic-chat', user_id='synthetic-user',
                           parent_session_id=parent, end_reason=reason, model_config=json.dumps(config or {}), started_at=0)
                row.update(overrides)
                db.execute('INSERT INTO sessions('+','.join(row)+') VALUES('+','.join('?'*len(row))+')', tuple(row.values()))
                db.execute('INSERT INTO messages(session_id,role,content,timestamp,message_uid) VALUES(?,?,?,?,?)',
                           (sid, 'user', 'TEST ONLY '+sid, 1, sid))
            add('reset-parent', reason='session_reset')
            add('continued-photon', parent='reset-parent', config={'_reset_from':'reset-parent', 'gateway_runtime':{}})
            add('compression-parent', reason='compression')
            add('compressed-photon', parent='compression-parent')
            add('delegate', parent='reset-parent', config={'_delegate_from':'reset-parent'})
            add('compression-delegate', parent='compression-parent', config={'_delegate_from':'compression-parent'})
            add('compression-branch', parent='compression-parent', config={'_branched_from':'compression-parent'})
            add('machine-flipped-parent', reason='session_reset', created_source='subagent')
            add('flipped-descendant', parent='machine-flipped-parent', config={'_reset_from':'machine-flipped-parent'})
            add('unproven', parent='reset-parent')
            add('wrong-reset', parent='reset-parent', config={'_reset_from':'other'})
            add('branch', parent='reset-parent', config={'_reset_from':'reset-parent','_branched_from':'reset-parent'})
            for sid, changes in [('machine',{'created_source':'subagent'}), ('hidden',{'hidden':1}),
                                 ('group',{'chat_type':'group'}), ('route',{'session_key':'different'}),
                                 ('principal',{'user_id':'different'}), ('chat',{'chat_id':'different'})]:
                add(sid, parent='reset-parent', config={'_reset_from':'reset-parent'}, **changes)
            add('machine-parent', reason='session_reset', source='subagent', created_source='subagent')
            add('machine-descendant', parent='machine-parent', config={'_reset_from':'machine-parent'})
            add('malformed', parent='reset-parent', model_config='{bad')
        adapter = HostAdapter(home)
        allowed = {'reset-parent','continued-photon','compression-parent','compressed-photon'}
        tokens = set_session_vars(platform='photon', chat_type='dm')
        try:
            assert adapter.caller(session_id='continued-photon') == 'user', adapter.sessions.user_source_of('continued-photon')
            with closing(sqlite3.connect(home / 'state.db')) as db:
                ids = [r[0] for r in db.execute('SELECT id FROM sessions')]
            for sid in ids:
                assert (adapter.caller(session_id=sid) == 'user') == (sid in allowed), sid
            turns = adapter.sessions.user_turns(0)
            assert {r['session_id'] for r in turns} == allowed
            for row in turns:
                assert adapter.sessions.read(row['ref'])['available']
            with closing(sqlite3.connect(home / 'state.db')) as db:
                refs = [(sid, mid) for sid, mid in db.execute('SELECT session_id,id FROM messages')]
            for sid, mid in refs:
                assert adapter.sessions.read(f'{sid}:{mid}')['available'] == (sid in allowed), sid
            k = Kernel(home, adapter=adapter)
            k.store.set_meta('intake_since', 0)
            intake.capture(k, 2)
            assert {e['payload']['session_id'] for e in k.store.query('signal')} == allowed
            tools = []
            surface.register(SimpleNamespace(register_tool=lambda **kw: tools.append(kw)), k)
            result = json.loads(tools[0]['handler']({'action':'read','data':{'kind':'goal'}},session_id='continued-photon'))
            assert result['ok'], result
            assert adapter.caller(session_id='continued-photon', parent_session_id='reset-parent') == 'child'
            with delegated_child_context('continued-photon'):
                assert adapter.caller(session_id='continued-photon') == 'child'
            for sid in set(ids) - allowed:
                result = json.loads(tools[0]['handler']({'action':'read','data':{'kind':'goal'}},session_id=sid))
                assert not result['ok'], sid
            assert not adapter.faults, list(adapter.faults)
        finally:
            clear_session_vars(tokens)
    print('Native Photon reset/compression vs delegated/machine/identity exclusions PASS')


if __name__ == '__main__':
    main()
