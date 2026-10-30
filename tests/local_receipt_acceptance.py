"""Exact live placeholder row plus immutable native LOCAL receipt, and fail-closed negatives."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from contextlib import closing
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from hermes_muse.host import HostAdapter
from hermes_muse import surface
from hermes_muse.kernel import Kernel, intake


def receipt(sid, source='cli'):
    route = 'agent:main:local:dm:' + sid
    platform = {'cli':'cli','tui':'tui','gui':'desktop','acp':'acp','oneshot':'cli','tool':'cli'}.get(source,source)
    return {'session_id':sid,'route':route,'principal_id':'user',
            'entry':{'session_id':sid,'session_key':route,'platform':'local',
                     'origin':{'platform':'local','chat_id':sid,'user_id':'user'}},
            'policy':{'source':source,'platform':platform,'request_json':json.dumps({'source':source})}}


def main():
    from hermes_state import SessionDB
    from gateway.session_context import set_session_vars,clear_session_vars
    for key in list(os.environ):
        if key.startswith('HERMES_SESSION_') or key in ('HERMES_CRON_SESSION','HERMES_PLATFORM','HERMES_DELEGATED_CHILD_CONTEXT'):
            os.environ.pop(key)
    with tempfile.TemporaryDirectory(prefix='muse-local-receipt-') as tmp:
        home=Path(tmp).resolve()
        os.environ['HERMES_HOME']=str(home)
        SessionDB(db_path=home/'state.db').close()
        cases={s:receipt(s,s) for s in ('cli','tui','gui','acp')}
        cases.update({'once':receipt('once','oneshot'),'tool':receipt('tool','tool'),
                      'bare':None,'bad-json':'{bad','wrong-id':receipt('another'),
                      'wrong-route':receipt('wrong-route'),'wrong-user':receipt('wrong-user'),
                      'wrong-request':receipt('wrong-request'),'wrong-platform':receipt('wrong-platform'),
                      'group':receipt('group'),'child':receipt('child'),'machine-created':receipt('machine-created'),
                      'source-machine':receipt('source-machine'),'hidden':receipt('hidden')})
        cases['wrong-route']['route']='other'
        cases['wrong-user']['principal_id']='other'
        cases['wrong-request']['policy']['request_json']=json.dumps({'source':'oneshot'})
        cases['wrong-platform']['policy']['platform']='cron'
        with closing(sqlite3.connect(home/'state.db')) as db,db:
            columns={r[1] for r in db.execute('PRAGMA table_info(sessions)')}
            if 'created_source' not in columns:
                db.execute('ALTER TABLE sessions ADD COLUMN created_source TEXT')
            db.execute('CREATE TABLE IF NOT EXISTS state_meta(key TEXT PRIMARY KEY,value TEXT)')
            for i,(sid,value) in enumerate(cases.items()):
                db.execute('INSERT INTO sessions(id,source,created_source,session_key,chat_id,user_id,chat_type,parent_session_id,hidden,started_at) VALUES(?,?,?,?,?,?,?,?,?,0)',
                           (sid,'oneshot' if sid=='source-machine' else 'local','cron' if sid=='machine-created' else 'unknown',
                            'agent:main:local:dm:'+sid,sid,'user','group' if sid=='group' else 'dm',
                            'cli' if sid=='child' else None,1 if sid=='hidden' else 0))
                if value is not None:
                    db.execute('INSERT INTO state_meta(key,value) VALUES(?,?)',('gateway.local_policy.v1:'+sid,value if isinstance(value,str) else json.dumps(value)))
                db.execute('INSERT INTO messages(session_id,role,content,timestamp,message_uid) VALUES(?,?,?,?,?)',(sid,'user','TEST ONLY '+sid,i+1,sid))
        adapter=HostAdapter(home)
        tokens=set_session_vars(platform='local',chat_type='dm')
        try:
            actual={sid:adapter.caller(session_id=sid) for sid in cases}
            assert actual=={sid:'user' if sid in ('cli','tui','gui','acp') else 'other' for sid in cases},actual
            turns=adapter.sessions.user_turns(0)
            assert {r['session_id'] for r in turns}=={'cli','tui','gui','acp'},turns
            assert {r['source'] for r in turns}=={'cli','tui','gui','acp'},turns
            assert all(adapter.sessions.sources(-1)[s]>=1 for s in ('cli','tui','gui','acp'))
            k=Kernel(home,adapter=adapter)
            k.store.set_meta('intake_since',0)
            intake.capture(k,200)
            assert {e['payload']['session_id'] for e in k.store.query('signal')}=={'cli','tui','gui','acp'}
            from types import SimpleNamespace
            registered=[]
            surface.register(SimpleNamespace(register_tool=lambda **kw:registered.append(kw)),k)
            result=json.loads(registered[0]['handler']({'action':'read','data':{'kind':'goal'}},session_id='cli'))
            assert result['ok'],result
            for row in turns:
                assert adapter.sessions.read(row['ref'])['available']
        finally:
            clear_session_vars(tokens)
        assert not adapter.faults,list(adapter.faults)
    print('Native LOCAL receipt placeholder authority, intake, read, tool and exclusions PASS')


if __name__=='__main__':
    main()
