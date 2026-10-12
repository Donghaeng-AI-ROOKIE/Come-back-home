import unittest
from preflight import encode_supervision


class TokenizerDouble:
    def __init__(self,prompt,full,answer=None):
        self.prompt=prompt;self.full=full;self.answer=answer if answer is not None else full[len(prompt):]
    def apply_chat_template(self,msgs,tokenize=True,**kwargs):
        ids=self.prompt if len(msgs)==2 else self.full
        return ids if tokenize else self.decode(ids)
    def encode(self,text,**kwargs):return self.answer
    def decode(self,ids,**kwargs):return ''.join(chr(64+i) for i in ids)


class SupervisionTest(unittest.TestCase):
    def setUp(self):self.m=[{'role':r,'content':'test'} for r in ('system','user','assistant')]
    def test_full_answer_is_kept_and_prompt_masked(self):
        x=encode_supervision(self.m,TokenizerDouble([1,2],[1,2,3,4]),4)
        self.assertEqual(x['labels'],[-100,-100,3,4])
        self.assertEqual(x['input_ids'],[1,2,3,4])
    def test_overflow_rejected_instead_of_truncating_answer(self):
        with self.assertRaisesRegex(ValueError,'truncated'):
            encode_supervision(self.m,TokenizerDouble([1,2],[1,2,3,4]),3)
    def test_entirely_masked_record_rejected(self):
        with self.assertRaisesRegex(ValueError,'no_supervised'):
            encode_supervision(self.m,TokenizerDouble([1,2],[1,2]),4)
    def test_template_prefix_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'prefix_mismatch'):
            encode_supervision(self.m,TokenizerDouble([1,5],[1,2,3]),4)

    def test_roundtrip_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'roundtrip'):
            encode_supervision(self.m,TokenizerDouble([1,2],[1,2,3],answer=[4]),4)
    def test_header_answer_bpe_merge_keeps_generation_prefix(self):
        class BoundaryTokenizer(TokenizerDouble):
            def apply_chat_template(self,msgs,tokenize=True,**kwargs):
                if not tokenize:return 'AB' if len(msgs)==2 else 'ABC'
                return [1,2] if len(msgs)==2 else [1,99]
        x=encode_supervision(self.m,BoundaryTokenizer([1,2],[1,99],answer=[3]),4)
        self.assertEqual(x['input_ids'],[1,2,3])
        self.assertEqual(x['labels'],[-100,-100,3])


if __name__=='__main__':unittest.main()
