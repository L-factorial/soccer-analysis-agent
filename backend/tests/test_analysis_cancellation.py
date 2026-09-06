import asyncio
from contextlib import ExitStack
from threading import Event
from uuid import uuid4
import unittest
from unittest.mock import patch
import httpx
from app.analysis_lifecycle import AnalysisCancelled, AnalysisRegistry, check_analysis_cancelled
from app.builders import build_initial_game_state
from app.main import app
from app.models.animation_response import AnimationResponse
from app.models.field_submission import FieldSubmission
from app.phases.search import search_tactical_phases
from app.rate_limits import InMemoryRateLimiter
from test_field_submission_validation import valid_payload


class CancellationTests(unittest.TestCase):
    def test_search_observes_cancellation(self):
        registry = AnalysisRegistry()
        initial = build_initial_game_state(FieldSubmission.model_validate(valid_payload()))
        with self.assertRaises(AnalysisCancelled):
            with registry.track('test'):
                registry.cancel('test')
                search_tactical_phases(initial)
        check_analysis_cancelled()

    def test_recent_ids_are_bounded(self):
        registry = AnalysisRegistry()
        for _ in range(1100):
            registry.cancel(str(uuid4()))
        self.assertEqual(len(registry._recent), 1024)


class CancellationHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_running_work_releases_slots(self):
        registry = AnalysisRegistry()
        limiter = InMemoryRateLimiter()
        started = Event()
        def analysis(_):
            started.set()
            for _ in range(500):
                check_analysis_cancelled()
                Event().wait(0.01)
            self.fail('Analysis did not stop')
        payload = {**valid_payload(), 'analysisId': str(uuid4())}
        with patch('app.api.field_configurations.analysis_registry', registry), patch('app.api.field_configurations.rate_limiter', limiter), patch('app.api.field_configurations._analyze_field_configuration', side_effect=analysis):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test/api/v1/field-configurations/') as client:
                task = asyncio.create_task(client.post('analyze', json=payload))
                try:
                    self.assertTrue(await asyncio.to_thread(started.wait, 2))
                    duplicate = await client.post('analyze', json=payload)
                    self.assertEqual(duplicate.status_code, 409)
                    self.assertEqual(duplicate.json()['detail']['code'], 'duplicate_analysis_id')
                    cancel = await client.post('cancel-analysis', json={'analysisId': payload['analysisId']})
                    self.assertEqual(cancel.status_code, 200)
                    self.assertEqual(cancel.json()['status'], 'cancelling')
                    result = await asyncio.wait_for(task, 2)
                    self.assertEqual(result.status_code, 409)
                    self.assertEqual(result.json()['detail']['code'], 'analysis_cancelled')
                finally:
                    registry.cancel(payload['analysisId'])
                    await task
        with ExitStack() as stack:
            for _ in range(5):
                stack.enter_context(limiter.analysis_slot())

    async def test_cancel_before_admission(self):
        payload = {**valid_payload(), 'analysisId': str(uuid4())}
        with patch('app.api.field_configurations.analysis_registry', AnalysisRegistry()), patch('app.api.field_configurations._analyze_field_configuration') as analyze:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test/api/v1/field-configurations/') as client:
                for _ in range(2):
                    cancel = await client.post('cancel-analysis', json={'analysisId': payload['analysisId']})
                    self.assertEqual(cancel.status_code, 200)
                    self.assertEqual(cancel.json()['status'], 'cancelled')
                result = await client.post('analyze', json=payload)
                self.assertEqual(result.status_code, 409)
                analyze.assert_not_called()
                invalid = await client.post('cancel-analysis', json={'analysisId': 'invalid'})
                self.assertEqual(invalid.status_code, 422)

    async def test_completed_response_echoes_id(self):
        payload = {**valid_payload(), 'analysisId': str(uuid4())}
        with patch('app.api.field_configurations.analysis_registry', AnalysisRegistry()), patch('app.api.field_configurations._analyze_field_configuration', return_value=AnimationResponse(duration=0, events=())):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test/api/v1/field-configurations/') as client:
                response = await client.post('analyze', json=payload)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['analysisId'], payload['analysisId'])
                cancelled = await client.post('cancel-analysis', json={'analysisId': payload['analysisId']})
                self.assertEqual(cancelled.json()['status'], 'completed')

    async def test_real_analysis_request_serializes_uuid(self):
        # Exercise the real handler, including logging and search, not a mock.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            for include_id in (True, False):
                payload = valid_payload()
                field = payload["fieldConfiguration"]
                field["players"][0]["position"] = {"x": 10000, "y": 4500}
                field["ball"]["position"] = {"x": 10000, "y": 4500}
                if include_id:
                    payload['analysisId'] = str(uuid4())
                response = await client.post('/api/v1/field-configurations/analyze', json=payload)
                self.assertIn(response.status_code, (200, 422))
                if response.status_code == 200:
                    from uuid import UUID
                    UUID(response.json()['analysisId'])
                    if include_id:
                        self.assertEqual(response.json()['analysisId'], payload['analysisId'])
                else:
                    self.assertEqual(response.json()['detail']['code'], 'no_goal_scoring_sequence')
