"""Gateway LOCAL provenance contract; synthetic native rows, no live/model IO."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hermes_muse.host import HostAdapter
from hermes_muse.host.sessions import classify
from hermes_muse.kernel import Kernel
from hermes_muse import surface


def main():
    from hermes_state import SessionDB
    from gateway.session_context import set_session_vars, clear_session_vars
    for name in list(os.environ):
        if name.startswith('HERMES_SESSION_') or name in ('HERMES_CRON_SESSION', 'HERMES_PLATFORM', 'HERMES_DELEGATED_CHILD_CONTEXT'):
            os.environ.pop(name)
    with tempfile.TemporaryDirectory(prefix='muse-local-') as tmp:
        home = Path(tmp).resolve()
        os.environ['HERMES_HOME'] = str(home)
        SessionDB(db_path=home / 'state.db').close()
        with closing(sqlite3.connect(home / 'state.db')) as db, db:
            columns = {r[1] for r in db.execute('PRAGMA table_info(sessions)')}
            if 'created_source' not in columns:
                db.execute('ALTER TABLE sessions ADD COLUMN created_source TEXT')
            cases = [(s, 'local', s, 'dm', None) for s in ('cli', 'tui', 'gui', 'acp')]
            cases += [(s, source, created, chat, parent) for s, source, created, chat, parent in [
                ('reserved', 'cli', 'cli', 'dm', None),  # native row before LOCAL peer refresh
                ('once', 'oneshot', 'cli', 'dm', None), ('tool', 'tool', 'cli', 'dm', None),
                ('bare', 'local', None, 'dm', None), ('unknown', 'local', 'future', 'dm', None),
                ('classic-unknown', 'local', 'unknown', 'dm', None),
                ('unknown-origin', 'cli', 'unknown', 'dm', None),
                ('import', 'local', 'imported', 'dm', None), ('background', 'local', 'cron', 'dm', None),
                ('flipped', 'cli', 'kanban', 'dm', None), ('child', 'local', 'cli', 'dm', 'cli'),
                ('hidden-session', 'local', 'cli', 'dm', None),
                ('group', 'local', 'cli', 'group', None), ('photon', 'photon', 'photon', 'dm', None)]]
            db.executemany('INSERT INTO sessions(id,source,created_source,chat_type,parent_session_id,started_at) VALUES(?,?,?,?,?,0)', cases)
            db.execute("UPDATE sessions SET hidden=1 WHERE id='hidden-session'")
            for i, (sid, *_rest) in enumerate(cases):
                db.execute('INSERT INTO messages(session_id,role,content,timestamp,message_uid) VALUES(?,?,?,?,?)',
                           (sid, 'user', 'TEST ONLY ' + sid, i + 1, sid))
            db.execute('INSERT INTO messages(session_id,role,content,timestamp,message_uid) VALUES(?,?,?,?,?)',
                       ('cli', 'user', '[Cronjob "test" output — scheduled job, not the user.] hi', 100, 'bg'))
            db.execute('INSERT INTO messages(session_id,role,content,timestamp,message_uid,display_kind) VALUES(?,?,?,?,?,?)',
                       ('cli', 'user', 'hidden', 101, 'hidden', 'hidden'))
        adapter = HostAdapter(home)
        counts = adapter.sessions.sources(-1)
        assert all(counts[s] >= 1 for s in ('cli', 'tui', 'gui', 'acp', 'photon')), counts
        assert counts['local'] >= 1, counts  # unresolved transports still surface in Health
        tokens = set_session_vars(platform='local', chat_type='dm')
        try:
            actual = {sid: adapter.caller(session_id=sid) for sid, *_ in cases}
            expected = {sid: 'user' if sid in ('cli','tui','gui','acp','photon','reserved') else 'other' for sid, *_ in cases}
            # Photon transport is not LOCAL, so test it in its own native binding below.
            expected['photon'] = 'other'
            assert actual == expected, actual
            turns = adapter.sessions.user_turns(0)
            assert {r['session_id'] for r in turns} == {'cli','tui','gui','acp','photon','reserved'}, turns
            assert {r['source'] for r in turns} == {'cli','tui','gui','acp','photon'}, turns
            for row in turns:
                assert adapter.sessions.read(row['ref'])['available'], row
            from hermes_muse.kernel import intake
            k = Kernel(home, adapter=adapter)
            k.store.set_meta('intake_since', 0)
            intake.capture(k, 200)
            assert {e['payload']['session_id'] for e in k.store.query('signal')} == {'cli','tui','gui','acp','photon','reserved'}
            for sid, *_ in cases:
                if sid not in ('cli','tui','gui','acp','photon','reserved'):
                    with closing(sqlite3.connect(home / 'state.db')) as db:
                        mid = db.execute('SELECT id FROM messages WHERE session_id=? LIMIT 1', (sid,)).fetchone()[0]
                    assert not adapter.sessions.read(f'{sid}:{mid}')['available'], sid
            registered = []
            from types import SimpleNamespace
            surface.register(SimpleNamespace(register_tool=lambda **kw: registered.append(kw)), Kernel(home, adapter=adapter))
            result = json.loads(registered[0]['handler']({'action':'read','data':{'kind':'goal'}}, session_id='cli'))
            assert result['ok'], result
        finally:
            clear_session_vars(tokens)
        tokens = set_session_vars(platform='cli', chat_type='dm')
        try:
            for sid, *_ in cases:
                if sid not in ('cli','tui','gui','acp','photon','reserved'):
                    assert adapter.caller(session_id=sid) != 'user', sid
        finally:
            clear_session_vars(tokens)
        for platform in ('oneshot','tool','cron','unknown'):
            tokens = set_session_vars(platform=platform, chat_type='dm')
            try:
                assert adapter.caller(session_id='cli') != 'user', platform
            finally:
                clear_session_vars(tokens)
        tokens = set_session_vars(platform='cli', chat_type='group')
        try:
            assert adapter.caller(session_id='cli') == 'group'
        finally:
            clear_session_vars(tokens)
        assert adapter.caller(session_id='cli', parent_session_id='parent') == 'child'
        assert classify('local') == 'unclassified'
        # Old native schemas retain their existing source policy, never infer LOCAL provenance.
        with closing(sqlite3.connect(home / 'state.db')) as db, db:
            for (index,) in db.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='sessions' AND sql LIKE '%created_source%'").fetchall():
                db.execute('DROP INDEX "' + index.replace('"', '""') + '"')
            db.execute('ALTER TABLE sessions DROP COLUMN created_source')
        assert {r['session_id'] for r in adapter.sessions.user_turns(0)} == {'flipped', 'photon', 'reserved', 'unknown-origin'}
        assert adapter.caller(session_id='cli') == 'other'
        assert not adapter.faults, list(adapter.faults)
    print('LOCAL native authority, intake, read, registered tool and producer exclusions PASS')


if __name__ == '__main__':
    main()
