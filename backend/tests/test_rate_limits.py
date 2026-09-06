import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from threading import Barrier, Event, Lock
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException

from app.api.field_configurations import CommentaryRequest, analyze_field_configuration, create_commentary
from app.main import app
from app.models.animation_response import AnimationResponse
from app.models.field_submission import FieldSubmission
from app.rate_limits import InMemoryRateLimiter, LimitExceeded
from test_commentary import _commentary_input
from test_field_submission_validation import valid_payload


class RateLimiterTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.limiter = InMemoryRateLimiter(clock=lambda: self.now)

    def test_five_analysis_slots_and_recovery(self):
        with ExitStack() as stack:
            for _ in range(5):
                stack.enter_context(self.limiter.analysis_slot())
            with self.assertRaises(LimitExceeded):
                with self.limiter.analysis_slot():
                    self.fail('Sixth analysis was admitted')
        with self.limiter.analysis_slot():
            pass

    def test_failed_analysis_releases_slot(self):
        with patch('app.api.field_configurations.rate_limiter', self.limiter):
            with patch('app.api.field_configurations._analyze_field_configuration', side_effect=RuntimeError('failed')):
                for _ in range(8):
                    with self.assertRaises(RuntimeError):
                        analyze_field_configuration(FieldSubmission.model_validate(valid_payload()))
            with ExitStack() as stack:
                for _ in range(5):
                    stack.enter_context(self.limiter.analysis_slot())

    def test_rolling_minute_boundary_and_rejected_attempts(self):
        for _ in range(3):
            self.limiter.reserve_commentary()
        self.now = 59.1
        for _ in range(5):
            with self.assertRaises(LimitExceeded) as caught:
                self.limiter.reserve_commentary()
            self.assertEqual(caught.exception.retry_after, 1)
        self.now = 60
        for _ in range(3):
            self.limiter.reserve_commentary()

    def test_rolling_day_boundary_and_stricter_retry(self):
        for minute in range(8):
            self.now = minute * 60
            for _ in range(3):
                self.limiter.reserve_commentary()
        with self.assertRaises(LimitExceeded) as caught:
            self.limiter.reserve_commentary()
        self.assertEqual(caught.exception.retry_after, 86400 - 420)
        self.now = 86399.1
        with self.assertRaises(LimitExceeded) as caught:
            self.limiter.reserve_commentary()
        self.assertEqual(caught.exception.retry_after, 1)
        self.now = 86400
        for _ in range(3):
            self.limiter.reserve_commentary()
        with self.assertRaises(LimitExceeded):
            self.limiter.reserve_commentary()

    def test_commentary_reservation_is_atomic(self):
        barrier = Barrier(16)
        def attempt(_):
            barrier.wait(timeout=5)
            try:
                self.limiter.reserve_commentary()
                return True
            except LimitExceeded:
                return False
        with ThreadPoolExecutor(max_workers=16) as pool:
            self.assertEqual(sum(pool.map(attempt, range(16))), 3)

    def test_commentary_rejection_does_not_generate_even_when_enabled(self):
        request = CommentaryRequest(
            commentaryEnabled=True,
            fieldSubmission=FieldSubmission.model_validate(valid_payload()),
            animationResponse=_commentary_input(),
        )
        with patch('app.api.field_configurations.rate_limiter', self.limiter), patch('app.api.field_configurations.generate_commentary', return_value=None) as generate:
            # Failed/unavailable generation still consumes admitted request quota.
            for _ in range(3):
                with self.assertRaises(HTTPException) as caught:
                    create_commentary(request)
                self.assertEqual(caught.exception.status_code, 503)
            with self.assertRaises(HTTPException) as caught:
                create_commentary(request)
            self.assertEqual(caught.exception.status_code, 429)
            self.assertEqual(caught.exception.headers['Retry-After'], '60')
            self.assertEqual(generate.call_count, 3)

    def test_disabled_commentary_does_not_consume_quota(self):
        request = CommentaryRequest(
            commentaryEnabled=False,
            fieldSubmission=FieldSubmission.model_validate(valid_payload()),
            animationResponse=_commentary_input(),
        )
        with patch('app.api.field_configurations.rate_limiter', self.limiter), patch('app.api.field_configurations.generate_commentary') as generate:
            with self.assertRaises(HTTPException) as caught:
                create_commentary(request)
            self.assertEqual(caught.exception.status_code, 400)
            generate.assert_not_called()
        for _ in range(3):
            self.limiter.reserve_commentary()


class RateLimitHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_sixth_request_rejected_while_five_are_running(self):
        started = Event()
        release = Event()
        lock = Lock()
        entered = 0
        def analysis(_):
            nonlocal entered
            with lock:
                entered += 1
                if entered == 5:
                    started.set()
            if not release.wait(timeout=10):
                raise RuntimeError('Test timed out')
            return AnimationResponse(duration=0, events=())
        with patch('app.api.field_configurations.rate_limiter', InMemoryRateLimiter()), patch('app.api.field_configurations._analyze_field_configuration', side_effect=analysis):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                url = '/api/v1/field-configurations/analyze'
                running = [asyncio.create_task(client.post(url, json=valid_payload())) for _ in range(5)]
                try:
                    self.assertTrue(await asyncio.to_thread(started.wait, 5))
                    response = await asyncio.wait_for(client.post(url, json=valid_payload(), headers={'Origin': 'http://localhost:8081'}), timeout=1)
                    self.assertEqual(response.status_code, 429)
                    self.assertEqual(response.json()['detail']['code'], 'analysis_capacity_exceeded')
                    self.assertEqual(response.headers['Retry-After'], '1')
                    self.assertIn('Retry-After', response.headers['access-control-expose-headers'])
                    self.assertEqual(entered, 5)
                finally:
                    release.set()
                    completed = await asyncio.gather(*running)
                self.assertTrue(all(r.status_code == 200 for r in completed))
                self.assertEqual((await client.post(url, json=valid_payload())).status_code, 200)

    async def test_commentary_http_limit_skips_generator(self):
        limiter = InMemoryRateLimiter(clock=lambda: 0)
        for _ in range(3):
            limiter.reserve_commentary()
        request = {'commentaryEnabled': True, 'fieldSubmission': valid_payload(), 'animationResponse': _commentary_input().model_dump(by_alias=True)}
        with patch('app.api.field_configurations.rate_limiter', limiter), patch('app.api.field_configurations.generate_commentary') as generate:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post('/api/v1/field-configurations/commentary', json=request)
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers['Retry-After'], '60')
            generate.assert_not_called()
