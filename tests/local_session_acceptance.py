"""Gateway LOCAL provenance contract; synthetic native rows, no live/model IO."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from contextlib import closing, contextmanager

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hermes_muse.host import HostAdapter
from hermes_muse.host.sessions import classify
from hermes_muse.kernel import Kernel
from hermes_muse import surface


@contextmanager
def local_turn(home, label='gui'):
    """A gateway LOCAL turn (Webapp, attached clients): the transport binds `local`, the turn runs in its launch policy."""
    from gateway.session_context import set_session_vars, clear_session_vars
    from gateway.session_policy import build_policy, policy_scope
    policy = build_policy({'source': label, 'cwd': str(home), 'model': 'synthetic', 'toolsets': []},
                          {'platform_toolsets': {'cli': [], 'acp': []}}, private_secrets={})
    tokens = set_session_vars(platform='local', chat_type='dm')
    try:
        with policy_scope(policy):
            yield
    finally:
        clear_session_vars(tokens)


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
                ('flipped', 'cli', 'kanban', 'dm', None), ('child', 'subagent', 'subagent', 'dm', 'cli'),
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
        with local_turn(home):
            # Photon is not a LOCAL session; it has its own binding below.
            actual = {sid: adapter.caller(session_id=sid) for sid, *_ in cases if sid != 'photon'}
            expected = {sid: 'user' if sid in ('cli','tui','gui','acp','reserved') else 'other' for sid, *_ in cases if sid != 'photon'}
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
        tokens = set_session_vars(platform='photon', chat_type='dm')
        try:
            assert adapter.caller(session_id='photon') == 'user'
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
        # Compression and /branch keep user authority on every surface; lineage is not delegation.
        continued = {f'{kind}-{s}': s for kind in ('compression', 'branch')
                     for s in ('local', 'cli', 'tui', 'gui', 'acp', 'photon', 'telegram')}
        with closing(sqlite3.connect(home / 'state.db')) as db, db:
            for sid, source in continued.items():
                db.execute('INSERT INTO sessions(id,source,created_source,chat_type,parent_session_id,started_at) VALUES(?,?,?,?,?,0)',
                           (sid, source, 'cli' if source == 'local' else source, 'dm', 'parent'))
                db.execute('INSERT INTO messages(session_id,role,content,timestamp,message_uid) VALUES(?,?,?,?,?)',
                           (sid, 'user', 'TEST ONLY ' + sid, 150, sid))
        for sid, source in continued.items():
            assert adapter.caller(session_id=sid) == 'user', sid
        continued_turns = [r for r in adapter.sessions.user_turns(0) if r['session_id'] in continued]
        assert {r['session_id'] for r in continued_turns} == set(continued)
        for row in continued_turns:
            assert adapter.sessions.read(row['ref'])['available'], row
        k.store.set_meta('intake_since', 0)
        intake.capture(k, 200)
        assert set(continued) <= {e['payload']['session_id'] for e in k.store.query('signal')}
        with closing(sqlite3.connect(home / 'state.db')) as db, db:
            for sid in continued:
                db.execute('DELETE FROM sessions WHERE id=?', (sid,))
        # A legacy Desktop Bot Chat row keeps its stored `desktop` label. Answered over gateway LOCAL (the Webapp) or the
        # TUI binding it is the user's; a turn Hermes injected there (cron output, a finished process) is automation,
        # which reads but never writes.
        with closing(sqlite3.connect(home / 'state.db')) as db, db:
            db.execute("INSERT INTO sessions(id,source,created_source,chat_type,title,hidden,started_at) "
                       "VALUES('bot','desktop','desktop','dm','Bot Chat',1,0)")
            db.execute("INSERT INTO messages(session_id,role,content,timestamp,message_uid) VALUES('bot','user','TEST ONLY hi',300,'bot-0')")

        def tool(action, data):
            return json.loads(registered[0]['handler']({'action': action, 'data': data}, session_id='bot'))

        def desktop_turns():
            """(Webapp kind, read, write), TUI kind"""
            with local_turn(home):
                webapp = adapter.caller(session_id='bot'), tool('read', {'kind': 'goal'}), tool('idea_add', {'title': 'TEST ONLY'})
            tokens = set_session_vars(source='desktop')
            try:
                return webapp, adapter.caller(session_id='bot')
            finally:
                clear_session_vars(tokens)
        (kind, read, write), tui = desktop_turns()
        assert kind == tui == 'user' and read['ok'] and write['ok'], (kind, tui, read, write)
        for i, (display_kind, text) in enumerate([
                ('internal_notification', '[Cronjob "test" output — scheduled job, not the user.] hi'),
                ('process_complete', 'TEST ONLY process finished'),
                (None, '[IMPORTANT: Background process finished]')]):  # stored before Hermes stamped it
            with closing(sqlite3.connect(home / 'state.db')) as db, db:
                db.execute('INSERT INTO messages(session_id,role,content,timestamp,message_uid,display_kind) VALUES(?,?,?,?,?,?)',
                           ('bot', 'user', text, 301 + i, f'bot-{i + 1}', display_kind))
            (kind, read, write), tui = desktop_turns()
            assert kind == tui == 'automation' and read['ok'] and write['code'] == 'permission_denied', (kind, tui, read, write)
        # An LLM hook gets the turn's own message before Hermes persists its row.
        with local_turn(home):
            assert adapter.caller(session_id='bot', platform='desktop', conversation_history=[
                {'role': 'user', 'content': 'TEST ONLY hi'}]) == 'user'
            assert adapter.caller(session_id='bot', platform='desktop', conversation_history=[
                {'role': 'user', 'content': 'TEST ONLY', 'display_kind': 'internal_notification'}]) == 'automation'
        with closing(sqlite3.connect(home / 'state.db')) as db, db:
            db.execute("DELETE FROM sessions WHERE id='bot'")
        # Old native schemas retain their existing source policy, never infer LOCAL provenance.
        with closing(sqlite3.connect(home / 'state.db')) as db, db:
            for (index,) in db.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='sessions' AND sql LIKE '%created_source%'").fetchall():
                db.execute('DROP INDEX "' + index.replace('"', '""') + '"')
            db.execute('ALTER TABLE sessions DROP COLUMN created_source')
        assert {r['session_id'] for r in adapter.sessions.user_turns(0)} == {'flipped', 'photon', 'reserved', 'unknown-origin'}
        assert adapter.caller(session_id='cli') == 'other'
        assert not adapter.faults, list(adapter.faults)
    print('PASS LOCAL native authority, intake, read, tools, compression/branch and producer exclusions')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'FAIL local_session_acceptance: {exc}')
        print('RESULT FAIL local_session_acceptance')
        raise
    print('RESULT PASS local_session_acceptance')
