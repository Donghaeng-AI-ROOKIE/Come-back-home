import unittest
from copy import deepcopy
from contract import validate, executable, messages


class ContractTest(unittest.TestCase):
    def setUp(self):
        self.c={'person':{'evidence_notes':[{'id':'N1','text':'합성 원문'}]},'research':[],
                'known_places':[{'label':'A'}],'environment':{'map_proximity_m':{'park':20}},
                'state':{'current_action':'seek','elapsed_minutes':60,'last_rest_end_minutes':58,
                         'recent_events':[{'kind':'lost','elapsed_minutes':59}]}}
        self.v={'status':'decision','action':'rest','goal_operation':'keep','goal_label':None,
                'avoid_feature':None,'evidence_ids':['N1','state'],'reason':'피로 조건에 따라 쉼','confusion_level':'unknown'}

    def test_abstention_never_executes(self):
        self.v.update(status='insufficient_information',action=None,goal_operation=None)
        self.assertIsNone(executable(self.v,self.c))
        self.v['action']='continue'
        with self.assertRaisesRegex(ValueError,'abstention'):validate(self.v,self.c)

    def test_rest_does_not_erase_goal(self):
        self.v['goal_operation']='clear'
        with self.assertRaisesRegex(ValueError,'goal_operation'):validate(self.v,self.c)

    def test_unknown_goal_rejected(self):
        self.v.update(action='seek',goal_operation='set',goal_label='unregistered')
        with self.assertRaisesRegex(ValueError,'unregistered'):validate(self.v,self.c)

    def test_unknown_source_rejected(self):
        self.v['evidence_ids']=['R99']
        with self.assertRaisesRegex(ValueError,'unknown_evidence'):validate(self.v,self.c)

    def test_stationary_continue_rejected(self):
        self.c['state']['current_action']='rest';self.v['action']='continue'
        with self.assertRaisesRegex(ValueError,'resume'):validate(self.v,self.c)

    def test_unmapped_avoidance_rejected(self):
        self.v.update(action='avoid',avoid_feature='water')
        with self.assertRaisesRegex(ValueError,'unmapped'):validate(self.v,self.c)

    def test_history_time_is_arithmetic_and_original_preserved(self):
        import json
        before=deepcopy(self.c);view=json.loads(messages(self.c)[1]['content'])
        self.assertEqual(view['state']['recent_events'][0]['minutes_before_current_decision'],1)
        self.assertEqual(view['state']['minutes_since_last_rest_completed'],2)
        self.assertEqual(before,self.c)


if __name__=='__main__':unittest.main()
