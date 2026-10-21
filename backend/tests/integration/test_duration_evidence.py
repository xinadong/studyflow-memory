import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db, get_llm
from app.infrastructure.database import Base, _upgrade_duration_schema
from app.infrastructure.models.memory import MemoryRecord
from app.main import app
from app.memory.durations import parse_duration
from tests.integration.test_preference_scope import PreferenceLLM


class DurationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name).as_posix()}/duration.db", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        def db():
            with self.sessions() as session:
                yield session
        app.dependency_overrides[get_db] = db
        self.llm = PreferenceLLM()
        app.dependency_overrides[get_llm] = lambda: self.llm
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close(); app.dependency_overrides.clear()
        self.engine.dispose(); self.temp.cleanup()

    def save(self, content, **extra):
        response = self.client.post('/feedback', json={
            'user_id': 'alice', 'scope': 'global', 'feedback_type': 'task_preference',
            'explicit': True, 'content': content, **extra,
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['memories'][0]

    def plan(self, **extra):
        self.llm = PreferenceLLM()
        response = self.client.post('/agent/plan', json={
            'user_id': 'alice', 'course': 'Algorithms', 'knowledge_point': 'BFS',
            'goal': 'Practice', 'available_minutes': 60, **extra,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_conservative_parser_understands_bounds_units_and_ambiguity(self):
        cases = {'首选15分钟，最多30分钟': (15, 30), '不要超过30分钟，最好15分钟': (15, 30),
                 '首选二十分钟': (20, None), '半小时以内': (None, 30), '每次20min': (20, None),
                 '15分钟或30分钟': (None, None), '至少15分钟': (None, None), '首选40分钟最多30分钟': (None, None)}
        for text, expected in cases.items():
            with self.subTest(text=text): self.assertEqual(parse_duration(text), expected)

    def test_preference_and_upper_bound_are_distinct_and_evidence_is_a_snapshot(self):
        saved = self.save('首选15分钟，最多30分钟')
        self.assertEqual((saved['preferred_minutes'], saved['max_minutes']), (15, 30))
        result = self.plan()
        self.assertEqual(result['tasks'][0]['duration_minutes'], 15)
        evidence = result['memory_evidence'][0]
        self.assertEqual(evidence['decision'], 'used')
        self.assertIn('确认的首选15分钟偏好', evidence['reason'])
        updated = self.client.patch('/memories/' + saved['id'], json={'preferred_minutes': 20})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(evidence['memory']['preferred_minutes'], 15)
        self.assertEqual(self.client.get('/memories/' + saved['id']).json()['content'], saved['content'])

    def test_nonbinding_maximum_is_retrieved_but_not_used_and_does_not_fill_time(self):
        saved = self.save('最多30分钟')
        result = self.plan()
        self.assertEqual(result['tasks'][0]['duration_minutes'], 25)
        self.assertEqual(result['used_memory_ids'], [])
        self.assertIn(saved['id'], result['retrieved_memory_ids'])
        self.assertEqual(result['memory_evidence'][0]['decision'], 'retrieved_not_used')
        self.assertIn('未触及上限', result['memory_evidence'][0]['reason'])

    def test_binding_cap_limits_duration_and_is_marked_used(self):
        saved = self.save('最多10分钟')
        result = self.plan()
        self.assertEqual(result['tasks'][0]['duration_minutes'], 10)
        self.assertEqual(result['used_memory_ids'], [saved['id']])
        self.assertIn('最多10分钟上限', result['memory_evidence'][0]['reason'])

    def test_new_confirmed_preference_archives_same_scope_and_keeps_other_scopes(self):
        old = self.save('首选40分钟')
        other = self.save('首选10分钟', scope='knowledge_point', course='Algorithms', knowledge_point='DFS')
        new = self.save('首选15分钟')
        previous = self.client.get('/memories/' + old['id']).json()
        self.assertEqual(previous['confirmation_status'], 'archived')
        self.assertEqual(previous['replaced_by_id'], new['id'])
        self.assertEqual(self.client.get('/memories/' + other['id']).json()['confirmation_status'], 'confirmed')
        self.assertEqual(self.plan()['used_memory_ids'], [new['id']])

    def test_pending_preference_does_not_replace_confirmed_until_confirmation(self):
        old = self.save('首选40分钟')
        pending = self.save('首选15分钟', explicit=False)
        result = self.plan()
        self.assertEqual(result['used_memory_ids'], [old['id']])
        self.assertEqual(next(e for e in result['memory_evidence'] if e['memory']['id'] == pending['id'])['decision'], 'pending')
        self.client.patch('/memories/' + pending['id'], json={'confirmation_status': 'confirmed'})
        self.assertEqual(self.client.get('/memories/' + old['id']).json()['confirmation_status'], 'archived')
        self.assertEqual(self.plan()['used_memory_ids'], [pending['id']])

    def test_edit_creates_version_and_old_version_cannot_be_reenabled(self):
        old = self.save('首选15分钟')
        response = self.client.patch('/memories/' + old['id'], json={'content': '首选20分钟，最多30分钟'})
        self.assertEqual(response.status_code, 200)
        new = response.json()
        self.assertNotEqual(new['id'], old['id'])
        self.assertEqual(new['supersedes_id'], old['id'])
        self.assertEqual((new['preferred_minutes'], new['max_minutes']), (20, 30))
        self.assertEqual(self.client.patch('/memories/' + old['id'], json={'confirmation_status': 'confirmed'}).status_code, 422)

    def test_pending_edit_keeps_the_confirmed_version_until_approved(self):
        old = self.save('首选40分钟')
        response = self.client.patch('/memories/' + old['id'], json={'content': '首选15分钟', 'confirmation_status': 'pending'})
        self.assertEqual(response.status_code, 200)
        pending = response.json()
        self.assertEqual(self.plan()['used_memory_ids'], [old['id']])
        self.client.patch('/memories/' + pending['id'], json={'confirmation_status': 'confirmed'})
        self.assertEqual(self.plan()['used_memory_ids'], [pending['id']])

    def test_explicit_numeric_update_can_clear_an_old_limit_without_reparsing_it(self):
        old = self.save('首选15分钟，最多30分钟')
        response = self.client.patch('/memories/' + old['id'], json={'preferred_minutes': 20, 'max_minutes': None})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['preferred_minutes'], 20)
        self.assertIsNone(response.json()['max_minutes'])
        self.assertEqual(response.json()['duration_source'], 'structured')
        self.assertEqual(self.plan()['tasks'][0]['duration_minutes'], 20)

    def test_invalid_numeric_update_is_rejected_without_archiving_old(self):
        old = self.save('首选15分钟，最多30分钟')
        self.assertEqual(self.client.patch('/memories/' + old['id'], json={'preferred_minutes': 40}).status_code, 422)
        self.assertEqual(self.client.get('/memories/' + old['id']).json()['confirmation_status'], 'confirmed')

    def test_failed_replacement_rolls_back_new_version_and_archive(self):
        old = self.save('首选40分钟')
        from app.memory.versions import archive_conflicts
        def fail(repo, memory):
            archive_conflicts(repo, memory)
            raise RuntimeError('Simulated failure')
        with patch('app.memory.versions.archive_conflicts', side_effect=fail):
            client = TestClient(app, raise_server_exceptions=False)
            try:
                response = client.post('/feedback', json={'user_id': 'alice', 'scope': 'global',
                    'feedback_type': 'task_preference', 'explicit': True, 'content': '首选15分钟'})
                self.assertEqual(response.status_code, 500)
            finally: client.close()
        with self.sessions() as session:
            rows = session.scalars(select(MemoryRecord)).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].id, old['id'])
            self.assertEqual(rows[0].confirmation_status, 'confirmed')

    def test_legacy_duration_migration_is_repeatable_and_preserves_text(self):
        engine = create_engine('sqlite://')
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql('CREATE TABLE memories (id TEXT, memory_type TEXT, content TEXT)')
                connection.exec_driver_sql("INSERT INTO memories VALUES ('old', 'task_preference', '首选15分钟，最多30分钟')")
                _upgrade_duration_schema(connection); _upgrade_duration_schema(connection)
                self.assertEqual(connection.exec_driver_sql('SELECT preferred_minutes,max_minutes,content FROM memories').one(),
                                 (15, 30, '首选15分钟，最多30分钟'))
        finally: engine.dispose()
