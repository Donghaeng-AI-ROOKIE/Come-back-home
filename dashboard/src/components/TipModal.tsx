import { useState } from "react";
import { api, isNeedMore, type Tip } from "../api";
import { T } from "../theme";

/** 모달 A — 제보 입력.
 *  자유텍스트 입력 → 구조화(LLM) → 신뢰도 p 판정(알고리즘).
 *  POST /tips 는 Tip 또는 {status:"need_more", missing:[...]} 두 형태를 반환하므로
 *  status 키 유무로 분기한다(API_CONTRACT 경고 박스 — 프런트 첫 걸림돌). */

const VERDICT = {
  layer1: { label: "반영(층1)", color: T.amber },
  layer2: { label: "재예측(층2)", color: T.red },
  discard: { label: "파기 (p<0.2)", color: T.tierDiscard },
} as const;

const TIME_CHIPS = ["방금 전", "10분 이내", "30분쯤 전", "1시간 이상"];

/** 되묻기 사유 코드 → 관제요원용 설명 (백엔드는 시각 분기에서만 reason 을 보낸다) */
const REASON_KO: Record<string, string> = {
  layer2_needs_time:
    "신뢰도 p가 재예측(층2) 문턱(0.8) 이상인 강한 제보 — 목격 시각을 확정해야 새 LKP로 반영됩니다.",
};

