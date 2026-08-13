import { useState } from "react";
import { api } from "../api";
import { T } from "../theme";

/** 모달 B — 케이스 종결. 종결 확정 시 개인정보 파기 라이프사이클(5일 TTL) 시작. */

export default function CloseModal({
  caseId,
  onClose,
  onClosed,
}: {
  caseId: string;
  onClose: () => void;
  onClosed: () => void;
}) {
  const [reason, setReason] = useState<"found" | "withdrawn">("found");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.closeCase(caseId, reason);
      onClosed();
    } catch (e) {
      setError(String(e).slice(0, 200));
      setBusy(false);
    }
  };

  const tab = (on: boolean): React.CSSProperties => ({
    padding: "8px 16px",
    borderRadius: 6,
    fontSize: 13,
    fontWeight: on ? 700 : 600,
    whiteSpace: "nowrap",
    cursor: "pointer",
    border: "none",
    background: on ? T.green : "transparent",
    color: on ? T.mapBg : T.sub,
  });

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
          width: 520,
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
            gap: 11,
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 9,
              background: "rgba(69,184,105,.16)",
              border: `1px solid ${T.greenBorder}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: T.greenText,
              fontWeight: 700,
            }}
          >
            ✓
          </div>
          <div>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>케이스 종결</h2>
            <div style={{ fontSize: 11.5, color: "#8a90a6", marginTop: 2 }}>
              종결 확정 후 개인정보 파기 라이프사이클 시작
            </div>
          </div>
        </div>

        <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 18 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#c1c5d6", marginBottom: 9 }}>
              종결 사유
            </div>
            <div
              style={{
                display: "flex",
                gap: 3,
                padding: 3,
                background: T.inset,
                border: `1px solid rgba(233,233,237,.1)`,
                borderRadius: 9,
                width: "fit-content",
              }}
            >
              <button style={tab(reason === "found")} onClick={() => setReason("found")}>
                안전 발견
              </button>
              <button style={tab(reason === "withdrawn")} onClick={() => setReason("withdrawn")}>
                신고 철회
              </button>
            </div>
          </div>

          <div
            style={{
              display: "flex",
              gap: 11,
              padding: "14px 15px",
              borderRadius: 11,
              background: "rgba(69,184,105,.08)",
              border: `1px solid rgba(69,184,105,.3)`,
            }}
          >
            <span style={{ color: T.greenText, flexShrink: 0, fontWeight: 700 }}>◈</span>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#a7e8bd" }}>
                개인정보 자동 파기 예약
              </div>
              <div style={{ fontSize: 12, color: "#8fc7a2", marginTop: 3, lineHeight: 1.55 }}>
                종결 확정 시 위치·인상착의·제보 등 수집 정보는{" "}
                <b style={{ color: "#a7e8bd" }}>종결 후 5일 뒤 자동 파기</b>됩니다. (privacy 파기
                라이프사이클)
              </div>
            </div>
          </div>

          {error && <div style={{ fontSize: 12, color: T.redText }}>{error}</div>}
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
            onClick={onClose}
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
            취소
          </button>
          <button
            onClick={confirm}
            disabled={busy}
            style={{
              padding: "10px 18px",
              borderRadius: 8,
              background: "transparent",
              border: `1px solid ${T.green}`,
              color: T.greenText,
              fontSize: 13,
              fontWeight: 700,
              cursor: "pointer",
              opacity: busy ? 0.5 : 1,
            }}
          >
            {busy ? "처리 중…" : "종결 확정 · 파기 예약"}
          </button>
        </div>
      </div>
    </div>
  );
}
