"""합성 보호자 대본이 실제 온보딩의 모든 슬롯을 덮는지 검증."""

from collections import Counter

from experiments.personalized_alert_replay.build_persona_bank import (
    ALL_SLOT_KEYS,
    AXES,
    LEVELS,
    answers_for,
    load_profiles,
)


def test_ten_profiles_have_every_slot_answer():
    profiles = load_profiles()
    assert len(profiles) == 10
    assert len({profile.profile_id for profile in profiles}) == 10
    for profile in profiles:
        answers = answers_for(profile)
        assert set(answers) == set(ALL_SLOT_KEYS)
        assert all(answer.strip() for answer in answers.values())
        assert profile.synthetic_name in answers["identity"]
        assert str(profile.age) in answers["identity"]
        assert profile.home_area in answers["home"]
        assert "도보" in answers["routine_destinations"]


def test_target_levels_are_balanced_but_not_directly_injected():
    profiles = load_profiles()
    expected = Counter({level: 2 for level in LEVELS})
    for axis in AXES:
        assert Counter(profile.target_levels[axis] for profile in profiles) == expected
    source = __import__(
        "experiments.personalized_alert_replay.build_persona_bank",
        fromlist=["dummy"],
    )
    assert not hasattr(source, "build_persona")


def test_behavior_patterns_are_balanced():
    profiles = load_profiles()
    counts = Counter(profile.expected_behavior_tendency for profile in profiles)
    assert counts == Counter({
        "stay": 2, "move": 4, "backtrack": 2, "hide": 2,
    })
    assert len({profile.behavior_archetype for profile in profiles}) == 10


def test_answers_are_individually_written_and_walk_only():
    profiles = load_profiles()
    wandering = []
    lost = []
    for profile in profiles:
        answers = answers_for(profile)
        wandering.append(answers["dementia_wandering_pattern"])
        lost.append(answers["lost_behavior"])
        joined = " ".join(answers.values())
        assert "대중교통을 이용합니다" not in joined
        assert "버스를 이용합니다" not in joined
        assert "지하철을 이용합니다" not in joined
    assert len(set(wandering)) == 10
    assert len(set(lost)) == 10
