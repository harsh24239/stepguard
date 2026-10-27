"""Cost controls must not reuse verdicts, bypass locks, or retry bad credentials."""

import os
import unittest
from unittest.mock import patch

import httpx

from backend import gemini_client
from backend.model_errors import ModelError
from backend.runtime import CheckLimiter, DetectionCache, model_call, observe_retries
from backend.tests.test_compiler import fixture, manual_pdf
from backend.tests.test_gemini import response, transport_patch


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"MODEL_MAX_RETRIES": "2", "DETECTION_CACHE_SECONDS": "30", "MAX_CHECKS_PER_MINUTE": "2"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_transient_failure_retries_twice_then_preserves_error_and_safe_logs(self):
        retries = []
        with patch('backend.runtime.time.sleep') as delay, self.assertLogs('stepguard.models', level='INFO') as logs:
            with observe_retries(lambda: retries.append(True)), self.assertRaises(ModelError):
                model_call('gemini', 'detect', lambda: (_ for _ in ()).throw(ModelError('PRIVATE_KEY_FRAME', 503, retryable=True)))
        self.assertEqual(len(retries), 2)
        self.assertEqual(delay.call_count, 2)
        self.assertEqual(len(logs.output), 3)
        self.assertNotIn('PRIVATE', ''.join(logs.output))
        self.assertTrue(all('latency_ms=' in item for item in logs.output))

    def test_auth_and_invalid_output_never_trigger_retries(self):
        with patch('backend.runtime.time.sleep') as delay:
            for status in (400, 502, 503):
                with self.assertRaises(ModelError):
                    model_call('gemini', 'compile', lambda: (_ for _ in ()).throw(ModelError('safe', status)))
            delay.assert_not_called()
        self.assertEqual(model_call('gemini', 'compile', lambda: 'ok'), 'ok')

    def test_unexpected_failure_is_not_logged_as_success_or_retried(self):
        with patch('backend.runtime.time.sleep') as delay, self.assertLogs('stepguard.models', level='INFO') as logs:
            with self.assertRaises(RuntimeError):
                model_call('gemini', 'judge', lambda: (_ for _ in ()).throw(RuntimeError('PRIVATE_RESPONSE')))
        delay.assert_not_called()
        self.assertEqual(len(logs.output), 1)
        self.assertIn('status=500', logs.output[0])
        self.assertNotIn('PRIVATE', logs.output[0])

    def test_recovery_returns_one_result_and_reports_only_actual_retries(self):
        calls, retries = [], []
        def operation():
            calls.append(True)
            if len(calls) == 1:
                raise ModelError('temporary', retryable=True)
            return {'real': True}
        with patch('backend.runtime.time.sleep'), observe_retries(lambda: retries.append(True)):
            self.assertEqual(model_call('gemini', 'judge', operation), {'real': True})
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(retries), 1)

    def test_limiter_is_global_rolling_and_allows_a_new_check_after_expiry(self):
        now = [100.]
        limiter = CheckLimiter(clock=lambda: now[0])
        limiter.reserve()
        limiter.reserve()
        with self.assertRaises(ModelError) as error:
            limiter.reserve()
        self.assertEqual(error.exception.status, 429)
        now[0] = 160.
        limiter.reserve()

    def test_cache_isolated_by_pixels_prompt_provider_and_expires_without_mutable_aliases(self):
        now, calls = [0.], []
        cache = DetectionCache(clock=lambda: now[0])
        def invoke():
            calls.append(True)
            return [{'score': .9}]
        first = cache.get_or_call('provider-A', b'image', 'pin', invoke)
        first[0]['score'] = 0
        self.assertEqual(cache.get_or_call('provider-A', b'image', 'pin', invoke)[0]['score'], .9)
        self.assertEqual(len(calls), 1)
        for identity, image, prompt in [('provider-B', b'image', 'pin'), ('provider-A', b'changed', 'pin'), ('provider-A', b'image', 'plate')]:
            cache.get_or_call(identity, image, prompt, invoke)
        self.assertEqual(len(calls), 4)
        now[0] = 30.
        cache.get_or_call('provider-A', b'image', 'pin', invoke)
        self.assertEqual(len(calls), 5)

    def test_cache_never_stores_errors_and_evicts_large_or_old_entries(self):
        cache = DetectionCache(max_bytes=20, max_entries=1)
        calls = []
        def fail():
            calls.append(True)
            raise ModelError('safe')
        for _ in range(2):
            with self.assertRaises(ModelError):
                cache.get_or_call('A', b'image', 'pin', fail)
        self.assertEqual(len(calls), 2)
        cache.get_or_call('A', b'image', 'pin', lambda: [1])
        cache.get_or_call('A', b'image', 'plate', lambda: [2])
        self.assertEqual(cache.get_or_call('A', b'image', 'pin', lambda: [3]), [3])
        cache.get_or_call('A', b'large', 'pin', lambda: ['x' * 100])
        self.assertEqual(cache.get_or_call('A', b'large', 'pin', lambda: [4]), [4])

    def test_compiler_repairs_validation_once_using_original_document(self):
        invalid = fixture()
        invalid['steps'][0]['zone_anchor'] = 'unknown anchor'
        with patch.object(gemini_client, '_generate', side_effect=[invalid, fixture()]) as generate:
            self.assertEqual(gemini_client.compile_manual(manual_pdf()), fixture())
        self.assertEqual(generate.call_count, 2)
        self.assertIn('failed local validation', generate.call_args.args[0])
        self.assertEqual(generate.call_args_list[0].args[1], generate.call_args_list[1].args[1])

    def test_actual_transport_retries_a_503_then_succeeds(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(503 if len(calls) == 1 else 200, json=response({'ok': True}))
        with patch.object(gemini_client, 'GEMINI_API_KEY', 'TEST_KEY'), patch('backend.runtime.time.sleep'), transport_patch(handler):
            self.assertEqual(gemini_client._generate('test', {'text':'test'}, {'type':'object'}), {'ok': True})
        self.assertEqual(len(calls), 2)
