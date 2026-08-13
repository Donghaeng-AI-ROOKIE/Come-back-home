import { useMemo, useState } from "react";
import type { LiveState } from "../App";
import { api, DEMO_CASE_ID } from "../api";
import { T } from "../theme";

/** S3 신고 접수 — 접수 즉시 D1 반경 경보 자동 발송(백엔드 reflex).
 *  라이브: POST /phase1/reports → 접수 완료 화면 → 관제 상세 이동.
 *  데모: 폼·완료 화면 시연(김순자 프리필). */

const JEONGNEUNG = { lat: 37.6027, lng: 127.0129 };

export default function Intake({
  live,
  onDone,
}: {
  live: LiveState;
  onDone: (caseId: string) => void;
}) {
  const [lat, setLat] = useState(String(JEONGNEUNG.lat));
  const [lng, setLng] = useState(String(JEONGNEUNG.lng));
  const [lkpTime, setLkpTime] = useState(() => {
    const d = new Date(Date.now() - 30 * 60000);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T${d.toTimeString().slice(0, 5)}`;
  });
  const [personaId, setPersonaId] = useState<string>("");
  const [desc, setDesc] = useState("회색 점퍼, 검은색 바지, 지팡이 사용. 흰머리, 키 155cm가량.");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [doneCase, setDoneCase] = useState<string | null>(null);

  const personas = useMemo(() => live.overview?.personas ?? [], [live.overview]);

  const submit = async () => {
    if (!live.live) {
      // 데모 모드 — 실제 접수 없이 완료 화면 시연
      setDoneCase(DEMO_CASE_ID);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const c = await api.createReport({
        missing_type: "dementia",   // 대상 유형은 치매 단독 (2026-08-03)
        lkp: { lat: parseFloat(lat), lng: parseFloat(lng) },
        lkp_time: lkpTime.replace("T", " "),
        persona_id: personaId || undefined,
        with_photo: false,
        with_document: false,
      });
      setDoneCase(c.id);
    } catch (e) {
      setError(String(e).slice(0, 250));
    } finally {
      setBusy(false);
    }
  };

  const label: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 600,
    color: "#c1c5d6",
    marginBottom: 9,
  };
  const field: React.CSSProperties = {
    width: "100%",
    padding: "11px 14px",
    borderRadius: 9,
    background: T.inset,
    border: `1px solid rgba(233,233,237,.1)`,
    fontSize: 13,
    color: T.text,
    outline: "none",
  };

  if (doneCase) {
    return (
      <div
        style={{
          flex: 1,
          background: T.mapBg,
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "center",
          padding: "60px 20px",
        }}
      >
        <div
          style={{
            width: 520,
            background: T.surface,
            border: `1px solid rgba(233,233,237,.1)`,
            borderRadius: 16,
            boxShadow: "0 24px 70px rgba(0,0,0,.5)",
            padding: "34px 30px",
            textAlign: "center",
            animation: "popIn .25s ease",
          }}
        >
          <div
            style={{
              width: 64,
              height: 64,
              borderRadius: "50%",
              background: T.redBg,
              border: `1px solid ${T.redBorder}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 18px",
              fontSize: 26,
              color: T.redText,
            }}
          >
            ✓
          </div>
          <h2 style={{ margin: 0, fontSize: 21, fontWeight: 700 }}>신고 접수 완료</h2>
          <div style={{ fontSize: 13.5, color: "#c1c5d6", marginTop: 8, lineHeight: 1.6 }}>
            케이스가 등록되었습니다.
            <br />
            <b style={{ color: T.redText }}>반경 즉시 경보(D1)</b>가 LKP 반경 19셀에 자동
            발송되었습니다.
          </div>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 7,
              marginTop: 14,
              padding: "6px 12px",
              borderRadius: 7,
              background: "rgba(240,166,60,.1)",
              border: `1px solid rgba(240,166,60,.3)`,
              fontSize: 11.5,
              color: T.amberText,
            }}
          >
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: T.amber }} />
            발송 시뮬레이션 · 응답 sent=false
          </div>
          <div
            style={{
              marginTop: 22,
              padding: 14,
              borderRadius: 10,
              background: T.inset,
              border: `1px solid rgba(233,233,237,.08)`,
              display: "flex",
              justifyContent: "space-between",
              fontSize: 12,
            }}
          >
            <span style={{ color: "#8a90a6" }}>케이스 ID</span>
            <span className="mono" style={{ color: T.text }}>
              {doneCase}
            </span>
          </div>
          <button
            onClick={() => onDone(doneCase)}
            style={{
              display: "block",
              width: "100%",
              marginTop: 20,
              padding: 12,
              borderRadius: 9,
              background: "transparent",
              border: `1px solid ${T.accent}`,
              color: T.accentLighter,
              fontSize: 14,
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            관제 상세(S2)로 이동 · AI 예측 실행
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        flex: 1,
        background: T.mapBg,
        backgroundImage: "radial-gradient(circle at 30% 40%,rgba(240,166,60,.05),transparent 40%)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        padding: "40px 20px",
      }}
    >
      <div
        style={{
          width: 640,
          background: T.surface,
          border: `1px solid rgba(233,233,237,.1)`,
          borderRadius: 16,
          boxShadow: "0 24px 70px rgba(0,0,0,.5)",
          overflow: "hidden",
          animation: "popIn .25s ease",
        }}
      >
        <div
          style={{
            padding: "20px 26px",
            borderBottom: `1px solid rgba(233,233,237,.08)`,
            display: "flex",
            alignItems: "center",
            gap: 11,
          }}
        >
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: 9,
              background: T.redBg,
              border: `1px solid rgba(242,85,90,.34)`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: T.redText,
              fontWeight: 700,
            }}
          >
            !
          </div>
          <div>
            <h2 style={{ margin: 0, fontSize: 19, fontWeight: 700 }}>실종 신고 접수</h2>
            <div style={{ fontSize: 12, color: "#8a90a6", marginTop: 2 }}>
              보호자 전화 접수 · 접수 즉시 D1 반경 경보 자동 발송
            </div>
          </div>
        </div>

        <div style={{ padding: "24px 26px", display: "flex", flexDirection: "column", gap: 20 }}>
          <div>
            <div style={label}>사전등록 페르소나 연결</div>
            {live.live ? (
              <select style={{ ...field, cursor: "pointer" }} value={personaId} onChange={(e) => setPersonaId(e.target.value)}>
                <option value="">연결 안 함</option>
                {personas.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.age} · 치매) — 끌림점{" "}
                    {p.n_attractions}곳
                  </option>
                ))}
              </select>
            ) : (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 11,
                  padding: "12px 14px",
                  borderRadius: 9,
                  background: "rgba(145,132,217,.1)",
                  border: `1px solid rgba(145,132,217,.3)`,
                }}
              >
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, color: "#d2cefd", fontWeight: 600 }}>
                    김순자 (78 · 치매) 사전등록 연결됨
                  </div>
                  <div className="mono" style={{ fontSize: 11, color: "#9089c4" }}>
                    데모 — 끌림점 4곳 · 축 점수 사전 확보
                  </div>
                </div>
              </div>
            )}
          </div>

          <div>
            <div style={label}>마지막 목격 위치 (LKP)</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <input style={field} className="mono" value={lat} onChange={(e) => setLat(e.target.value)} placeholder="위도" />
              <input style={field} className="mono" value={lng} onChange={(e) => setLng(e.target.value)} placeholder="경도" />
            </div>
            <div style={{ fontSize: 11, color: T.faint, marginTop: 7 }}>
              기본값 = 정릉2동 정릉전통시장 인근 (데모 시드 좌표) — 지도 클릭 지정은 후속 작업
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <div>
              <div style={label}>목격 시각</div>
              <input
                style={field}
                className="mono"
                type="datetime-local"
                value={lkpTime}
                onChange={(e) => setLkpTime(e.target.value)}
              />
            </div>
            <div>
              <div style={label}>신고 시각</div>
              <div style={{ ...field, color: "#8a90a6" }} className="mono">
                현재 시각 (자동)
              </div>
            </div>
          </div>

          <div>
            <div style={label}>인상착의</div>
            <textarea
              style={{ ...field, minHeight: 64, resize: "vertical", lineHeight: 1.6 }}
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
            />
            <div style={{ fontSize: 11, color: T.faint, marginTop: 7 }}>
              인상착의는 알림 메시지에 포함됩니다 (현재 계약에는 별도 필드 없음 — 표시용)
            </div>
          </div>

          {error && <div style={{ fontSize: 12, color: T.redText, lineHeight: 1.5 }}>{error}</div>}
        </div>

        <div
          style={{
            padding: "18px 26px",
            borderTop: `1px solid rgba(233,233,237,.08)`,
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          <div
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              gap: 7,
              fontSize: 11,
              color: T.faint,
            }}
          >
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: T.amber }} />
            접수 시 D1 자동 발송 — 실발송(FCM) 미구현으로 시뮬레이션(sent=false)
          </div>
          <button
            onClick={submit}
            disabled={busy}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "11px 20px",
              borderRadius: 9,
              background: "transparent",
              border: `1px solid ${T.red}`,
              color: T.redText,
              fontSize: 14,
              fontWeight: 700,
              cursor: "pointer",
              whiteSpace: "nowrap",
              opacity: busy ? 0.5 : 1,
            }}
          >
            {busy ? "접수 중…" : "신고 접수 · D1 발송"}
          </button>
        </div>
      </div>
    </div>
  );
}
