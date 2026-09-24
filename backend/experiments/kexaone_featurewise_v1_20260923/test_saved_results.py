"""Verify the saved study without APIs, app imports, or new walking simulations."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import unittest

from format_guard import FormatRejected, recover_envelope
from protocol import inspect

ROOT = Path(__file__).resolve().parent

def read(name):
    return json.loads((ROOT / name).read_text())


class SavedExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outputs = read('saved_outputs.json')
        cls.cases = {x['case']: x for x in read('cases.json')}
        cls.replays = read('replay_diagnostics.json')

    def test_original_outcomes_are_preserved(self):
        self.assertEqual(len(self.outputs), 24)
        self.assertEqual(len({x['id'] for x in self.outputs}), 24)
        for row in self.outputs:
            checked = inspect(row['raw_content'], self.cases[row['case']], row['condition'])
            self.assertEqual(checked['prior_usable'], row['original_prior_usable'], row['id'])
            self.assertEqual(checked['envelope_valid'], row['original_envelope_valid'], row['id'])
            self.assertEqual(checked['envelope_errors'], row['original_envelope_errors'], row['id'])
            self.assertEqual(row['finish_reason'], 'stop')
        self.assertEqual(sum(x['original_prior_usable'] for x in self.outputs), 21)
        self.assertEqual(sum(x['original_envelope_valid'] for x in self.outputs), 2)

    def test_recovery_preserves_values_and_remaining_failures(self):
        usable = strict = recovered_failures = 0
        for row in self.outputs:
            original = inspect(row['raw_content'], self.cases[row['case']], row['condition'])
            value, repairs = recover_envelope(row['raw_content'], row['condition'])
            checked = inspect(json.dumps(value, ensure_ascii=False), self.cases[row['case']], row['condition'])
            usable += checked['prior_usable']
            strict += checked['envelope_valid']
            recovered_failures += checked['prior_usable'] and not row['original_prior_usable']
            parsed = original.get('structured', {})
            if 'prior' in parsed:
                self.assertEqual(parsed['prior'], value['prior'])
            if 'lift_unique_misnested_integration_and_prior' in repairs:
                self.assertEqual(parsed['features']['prior'], value['prior'])
                self.assertEqual(parsed['features']['integration'], value['integration'])
        self.assertEqual((usable, strict, recovered_failures), (24, 5, 3))

    def test_ambiguous_or_incomplete_json_is_rejected(self):
        for raw in ['{"a":1} prose', '{"a":1}{"b":2}', '{"a":1,"a":2}',
                    '{"a":NaN}', '{"prior":', '```json\n{}\n``` trailing', '{"a":1}}}']:
            with self.subTest(raw=raw), self.assertRaises(FormatRejected):
                recover_envelope(raw, 'CONTROL')

    def test_missing_or_invalid_prior_is_not_invented(self):
        sample = next(x for x in self.outputs if x['id'] == 'C03_FEATURES_0')
        value, _ = recover_envelope(sample['raw_content'], 'FEATURES')
        for mutation in ['missing_strategy', 'wrong_number', 'wrong_label']:
            broken = copy.deepcopy(value)
            if mutation == 'missing_strategy':
                del broken['prior']['strategy_probs']['random_walk']
            elif mutation == 'wrong_number':
                broken['prior']['strategy_probs']['random_walk'] = '높음'
            else:
                broken['prior']['attraction_levels']['미등록장소'] = '상'
            repaired, _ = recover_envelope(json.dumps(broken), 'FEATURES')
            self.assertEqual(repaired, broken)
            self.assertFalse(inspect(json.dumps(repaired), self.cases['C03'], 'FEATURES')['prior_usable'])
        conflict = {'features': dict(value['features'], prior=value['prior'], integration=value['integration']),
                    'prior': dict(value['prior'], radius_level='하')}
        repaired, repairs = recover_envelope(json.dumps(conflict), 'FEATURES')
        self.assertEqual(repaired, conflict)
        self.assertEqual(repairs, [])

    def test_replay_coverage_and_junction_denominators(self):
        self.assertEqual(len(self.replays), 63)
        outputs = {x['id']: x for x in self.outputs}
        seen = set()
        for row in self.replays:
            key = (row['case'], row['condition'], row['repeat'], row['seed'])
            self.assertNotIn(key, seen)
            seen.add(key)
            source = f"{row['case']}_{row['condition']}_{row['repeat']}"
            self.assertTrue(outputs[source]['original_prior_usable'])
            self.assertEqual(row['metrics']['walkers'], 500)
            self.assertEqual(row['metrics']['nonedge_transitions'], 0)
            j = row['junction_metrics']
            for count, rate in [('side_turn_count', 'side_turn_rate'), ('turn_45plus_count', 'turn_45plus_rate')]:
                self.assertLessEqual(j[count], j['junction_opportunities'])
                if j['junction_opportunities']:
                    self.assertAlmostEqual(j[rate], j[count] / j['junction_opportunities'])
                else:
                    self.assertIsNone(j[rate])
        for row in self.outputs:
            actual = {key[3] for key in seen if key[:3] == (row['case'], row['condition'], row['repeat'])}
            self.assertEqual(actual, {41, 73, 109} if row['original_prior_usable'] else set())

    def test_matched_comparison_is_recomputed_from_saved_runs(self):
        outputs = {(x['case'], x['condition'], x['repeat']): x for x in self.outputs}
        matched = read('matched_comparison.json')['rows']
        for row in matched:
            expected_repeats = [r for r in [0, 1] if all(
                outputs[(c, condition, r)]['original_prior_usable']
                for c in [row['a'], row['b']] for condition in ['CONTROL', 'FEATURES'])]
            self.assertEqual(row['matched_repeats'], expected_repeats)
            for side in ['a', 'b']:
                runs = [x for x in self.replays if x['case'] == row[side]
                        and x['condition'] == row['condition'] and x['repeat'] in expected_repeats]
                saved = row['values'][side]
                self.assertEqual(saved['runs'], len(runs))
                for key, getter in [('near_origin', lambda x: x['metrics']['endpoint_within_200m']),
                                    ('road_km', lambda x: x['metrics']['road_path_km']),
                                    ('side_turn', lambda x: x['junction_metrics']['side_turn_rate'])]:
                    if runs:
                        self.assertAlmostEqual(saved[key], statistics.mean(getter(x) for x in runs))
                    else:
                        self.assertIsNone(saved[key])
                for place, value in saved['zone_entry'].items():
                    self.assertAlmostEqual(value, statistics.mean(x['metrics']['zone_entry_share'][place] for x in runs))
                for group, prior_key in [('strategy', 'strategy_probs'), ('attraction', 'attraction_weights')]:
                    for name, value in saved[group].items():
                        self.assertAlmostEqual(value, statistics.mean(
                            outputs[(row[side], row['condition'], r)]['final_prior'][prior_key][name]
                            for r in expected_repeats))

    def test_action_mismatches_use_raw_prior_before_guardrails(self):
        baseline = read('provenance.json')['SAR_reference']['final_prior']['strategy_probs']
        actions = []
        for row in self.outputs:
            if row['condition'] != 'FEATURES' or not row['original_prior_usable']:
                continue
            value, _ = recover_envelope(row['raw_content'], 'FEATURES')
            for action in value['integration']:
                keys = action['target'].split('.')
                if len(keys) != 2 or keys[0] != 'strategy_probs':
                    continue
                delta = value['prior']['strategy_probs'][keys[1]] - baseline[keys[1]]
                actual = 'maintain' if abs(delta) < 1e-9 else 'increase' if delta > 0 else 'decrease'
                actions.append((row['id'], action['action'], action['action'] != 'uncertain' and actual != action['action']))
        self.assertEqual(sum(x[1] != 'uncertain' for x in actions), 33)
        self.assertEqual(sum(x[2] for x in actions), 9)
        self.assertEqual(len({x[0] for x in actions if x[2]}), 7)

    def test_example_quotes_match_stored_input_or_output(self):
        outputs = {x['id']: x for x in self.outputs}
        document = (ROOT / 'EXAMPLES.md').read_text()
        for quote in read('example_quotes.json'):
            if quote['source_type'] == 'case_note':
                actual = self.cases[quote['source_id']]['notes'][quote['note_index']]
            else:
                actual, _ = recover_envelope(outputs[quote['source_id']]['raw_content'], 'FEATURES')
                for field in quote['field']:
                    actual = actual[field]
            self.assertEqual(actual, quote['text'])
            self.assertIn(quote['text'], document)
        for output_id in ['C03_FEATURES_1', 'C05_FEATURES_1', 'C06_FEATURES_1']:
            self.assertIn(outputs[output_id]['raw_content'], document)

    def test_map_panels_use_matching_saved_run_metrics(self):
        with gzip.open(ROOT / 'assets/map_data.json.gz', 'rt') as handle:
            data = json.load(handle)
        self.assertEqual(len(data['panels']), 4)
        self.assertEqual({(p['case'], p['condition']) for p in data['panels']},
                         {(c, m) for c in ['C02', 'C04'] for m in ['CONTROL', 'FEATURES']})
        for panel in data['panels']:
            self.assertEqual((panel['repeat'], panel['seed']), (1, 41))
            self.assertEqual(len(panel['paths']), 40)
            source = next(x for x in self.replays if x['case'] == panel['case']
                          and x['condition'] == panel['condition']
                          and x['repeat'] == 1 and x['seed'] == 41)
            self.assertEqual(source['metrics'], panel['metrics'])
            for path in panel['paths']:
                self.assertTrue(path)
                self.assertEqual(path[0], [0.0, 0.0])
                self.assertTrue(all(abs(x) <= data['extent_km'] and abs(y) <= data['extent_km']
                                    for x, y in path))

    def test_usage_and_frozen_text_hashes(self):
        usage = read('usage_summary.json')
        self.assertEqual(usage['new_k_calls'], 24)
        self.assertEqual(usage['new_replays'], 63)
        self.assertEqual(usage['prompt_tokens'] + usage['completion_tokens'], 76710)
        for key in ['new_sar_calls', 'new_embedding_calls', 'new_map_calls', 'retries']:
            self.assertEqual(usage[key], 0)
        for key in ['actual_cost', 'unit_price', 'support_round']:
            self.assertIsNone(usage[key])
        hashes = read('provenance.json')['original_source_hashes']
        for name in ['control_prompt.txt', 'feature_prompt.txt', 'protocol.py', 'legacy_protocol.py']:
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), hashes[name])


if __name__ == '__main__':
    unittest.main()
