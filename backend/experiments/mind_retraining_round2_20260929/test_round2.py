import unittest
from pathlib import Path
import json,hashlib
from train_round2 import validate_round2_spec
from audit import audit

ROOT=Path(__file__).resolve().parent
class StudyGuards(unittest.TestCase):
    def spec(self):
        return dict(epochs=6,probe_epochs=[2,4,6],seed=928,learning_rate=1e-4,
            scheduler='constant',wall_seconds=1200,generation_attempt_limit=48,
            generation_max_tokens=900,development_generation=True,dataset_kind='original72')
    def test_both_approved_shapes(self):
        for arm in ['original72','augmented120']:
            s=self.spec();s['dataset_kind']=arm;validate_round2_spec(s)
    def test_reject_scope_expansion(self):
        for k,v in [('epochs',8),('probe_epochs',[1,2,4,6]),('wall_seconds',1201),
            ('generation_attempt_limit',49),('generation_max_tokens',901),
            ('development_generation',False),('scheduler','cosine'),('seed',12),('dataset_kind','other')]:
            with self.subTest(k=k):
                s=self.spec();s[k]=v
                with self.assertRaises(ValueError):validate_round2_spec(s)
    def test_dataset_audit(self):
        self.assertEqual(audit(ROOT/'dataset_augmented')['errors'],[])
    def test_old_rows_unchanged(self):
        old=ROOT.parent/'mind_retraining_20260928'/'lora'/'dataset_v2'
        for split in ['development','evaluation']:
            self.assertEqual((old/(split+'.jsonl')).read_bytes(),(ROOT/'dataset_augmented'/(split+'.jsonl')).read_bytes())
        before=[json.loads(x) for x in (old/'train.jsonl').read_text().splitlines()]
        after=[json.loads(x) for x in (ROOT/'dataset_augmented'/'train.jsonl').read_text().splitlines()]
        self.assertEqual(before,after[:72]);self.assertEqual(len(after),120)
    def test_supplements_not_shared_across_splits(self):
        rows=[json.loads(x) for x in (ROOT/'dataset_augmented'/'train.jsonl').read_text().splitlines()][72:]
        self.assertEqual(len({r['case_family'] for r in rows}),8)
        self.assertTrue(all(r['split']=='train' and not r['review']['independent_human_review'] for r in rows))

if __name__=='__main__':unittest.main()
