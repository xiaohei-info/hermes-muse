import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from hermes_muse.operations import Operations
from hermes_muse.store import Store, stamp


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.store = Store(self.home)
        self.now = 1800000000.0
        self.host = SimpleNamespace(manifest=lambda: {"jobs": {"owned": {}}})
        self.ops = Operations(self.store, self.host, lambda: self.now)
        self.db = sqlite3.connect(self.home / 'state.db')
        self.addCleanup(self.db.close)
        self.db.executescript('''CREATE TABLE sessions (id TEXT PRIMARY KEY,parent_session_id TEXT,chat_type TEXT);
        CREATE TABLE messages (id INTEGER PRIMARY KEY,session_id TEXT,role TEXT,content TEXT,tool_calls TEXT,tool_call_id TEXT,tool_name TEXT,timestamp REAL);''')
        (self.home / 'cron').mkdir()
        with sqlite3.connect(self.home / 'cron/executions.db') as d:
            d.execute('CREATE TABLE executions (id TEXT,job_id TEXT,status TEXT,claimed_at TEXT,finished_at TEXT,error TEXT,delivery_outcome TEXT)')
        self.session('main')
        self.store.write('session', 'main', {'id': 'main'})

    def session(self, sid, parent=None, kind='private'):
        self.db.execute('INSERT INTO sessions VALUES(?,?,?)', (sid, parent, kind))
        self.db.commit()

    def message(self, sid='main', role='assistant', text=None, tool_calls=None, call_id=None, at=None):
        row = self.db.execute('INSERT INTO messages(session_id,role,content,tool_calls,tool_call_id,tool_name,timestamp) VALUES(?,?,?,?,?,?,?)',
                             (sid, role, text, json.dumps(tool_calls) if tool_calls else None, call_id, 'example', at or self.now - 10))
        self.db.commit()
        return row.lastrowid

    def call(self, key='write1', sid='main', name='write_file', args=None):
        return self.message(sid, tool_calls=[{'id': key, 'function': {'name': name, 'arguments': json.dumps(args or {'path': 'goal.md'})}}])

    def finish(self, page):
        return self.ops.complete({'token': page['token'], 'summary': 'Compared actual intent, receipts and state; saved relevant findings.'})

    def test_scopes_owned_silent_cron_children_and_excludes_groups_unrelated(self):
        for sid, parent, kind in [('cron_owned_1', None, 'private'), ('child', 'cron_owned_1', 'private'),
                                  ('group', 'main', 'group'), ('group-child', 'group', 'private'), ('other', None, 'private')]:
            self.session(sid, parent, kind)
            self.call(sid=sid)
        page = self.ops.read({})
        self.assertEqual({'cron_owned_1', 'child'}, {e['session_id'] for e in page['events']})
        self.ops.track('rotated', 'cron:owned:execution1')
        self.session('rotated')
        self.call(sid='rotated')
        self.assertIn('rotated', {e['session_id'] for e in self.ops.read({})['events']})
        self.ops.track('other', 'cron:foreign:execution2')
        self.assertIsNone(self.store.read('operation_session', 'other'))

    def test_late_result_includes_older_call_after_checkpoint(self):
        call_id = self.call()
        self.finish(self.ops.read({}))
        result_id = self.message(role='tool', text='Saved goal.md', call_id='write1')
        page = self.ops.read({})
        self.assertEqual([result_id], [e['id'] for e in page['events']])
        self.assertEqual(call_id, page['events'][0]['related_call']['message_id'])
        self.assertEqual('Saved goal.md', page['events'][0]['content'])

    def test_pagination_snapshot_does_not_skip_new_arrivals_or_store_transcripts(self):
        for n in range(103):
            self.call(str(n))
        first = self.ops.read({})
        self.assertEqual(100, len(first['events']))
        self.assertTrue(first['more'])
        self.call('late')
        self.finish(first)
        with self.assertRaises(ValueError):
            self.finish(first)
        second = self.ops.read({'through': first['through']})
        self.assertEqual(3, len(second['events']))
        self.assertFalse(second['more'])
        self.finish(second)
        self.assertEqual(1, len(self.ops.read({})['events']))
        with self.store.transaction() as d:
            state = ' '.join(row[0] for row in d.execute('SELECT data FROM records'))
        self.assertNotIn('goal.md', state)
        self.assertNotIn('write_file', state)

    def test_inspection_does_not_audit_itself_or_expose_assistant_reasoning(self):
        self.call('review', name='muse_manage', args={'action': 'operations_read'})
        self.message(role='tool', text='PRIVATE EVIDENCE COPY', call_id='review')
        self.message(text='Hidden analysis', tool_calls=[{'id': 'real', 'function': {'name': 'delete_file', 'arguments': '{}'}}])
        page = self.ops.read({})
        self.assertEqual(1, len(page['events']))
        self.assertIsNone(page['events'][0]['content'])
        self.assertNotIn('PRIVATE EVIDENCE COPY', json.dumps(page))

    def test_failed_read_and_missing_ledger_never_advance(self):
        self.call()
        (self.home / 'cron/executions.db').unlink()
        page = self.ops.read({})
        self.assertTrue(page['gaps'])
        with self.assertRaises(ValueError):
            self.finish(page)
        self.assertEqual(0, self.ops.checkpoint()['message_id'])
        self.db.execute('DROP TABLE messages')
        page = self.ops.read({})
        self.assertFalse(page['available'])
        self.assertNotIn('token', page)

    def test_execution_failure_without_session_and_later_completion(self):
        with sqlite3.connect(self.home / 'cron/executions.db') as d:
            d.execute('INSERT INTO executions VALUES(?,?,?,?,?,?,?)', ('failed', 'owned', 'failed', stamp(self.now - 30), stamp(self.now - 5), 'model unavailable', None))
            d.execute('INSERT INTO executions VALUES(?,?,?,?,?,?,?)', ('other', 'foreign', 'failed', stamp(self.now - 30), stamp(self.now - 5), 'private', None))
            d.execute('INSERT INTO executions VALUES(?,?,?,?,?,?,?)', ('late', 'owned', 'running', stamp(self.now - 30), None, None, None))
        page = self.ops.read({})
        self.assertEqual({'failed', 'late'}, {e['id'] for e in page['executions']})
        self.finish(page)
        self.now += 50
        with sqlite3.connect(self.home / 'cron/executions.db') as d:
            d.execute("UPDATE executions SET status='completed', finished_at=? WHERE id='late'", (stamp(self.now - 5),))
        self.assertEqual(['late'], [e['id'] for e in self.ops.read({})['executions']])

    def test_findings_require_observed_evidence_and_verified_disclosure_for_closure(self):
        self.call()
        page = self.ops.read({})
        data = {'evidence': [page['events'][0]['ref']], 'summary': 'Duplicate watch', 'impact': 'User would receive duplicate reminders'}
        with self.assertRaises(ValueError):
            self.ops.finding({**data, 'evidence': ['message:999']})
        finding = self.ops.finding(data)
        self.assertEqual(finding['id'], self.ops.finding(data)['id'])
        self.finish(page)
        with self.assertRaises(ValueError):
            self.ops.finding({'id': finding['id'], 'status': 'resolved'})
        with self.assertRaises(ValueError):
            self.ops.finding({'id': finding['id'], 'status': 'resolved', 'verification': 'Paused duplicate; original still enabled'})
        closed = self.ops.finding({'id': finding['id'], 'status': 'resolved', 'verification': 'Paused duplicate; original still enabled', 'disclosure': 'Actual correction in native message 45'})
        self.assertEqual('resolved', closed['status'])

    def test_forgotten_finding_is_not_recreated(self):
        self.call()
        page = self.ops.read({})
        data = {'evidence': [page['events'][0]['ref']], 'summary': 'An error', 'impact': 'No external effect'}
        finding = self.ops.finding(data)
        with self.store.transaction() as d:
            self.store.delete(d, 'operation_finding', finding['id'])
            self.store.put(d, 'forgotten', 'operation_finding:' + finding['id'], self.now)
        with self.assertRaises(ValueError):
            self.ops.finding(data)

    def test_profile_isolation_and_initial_scope(self):
        self.call()
        self.message(role='tool', text='old', at=self.now - 90000)
        page = self.ops.read({})
        self.assertEqual(1, len(page['events']))
        with tempfile.TemporaryDirectory() as other:
            isolated = Operations(Store(other), self.host, lambda: self.now).read({})
        self.assertFalse(isolated['available'])
        self.assertEqual([], isolated['events'])