export default function TipModal({
  caseId,
  onClose,
  onSubmitted,
}: {
  caseId: string;
  onClose: () => void;
  onSubmitted: () => void;
}) {
  const [text, setText] = useState("");
  const [missing, setMissing] = useState<string[] | null>(null);
  const [needReason, setNeedReason] = useState<string | null>(null);
  const [result, setResult] = useState<Tip | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (extra?: string, force = false) => {
    const full = extra ? `${text} ${extra}` : text;
    if (!full.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.submitTip(caseId, { text: full, force });
      if (isNeedMore(r)) {
        setMissing(r.missing);
        setNeedReason(r.reason ?? null);
        setResult(null);
      } else {
        setResult(r);
        setMissing(null);
        setNeedReason(null);
      }
    } catch (e) {
      setError(String(e).slice(0, 200));
    } finally {
      setBusy(false);
    }
  };

  const field: React.CSSProperties = {
    width: "100%",
    padding: "13px 14px",
    borderRadius: 9,
    background: T.inset,
    border: `1px solid rgba(233,233,237,.1)`,
    fontSize: 13.5,
    color: T.text,
    lineHeight: 1.6,
    minHeight: 72,
    resize: "vertical",
    outline: "none",
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(8,10,16,.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 560,
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
            padding: "18px 24px",
            borderBottom: `1px solid rgba(233,233,237,.08)`,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>제보 입력</h2>
            <div style={{ fontSize: 11.5, color: "#8a90a6", marginTop: 2 }}>
              자유텍스트 입력 → 구조화(LLM) → 신뢰도 p 판정(알고리즘)
            </div>
          </div>
          <span style={{ fontSize: 20, color: T.faint, cursor: "pointer" }} onClick={onClose}>
            ×
          </span>
        </div>

        <div style={{ padding: "18px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#c1c5d6", marginBottom: 8 }}>
              제보 내용
            </div>
            <textarea
              style={field}
              placeholder='예: "정릉시장 입구에서 회색 점퍼 입은 할머니를 봤어요"'
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </div>

          {missing && (
            <div
              style={{
                padding: "15px 16px",
                borderRadius: 11,
                background: "rgba(240,166,60,.09)",
                border: `1px solid ${T.amberBorder}`,
                animation: "popIn .2s ease",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <span
                  className="mono"
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color: T.amberText,
                    padding: "2px 8px",
                    borderRadius: 5,
                    background: "rgba(240,166,60,.16)",
                    border: `1px solid ${T.amberBorder}`,
                  }}
                >
                  need_more
                </span>
                <span style={{ fontSize: 12.5, color: T.amberText, fontWeight: 600 }}>
                  추가 정보가 필요합니다
                </span>
              </div>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 11 }}>
                {missing.includes("location") ? "어디쯤에서 보셨나요?" : "언제쯤 보셨나요?"}
              </div>
              {needReason && (
                <div style={{ fontSize: 11.5, color: "#c9a86a", lineHeight: 1.55, marginBottom: 11 }}>
                  {REASON_KO[needReason] ?? `사유 코드: ${needReason}`}
                </div>
              )}
              {missing.includes("time") && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 7, marginBottom: 12 }}>
                  {TIME_CHIPS.map((c) => (
                    <button
                      key={c}
                      onClick={() => submit(c)}
                      disabled={busy}
                      style={{
                        fontSize: 12,
                        padding: "7px 13px",
                        borderRadius: 7,
                        background: T.chip,
                        border: `1px solid rgba(233,233,237,.12)`,
                        color: "#d3d6e2",
                        cursor: "pointer",
                      }}
                    >
                      {c}
                    </button>
                  ))}
                </div>
              )}
              {missing.includes("location") && (
                <div style={{ fontSize: 12, color: "#c1c5d6", marginBottom: 12, lineHeight: 1.6 }}>
                  제보 내용에 장소를 덧붙여 다시 제출해 주세요 (예: "정릉시장 입구에서").
                </div>
              )}
              <button
                onClick={() => submit(undefined, true)}
                disabled={busy}
                style={{
                  width: "100%",
                  padding: 11,
                  borderRadius: 8,
                  background: "transparent",
                  border: `1px solid ${T.amber}`,
                  color: T.amberText,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                이대로 확정 (force=true)
              </button>
            </div>
          )}

          {result && (
            <div
              style={{
                padding: 16,
                borderRadius: 11,
                background: T.inset,
                border: `1px solid ${result.decision ? VERDICT[result.decision].color : T.border}55`,
                animation: "popIn .2s ease",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 12,
                }}
              >
                <span style={{ fontSize: 12.5, color: "#c1c5d6", fontWeight: 600 }}>판정 결과</span>
                {result.decision && (
                  <span
                    style={{
                      fontSize: 11.5,
                      fontWeight: 700,
                      padding: "3px 10px",
                      borderRadius: 6,
                      color: VERDICT[result.decision].color,
                      background: `${VERDICT[result.decision].color}22`,
                      border: `1px solid ${VERDICT[result.decision].color}55`,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {VERDICT[result.decision].label}
                  </span>
                )}
              </div>
              {result.p != null && (
                <>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                    <span style={{ fontSize: 11, color: "#8a90a6", whiteSpace: "nowrap" }}>신뢰도 p</span>
                    <div style={{ flex: 1, height: 7, borderRadius: 4, background: "#26293a", overflow: "hidden" }}>
                      <div
                        style={{
                          height: "100%",
                          borderRadius: 4,
                          width: `${Math.round(result.p * 100)}%`,
                          background: result.decision ? VERDICT[result.decision].color : T.amber,
                        }}
                      />
                    </div>
                    <span className="mono" style={{ fontSize: 14, fontWeight: 700 }}>
                      p={result.p.toFixed(2)}
                    </span>
                  </div>
                  <div
                    className="mono"
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: 9.5,
                      color: "#5f6474",
                    }}
                  >
                    <span>파기 &lt;0.2</span>
                    <span>반영 0.2–0.8</span>
                    <span>재예측 ≥0.8</span>
                  </div>
                </>
              )}
            </div>
          )}

          {error && (
            <div style={{ fontSize: 12, color: T.redText, lineHeight: 1.5 }}>{error}</div>
          )}
        </div>

        <div
          style={{
            padding: "16px 24px",
            borderTop: `1px solid rgba(233,233,237,.08)`,
            display: "flex",
            gap: 10,
            justifyContent: "flex-end",
          }}
        >
          <button
            onClick={result ? onSubmitted : onClose}
            style={{
              padding: "10px 18px",
              borderRadius: 8,
              background: "transparent",
              border: `1px solid ${T.borderStrong}`,
              color: T.sub,
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {result ? "닫기" : "취소"}
          </button>
          {!result && (
            <button
              onClick={() => submit()}
              disabled={busy || !text.trim()}
              style={{
                padding: "10px 18px",
                borderRadius: 8,
                background: "transparent",
                border: `1px solid ${T.accent}`,
                color: T.accentLighter,
                fontSize: 13,
                fontWeight: 700,
                cursor: "pointer",
                opacity: busy || !text.trim() ? 0.5 : 1,
              }}
            >
              {busy ? "판정 중…" : "판정 요청"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
