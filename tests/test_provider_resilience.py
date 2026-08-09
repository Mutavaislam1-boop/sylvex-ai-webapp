import asyncio
import os
import unittest
from unittest.mock import patch

from provider_resilience import classify_provider_failure, run_with_provider_retry


class MemoryCircuits:
    def __init__(self, threshold=5):
        self.threshold = threshold
        self.states = {}

    def recorder(self, provider):
        async def record(transient):
            current = self.states.setdefault(provider, {"state": "CLOSED", "failure_count": 0})
            previous = current["state"]
            if transient:
                current["failure_count"] += 1
                if previous == "HALF_OPEN" or current["failure_count"] >= self.threshold:
                    current["state"] = "OPEN"
            else:
                current.update(state="CLOSED", failure_count=0)
            return {
                **current,
                "opened": previous != "OPEN" and current["state"] == "OPEN",
                "closed": previous != "CLOSED" and current["state"] == "CLOSED",
            }
        return record


class ProviderResilienceTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "PROVIDER_RETRY_MAX_ATTEMPTS": "3",
            "PROVIDER_RETRY_BASE_DELAY_SECONDS": "0",
            "PROVIDER_RETRY_MAX_DELAY_SECONDS": "0.1",
        })
        self.environment.start()
        self.circuits = MemoryCircuits()
        self.logs = []

    def tearDown(self):
        self.environment.stop()

    async def no_sleep(self, _delay):
        return None

    def logger(self, stage, **data):
        self.logs.append((stage, data))

    def run_sequence(self, provider, responses):
        calls = 0

        async def operation():
            nonlocal calls
            value = responses[min(calls, len(responses) - 1)]
            calls += 1
            return value

        result = asyncio.run(run_with_provider_retry(
            provider, "job-test", operation, self.circuits.recorder(provider),
            self.logger, "worker-test", sleep=self.no_sleep,
        ))
        return result, calls

    def test_429_twice_then_success(self):
        result, calls = self.run_sequence("OPENAI", [
            {"ok": False, "status_code": 429, "error": "rate limit"},
            {"ok": False, "status_code": 429, "error": "rate limit"},
            {"ok": True, "value": "done"},
        ])
        self.assertTrue(result["ok"])
        self.assertEqual(calls, 3)

    def test_503_three_times_then_success(self):
        result, calls = self.run_sequence("GEMINI", [
            {"ok": False, "status_code": 503, "error": "unavailable"},
            {"ok": False, "status_code": 503, "error": "unavailable"},
            {"ok": False, "status_code": 503, "error": "unavailable"},
            {"ok": True},
        ])
        self.assertTrue(result["ok"])
        self.assertEqual(calls, 4)

    def test_five_failures_open_only_that_provider(self):
        self.run_sequence("KLING", [{"ok": False, "status_code": 503}])
        result, _ = self.run_sequence("KLING", [
            {"ok": False, "status_code": 503}, {"ok": True},
        ])
        self.assertFalse(result["ok"])
        self.assertEqual(self.circuits.states["KLING"]["state"], "OPEN")
        other, calls = self.run_sequence("OPENAI", [{"ok": True}])
        self.assertTrue(other["ok"])
        self.assertEqual(calls, 1)

    def test_half_open_success_closes(self):
        self.circuits.states["RUNWAY"] = {"state": "HALF_OPEN", "failure_count": 5}
        result, _ = self.run_sequence("RUNWAY", [{"ok": True}])
        self.assertTrue(result["ok"])
        self.assertEqual(self.circuits.states["RUNWAY"], {"state": "CLOSED", "failure_count": 0})
        self.assertIn("PROVIDER_CIRCUIT_CLOSED", [item[0] for item in self.logs])

    def test_permanent_400_is_not_retried(self):
        result, calls = self.run_sequence("QWEN", [
            {"ok": False, "status_code": 400, "error": "validation error"},
            {"ok": True},
        ])
        self.assertFalse(result["ok"])
        self.assertEqual(calls, 1)

    def test_payment_402_is_not_retried(self):
        result, calls = self.run_sequence("ELEVENLABS", [
            {"ok": False, "status_code": 402, "error": "insufficient balance"},
            {"ok": True},
        ])
        self.assertFalse(result["ok"])
        self.assertEqual(calls, 1)

    def test_numeric_status_field_is_classified(self):
        failure = classify_provider_failure({"ok": False, "status": 504})
        self.assertTrue(failure.transient)
        self.assertEqual(failure.status_code, 504)

    def test_timeout_and_connection_errors_are_transient(self):
        self.assertTrue(classify_provider_failure(TimeoutError("timed out")).transient)
        self.assertTrue(classify_provider_failure(ConnectionError("connection reset")).transient)


if __name__ == "__main__":
    unittest.main()
