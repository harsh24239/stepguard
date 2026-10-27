"""Evaluation accounting includes errors and never relabels Gemini as Meta."""

import json
from contextlib import redirect_stdout
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend import meta_client
from backend.model_errors import ModelError
from backend.schemas import Checklist
from backend.tests.test_compiler import fixture
from backend.tests.test_gemini import png
from backend.tests.test_judge import model_output
from eval import baseline_vs_stepguard as evaluation


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.case = evaluation.Case(case_id='missing-01', image='photo.png', step_id=1, category='missing', expected_verdict='fail')
        self.step = Checklist.model_validate(fixture()).steps[0]
        self.prepared = [(self.case, self.step, png())]

    def test_mock_and_unacknowledged_demo_never_produce_measured_results(self):
        with patch.object(meta_client, 'MOCK_MODE', True), self.assertRaisesRegex(ValueError, 'refuses MOCK'):
            evaluation.evaluate(self.prepared, allow_gemini_demo=True)
        with patch.object(meta_client, 'MOCK_MODE', False), patch.object(meta_client, 'MODEL_PROVIDER', 'gemini'), self.assertRaisesRegex(ValueError, 'allow-gemini-demo'):
            evaluation.evaluate(self.prepared)

    def test_disagreement_errors_and_false_passes_are_counted_without_media(self):
        with patch.object(meta_client, 'MOCK_MODE', False), patch.object(meta_client, 'MODEL_PROVIDER', 'gemini'), \
                patch.object(meta_client, 'baseline', return_value=model_output()), \
                patch.object(evaluation, 'inspect_step', side_effect=ModelError('PRIVATE_KEY_IMAGE')):
            report = evaluation.evaluate(self.prepared, allow_gemini_demo=True)
        self.assertEqual(report['baseline']['false_passes'], 1)
        self.assertEqual(report['baseline']['agreements'], 0)
        self.assertEqual(report['stepguard']['errors'], 1)
        self.assertEqual(report['stepguard']['total_cases'], 1)
        self.assertIsNone(report['stepguard']['median_latency_ms'])
        self.assertNotIn('PRIVATE', json.dumps(report))
        self.assertNotIn('photo.png', json.dumps(report))
        self.assertIn('GEMINI DEMO EXPERIMENT', evaluation.markdown(report))

    def test_same_pixels_reach_both_paths_and_pipeline_stays_stateless(self):
        with patch.object(meta_client, 'MOCK_MODE', False), patch.object(meta_client, 'MODEL_PROVIDER', 'gemini'), \
                patch.object(meta_client, 'baseline', return_value=model_output()) as baseline, \
                patch.object(evaluation, 'inspect_step', return_value='EVIDENCE') as inspector, \
                patch.object(evaluation, 'judge_step', return_value=SimpleNamespace(verdict='fail')):
            report = evaluation.evaluate(self.prepared, allow_gemini_demo=True)
        self.assertEqual(baseline.call_args.args[1], inspector.call_args.args[1])
        self.assertEqual(report['stepguard']['agreements'], 1)

    def test_json_report_target_is_rejected_before_inputs_or_paid_calls(self):
        with patch('sys.argv', ['evaluate', '--checklist', 'unused.json', '--cases', 'unused.json', '--output', 'result.json']), \
                patch.object(evaluation, 'load_cases') as loader, \
                patch.object(evaluation, 'evaluate') as invoke, redirect_stdout(io.StringIO()):
            self.assertEqual(evaluation.main(), 2)
        loader.assert_not_called()
        invoke.assert_not_called()

    def test_load_validates_every_image_and_rejects_escape_duplicate_or_missing_inputs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'checklist.json').write_text(json.dumps(fixture()))
            (root/'photo.png').write_bytes(png())
            manifest = root/'cases.json'
            manifest.write_text(json.dumps([self.case.model_dump()]))
            self.assertEqual(len(evaluation.load_cases(root/'checklist.json', manifest)), 1)
            for cases in [[], [self.case.model_dump()] * 2, [{**self.case.model_dump(), 'image':'../outside.png'}],
                          [{**self.case.model_dump(), 'step_id':99}], [{**self.case.model_dump(), 'expected_verdict':'invented'}]]:
                manifest.write_text(json.dumps(cases))
                with self.assertRaises(ValueError):
                    evaluation.load_cases(root/'checklist.json', manifest)
