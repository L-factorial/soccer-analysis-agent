from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import unittest
from unittest.mock import patch

import httpx

from app.api.field_configurations import AnalysisRequest
from app.analysis_lifecycle import AnalysisRegistry
from app.main import app
from app.models.animation_response import AlternativePlan, AnimationResponse, CommentaryTrack
from app.models.field_submission import FieldSubmission
from app.solution_cache import SolutionCache, configuration_hash
from test_field_submission_validation import valid_payload
from test_shooting import shooting_state


class SolutionCacheTests(unittest.TestCase):
    def test_commentary_languages_survive_independent_updates(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'solutions.sqlite3'
            cache = SolutionCache(path)
            submission = FieldSubmission.model_validate(valid_payload())
            cache.put('field', submission, AnimationResponse(duration=0, events=()))
            english = CommentaryTrack(title='English', summary='A fine goal', cues=())
            nepali = CommentaryTrack(language='ne', script='devanagari', title='नेपाली', summary='आहा, क्या राम्रो!', cues=())
            cache.save_commentary('field', 'requested', english)
            cache.save_commentary('field', 'requested', nepali)
            restored = SolutionCache(path).get('field')[1]
            self.assertEqual(restored.commentary, english)
            self.assertEqual(restored.commentary_by_language, {'en': english, 'ne': nepali})

    def test_hash_normalizes_order_and_excludes_request_id(self):
        payload = valid_payload()
        original = configuration_hash(AnalysisRequest.model_validate({**payload, 'analysisId': str(uuid4())}))
        for key in ('players', 'teams', 'goals', 'openSpaces'):
            payload['fieldConfiguration'][key].reverse()
        reordered = configuration_hash(AnalysisRequest.model_validate({**payload, 'analysisId': str(uuid4())}))
        self.assertEqual(original, reordered)
        payload['fieldConfiguration']['ball']['position']['x'] += 1
        self.assertNotEqual(original, configuration_hash(FieldSubmission.model_validate(payload)))

    def test_hash_includes_instructions_and_engine_version(self):
        submission = FieldSubmission.model_validate(valid_payload())
        original = configuration_hash(submission)
        self.assertNotEqual(original, configuration_hash(submission.model_copy(update={'tactical_instruction': 'attack wide'})))
        with patch('app.solution_cache.store.ENGINE_CACHE_VERSION', 'next-engine'):
            self.assertNotEqual(original, configuration_hash(submission))

    def test_lru_and_persistence(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'solutions.sqlite3'
            cache = SolutionCache(path, capacity=2)
            submission = FieldSubmission.model_validate(valid_payload())
            response = AnimationResponse(duration=0, events=())
            for key in ('first', 'second'):
                cache.put(key, submission, response.model_copy(update={'field_hash': key}))
            self.assertIsNotNone(cache.get('first'))
            cache.put('third', submission, response.model_copy(update={'field_hash': 'third'}))
            reopened = SolutionCache(path, capacity=2)
            self.assertIsNone(reopened.get('second'))
            self.assertEqual(reopened.get('first')[1].field_hash, 'first')
            self.assertIsNotNone(reopened.get('third'))

    def test_default_retains_no_more_than_fifty(self):
        with TemporaryDirectory() as directory:
            cache = SolutionCache(Path(directory) / 'solutions.sqlite3')
            submission = FieldSubmission.model_validate(valid_payload())
            response = AnimationResponse(duration=0, events=())
            for index in range(51):
                cache.put(str(index), submission, response)
            self.assertIsNone(cache.get('0'))
            self.assertTrue(all(cache.get(str(index)) is not None for index in range(1, 51)))

    def test_commentary_does_not_revive_evicted_solution(self):
        with TemporaryDirectory() as directory:
            cache = SolutionCache(Path(directory) / 'solutions.sqlite3', capacity=1)
            submission = FieldSubmission.model_validate(valid_payload())
            animation = AnimationResponse(duration=0, events=())
            cache.put('old', submission, animation)
            cache.put('new', submission, animation)
            commentary = CommentaryTrack(title='Late', summary='Completed after eviction', cues=())
            cache.save_commentary('old', 'requested', commentary)
            self.assertIsNone(cache.get('old'))
            self.assertIsNotNone(cache.get('new'))


class SharedSolutionHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_nepali_request_does_not_reuse_english_track(self):
        submission = FieldSubmission.model_validate(valid_payload())
        field_hash = configuration_hash(submission)
        english = CommentaryTrack(title='English', summary='English call', cues=())
        nepali = CommentaryTrack(language='ne', script='devanagari', title='नेपाली', summary='आहा, क्या राम्रो!', cues=())
        with TemporaryDirectory() as directory:
            cache = SolutionCache(Path(directory) / 'solutions.sqlite3')
            cache.put(field_hash, submission, AnimationResponse(duration=1, events=(), commentary=english, commentary_by_language={'ne': nepali.model_copy(update={'script': 'latin'})}))
            body = {'commentaryEnabled': True, 'fieldHash': field_hash, 'language': 'ne',
                    'fieldSubmission': submission.model_dump(mode='json', by_alias=True),
                    'animationResponse': {'duration': 1, 'events': []}}
            with patch('app.api.field_configurations.solution_cache', cache), patch('app.api.field_configurations.rate_limiter.reserve_commentary'), patch('app.api.field_configurations.generate_commentary', return_value=nepali) as generate:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test/api/v1/field-configurations/') as client:
                    for _ in range(2):
                        response = await client.post('commentary', json=body)
                        self.assertEqual(response.status_code, 200, response.text)
                        self.assertEqual(response.json()['language'], 'ne')
                    generate.assert_called_once()
                    self.assertEqual(generate.call_args.kwargs['language'], 'ne')
                    response = await client.post('commentary', json={**body, 'language': 'en'})
                    self.assertEqual(response.json()['title'], 'English')
                    self.assertEqual((await client.post('commentary', json={**body, 'language': 'unknown'})).status_code, 422)

    async def test_commentary_is_saved_per_plan_and_reused_without_generation(self):
        submission = FieldSubmission.model_validate(valid_payload())
        field_hash = configuration_hash(submission)
        animation = AnimationResponse(duration=1, events=(), field_hash=field_hash,
            alternative_plans=(AlternativePlan(id='alt', label='Alternative', reason='Different route', duration=2, events=()),))
        primary = CommentaryTrack(title='Primary', summary='Primary narration', cues=())
        alternative = CommentaryTrack(title='Alternative', summary='Alternative narration', cues=())
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'solutions.sqlite3'
            cache = SolutionCache(path)
            cache.put(field_hash, submission, animation)
            body = {'commentaryEnabled': True, 'fieldHash': field_hash,
                    'fieldSubmission': submission.model_dump(mode='json', by_alias=True),
                    'animationResponse': {'duration': 999, 'events': []}}
            with patch('app.api.field_configurations.solution_cache', cache):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test/api/v1/field-configurations/') as client:
                    with patch('app.api.field_configurations.rate_limiter.reserve_commentary'), patch('app.api.field_configurations.generate_commentary', side_effect=[primary, alternative]) as generate:
                        for plan_id, expected_duration in (('requested', 1), ('alt', 2)):
                            result = await client.post('commentary', json={**body, 'planId': plan_id})
                            self.assertEqual(result.status_code, 200, result.text)
                            self.assertEqual(generate.call_args.args[0].duration, expected_duration)
                    with patch('app.api.field_configurations.generate_commentary', side_effect=AssertionError('Must reuse commentary')), patch('app.api.field_configurations.rate_limiter.reserve_commentary', side_effect=AssertionError('Cache hit must not spend quota')):
                        for plan_id, expected in (('requested', primary), ('alt', alternative)):
                            result = await client.post('commentary', json={**body, 'planId': plan_id})
                            self.assertEqual(result.status_code, 200)
                            self.assertEqual(result.json()['title'], expected.title)
                        self.assertEqual((await client.post('commentary', json={**body, 'commentaryEnabled': False})).status_code, 400)
                        self.assertEqual((await client.post('commentary', json={**body, 'planId': 'missing'})).status_code, 404)
                    shared = await client.get(f'solutions/{field_hash}')
                    self.assertEqual(shared.json()['animationResponse']['commentary']['title'], 'Primary')
                    self.assertEqual(shared.json()['animationResponse']['alternativePlans'][0]['commentary']['title'], 'Alternative')
            restored = SolutionCache(path).get(field_hash)[1]
            self.assertEqual(restored.commentary, primary)
            self.assertEqual(restored.alternative_plans[0].commentary, alternative)

    async def test_compute_once_then_reuse_and_restore_by_hash(self):
        submission, _ = shooting_state('team1')
        with TemporaryDirectory() as directory:
            cache = SolutionCache(Path(directory) / 'solutions.sqlite3')
            with patch('app.api.field_configurations.solution_cache', cache), patch('app.api.field_configurations.analysis_registry', AnalysisRegistry()):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test/api/v1/field-configurations/') as client:
                    first = await client.post('analyze', json={**submission.model_dump(mode='json', by_alias=True), 'analysisId': str(uuid4())})
                    self.assertEqual(first.status_code, 200, first.text)
                    field_hash = first.json()['fieldHash']
                    self.assertEqual(len(field_hash), 64)
                    with patch('app.api.field_configurations.SoccerGameEngine', side_effect=AssertionError('Cache hit must not recompute')):
                        second = await client.post('analyze', json={**submission.model_dump(mode='json', by_alias=True), 'analysisId': str(uuid4())})
                        shared = await client.get(f'solutions/{field_hash}')
                    self.assertEqual(second.status_code, 200, second.text)
                    self.assertEqual(second.json()['fieldHash'], field_hash)
                    self.assertNotEqual(second.json()['analysisId'], first.json()['analysisId'])
                    self.assertEqual(second.json()['events'], first.json()['events'])
                    self.assertEqual(shared.status_code, 200, shared.text)
                    self.assertEqual(shared.json()['animationResponse']['events'], first.json()['events'])
                    self.assertEqual(shared.json()['fieldSubmission'], submission.model_dump(mode='json', by_alias=True))
                    self.assertEqual((await client.get('solutions/' + '0' * 64)).status_code, 404)
                    self.assertEqual((await client.get('solutions/not-a-hash')).status_code, 404)


if __name__ == '__main__':
    unittest.main()
