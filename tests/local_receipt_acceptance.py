"""Native LOCAL receipts through their host writer; explicit corruption negatives."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from contextlib import closing
from dataclasses import asdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hermes_muse.host import HostAdapter
from hermes_muse import surface
from hermes_muse.kernel import Kernel, intake
from local_session_acceptance import local_turn


def receipt(db, epoch, sid, home, source='cli'):
    from hermes_state_local import commit_local_session
    from gateway.config import Platform
    from gateway.session import SessionEntry, SessionSource
    from gateway.session_lifecycle import _now
    from gateway.session_policy import build_policy

    origin = SessionSource(platform=Platform.LOCAL, chat_id=sid, user_id='user', chat_type='dm')
    entry = SessionEntry('agent:main:local:dm:' + sid, sid, _now(), _now(),
                         origin=origin, platform=Platform.LOCAL)
    policy = build_policy({'source': source, 'cwd': str(home), 'model': 'synthetic', 'toolsets': []},
                          {'platform_toolsets': {'cli': [], 'acp': []}}, private_secrets={})
    return commit_local_session(db, epoch=epoch, receipt={
        'profile_id': 'synthetic', 'principal_id': 'user', 'request_id': sid,
        'session_id': sid, 'route': entry.session_key, 'entry': entry.to_dict(), 'policy': asdict(policy)})


def main():
    from hermes_state import SessionDB
    from hermes_state_local import POLICY_PREFIX
    from hermes_state_runtime import begin_runtime_epoch
    for key in list(os.environ):
        if key.startswith('HERMES_SESSION_') or key in ('HERMES_CRON_SESSION', 'HERMES_PLATFORM', 'HERMES_DELEGATED_CHILD_CONTEXT'):
            os.environ.pop(key)
    with tempfile.TemporaryDirectory(prefix='muse-local-receipt-') as tmp:
        home = Path(tmp).resolve()
        os.environ['HERMES_HOME'] = str(home)
        names = ('cli', 'tui', 'gui', 'acp', 'once', 'tool', 'bare', 'bad-json', 'wrong-id',
                 'wrong-route', 'wrong-user', 'wrong-request', 'wrong-platform', 'group',
                 'child', 'machine-created', 'source-machine', 'hidden', 'continued')
        with closing(SessionDB(db_path=home / 'state.db')) as native:
            epoch = begin_runtime_epoch(native, instance_id='synthetic')
            cases = {sid: receipt(native, epoch, sid, home,
                                 sid if sid in ('cli', 'tui', 'gui', 'acp', 'tool') else 'oneshot' if sid == 'once' else 'cli')
                     for sid in names}
        # Corrupt only negative fixtures after the real producer has written its complete payload.
        cases['bare'] = None
        cases['bad-json'] = '{bad'
        cases['wrong-id']['session_id'] = 'other'
        cases['wrong-route']['route'] = 'other'
        cases['wrong-user']['principal_id'] = 'other'
        cases['wrong-request']['policy']['request_json'] = json.dumps({'source': 'oneshot'})
        cases['wrong-platform']['policy']['platform'] = 'cron'
        with closing(sqlite3.connect(home / 'state.db')) as db, db:
            if 'created_source' not in {r[1] for r in db.execute('PRAGMA table_info(sessions)')}:
                db.execute('ALTER TABLE sessions ADD COLUMN created_source TEXT')
            for i, (sid, value) in enumerate(cases.items()):
                db.execute('UPDATE sessions SET source=?,created_source=?,chat_type=?,parent_session_id=?,hidden=? WHERE id=?',
                           ('subagent' if sid == 'child' else 'oneshot' if sid == 'source-machine' else 'local',
                            'cron' if sid == 'machine-created' else 'unknown', 'group' if sid == 'group' else 'dm',
                            'cli' if sid in ('child', 'continued') else None, int(sid == 'hidden'), sid))
                if value is None:
                    db.execute('DELETE FROM state_meta WHERE key=?', (POLICY_PREFIX + sid,))
                elif sid in ('bad-json', 'wrong-id', 'wrong-route', 'wrong-user', 'wrong-request', 'wrong-platform'):
                    db.execute('UPDATE state_meta SET value=? WHERE key=?',
                               (value if isinstance(value, str) else json.dumps(value), POLICY_PREFIX + sid))
                db.execute('INSERT INTO messages(session_id,role,content,timestamp,message_uid) VALUES(?,?,?,?,?)',
                           (sid, 'user', 'TEST ONLY ' + sid, i + 1, sid))
        adapter = HostAdapter(home)
        allowed = {'cli', 'tui', 'gui', 'acp', 'continued'}
        with local_turn(home):
            actual = {sid: adapter.caller(session_id=sid) for sid in cases}
            assert actual == {sid: 'user' if sid in allowed else 'other' for sid in cases}, actual
            turns = adapter.sessions.user_turns(0)
            assert {r['session_id'] for r in turns} == allowed, turns
            assert {r['source'] for r in turns} == {'cli', 'tui', 'gui', 'acp'}, turns
            assert all(adapter.sessions.sources(-1)[s] >= 1 for s in ('cli', 'tui', 'gui', 'acp'))
            k = Kernel(home, adapter=adapter)
            k.store.set_meta('intake_since', 0)
            intake.capture(k, 200)
            assert {e['payload']['session_id'] for e in k.store.query('signal')} == allowed
            from types import SimpleNamespace
            registered = []
            surface.register(SimpleNamespace(register_tool=lambda **kw: registered.append(kw)), k)
            for sid in allowed:
                result = json.loads(registered[0]['handler']({'action': 'read', 'data': {'kind': 'goal'}}, session_id=sid))
                assert result['ok'], result
            for row in turns:
                assert adapter.sessions.read(row['ref'])['available']
        assert not adapter.faults, list(adapter.faults)
    print('PASS native LOCAL writer receipts, continuations, authority, intake, read, tools and exclusions')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'FAIL local_receipt_acceptance: {exc}')
        print('RESULT FAIL local_receipt_acceptance')
        raise
    print('RESULT PASS local_receipt_acceptance')
