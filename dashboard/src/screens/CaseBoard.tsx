import { useEffect, useMemo, useState } from "react";
import type { LiveState } from "../App";
import { T } from "../theme";
import { DEMO_CARDS, type DemoCard } from "../demo";

/** S1 케이스 보드 — 경과시간에 따라 카드 긴급도 상승(골든타임 서사).
 *  라이브: GET /debug/overview 케이스 목록 / 데모: 디자인 확정 샘플 6건. */

type Filter = "all" | "active" | "closed";

interface CardVM extends DemoCard {
  id: string | null; // null = 데모 샘플(상세 진입 불가)
}

const TONE = {
  amber: { c: T.amberText, bg: T.amberBg, bd: "rgba(240,166,60,.3)" },
  red: { c: T.redText, bg: T.redBg, bd: T.redBorder },
  accent: { c: T.accentLighter, bg: T.accentTint, bd: "rgba(145,132,217,.32)" },
  green: { c: T.greenText, bg: "rgba(69,184,105,.16)", bd: T.greenBorder },
} as const;

const STATUS_KO: Record<string, { label: string; tone: keyof typeof TONE }> = {
  intake: { label: "접수", tone: "amber" },
  predicted: { label: "예측완료", tone: "accent" },
  searching: { label: "수색 중", tone: "red" },
  found: { label: "종결 · 발견", tone: "green" },
  closed: { label: "종결", tone: "green" },
};

