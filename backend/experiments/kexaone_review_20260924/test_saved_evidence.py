"""Offline integrity checks; these do not judge model semantic correctness."""
from pathlib import Path
import collections
import hashlib
import json
import math
import re
import unittest

ROOT=Path(__file__).resolve().parent
def read(path): return json.loads((ROOT/path).read_text())
def outputs(alias):return read(f'evidence/{alias}/saved_outputs.json')

class SavedEvidenceTests(unittest.TestCase):
    def test_all_raw_responses_preserved_and_hashed(self):
        counts={'01_prior':72,'03_chain':72,'04_prompt_v3':12,'05_prompt_sweep':48,'06_refinement':24,'07_featurewise':24,'08_casewise':40,'09_observation':32}
        for alias,n in counts.items():
            data=outputs(alias);self.assertEqual(len(data),n)
            self.assertEqual(len({o['file'] for o in data}),n)
            for o in data:self.assertEqual(hashlib.sha256(o['raw_content'].encode()).hexdigest(),o['raw_sha256'])

    def test_quotes_match_literal_output(self):
        for q in read('example_quotes.json'):
            raw=next(o['raw_content'] for o in outputs(q['experiment']) if o['file']==q['file'])
            self.assertIn(q['quote'],raw)

    def test_historical_reports_unchanged(self):
        for p in read('source_provenance.json')['sources']:
            if p['transform'].startswith('byte-for-byte'):
                self.assertEqual(hashlib.sha256((ROOT/p['export']).read_bytes()).hexdigest(),p['source_sha256'])

    def test_ledger_totals_and_model_outputs_agree(self):
        events=read('usage_terminal_events.json');self.assertEqual(len(events),330)
        self.assertEqual(len({o['event_id'] for o in events}),330)
        self.assertEqual(len({o['attempt_id'] for o in events}),330)
        totals=collections.defaultdict(lambda:[0,0])
        for e in events:
            totals[e['model_requested']][0]+=1;totals[e['model_requested']][1]+=e['usage']['total_tokens']
            self.assertIsNone(e.get('actual_cost'));self.assertIsNone(e.get('support_round'))
            self.assertNotIn('endpoint_host',e)
        expected=read('usage_totals.json')['by_model']
        for model,(calls,tokens) in totals.items():self.assertEqual(expected[model],{'calls':calls,'total_tokens':tokens})
        generated=collections.defaultdict(lambda:[0,0])
        for f in ROOT.glob('evidence/*/saved_outputs.json'):
            for o in json.loads(f.read_text()):
                generated[o['model_returned']][0]+=1;generated[o['model_returned']][1]+=o['usage']['total_tokens']
        self.assertEqual(dict(generated),{m:v for m,v in totals.items() if m!='embedding-query'})

    def test_latest_contract_counts_keep_posthoc_separate(self):
        data=outputs('09_observation');post=read('evidence/09_observation/shape_diagnostic.json')
        for arm,decodable,after in [('NO_RAG',11,7),('WITH_RAG',12,2)]:
            group=[o for o in data if o['arm']==arm];self.assertEqual(len(group),16)
            decoded=0
            for o in group:
                try:json.loads(o['raw_content']);decoded+=1
                except json.JSONDecodeError:pass
                self.assertEqual(o['finish_reason'],'stop')
            self.assertEqual(decoded,decodable)
            self.assertEqual(sum(o['checks']['valid'] for o in group),0)
            self.assertEqual(sum(post[o['id']]['valid'] for o in group),after)
        self.assertEqual(max(o['usage']['completion_tokens'] for o in data),799)

    def test_casewise_structure_counts_and_diagnostic_denominator(self):
        data=outputs('08_casewise')
        for arm,expected in [('A',13),('B',12)]:
            group=[o for o in data if o['arm']==arm]
            self.assertEqual(len(group),16);self.assertEqual(sum(o['checks']['valid'] for o in group),expected)
        diag=read('evidence/08_casewise/verification_final.json')['unsupported_straight_diagnostic']
        self.assertTrue(diag['post_hoc']);self.assertEqual(len(diag['cases']),6)
        for arm,n in [('A',1),('B',5)]:
            ids=[s for s in diag['flagged_ids'] if f'_{arm}_' in s]
            self.assertEqual(len(ids),n);self.assertEqual(diag['counts'][arm]['raw_reviewed'],12)
            for id in ids:self.assertIn('직진',next(o['raw_content'] for o in data if o['id']==id))

    def test_matched_walking_values_and_fixed_path_selection(self):
        rows=[r for r in read('evidence/06_refinement/matched_comparison.json')['rows'] if r['family']=='F05']
        for r,diff in zip(rows,[.004,.06133333333333335,.1]):
            self.assertEqual(r['repeat'],1);self.assertEqual(r['n_seeds'],3)
            self.assertAlmostEqual(r['variants']['A']['endpoint_within_200m']-r['variants']['B']['endpoint_within_200m'],diff)
        d=read('assets/path_evidence.json');self.assertEqual(len(d['panels']),4)
        for p in d['panels']:
            self.assertEqual(p['seed'],41);self.assertEqual(p['repeat'],1);self.assertEqual(p['source_count'],500)
            self.assertEqual([w['walker_idx'] for w in p['paths']],list(range(40)))
            for w in p['paths']:
                self.assertFalse(w['mind_fired'])
                segments=[d['segments'][k] for k in w['segments']]
                for a,b in zip(segments,segments[1:]):
                    self.assertLess(math.hypot((a[-1][0]-b[0][0])*111000,(a[-1][1]-b[0][1])*88000),1)

    def test_editorial_links_and_no_credentials_in_exports(self):
        for file in ROOT.glob('*.md'):
            for link in re.findall(r'\]\(([^)]+)\)',file.read_text()):
                if link.startswith(('https://','http://','#')):continue
                self.assertTrue((file.parent/link.split('#')[0]).exists(),(file.name,link))
        for file in ROOT.rglob('*.json'):
            text=file.read_text()
            self.assertNotRegex(text,r'(?:sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|Bearer [A-Za-z0-9._-]{20,})')

if __name__=='__main__':unittest.main()
