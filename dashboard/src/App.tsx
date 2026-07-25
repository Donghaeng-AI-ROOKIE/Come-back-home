import { useEffect, useState } from "react";
import { api, DEMO_CASE_ID, type Overview } from "./api";
import { T } from "./theme";
import CaseBoard from "./screens/CaseBoard";
import ControlDetail from "./screens/ControlDetail";
import Intake from "./screens/Intake";

type Screen = "board" | "detail" | "intake";

/** 라이브 상태 — 백엔드 프로브 결과. demo = 미기동(디자인 확정 데모 데이터로 동작) */
export interface LiveState {
  live: boolean;
  overview: Overview | null;
  caseId: string;
  refresh: () => void;
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("board");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [probed, setProbed] = useState(false);
  const [caseId, setCaseId] = useState(DEMO_CASE_ID);

  const probe = () => {
    api
      .overview()
      .then((o) => setOverview(o))
      .catch(() => setOverview(null))
      .finally(() => setProbed(true));
  };

  useEffect(() => {
    probe();
    const t = setInterval(probe, 30000);
    return () => clearInterval(t);
  }, []);

  const live: LiveState = {
    live: overview !== null,
    overview,
    caseId,
    refresh: probe,
  };

  const navBtn = (active: boolean): React.CSSProperties => ({
    fontSize: 13,
    color: active ? T.text : T.sub,
    fontWeight: 600,
    padding: "6px 11px",
    borderRadius: 6,
    background: active ? T.accentTint : "transparent",
    border: "none",
    cursor: "pointer",
    whiteSpace: "nowrap",
  });

  return (
    <div
      style={{
        width: "100%",
        maxWidth: 1440,
        minWidth: 1180,
        margin: "0 auto",
        background: T.appBg,
        color: T.text,
        minHeight: "100vh",
        borderLeft: `1px solid rgba(233,233,237,.06)`,
        borderRight: `1px solid rgba(233,233,237,.06)`,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <header
        style={{
          height: 56,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 20px",
          borderBottom: `1px solid ${T.border}`,
          background: T.surface,
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <div
              style={{
                width: 9,
                height: 9,
                borderRadius: 2,
                background: T.red,
                boxShadow: "0 0 10px rgba(242,85,90,.7)",
              }}
            />
            <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: "-.01em" }}>돌아오길</span>
            <span style={{ fontSize: 12, color: "#8a90a6", fontWeight: 500 }}>관제 콘솔</span>
          </div>
          <div style={{ width: 1, height: 22, background: "rgba(233,233,237,.12)" }} />
          <nav style={{ display: "flex", gap: 2, whiteSpace: "nowrap" }}>
            <button style={navBtn(screen === "board")} onClick={() => setScreen("board")}>
              케이스 보드
            </button>
            <button style={navBtn(screen === "detail")} onClick={() => setScreen("detail")}>
              관제 상세
            </button>
            <button style={navBtn(screen === "intake")} onClick={() => setScreen("intake")}>
              신고 접수
            </button>
          </nav>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {/* 정직성 라벨 — FCM 실발송 미구현이라 상시 표기, 제거 금지 */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 7,
              padding: "5px 10px",
              borderRadius: 6,
              background: "rgba(240,166,60,.1)",
              border: `1px solid ${T.amberBorder}`,
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: T.amber,
                animation: "pulseDot 1.6s infinite",
              }}
            />
            <span
              style={{ fontSize: 11.5, color: T.amberText, fontWeight: 600, whiteSpace: "nowrap" }}
            >
              {probed && live.live ? "라이브(스텁 백엔드) · 발송 시뮬레이션" : "데모 · 발송 시뮬레이션 모드"}
            </span>
          </div>
          <div style={{ textAlign: "right", lineHeight: 1.25 }}>
            <div style={{ fontSize: 12.5, color: T.text, fontWeight: 600, whiteSpace: "nowrap" }}>
              성북경찰서 여성청소년과
            </div>
            <div style={{ fontSize: 11, color: T.dim }}>관제요원 · 데모 계정</div>
          </div>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: "50%",
              background: "#2a2e3d",
              border: `1px solid rgba(233,233,237,.12)`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 12,
              color: "#c7cbdb",
              fontWeight: 600,
            }}
          >
            관
          </div>
        </div>
      </header>

      {screen === "board" && (
        <CaseBoard
          live={live}
          onOpenCase={(id) => {
            setCaseId(id);
            setScreen("detail");
          }}
          onIntake={() => setScreen("intake")}
        />
      )}
      {screen === "detail" && <ControlDetail live={live} />}
      {screen === "intake" && (
        <Intake
          live={live}
          onDone={(id) => {
            setCaseId(id);
            live.refresh();
            setScreen("detail");
          }}
        />
      )}
    </div>
  );
}
