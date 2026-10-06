"""Uncalled ablation: exact caregiver notes with an explicit scene description.

This removes the prepared-summary input, not the source. It tests whether input
representation contributes to errors; it is not a production replacement and
contains no guardian keyword-to-action map. Output contracts and menus are kept
identical to situated_actions to isolate the input view.
"""
import json
from experiments.mind_policy_candidates import situated_actions


SCENE_FIELDS = {
    'elapsed_minutes': '실종 후 경과 시간(분), 걸은 시간과 다름',
    'actual_walking_minutes': '현재까지 실제 보행한 누적 시간(분)',
    'continuous_walk_minutes': '마지막 휴식 이후 연속 보행 시간(분)',
    'distance_since_rest_m': '마지막 휴식 이후 보행 거리(m)',
    'fatigue_high': '시뮬레이션의 높은 피로 상태, 임상 측정값 아님',
    'current_action': '현재 실행 중인 동작, 다음 동작의 정답 아님',
    'current_target_label': '기억 중인 목표, 지금 이동 중이라는 뜻 아님',
    'physical_arrival': '목적지 좌표에 도착했는가',
    'target_recognized': '목적지를 알아보았는가',
    'lost_awareness': '길을 잃었다고 알고 있는가',
    'family_present': '가족이 곁에 있는가',
    'pain_observed': '현재 통증을 확인했는가',
    'clock_hour': '현재 한국 시각(시), 경과 시간과 다름',
    'noisy': '현재 장소의 소음이 확인되었는가',
    'crowded': '현재 장소의 혼잡이 확인되었는가',
    'current_place_label': '현재 장소 이름',
    'map_distance_m': '지도 시설까지 거리(m), 소음·혼잡 관측과 다름',
}


def request(personal, scene, model):
    body = situated_actions.request(personal, scene, model, thinking=True)
    # Copy every source verbatim; neither relevance retrieval nor textual rules
    # can quietly erase a correction or broaden a named-place scope.
    view = {
        '원문': personal['notes'],
        '등록_장소': personal['places'],
        '현재_사실': [
            {'항목': title, '값': scene.get(key)}
            for key, title in SCENE_FIELDS.items()
        ],
        '현재_사실의_뜻': 'true는 확인된 참, false는 확인된 거짓, null은 미확인. 기록은 합성 장면.',
        '선택_명령': situated_actions.menu(scene, personal),
        '연구_발췌': [],
        '생략한_입력': '저장된 초기 요약만 제외한 개발 비교. 보호자 원문은 전부 보존.',
    }
    body['messages'][1]['content'] = json.dumps(view, ensure_ascii=False)
    if len(json.dumps(body, ensure_ascii=False).encode()) > 40000:
        raise ValueError('input byte cap')
    return body


validate = situated_actions.validate
