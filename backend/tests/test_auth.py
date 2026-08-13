"""계정 — 아이디/비밀번호 로그인과 사용자별 기록 분리."""
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)


def test_signup_login_and_token_lifecycle():
    r = c.post('/auth/signup', json={'login_id': 'AliceKim', 'password': 'pw1234', 'role': 'citizen'})
    assert r.status_code == 200
    body = r.json()
    assert body['login_id'] == 'alicekim'          # 소문자 정규화
    assert 'password' not in str(body)             # 해시·원문 미노출
    token = body['token']

    # 같은 아이디 재가입 불가 (대소문자 무관)
    assert c.post('/auth/signup', json={'login_id': 'alicekim', 'password': 'x1234'}).status_code == 409

    # 로그인 성공/실패
    assert c.post('/auth/login', json={'login_id': 'alicekim', 'password': 'pw1234'}).status_code == 200
    assert c.post('/auth/login', json={'login_id': 'alicekim', 'password': 'nope'}).status_code == 401
    # 없는 아이디도 같은 401 — 계정 열거 방지
    assert c.post('/auth/login', json={'login_id': 'ghost', 'password': 'pw1234'}).status_code == 401

    # 토큰 확인 → 로그아웃 → 무효화
    assert c.get('/auth/me', headers={'Authorization': f'Bearer {token}'}).status_code == 200
    assert c.post('/auth/logout', headers={'Authorization': f'Bearer {token}'}).status_code == 200
    assert c.get('/auth/me', headers={'Authorization': f'Bearer {token}'}).status_code == 401


def test_invalid_inputs_rejected():
    assert c.post('/auth/signup', json={'login_id': 'ab', 'password': 'pw1234'}).status_code == 400
    assert c.post('/auth/signup', json={'login_id': '한글아이디', 'password': 'pw1234'}).status_code == 400
    # 시안이 "이메일 주소"를 받으므로 이메일도 통과해야 한다
    assert c.post('/auth/signup', json={'login_id': 'walker@sogang.ac.kr', 'password': 'pw1234'}).status_code == 200
    assert c.post('/auth/signup', json={'login_id': 'a@b', 'password': 'pw1234'}).status_code == 400
    assert c.post('/auth/signup', json={'login_id': 'okid1', 'password': '12'}).status_code == 400
    assert c.post('/auth/signup', json={'login_id': 'okid2', 'password': 'pw1234', 'role': 'admin'}).status_code == 400


def test_walk_records_are_separated_by_user():
    a = c.post('/auth/signup', json={'login_id': 'walkerA', 'password': 'pw1234'}).json()
    b = c.post('/auth/signup', json={'login_id': 'walkerB', 'password': 'pw1234'}).json()

    s = c.post('/walk/sessions', json={'user_id': a['user_id'], 'area_label': '신촌'}).json()
    c.post(f"/walk/sessions/{s['id']}/end", json={'distance_km': 1.5, 'duration_min': 20})

    stats_a = c.get(f"/walk/stats?user_id={a['user_id']}").json()
    stats_b = c.get(f"/walk/stats?user_id={b['user_id']}").json()
    assert stats_a['walk_count'] == 1 and stats_a['total_km'] == 1.5
    assert stats_b['walk_count'] == 0, "다른 계정의 기록이 보이면 안 된다"


def test_password_is_not_stored_in_plaintext():
    c.post('/auth/signup', json={'login_id': 'secretly', 'password': 'sup3rsecret'})
    from app import storage
    acc = next(a for a in storage.accounts.list() if a.login_id == 'secretly')
    assert 'sup3rsecret' not in acc.password_hash
    assert acc.password_hash != 'sup3rsecret'
    assert len(acc.password_salt) == 32
