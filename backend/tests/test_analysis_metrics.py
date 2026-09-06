import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import httpx

from app.analysis_lifecycle import AnalysisCancelled, AnalysisRegistry, DuplicateAnalysis
from app.main import app


class MetricsTests(unittest.TestCase):
    def test_rolling_window_and_exit_paths(self):
        now = [0.0]
        registry = AnalysisRegistry(clock=lambda: now[0])
        with registry.track("first"):
            self.assertEqual(registry.metrics(), {
                "ongoingAnalyses": 1, "analysesLast24Hours": 1,
            })
            with self.assertRaises(DuplicateAnalysis):
                with registry.track("first"):
                    pass
        now[0] = 10
        with self.assertRaises(ValueError):
            with registry.track("failed"):
                raise ValueError()
        with self.assertRaises(AnalysisCancelled):
            with registry.track("cancelled"):
                registry.cancel("cancelled")
        registry.cancel("never-started")
        with self.assertRaises(AnalysisCancelled):
            with registry.track("never-started"):
                pass
        self.assertEqual(registry.metrics(), {
            "ongoingAnalyses": 0, "analysesLast24Hours": 3,
        })
        now[0] = 86400
        self.assertEqual(registry.metrics()["analysesLast24Hours"], 2)
        now[0] = 86410
        self.assertEqual(registry.metrics()["analysesLast24Hours"], 0)

    def test_parallel_starts_are_counted_once(self):
        registry = AnalysisRegistry()
        entered, release = Barrier(5), Barrier(5)
        def work(index):
            with registry.track(str(index)):
                entered.wait(timeout=5)
                release.wait(timeout=5)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(work, i) for i in range(4)]
            entered.wait(timeout=5)
            try:
                self.assertEqual(registry.metrics(), {
                    "ongoingAnalyses": 4, "analysesLast24Hours": 4,
                })
            finally:
                release.wait(timeout=5)
            for future in futures:
                future.result()
        self.assertEqual(registry.metrics()["ongoingAnalyses"], 0)


class MetricsHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_metrics_endpoint_returns_live_snapshot(self):
        registry = AnalysisRegistry()
        with patch("app.api.field_configurations.analysis_registry", registry):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                with registry.track("active"):
                    response = await client.get("/api/v1/field-configurations/metrics")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json(), {
                        "ongoingAnalyses": 1, "analysesLast24Hours": 1,
                    })
                    self.assertEqual(response.headers["cache-control"], "no-store")
                response = await client.get("/api/v1/field-configurations/metrics")
                self.assertEqual(response.json()["ongoingAnalyses"], 0)
