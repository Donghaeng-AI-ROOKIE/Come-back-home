import assert from 'node:assert/strict';
import test from 'node:test';
import { appearanceLine, appearanceTags, bodyNotes } from '../src/utils/bodyNotes.ts';

test('bare numbers in the "height/build/belongings" box read as height then weight', () => {
  // 10/27 운영 사건 7ccf1a190cd3: 보호자가 네 번째 칸에 이렇게 적었고 시민 화면에 그대로 나왔다.
  assert.deepEqual(bodyNotes('160/50/검정 핸드백'), ['키 160cm', '몸무게 50kg', '검정 핸드백']);
  // 순서가 바뀌어도 범위로 가른다 — 50 은 키 범위(100~230) 밖이라 몸무게다.
  assert.deepEqual(bodyNotes('50/160'), ['몸무게 50kg', '키 160cm']);
});

test('a measurement written with a unit is split off from the words around it', () => {
  // seed 예시(backend 시드 신고)와 같은 꼴.
  assert.deepEqual(bodyNotes('160cm 마른 체형, 흰머리'), ['키 160cm', '마른 체형', '흰머리']);
  assert.deepEqual(bodyNotes('키 165, 지팡이'), ['키 165cm', '지팡이']);
  assert.deepEqual(bodyNotes('50kg'), ['몸무게 50kg']);
  assert.deepEqual(bodyNotes('160센티'), ['키 160cm']);
  assert.deepEqual(bodyNotes('50키로'), ['몸무게 50kg']);
  assert.deepEqual(bodyNotes('몸무게 50'), ['몸무게 50kg']);
  assert.deepEqual(bodyNotes('키160 몸무게50'), ['키 160cm', '몸무게 50kg']);
  assert.deepEqual(bodyNotes('약 155cm 정도'), ['키 약 155cm']);
});

test('numbers outside the ranges, or a second bare number, stay as written', () => {
  assert.deepEqual(bodyNotes('300/10/검정 가방'), ['300', '10', '검정 가방']);
  assert.deepEqual(bodyNotes('160/50/45'), ['키 160cm', '몸무게 50kg', '45']);
  // 단위가 붙어도 범위 밖이면 키·몸무게로 이름 붙이지 않는다(쌀 10kg 같은 소지품).
  assert.deepEqual(bodyNotes('쌀 10kg'), ['쌀 10kg']);
  // 키라고 써 놓고 kg 을 붙이면 무엇인지 모른다.
  assert.deepEqual(bodyNotes('키 50kg'), ['키 50kg']);
  // 숫자가 낀 다른 말은 건드리지 않는다.
  assert.deepEqual(bodyNotes('60대 후반'), ['60대 후반']);
});

test('commas, middle dots, slashes and line breaks all separate pieces; empty input gives nothing', () => {
  assert.deepEqual(bodyNotes('160·50, 검정 핸드백/지팡이\n흰머리'),
    ['키 160cm', '몸무게 50kg', '검정 핸드백', '지팡이', '흰머리']);
  assert.deepEqual(bodyNotes(''), []);
  assert.deepEqual(bodyNotes(' / , '), []);
  assert.deepEqual(bodyNotes(undefined), []);
  assert.deepEqual(bodyNotes('마른 체형'), ['마른 체형']);
});

test('alert tags keep clothing as written and name the measurements in the rest', () => {
  // 서버 경보의 appearance 는 [상의, 하의, 신발, 키/체형/소지품] 에서 빈 칸을 뺀 배열이다.
  assert.deepEqual(appearanceTags(['노란색 티', '검정 바지', '갈색 운동화', '160/50/검정 핸드백']),
    ['노란색 티', '검정 바지', '갈색 운동화', '키 160cm', '몸무게 50kg', '검정 핸드백']);
  // 구조화 인상착의가 비면 요약 한 줄이 온다(missingView.alertToView).
  assert.deepEqual(appearanceTags(['노란색 티, 검정 바지, 갈색 운동화, 160/50/검정 핸드백']),
    ['노란색 티', '검정 바지', '갈색 운동화', '키 160cm', '몸무게 50kg', '검정 핸드백']);
});

test('sizes written next to clothing are not read as height or weight', () => {
  // 옷 치수(상의 105, 신발 230)가 키로 읽히면 시민에게 틀린 키가 나간다.
  assert.deepEqual(appearanceTags(['남색 점퍼/105', '검정 구두/230', '170']),
    ['남색 점퍼/105', '검정 구두/230', '키 170cm']);
  assert.deepEqual(appearanceTags([]), []);
});

test('the alert summary line on list cards gets the same names as the chips', () => {
  // 10/28 12회차 C2: 칩은 고쳐졌는데 목록 카드 본문은 서버 summary 원문이 그대로였다.
  assert.equal(appearanceLine('회색 점퍼, 검은 바지, 흰 운동화, 160/50/검정 핸드백'),
    '회색 점퍼, 검은 바지, 흰 운동화, 키 160cm, 몸무게 50kg, 검정 핸드백');
  // 숫자가 없는 요약·대체 문구는 그대로다.
  assert.equal(appearanceLine('인상착의 정보 없음'), '인상착의 정보 없음');
  assert.equal(appearanceLine('남색 점퍼/105, 지팡이'), '남색 점퍼/105, 지팡이');
});