function fmt(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(h)}:${p(m)}:${p(s)}`;
}

function urgency(sec: number, closed: boolean) {
  if (closed)
    return { bar: T.green, border: "rgba(69,184,105,.28)", glow: "none", pct: 100, note: "종결" };
  const pct = Math.min(100, Math.round((sec / 3600) * 100));
  if (sec > 10800)
    return {
      bar: T.red,
      border: "rgba(242,85,90,.5)",
      glow: "0 0 0 1px rgba(242,85,90,.25), 0 8px 26px rgba(242,85,90,.14)",
      pct: 100,
      note: "긴급",
    };
  if (sec > 3600)
    return {
      bar: T.amber,
      border: "rgba(240,166,60,.4)",
      glow: "0 0 0 1px rgba(240,166,60,.18)",
      pct: 100,
      note: "수색",
    };
  return { bar: T.amber, border: "rgba(233,233,237,.1)", glow: "none", pct, note: "초기 대응" };
}

export default function CaseBoard({
  live,
  onOpenCase,
  onIntake,
}: {
  live: LiveState;
  onOpenCase: (id: string) => void;
  onIntake: () => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setTick((v) => v + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const cards: CardVM[] = useMemo(() => {
    if (live.live && live.overview) {
      const personas = new Map(live.overview.personas.map((p) => [p.id, p]));
      return live.overview.cases.map((c) => {
        const p = c.persona_id ? personas.get(c.persona_id) : undefined;
        const st = STATUS_KO[c.status] ?? STATUS_KO.intake;
        const closed = c.status === "found" || c.status === "closed";
        const elapsed = Math.max(
          0,
          Math.floor((Date.now() - new Date(c.lkp_time).getTime()) / 1000),
        );
        return {
          id: c.id,
          name: p?.name ?? c.id,
          age: p?.age ?? 0,
          type: "치매" as const,
          baseSec: elapsed,
          status: st.label,
          tone: st.tone,
          lkp: `${c.lkp.lat.toFixed(4)}, ${c.lkp.lng.toFixed(4)}`,
          lastAlert: "—",
          featured: c.id === live.caseId,
          closed,
        };
      });
    }
    return DEMO_CARDS.map((d) => ({ ...d, id: d.featured ? live.caseId : null }));
  }, [live.live, live.overview, live.caseId]);

  const total = cards.length;
  const activeN = cards.filter((c) => !c.closed).length;
  const closedN = total - activeN;
  const shown = cards.filter((c) =>
    filter === "all" ? true : filter === "active" ? !c.closed : c.closed,
  );

  const fb = (on: boolean): React.CSSProperties => ({
    whiteSpace: "nowrap",
    padding: "8px 14px",
    borderRadius: 8,
    border: `1px solid ${on ? "rgba(145,132,217,.4)" : "rgba(233,233,237,.1)"}`,
    fontSize: 12.5,
    fontWeight: 600,
    cursor: "pointer",
    background: on ? T.accentTint : "transparent",
    color: on ? T.text : T.sub,
  });

  return (
    <div style={{ padding: "22px 30px", flex: 1 }}>
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          marginBottom: 18,
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
            <h1 style={{ margin: 0, fontSize: 23, fontWeight: 700, letterSpacing: "-.01em" }}>
              진행 중 케이스
            </h1>
            <span
              className="mono"
              style={{
                fontSize: 13,
                fontWeight: 700,
                padding: "3px 10px",
                borderRadius: 7,
                background: T.redBg,
                color: T.redText,
                whiteSpace: "nowrap",
              }}
            >
              {activeN}건
            </span>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginTop: 8,
              fontSize: 12,
              color: "#8a90a6",
            }}
          >
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: T.amber }} />
            실종 <b style={{ color: "#c7cbdb" }}>1시간 내 발견율 43%</b> — 경과시간이 길수록 카드
            긴급도가 올라갑니다(골든타임)
          </div>
        </div>
        <button
          onClick={onIntake}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "10px 16px",
            borderRadius: 9,
            background: "transparent",
            border: `1px solid ${T.red}`,
            color: T.redText,
            fontSize: 13.5,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          + 신고 접수
        </button>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        <button style={fb(filter === "all")} onClick={() => setFilter("all")}>
          전체 {total}
        </button>
        <button style={fb(filter === "active")} onClick={() => setFilter("active")}>
          진행 중 {activeN}
        </button>
        <button style={fb(filter === "closed")} onClick={() => setFilter("closed")}>
          종결 {closedN}
        </button>
        <div style={{ flex: 1 }} />
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 7,
            fontSize: 12,
            color: T.dim,
            padding: "8px 12px",
            borderRadius: 8,
            background: T.inset,
            border: `1px solid rgba(233,233,237,.08)`,
          }}
        >
          <span>정렬</span>
          <span style={{ color: "#c7cbdb", fontWeight: 600 }}>경과시간 ↓</span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 16 }}>
        {shown.map((c, i) => {
          const sec = c.closed ? c.baseSec : c.baseSec + tick;
          const u = urgency(sec, c.closed);
          const tone = TONE[c.tone];
          const clickable = c.id !== null;
          return (
            <div
              key={i}
              onClick={() => clickable && onOpenCase(c.id!)}
              style={{
                padding: 18,
                borderRadius: 14,
                background: T.card,
                border: `1px solid ${u.border}`,
                boxShadow: u.glow,
                cursor: clickable ? "pointer" : "default",
                opacity: c.closed ? 0.72 : 1,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 14,
                }}
              >
                <span
                  style={{
                    fontSize: 11.5,
                    fontWeight: 700,
                    padding: "3px 10px",
                    borderRadius: 6,
                    whiteSpace: "nowrap",
                    color: tone.c,
                    background: tone.bg,
                    border: `1px solid ${tone.bd}`,
                  }}
                >
                  {c.status}
                </span>
                {c.featured && (
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      color: T.accentLight,
                      padding: "2px 8px",
                      borderRadius: 5,
                      background: T.accentTint,
                      border: `1px solid rgba(145,132,217,.3)`,
                      whiteSpace: "nowrap",
                    }}
                  >
                    데모 케이스
                  </span>
                )}
              </div>

              <div style={{ display: "flex", gap: 13, alignItems: "center", marginBottom: 16 }}>
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: 10,
                    background: "linear-gradient(160deg,#2a2e3d,#20232f)",
                    border: `1px solid rgba(233,233,237,.1)`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                    color: T.dim,
                    fontSize: 18,
                    fontWeight: 700,
                  }}
                >
                  {c.name.slice(0, 1)}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 17, fontWeight: 700 }}>{c.name}</span>
                    {c.age > 0 && (
                      <span className="mono" style={{ fontSize: 12.5, color: T.sub }}>
                        {c.age}세
                      </span>
                    )}
                  </div>
                  <div style={{ marginTop: 5 }}>
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 600,
                        padding: "2px 8px",
                        borderRadius: 5,
                        color: T.amberText,
                        background: "rgba(240,166,60,.12)",
                        border: `1px solid rgba(240,166,60,.26)`,
                      }}
                    >
                      {c.type}
                    </span>
                  </div>
                </div>
              </div>

              <div
                style={{
                  padding: "12px 13px",
                  borderRadius: 10,
                  background: "rgba(0,0,0,.22)",
                  marginBottom: 13,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    justifyContent: "space-between",
                    marginBottom: 8,
                  }}
                >
                  <span style={{ fontSize: 11, color: T.dim }}>경과시간</span>
                  <span
                    className="mono"
                    style={{
                      fontSize: 19,
                      fontWeight: 700,
                      color: c.closed
                        ? T.greenText
                        : sec > 10800
                          ? T.redText
                          : sec > 3600
                            ? T.amberText
                            : T.text,
                    }}
                  >
                    {c.closed ? "종결" : fmt(sec)}
                  </span>
                </div>
                <div
                  style={{ height: 5, borderRadius: 3, background: "#26293a", overflow: "hidden" }}
                >
                  <div
                    style={{
                      height: "100%",
                      borderRadius: 3,
                      width: `${u.pct}%`,
                      background: u.bar,
                    }}
                  />
                </div>
                <div
                  className="mono"
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: 9.5,
                    color: "#5f6474",
                    marginTop: 4,
                  }}
                >
                  <span>골든타임 1h</span>
                  <span>{u.note}</span>
                </div>
              </div>

              <div
                style={{ display: "flex", flexDirection: "column", gap: 7, fontSize: 12, color: T.sub }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ color: T.faint }}>LKP</span>
                  <span style={{ color: "#c1c5d6" }}>{c.lkp}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ color: T.faint }}>마지막 알림</span>
                  <span style={{ color: "#c1c5d6" }}>{c.lastAlert}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div
        style={{
          marginTop: 22,
          display: "flex",
          alignItems: "center",
          gap: 8,
          fontSize: 11,
          color: "#5f6474",
        }}
      >
        <span style={{ width: 5, height: 5, borderRadius: "50%", background: T.amber, flexShrink: 0 }} />
        {live.live ? (
          <>
            라이브 모드 — 백엔드 인메모리 저장으로, 서버 재시작 시{" "}
            <b style={{ color: "#8a90a6" }}>김순자 데모 케이스</b>만 유지됩니다.
          </>
        ) : (
          <>
            데모 모드 — 백엔드 미연결. 카드는 보드 레이아웃 시연용 샘플이며{" "}
            <b style={{ color: "#8a90a6" }}>김순자 데모 케이스</b>만 상세 진입이 가능합니다.
          </>
        )}
      </div>
    </div>
  );
}
