import pytest
from experiments.mind_contract_ab_20261007 import probe_typed_source as t


def test_translation_keeps_required_start_release_and_scope():
    src = {'행동': '기다림', '시작에모두필요': ['길잃음인지', '가족안보임'],
           '종료에모두필요': ['가족보임'], '한정장소': '그늘터'}
    assert t.translate(src, True) == {'action': 'wait', 'start_all': ['lost_awareness', 'family_absent'],
                                     'end_all': ['family_visible'], 'only_at': '그늘터'}


def test_unknown_enum_not_repaired_from_words():
    with pytest.raises(KeyError):
        t.translate({'행동': '기다림', '시작에모두필요': ['가족이 없으면'],
                     '종료에모두필요': [], '한정장소': None}, True)


def test_schema_does_not_imply_person_specific_conditions():
    schema = t.schema(True)
    assert set(schema['properties']['시작에모두필요']['items']['enum']) == set(t.KO_FACT.values())
    assert 'default' not in str(schema)
