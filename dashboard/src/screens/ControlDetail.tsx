import { useEffect, useMemo, useRef, useState } from "react";
import type { LiveState } from "../App";
import {
  api,
  type AttractionPoint,
  type CaseDetail,
  type Persona,
  type PoaCell,
  type PoaResponse,
  type RerunCheck,
  type GeoPoint,
  type Tip,
} from "../api";
import { T, axisLabel } from "../theme";
import {
  buildDemoCells,
  demoAlerts,
  demoTimeline,
  demoTipPins,
  DEMO_APPEARANCE,
  DEMO_ATTRACTIONS,
  DEMO_AXIS_SCORES,
  DEMO_BEHAVIOR_NOTE,
  probColor,
  type DemoTimelineEvent,
  type DemoView,
  type PanelTab,
  type PoaLayer,
} from "../demo";
import TipModal from "../components/TipModal";
import CloseModal from "../components/CloseModal";

/** S2 관제 상세 — 지도(좌) + 패널(우 452px).
 *  데모: 디자인 확정 4상태 스위처 + 합성 히트맵.
 *  라이브: 실 POA 폴리곤을 등장방형 투영으로 SVG에 렌더 + 실 케이스·페르소나·제보. */

const VB_W = 960;
const VB_H = 780;

const STEP_LABELS = ["신고 정보 분석", "성향(페르소나) 추론", "500 워커 몬테카를로 시뮬레이션", "확률지도(POA) 생성"];
const STEP_BOUNDS = [4, 9, 20, 27];

const VERDICT = {
  layer1: { label: "반영(층1)", color: T.amber },
  layer2: { label: "재예측(층2)", color: T.red },
  discard: { label: "파기 (p<0.2)", color: T.tierDiscard },
} as const;

const TAG_TONE: Record<string, string> = {
  red: T.red,
  amber: T.amber,
  green: T.green,
  accent: T.accent,
  gray: T.tierDiscard,
};

/** bundle poa_layers 키 → 프론트 레이어 키 */
const BUNDLE_KEY: Record<string, PoaLayer> = {
  combined: "combined",
  topdown: "top_down",
  bottomup: "bottom_up",
  statistical: "statistical",
};

const fmtDur = (sec: number): string => {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(Math.floor(sec / 3600))}:${p(Math.floor((sec % 3600) / 60))}:${p(sec % 60)}`;
};

/** 위경도 → SVG viewBox 등장방형 투영 (경도에 cos(lat) 보정) */
function makeProjector(points: GeoPoint[]) {
  const lats = points.map((p) => p.lat);
  const lngs = points.map((p) => p.lng);
  const latC = (Math.min(...lats) + Math.max(...lats)) / 2;
  const kx = Math.cos((latC * Math.PI) / 180);
  const xs = lngs.map((l) => l * kx);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const spanX = Math.max(maxX - minX, 1e-6);
  const spanY = Math.max(maxLat - minLat, 1e-6);
  const scale = Math.min((VB_W * 0.86) / spanX, (VB_H * 0.86) / spanY);
  const cx = (minX + maxX) / 2, cy = (minLat + maxLat) / 2;
  return (p: GeoPoint): { x: number; y: number } => ({
    x: VB_W / 2 + (p.lng * kx - cx) * scale,
    y: VB_H / 2 - (p.lat - cy) * scale,
  });
}

function StatusChip({ label, color, bg }: { label: string; color: string; bg: string }) {
  return (
    <span
      style={{
        fontSize: 11.5,
        fontWeight: 600,
        padding: "3px 10px",
        borderRadius: 6,
        color,
        background: bg,
      }}
    >
      {label}
    </span>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: ".09em",
        color: T.faint,
        textTransform: "uppercase",
        marginBottom: 10,
      }}
    >
      {children}
    </div>
  );
}

function PBar({ p, color }: { p: number; color: string }) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 24,
        height: 5,
        borderRadius: 3,
        background: "#26293a",
        overflow: "hidden",
      }}
    >
      <div style={{ height: "100%", borderRadius: 3, width: `${Math.round(p * 100)}%`, background: color }} />
    </div>
  );
}

export default function ControlDetail({ live }: { live: LiveState }) {
  // 데모 상태
  const [view, setView] = useState<DemoView>("tips3");
  const [tab, setTab] = useState<PanelTab>("timeline");
  const [layer, setLayer] = useState<PoaLayer>("combined");
  const [elapsed, setElapsed] = useState(0);

  // 라이브 데이터
  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [poa, setPoa] = useState<PoaResponse | null>(null);
  const [persona, setPersona] = useState<Persona | null>(null);
  const [rerun, setRerun] = useState<RerunCheck | null>(null);
  const [predicting, setPredicting] = useState(false);
  const [liveLog, setLiveLog] = useState<string[]>([]);
  // 이 세션에서 발송한 알림 — 백엔드에 알림 이력 API가 없어 타임라인은 세션분만 표시
  const [sessionAlerts, setSessionAlerts] = useState<{ ts: number; cells: number }[]>([]);
  // 4층 POA (bundle) — 트레이스 예측을 돌린 케이스만 4층이 다 찬다
  const [liveLayers, setLiveLayers] = useState<Partial<Record<PoaLayer, PoaCell[]>> | null>(null);
  const [layersPreparing, setLayersPreparing] = useState(false);
  // 마지막 발송 알림의 대상 셀 — 지도 외곽선 표시용
  const [alertCells, setAlertCells] = useState<Set<string>>(new Set());
  const [tipOpen, setTipOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const predStart = useRef(0);
  const autoTraceRan = useRef(false);
  // 경과시간 타이머(1초 틱) — 관제에서 가장 중요한 숫자
  const [clock, setClock] = useState(() => Date.now());
  const mountTs = useRef(Date.now());
  useEffect(() => {
    const t = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const isLive = live.live;

  const loadLive = () => {
    if (!isLive) return;
    api.getCase(live.caseId).then(setCaseDetail).catch(() => setCaseDetail(null));
    api.poa(live.caseId, 80).then(setPoa).catch(() => setPoa(null));
    api.rerunCheck(live.caseId).then(setRerun).catch(() => setRerun(null));
    api
      .bundle(live.caseId)
      .then((b) => {
        const m: Partial<Record<PoaLayer, PoaCell[]>> = {};
        Object.entries(b.poa_layers ?? {}).forEach(([k, v]) => {
          const key = BUNDLE_KEY[k];
          if (key) m[key] = v.cells;
        });
        setLiveLayers(m);
      })
      .catch(() => setLiveLayers(null));
  };

  useEffect(loadLive, [isLive, live.caseId]);

  // 4층 분해 자동 준비 — 부팅 시드는 트레이스 없이 예측돼 combined만 있으므로,
  // 트레이스 재예측을 1회 백그라운드 실행해 top-down/bottom-up/statistical을 채운다.
  useEffect(() => {
    if (!isLive || !liveLayers || liveLayers.top_down || autoTraceRan.current) return;
    autoTraceRan.current = true;
    setLayersPreparing(true);
    api
      .predictTraced(live.caseId)
      .then(() => loadLive())
      .catch(() => {})
      .finally(() => setLayersPreparing(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLive, liveLayers]);

  useEffect(() => {
    if (caseDetail?.report?.persona_id) {
      api.persona(caseDetail.report.persona_id).then(setPersona).catch(() => setPersona(null));
    }
  }, [caseDetail?.report?.persona_id]);

  // 로딩 경과초 (데모 스위처 + 라이브 predict 공용)
  const loadingActive = (!isLive && view === "loading") || predicting;
  useEffect(() => {
    if (!loadingActive) return;
    const t = setInterval(() => setElapsed((e) => Math.min(e + 1, 27)), 1000);
    return () => clearInterval(t);
  }, [loadingActive]);

  const runPredict = async () => {
    if (!isLive || predicting) return;
    setPredicting(true);
    setElapsed(0);
    predStart.current = Date.now();
    try {
      // 트레이스 모드 — 같은 파이프라인(결과 불변)이지만 4층 분해가 함께 갱신된다
      await api.predictTraced(live.caseId);
      const took = ((Date.now() - predStart.current) / 1000).toFixed(1);
      setLiveLog((l) => [...l, `AI 예측 완료 — 실측 ${took}초`]);
    } catch (e) {
      setLiveLog((l) => [...l, `예측 실패: ${String(e).slice(0, 120)}`]);
    } finally {
      setPredicting(false);
      loadLive();
    }
  };

  const runAlert = async () => {
    if (!isLive) return;
    try {
      const r = await api.alert(live.caseId);
      setLiveLog((l) => [
        ...l,
        `알림 발송(시뮬) — target_cells=${r.target_cells.length}셀, sent=${r.sent}`,
      ]);
      setSessionAlerts((s) => [...s, { ts: Date.now(), cells: r.target_cells.length }]);
      setAlertCells(new Set(r.target_cells));
      loadLive();
    } catch (e) {
      setLiveLog((l) => [...l, `알림 실패: ${String(e).slice(0, 120)}`]);
    }
  };

  // ── 지도 셀·핀 (데모 vs 라이브) ────────────────────────────────
  const projector = useMemo(() => {
    if (!isLive || !poa || poa.top_cells.length === 0) return null;
    // 레이어 전환 시 화면이 튀지 않도록 로드된 모든 레이어를 경계에 포함
    const pts: GeoPoint[] = poa.top_cells.flatMap((c) => c.polygon);
    if (liveLayers) {
      Object.values(liveLayers).forEach((cells) =>
        cells?.forEach((c) => c.polygon.forEach((p) => pts.push(p))),
      );
    }
    if (caseDetail) pts.push(caseDetail.lkp);
    if (persona) {
      pts.push(persona.home);
      persona.attraction_points.forEach((a) => {
        if (a.location) pts.push(a.location);
      });
    }
    return makeProjector(pts);
  }, [isLive, poa, caseDetail, persona, liveLayers]);

  const liveCells = useMemo(() => {
    if (!projector) return [];
    const src: PoaCell[] = liveLayers?.[layer] ?? poa?.top_cells ?? [];
    if (src.length === 0) return [];
    const maxP = Math.max(...src.map((c) => c.prob), 1e-9);
    return src.map((c) => {
      const rel = c.prob / maxP;
      const { fill, opacity } = probColor(rel);
      return {
        points: c.polygon.map((v) => {
          const { x, y } = projector(v);
          return `${x.toFixed(1)},${y.toFixed(1)}`;
        }).join(" "),
        fill,
        opacity,
        prob: c.prob,
        alerted: alertCells.has(c.cell),
      };
    });
  }, [projector, poa, liveLayers, layer, alertCells]);

  const liveLkp = useMemo(() => {
    if (!projector || !caseDetail) return null;
    return projector(caseDetail.lkp);
  }, [projector, caseDetail]);

  const liveHome = useMemo(
    () => (projector && persona ? projector(persona.home) : null),
    [projector, persona],
  );

  const liveAttractions = useMemo(() => {
    if (!projector || !persona) return [];
    return persona.attraction_points
      .filter((a): a is AttractionPoint & { location: GeoPoint } => a.location != null)
      .map((a) => ({ ...projector(a.location), label: a.label }));
  }, [projector, persona]);

  const liveTipPins = useMemo(() => {
    if (!projector || !caseDetail) return [];
    return caseDetail.tips
      .filter((t): t is Tip & { location: GeoPoint } => t.location != null)
      .map((t, i) => {
        const { x, y } = projector(t.location);
        const v = t.decision ? VERDICT[t.decision] : VERDICT.layer1;
        return { x, y, num: String(i + 1), color: v.color };
      });
  }, [projector, caseDetail]);

  const demoCells = useMemo(
    () => (isLive ? [] : buildDemoCells(layer, view)),
    [isLive, layer, view],
  );

  // ── 패널 데이터 ────────────────────────────────────────────────
  const statusMap: Record<DemoView, { l: string; c: string; bg: string }> = {
    loading: { l: "예측 진행 중", c: T.accentLight, bg: T.accentTint },
    tips3: { l: "제보 3건 반영", c: T.amberText, bg: T.amberBg },
    d3: { l: "신규 지역 발생", c: T.redText, bg: T.redBg },
    closed: { l: "종결 · 안전", c: T.greenText, bg: T.greenBg },
  };
  const liveStatusKo: Record<string, { l: string; c: string; bg: string }> = {
    intake: { l: "접수", c: T.amberText, bg: T.amberBg },
    predicted: { l: "예측 완료", c: T.accentLight, bg: T.accentTint },
    searching: { l: "수색 중", c: T.redText, bg: T.redBg },
    found: { l: "종결 · 발견", c: T.greenText, bg: T.greenBg },
    closed: { l: "종결", c: T.greenText, bg: T.greenBg },
  };
  const st = isLive
    ? liveStatusKo[caseDetail?.status ?? "intake"]
    : statusMap[view];

  const timeline = useMemo<DemoTimelineEvent[]>(() => {
    if (!isLive) return demoTimeline(view);
    if (!caseDetail) return [];
    const hhmm = (v: string | number) => new Date(v).toTimeString().slice(0, 5);
    // 실데이터(created_at·last_sim_at·tips) + 이 세션 발송분만 — 백엔드에 알림 이력 API 없음
    const evts: (DemoTimelineEvent & { ts: number })[] = [
      {
        ts: +new Date(caseDetail.created_at),
        t: hhmm(caseDetail.created_at),
        tag: "접수",
        tone: "amber",
        title: "실종 신고 접수",
        desc: `LKP ${caseDetail.lkp.lat.toFixed(4)}, ${caseDetail.lkp.lng.toFixed(4)}`,
      },
    ];
    if (caseDetail.last_sim_at) {
      evts.push({
        ts: +new Date(caseDetail.last_sim_at),
        t: hhmm(caseDetail.last_sim_at),
        tag: "예측",
        tone: "accent",
        title: "AI 예측 완료",
        desc: "몬테카를로 시뮬레이션 · POA 생성 (last_sim_at)",
      });
    }
    caseDetail.tips.forEach((tip, i) => {
      evts.push({
        ts: +new Date(tip.created_at),
        t: hhmm(tip.created_at),
        tag: "제보",
        tone: "amber",
        title: `제보 #${i + 1}`,
        desc: `"${tip.text.slice(0, 60)}"`,
        p: tip.p ?? undefined,
        verdict: tip.decision ?? undefined,
      });
    });
    sessionAlerts.forEach((al) => {
      evts.push({
        ts: al.ts,
        t: hhmm(al.ts),
        tag: "알림",
        tone: "red",
        sim: true,
        title: "예측기반 경보 발송",
        desc: `target_cells=${al.cells}셀 발송 (sent=false)`,
      });
    });
    return evts.sort((a, b) => a.ts - b.ts);
  }, [isLive, view, caseDetail, sessionAlerts]);

  const personaName = isLive ? persona?.name ?? "—" : "김순자";
  const personaAge = isLive ? persona?.age ?? 0 : 78;
  const personaType = "치매";   // 대상 유형은 치매 단독 (2026-08-03)
  const axisScores = isLive ? persona?.axis_scores ?? {} : DEMO_AXIS_SCORES;
  const attractions = isLive
    ? (persona?.attraction_points ?? []).map((a) => ({ label: a.label, note: a.weight ?? "" }))
    : DEMO_ATTRACTIONS;
  const behaviorNote = isLive
    ? (persona?.behavior_notes ?? []).slice(0, 3).join(" · ")
    : DEMO_BEHAVIOR_NOTE;
  const appearance = isLive
    ? caseDetail?.report?.appearance?.summary ??
      "인상착의 미등록 — 사진 접수 시 추출(VARCO)"
    : DEMO_APPEARANCE;
  const reporter = isLive
    ? caseDetail?.report?.reporter ?? null
    : { name: "김보호", relation: "자녀", phone: "010-0000-0000 (데모)" };

  // 실종 경과시간 — LKP 시각 기준, 종결 시 동결
  const missingSec = (() => {
    if (isLive) {
      if (!caseDetail) return null;
      const end = caseDetail.closed_at ? +new Date(caseDetail.closed_at) : clock;
      return Math.max(0, Math.floor((end - +new Date(caseDetail.lkp_time)) / 1000));
    }
    if (view === "closed") return null;
    return 9680 + Math.floor((clock - mountTs.current) / 1000);
  })();
  const lkpClock = isLive
    ? caseDetail
      ? new Date(caseDetail.lkp_time).toTimeString().slice(0, 5)
      : "—"
    : "08:00";

  // 수색 우선순위 — POA 상위 셀 (순찰 지시용 요약)
  const priorityRows = useMemo(() => {
    if (!isLive)
      return [
        { rank: 1, name: "정릉시장 일대 (데모)", prob: 0.24, rel: 1 },
        { rank: 2, name: "정릉천 산책로 (데모)", prob: 0.18, rel: 0.75 },
        { rank: 3, name: "북한산 입구 (데모)", prob: 0.15, rel: 0.62 },
      ];
    const src = liveLayers?.combined ?? poa?.top_cells ?? [];
    const top = src.slice(0, 5);
    const maxP = top[0]?.prob ?? 1;
    return top.map((c, i) => ({
      rank: i + 1,
      name: `셀 …${c.cell.slice(-7)}`,
      prob: c.prob,
      rel: c.prob / maxP,
    }));
  }, [isLive, liveLayers, poa]);
  const priorityCum = priorityRows.reduce((s, r) => s + r.prob, 0);

  // ── 스타일 헬퍼 ────────────────────────────────────────────────
  const seg = (on: boolean): React.CSSProperties => ({
    whiteSpace: "nowrap",
    padding: "6px 12px",
    borderRadius: 6,
    border: "none",
    fontSize: 12.5,
    fontWeight: 600,
    cursor: "pointer",
    background: on ? T.accent : "transparent",
    color: on ? "#fff" : T.sub,
  });
  const ly = (on: boolean, disabled = false): React.CSSProperties => ({
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "6px 8px",
    borderRadius: 6,
    border: "none",
    fontSize: 12,
    cursor: disabled ? "not-allowed" : "pointer",
    textAlign: "left",
    width: "100%",
    background: on ? "rgba(145,132,217,.18)" : "transparent",
    color: disabled ? "#5a5f70" : on ? T.text : "#a2a7ba",
    fontWeight: on ? 600 : 500,
  });
  const tb = (on: boolean): React.CSSProperties => ({
    padding: "12px 4px",
    marginRight: 14,
    background: "none",
    border: "none",
    borderBottom: `2px solid ${on ? T.accent : "transparent"}`,
    fontSize: 13.5,
    fontWeight: 600,
    cursor: "pointer",
    color: on ? T.text : "#8a90a6",
  });

  const showLoadingOverlay = loadingActive;
  const activeStep = (() => {
    const i = STEP_BOUNDS.findIndex((b) => elapsed < b);
    return i < 0 ? 3 : i;
  })();

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      {/* 상태 스위처 (데모) / 케이스 표시줄 (라이브) */}
      <div
        style={{
          height: 46,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 20px",
          background: "#13151f",
          borderBottom: `1px solid rgba(233,233,237,.07)`,
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <span
            style={{
              fontSize: 10.5,
              fontWeight: 700,
              letterSpacing: ".11em",
              color: T.faint,
              textTransform: "uppercase",
            }}
          >
            {isLive ? "라이브 케이스" : "화면 상태 · 데모"}
          </span>
          {!isLive && (
            <div
              style={{
                display: "flex",
                gap: 3,
                padding: 3,
                background: T.inset,
                border: `1px solid ${T.border}`,
                borderRadius: 8,
              }}
            >
              <button style={seg(view === "loading")} onClick={() => { setView("loading"); setElapsed(0); }}>
                예측 로딩
              </button>
              <button style={seg(view === "tips3")} onClick={() => setView("tips3")}>
                제보 3건 반영
              </button>
              <button style={seg(view === "d3")} onClick={() => setView("d3")}>
                D3 새 지역
              </button>
              <button style={seg(view === "closed")} onClick={() => setView("closed")}>
                종결
              </button>
            </div>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11.5, color: T.dim }}>케이스</span>
          <span className="mono" style={{ fontSize: 11.5, color: "#c7cbdb" }}>
            {live.caseId}
          </span>
        </div>
      </div>

      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        {/* ── 지도 ── */}
        <section style={{ flex: 1, position: "relative", background: T.mapBg, overflow: "hidden" }}>
          <svg
            viewBox={`0 0 ${VB_W} ${VB_H}`}
            preserveAspectRatio="xMidYMid slice"
            style={{ width: "100%", height: "100%", display: "block" }}
          >
            <rect width={VB_W} height={VB_H} fill={T.mapBg} />
            {/* 도로망 플레이스홀더 (정릉동 느낌) */}
            <path d="M600,-20 L980,120 L980,340 L720,300 L640,140 Z" fill="#12251b" opacity={0.55} />
            <path
              d="M120,-20 C220,140 180,320 320,430 C440,520 400,690 520,800"
              fill="none" stroke="#16323f" strokeWidth={9} strokeLinecap="round" opacity={0.85}
            />
            <path
              d="M120,-20 C220,140 180,320 320,430 C440,520 400,690 520,800"
              fill="none" stroke="#1d4356" strokeWidth={3} strokeLinecap="round" opacity={0.7}
            />
            <g stroke="#343a4d" strokeWidth={6} fill="none" strokeLinecap="round">
              <path d="M-20,250 L360,300 L620,250 L980,300" />
              <path d="M430,-20 L470,360 L520,780" />
              <path d="M-20,540 L400,520 L780,560 L980,520" />
            </g>
            <g stroke="#282d3d" strokeWidth={3} fill="none" strokeLinecap="round">
              <path d="M60,120 L900,180" />
              <path d="M120,660 L860,700" />
              <path d="M250,-20 L300,780" />
              <path d="M700,-20 L740,780" />
              <path d="M-20,400 L960,430" />
            </g>

            {/* POA 히트맵 */}
            {!showLoadingOverlay &&
              (isLive
                ? liveCells.map((c, i) => (
                    <polygon
                      key={i}
                      points={c.points}
                      fill={c.fill}
                      opacity={c.opacity}
                      stroke={c.alerted ? "#cfe4ff" : "#0e1017"}
                      strokeWidth={c.alerted ? 1.4 : 0.6}
                      strokeOpacity={c.alerted ? 0.72 : 1}
                      style={c.alerted ? { strokeDasharray: "3 3" } : undefined}
                    >
                      <title>{`${c.prob.toFixed(4)}`}</title>
                    </polygon>
                  ))
                : demoCells.map((c, i) => (
                    <polygon
                      key={i}
                      points={c.points}
                      fill={c.fill}
                      opacity={c.opacity}
                      stroke={c.stroke}
                      strokeWidth={c.sw}
                      strokeOpacity={c.sop}
                      style={{ strokeDasharray: c.dash }}
                    />
                  )))}

            {/* 제보 핀 */}
            {!showLoadingOverlay &&
              (isLive ? liveTipPins : demoTipPins(view)).map((p, i) => (
                <g key={i} transform={`translate(${p.x} ${p.y})`}>
                  <circle r={10} fill="none" stroke={p.color} strokeWidth={1.6} opacity={0.5} />
                  <circle r={6} fill={p.color} stroke={T.mapBg} strokeWidth={1.6} />
                  <text
                    y={3.4}
                    textAnchor="middle"
                    fontSize={8}
                    fontWeight={700}
                    fill={T.mapBg}
                    fontFamily="ui-monospace,monospace"
                  >
                    {p.num}
                  </text>
                </g>
              ))}

            {/* LKP 크로스헤어 */}
            {(() => {
              const pos = isLive ? liveLkp : { x: 430, y: 360 };
              if (!pos) return null;
              return (
                <g transform={`translate(${pos.x} ${pos.y})`}>
                  <circle r={9} fill={T.red} opacity={0.5} style={{ animation: "lkpPing 2.4s infinite" }} />
                  <path d="M0,-13 L0,13 M-13,0 L13,0" stroke="#ff8a8e" strokeWidth={1.6} />
                  <circle r={5} fill={T.red} stroke={T.appBg} strokeWidth={2} />
                </g>
              );
            })()}

            {/* 자택·끌림점 마커 — 데모는 고정 좌표, 라이브는 페르소나 실좌표 투영 */}
            {!isLive && (
              <>
                <g transform="translate(560 540)">
                  <rect x={-7} y={-6.5} width={14} height={13} rx={2.5} fill="#12283f" stroke={T.home} strokeWidth={1.8} />
                  <path d="M-4.5,-1.5 L0,-6 L4.5,-1.5" fill="none" stroke="#a9d2f2" strokeWidth={1.7} strokeLinecap="round" />
                </g>
                <g transform="translate(300 236)">
                  <path d="M0,-8 L8,7 L-8,7 Z" fill="#3a2c12" stroke={T.amberText} strokeWidth={1.9} strokeLinejoin="round" />
                </g>
                <g transform="translate(648 430)">
                  <path d="M0,-8 L8,7 L-8,7 Z" fill="#3a2c12" stroke={T.amberText} strokeWidth={1.9} strokeLinejoin="round" />
                </g>
              </>
            )}
            {isLive && !showLoadingOverlay && liveHome && (
              <g transform={`translate(${liveHome.x} ${liveHome.y})`}>
                <rect x={-7} y={-6.5} width={14} height={13} rx={2.5} fill="#12283f" stroke={T.home} strokeWidth={1.8} />
                <path d="M-4.5,-1.5 L0,-6 L4.5,-1.5" fill="none" stroke="#a9d2f2" strokeWidth={1.7} strokeLinecap="round" />
                <title>자택</title>
              </g>
            )}
            {isLive &&
              !showLoadingOverlay &&
              liveAttractions.map((a, i) => (
                <g key={i} transform={`translate(${a.x} ${a.y})`}>
                  <path d="M0,-8 L8,7 L-8,7 Z" fill="#3a2c12" stroke={T.amberText} strokeWidth={1.9} strokeLinejoin="round" />
                  <title>{`끌림점 · ${a.label}`}</title>
                </g>
              ))}
          </svg>

          {/* 레이어 토글 */}
          <div
            style={{
              position: "absolute",
              top: 14,
              left: 14,
              width: 186,
              background: "rgba(20,22,32,.9)",
              backdropFilter: "blur(6px)",
              border: `1px solid rgba(233,233,237,.11)`,
              borderRadius: 10,
              padding: "11px 12px",
            }}
          >
            <div
              style={{
                fontSize: 10.5,
                fontWeight: 700,
                letterSpacing: ".09em",
                color: T.dim,
                textTransform: "uppercase",
                marginBottom: 9,
              }}
            >
              POA 레이어
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <button style={ly(layer === "combined")} onClick={() => setLayer("combined")}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: T.amber }} />
                결합 POA
                <span style={{ marginLeft: "auto", fontSize: 10, color: T.faint }}>기본</span>
              </button>
              <button
                style={ly(layer === "top_down", isLive && !liveLayers?.top_down)}
                disabled={isLive && !liveLayers?.top_down}
                onClick={() => setLayer("top_down")}
              >
                <span style={{ width: 8, height: 8, borderRadius: 2, background: "#c98a3a" }} />
                top-down
              </button>
              <button
                style={ly(layer === "bottom_up", isLive && !liveLayers?.bottom_up)}
                disabled={isLive && !liveLayers?.bottom_up}
                onClick={() => setLayer("bottom_up")}
              >
                <span style={{ width: 8, height: 8, borderRadius: 2, background: "#e5764a" }} />
                bottom-up
                <span style={{ marginLeft: "auto", fontSize: 9.5, color: "#8a7ad9", fontWeight: 700 }}>AI</span>
              </button>
              <button
                style={ly(layer === "statistical", isLive && !liveLayers?.statistical)}
                disabled={isLive && !liveLayers?.statistical}
                onClick={() => setLayer("statistical")}
              >
                <span style={{ width: 8, height: 8, borderRadius: 2, background: "#8a6a3a" }} />
                statistical
              </button>
            </div>
            {isLive && !liveLayers?.top_down && (
              <div style={{ fontSize: 9.5, color: T.faint, marginTop: 8, lineHeight: 1.5 }}>
                {layersPreparing
                  ? "4층 분해 준비 중 — 트레이스 재예측 실행(17–27초)…"
                  : "4층 분해 미준비 — 재예측 실행 시 활성화"}
              </div>
            )}
          </div>

          {/* 지도 라벨 */}
          <div
            style={{
              position: "absolute",
              top: 14,
              right: 14,
              fontSize: 10,
              color: T.faint,
              background: "rgba(20,22,32,.85)",
              padding: "4px 8px",
              borderRadius: 6,
              border: `1px solid ${T.border}`,
            }}
          >
            {isLive ? "정릉동 · 실 POA (플레이스홀더 배경)" : "정릉동 · 데모 지도(플레이스홀더)"}
          </div>

          {/* 범례 */}
          <div
            style={{
              position: "absolute",
              bottom: 14,
              left: 14,
              width: 230,
              background: "rgba(20,22,32,.9)",
              backdropFilter: "blur(6px)",
              border: `1px solid rgba(233,233,237,.11)`,
              borderRadius: 10,
              padding: "11px 12px",
            }}
          >
            <div
              style={{
                fontSize: 10.5,
                fontWeight: 700,
                letterSpacing: ".09em",
                color: T.dim,
                textTransform: "uppercase",
                marginBottom: 8,
              }}
            >
              범례
            </div>
            <div style={{ fontSize: 10.5, color: T.sub, marginBottom: 5 }}>
              위치 확률(POA) — 색 + 불투명도
            </div>
            <div
              style={{
                height: 9,
                borderRadius: 3,
                marginBottom: 3,
                background:
                  "linear-gradient(90deg,rgba(120,84,26,.28),rgba(214,140,44,.62),rgba(240,86,52,.92))",
              }}
            />
            <div
              className="mono"
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 9.5,
                color: T.dim,
                marginBottom: 10,
              }}
            >
              <span>낮음</span>
              <span>높음</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 11, color: "#c1c5d6" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ color: T.red, fontWeight: 700 }}>+</span>최종 목격(LKP)
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 12, height: 12, borderRadius: "50%", background: T.amber, border: `1.5px solid ${T.mapBg}` }} />
                제보 · 반영(층1)
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 12, height: 12, borderRadius: "50%", background: T.red, border: `1.5px solid ${T.mapBg}` }} />
                제보 · 재예측(층2)
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 12, height: 12, borderRadius: "50%", background: T.tierDiscard, border: `1.5px dashed ${T.sub}` }} />
                제보 · 파기(p&lt;0.2)
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 12, height: 12, borderRadius: 2, border: "1.5px dashed #cfe4ff", opacity: 0.8 }} />
                알림 발송 구역
              </div>
              {(!isLive || liveHome != null || liveAttractions.length > 0) && (
                <>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ width: 11, height: 11, background: "#12283f", border: `1.6px solid ${T.home}`, borderRadius: 2 }} />
                    자택
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ width: 0, height: 0, borderLeft: "6px solid transparent", borderRight: "6px solid transparent", borderBottom: `10px solid ${T.amberText}` }} />
                    끌림점(자주 가던 곳)
                  </div>
                </>
              )}
            </div>
          </div>

          {/* D3 배너 (데모) */}
          {!isLive && view === "d3" && (
            <div
              style={{
                position: "absolute",
                top: 16,
                left: "50%",
                transform: "translateX(-50%)",
                display: "flex",
                alignItems: "center",
                gap: 13,
                padding: "10px 16px",
                background: "rgba(56,20,22,.94)",
                border: `1px solid rgba(242,85,90,.55)`,
                borderRadius: 10,
                boxShadow: "0 8px 26px rgba(0,0,0,.5)",
              }}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: T.red,
                  animation: "pulseDot 1.2s infinite",
                }}
              />
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#ffb4b7" }}>
                  신규 고확률 지역 감지 — 3차 알림(D3) 발송 권고
                </div>
                <div style={{ fontSize: 11, color: "#e39ca0" }}>
                  정릉4동 우이천 일대 신규 클러스터 · rerun-check 트리거됨
                </div>
              </div>
            </div>
          )}

          {/* 종결 오버레이 (데모) */}
          {!isLive && view === "closed" && (
            <div
              style={{
                position: "absolute",
                inset: 0,
                background: "rgba(14,16,23,.5)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                pointerEvents: "none",
              }}
            >
              <div
                style={{
                  textAlign: "center",
                  padding: "22px 34px",
                  background: "rgba(16,32,22,.9)",
                  border: `1px solid rgba(69,184,105,.45)`,
                  borderRadius: 14,
                }}
              >
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".1em", color: "#6ecb8a", marginBottom: 6 }}>
                  CASE CLOSED
                </div>
                <div style={{ fontSize: 19, fontWeight: 700, color: "#e9f6ee" }}>케이스 종결 · 안전 발견</div>
                <div style={{ fontSize: 12.5, color: "#9dc7ac", marginTop: 4 }}>
                  정릉4동 우이천 산책로 · 10:12 발견
                </div>
              </div>
            </div>
          )}

          {/* 예측 로딩 오버레이 — 스피너 금지, 단계 스테퍼 + 경과초 */}
          {showLoadingOverlay && (
            <div
              style={{
                position: "absolute",
                inset: 0,
                background: "rgba(11,13,20,.86)",
                backdropFilter: "blur(3px)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <div
                style={{
                  width: 440,
                  background: T.card,
                  border: `1px solid rgba(233,233,237,.12)`,
                  borderRadius: 16,
                  padding: "26px 28px",
                  boxShadow: "0 20px 60px rgba(0,0,0,.6)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 5 }}>
                  <div style={{ fontSize: 16, fontWeight: 700 }}>AI 예측 실행 중</div>
                  <div className="mono" style={{ fontSize: 13, color: T.accentLight }}>
                    경과 {elapsed}s
                  </div>
                </div>
                <div style={{ fontSize: 12, color: "#8a90a6", marginBottom: 18 }}>
                  예상 소요 17–27초 · 500 워커 몬테카를로 시뮬레이션
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 2, marginBottom: 18 }}>
                  {STEP_LABELS.map((label, i) => {
                    const done = i < activeStep;
                    const cur = i === activeStep;
                    return (
                      <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "9px 6px" }}>
                        <div
                          className="mono"
                          style={{
                            width: 24,
                            height: 24,
                            borderRadius: "50%",
                            flexShrink: 0,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: 11,
                            fontWeight: 700,
                            ...(done
                              ? { background: T.green, color: T.mapBg }
                              : cur
                                ? {
                                    background: T.accent,
                                    color: "#fff",
                                    boxShadow: "0 0 0 4px rgba(145,132,217,.22)",
                                    animation: "pulseDot 1.3s infinite",
                                  }
                                : { background: "#26293a", color: T.faint }),
                          }}
                        >
                          {done ? "✓" : cur ? "" : i + 1}
                        </div>
                        <div style={{ flex: 1, fontSize: 13, color: done || cur ? T.text : T.faint, fontWeight: done || cur ? 600 : 400 }}>
                          {label}
                        </div>
                        <div style={{ fontSize: 11, color: done ? "#6ecb8a" : cur ? T.accentLight : "#5a5f70" }}>
                          {done ? "완료" : cur ? "진행 중" : "대기"}
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div style={{ height: 6, borderRadius: 3, background: "#26293a", overflow: "hidden", marginBottom: 12 }}>
                  <div
                    style={{
                      height: "100%",
                      borderRadius: 3,
                      background: "linear-gradient(90deg,#9184d9,#b5abfc)",
                      width: `${Math.min(100, Math.round((elapsed / 24) * 100))}%`,
                    }}
                  />
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 11, color: T.faint }}>
                  <span style={{ width: 5, height: 5, borderRadius: "50%", background: T.amber }} />
                  실제 파이프라인 실행{isLive ? "" : "(스텁 모드)"} · 실발송(FCM) 미구현 — 발송은 시뮬레이션입니다
                </div>
              </div>
            </div>
          )}
        </section>

        {/* ── 우측 패널 ── */}
        <aside
          style={{
            width: 452,
            flexShrink: 0,
            background: T.surface,
            borderLeft: `1px solid ${T.border}`,
            display: "flex",
            flexDirection: "column",
            minHeight: 0,
          }}
        >
          <div style={{ padding: "16px 18px", borderBottom: `1px solid rgba(233,233,237,.08)` }}>
            <div style={{ display: "flex", gap: 13, alignItems: "center" }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3, flexShrink: 0 }}>
                <div
                  style={{
                    width: 54,
                    height: 54,
                    borderRadius: 10,
                    background: "linear-gradient(160deg,#2a2e3d,#20232f)",
                    border: `1px solid rgba(233,233,237,.12)`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 20,
                    fontWeight: 700,
                    color: T.dim,
                  }}
                >
                  {personaName.slice(0, 1)}
                </div>
                <span style={{ fontSize: 8.5, color: T.faint }}>사진 미등록</span>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 18, fontWeight: 700 }}>{personaName}</span>
                  {personaAge > 0 && (
                    <span className="mono" style={{ fontSize: 13, color: T.sub }}>
                      {personaAge}세
                    </span>
                  )}
                  <span
                    style={{
                      fontSize: 11,
                      padding: "2px 8px",
                      borderRadius: 5,
                      background: T.amberBg,
                      color: T.amberText,
                      fontWeight: 600,
                      border: `1px solid rgba(240,166,60,.28)`,
                    }}
                  >
                    {personaType}
                  </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6, flexWrap: "wrap" }}>
                  <StatusChip label={st.l} color={st.c} bg={st.bg} />
                  {missingSec != null && (
                    <span
                      className="mono"
                      style={{
                        fontSize: 12.5,
                        fontWeight: 700,
                        color: missingSec > 10800 ? T.redText : missingSec > 3600 ? T.amberText : T.sub,
                      }}
                    >
                      경과 {fmtDur(missingSec)}
                    </span>
                  )}
                  <span style={{ fontSize: 11, color: T.dim, whiteSpace: "nowrap" }}>
                    최종 목격 {lkpClock}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div style={{ display: "flex", padding: "0 18px", borderBottom: `1px solid rgba(233,233,237,.08)`, gap: 2 }}>
            <button style={tb(tab === "profile")} onClick={() => setTab("profile")}>프로필</button>
            <button style={tb(tab === "timeline")} onClick={() => setTab("timeline")}>타임라인</button>
            <button style={tb(tab === "manage")} onClick={() => setTab("manage")}>알림·제보</button>
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: 18 }}>
            {tab === "profile" && (
              <div>
                <SectionLabel>인상착의</SectionLabel>
                <div
                  style={{
                    fontSize: 12.5,
                    color: "#dfe2ec",
                    lineHeight: 1.6,
                    padding: "11px 13px",
                    borderRadius: 8,
                    background: "#1e2130",
                    border: `1px solid rgba(233,233,237,.07)`,
                    marginBottom: 20,
                  }}
                >
                  {appearance}
                </div>

                <SectionLabel>신고자(보호자)</SectionLabel>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 9,
                    padding: "11px 13px",
                    borderRadius: 8,
                    background: "#1e2130",
                    border: `1px solid rgba(233,233,237,.07)`,
                    marginBottom: 20,
                  }}
                >
                  {reporter ? (
                    <>
                      <span style={{ fontSize: 13, color: "#dfe2ec" }}>
                        {reporter.name}{" "}
                        <span style={{ fontSize: 11, color: T.dim }}>({reporter.relation})</span>
                      </span>
                      <span className="mono" style={{ fontSize: 12, color: T.amberText, whiteSpace: "nowrap" }}>
                        {reporter.phone}
                      </span>
                    </>
                  ) : (
                    <span style={{ fontSize: 12, color: T.dim }}>
                      신고자 정보 미등록 — 신고서(문서) 접수 시 추출(Upstage)
                    </span>
                  )}
                </div>

                <div
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    justifyContent: "space-between",
                    gap: 8,
                  }}
                >
                  <SectionLabel>페르소나 요약 · 끌림점</SectionLabel>
                  <span
                    style={{
                      fontSize: 10,
                      color: T.faint,
                      border: `1px solid ${T.border}`,
                      borderRadius: 5,
                      padding: "2px 7px",
                      whiteSpace: "nowrap",
                    }}
                  >
                    보호자 사전등록 인터뷰 기반
                  </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 7, marginBottom: 20 }}>
                  {attractions.length === 0 && (
                    <div style={{ fontSize: 12, color: T.dim }}>등록된 끌림점 없음</div>
                  )}
                  {attractions.map((a, i) => (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 9,
                        padding: "9px 11px",
                        borderRadius: 8,
                        background: "#1e2130",
                        border: `1px solid rgba(233,233,237,.07)`,
                      }}
                    >
                      <span
                        className="mono"
                        style={{
                          width: 20,
                          height: 20,
                          borderRadius: 5,
                          background: "rgba(240,166,60,.15)",
                          color: T.amberText,
                          fontSize: 11,
                          fontWeight: 700,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                      >
                        {i + 1}
                      </span>
                      <span style={{ fontSize: 13, color: "#dfe2ec", flex: 1 }}>{a.label}</span>
                      <span style={{ fontSize: 11, color: T.dim }}>{a.note}</span>
                    </div>
                  ))}
                </div>

                <SectionLabel>행동 축 점수</SectionLabel>
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {Object.entries(axisScores).length === 0 && (
                    <div style={{ fontSize: 12, color: T.dim }}>
                      축 점수 없음 (AXIS_SCORING_ENABLED=false 기본값)
                    </div>
                  )}
                  {Object.entries(axisScores).map(([key, val]) => (
                    <div key={key}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 5 }}>
                        <span style={{ color: "#c1c5d6" }} title={key}>
                          {axisLabel(key)}
                        </span>
                        <span className="mono" style={{ color: val >= 0.7 ? T.amberText : T.text }}>
                          {val.toFixed(2)}
                        </span>
                      </div>
                      <div style={{ height: 6, borderRadius: 3, background: "#26293a" }}>
                        <div
                          style={{
                            height: "100%",
                            borderRadius: 3,
                            width: `${Math.round(val * 100)}%`,
                            background: val >= 0.7 ? T.amber : T.accent,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>

                {behaviorNote && (
                  <div
                    style={{
                      fontSize: 11.5,
                      color: "#8a90a6",
                      lineHeight: 1.6,
                      marginTop: 16,
                      paddingTop: 16,
                      borderTop: `1px solid rgba(233,233,237,.07)`,
                    }}
                  >
                    {behaviorNote}
                  </div>
                )}
              </div>
            )}

            {tab === "timeline" && (
              <div style={{ position: "relative", paddingLeft: 6 }}>
                {timeline.map((ev, i) => {
                  const col = TAG_TONE[ev.tone] ?? T.tierDiscard;
                  const v = ev.verdict ? VERDICT[ev.verdict] : null;
                  return (
                    <div key={i} style={{ display: "flex", gap: 12, paddingBottom: 16 }}>
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
                        <div
                          style={{
                            width: 11,
                            height: 11,
                            borderRadius: "50%",
                            marginTop: 3,
                            background: col,
                            boxShadow: `0 0 0 3px ${col}22`,
                          }}
                        />
                        <div style={{ width: 1.5, flex: 1, background: "rgba(233,233,237,.1)", marginTop: 2 }} />
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 3 }}>
                          <span className="mono" style={{ fontSize: 11, color: T.dim }}>{ev.t}</span>
                          {ev.tag && (
                            <span
                              style={{
                                fontSize: 10,
                                fontWeight: 700,
                                padding: "2px 7px",
                                borderRadius: 5,
                                color: col,
                                background: `${col}22`,
                                border: `1px solid ${col}55`,
                              }}
                            >
                              {ev.tag}
                            </span>
                          )}
                          {ev.sim && (
                            <span
                              style={{
                                fontSize: 9.5,
                                color: T.dim,
                                padding: "1px 6px",
                                borderRadius: 4,
                                border: `1px solid ${T.borderStrong}`,
                              }}
                            >
                              시뮬
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 2 }}>{ev.title}</div>
                        <div style={{ fontSize: 11.5, color: "#8a90a6", lineHeight: 1.5 }}>{ev.desc}</div>
                        {ev.p != null && v && (
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 8,
                              marginTop: 7,
                              padding: "7px 9px",
                              borderRadius: 7,
                              background: T.inset,
                              border: `1px solid rgba(233,233,237,.07)`,
                            }}
                          >
                            <span style={{ fontSize: 10.5, color: T.dim, whiteSpace: "nowrap" }}>신뢰도 p</span>
                            <PBar p={ev.p} color={v.color} />
                            <span className="mono" style={{ fontSize: 12, fontWeight: 700, flexShrink: 0 }}>
                              p={ev.p.toFixed(2)}
                            </span>
                            <span
                              style={{
                                fontSize: 10,
                                fontWeight: 700,
                                padding: "2px 8px",
                                borderRadius: 5,
                                color: v.color,
                                background: `${v.color}22`,
                                border: `1px solid ${v.color}55`,
                                whiteSpace: "nowrap",
                                flexShrink: 0,
                              }}
                            >
                              {v.label}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {tab === "manage" && (
              <div>
                {(isLive ? rerun?.should_rerun : view === "tips3" || view === "d3") && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 10,
                      padding: "12px 13px",
                      borderRadius: 10,
                      background: "rgba(242,85,90,.1)",
                      border: `1px solid rgba(242,85,90,.38)`,
                      marginBottom: 18,
                    }}
                  >
                    <span
                      style={{
                        width: 7,
                        height: 7,
                        borderRadius: "50%",
                        background: T.red,
                        marginTop: 5,
                        animation: "pulseDot 1.4s infinite",
                      }}
                    />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 700, color: "#ffb4b7" }}>
                        재예측 권장 (rerun-check)
                      </div>
                      <div style={{ fontSize: 11.5, color: "#e39ca0", marginTop: 2 }}>
                        {isLive
                          ? rerun?.reason ?? ""
                          : view === "d3"
                            ? "우이천 신규 고확률 클러스터 감지 — 3차 알림(D3) 발송 검토"
                            : "제보 #3(p=0.87) 층2 판정 — POA 재예측 완료, 신규 알림 검토"}
                      </div>
                    </div>
                  </div>
                )}

                <SectionLabel>수색 우선순위 — POA 상위 셀</SectionLabel>
                <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 8 }}>
                  {priorityRows.length === 0 && (
                    <div style={{ fontSize: 12, color: T.dim }}>POA 없음 — 예측을 먼저 실행</div>
                  )}
                  {priorityRows.map((r) => (
                    <div
                      key={r.rank}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 9,
                        padding: "8px 11px",
                        borderRadius: 8,
                        background: "#1e2130",
                        border: `1px solid rgba(233,233,237,.07)`,
                      }}
                    >
                      <span
                        className="mono"
                        style={{
                          width: 18,
                          textAlign: "center",
                          fontSize: 11,
                          fontWeight: 700,
                          color: r.rank === 1 ? T.redText : T.amberText,
                        }}
                      >
                        {r.rank}
                      </span>
                      <span className="mono" style={{ flex: 1, fontSize: 11.5, color: "#dfe2ec" }}>
                        {r.name}
                      </span>
                      <PBar p={r.rel} color={T.amber} />
                      <span
                        className="mono"
                        style={{ fontSize: 11, color: T.text, width: 46, textAlign: "right", flexShrink: 0 }}
                      >
                        {(r.prob * 100).toFixed(1)}%
                      </span>
                    </div>
                  ))}
                </div>
                {priorityRows.length > 0 && (
                  <div style={{ fontSize: 10, color: T.faint, lineHeight: 1.5, marginBottom: 20 }}>
                    상위 {priorityRows.length}셀 누적 {(priorityCum * 100).toFixed(0)}% —
                    셀→장소명 매핑(역지오코딩)은 후속, 라이브는 H3 셀 ID 기준
                  </div>
                )}

                <SectionLabel>알림 발송 이력</SectionLabel>
                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 22 }}>
                  {(isLive ? [] : demoAlerts(view)).map((al, i) => (
                    <div
                      key={i}
                      style={{
                        padding: "11px 12px",
                        borderRadius: 9,
                        background: "#1e2130",
                        border: `1px solid rgba(233,233,237,.08)`,
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                        <span
                          style={{
                            fontSize: 10,
                            fontWeight: 700,
                            padding: "2px 8px",
                            borderRadius: 5,
                            color: T.red,
                            background: `${T.red}22`,
                            border: `1px solid ${T.red}55`,
                          }}
                        >
                          {al.code}
                        </span>
                        <span style={{ fontSize: 12.5, fontWeight: 600, flex: 1 }}>{al.name}</span>
                        <span className="mono" style={{ fontSize: 10.5, color: T.dim }}>{al.time}</span>
                      </div>
                      <div style={{ display: "flex", gap: 16, fontSize: 11.5, color: T.sub }}>
                        <span>
                          발송 셀 <b className="mono" style={{ color: "#dfe2ec" }}>{al.cells}</b>
                        </span>
                        <span>
                          도달 추정<span style={{ fontSize: 9.5, color: T.dim }}>(데모)</span>{" "}
                          <b style={{ color: "#dfe2ec" }}>{al.reach}</b>
                        </span>
                        <span
                          style={{
                            color: al.pending ? T.amberText : "#6ecb8a",
                            background: al.pending ? T.amberBg : T.greenBg,
                            padding: "1px 7px",
                            borderRadius: 4,
                            fontSize: 10.5,
                          }}
                        >
                          {al.pending ? "발송 대기" : "시뮬 발송됨"}
                        </span>
                      </div>
                    </div>
                  ))}
                  {isLive && liveLog.length === 0 && (
                    <div style={{ fontSize: 12, color: T.dim }}>
                      이 세션에서 발송한 알림 없음 — 아래 작업 버튼으로 실행
                    </div>
                  )}
                  {isLive &&
                    liveLog.map((l, i) => (
                      <div
                        key={i}
                        className="mono"
                        style={{
                          fontSize: 11.5,
                          color: "#c1c5d6",
                          padding: "9px 11px",
                          borderRadius: 8,
                          background: "#1e2130",
                          border: `1px solid rgba(233,233,237,.08)`,
                        }}
                      >
                        {l}
                      </div>
                    ))}
                </div>

                <SectionLabel>작업</SectionLabel>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <ActionBtn
                    color={T.amberText}
                    border="rgba(240,166,60,.4)"
                    title="재예측 실행"
                    sub="POA 갱신 · 17–27초"
                    onClick={runPredict}
                    disabled={!isLive || predicting}
                  />
                  <ActionBtn
                    color={T.redText}
                    border={T.redBorder}
                    title="알림 발송"
                    sub="D2/D3 · 시뮬레이션"
                    onClick={runAlert}
                    disabled={!isLive}
                  />
                  <ActionBtn
                    color={T.accentLighter}
                    border="rgba(145,132,217,.4)"
                    title="제보 입력"
                    sub="need_more 분기 지원"
                    onClick={() => setTipOpen(true)}
                    disabled={!isLive}
                  />
                  <ActionBtn
                    color={T.greenText}
                    border={T.greenBorder}
                    title="케이스 종결"
                    sub="발견 · 파기 시작"
                    onClick={() => setCloseOpen(true)}
                    disabled={!isLive}
                  />
                </div>
                <div
                  style={{
                    fontSize: 10.5,
                    color: T.faint,
                    lineHeight: 1.6,
                    marginTop: 14,
                    display: "flex",
                    gap: 7,
                  }}
                >
                  <span
                    style={{
                      width: 5,
                      height: 5,
                      borderRadius: "50%",
                      background: T.amber,
                      marginTop: 5,
                      flexShrink: 0,
                    }}
                  />
                  <span>
                    알림 실발송(FCM)은 미구현 상태로, 모든 발송은{" "}
                    <b style={{ color: T.sub }}>시뮬레이션</b>이며 응답 sent=false로 기록됩니다.
                    {!isLive && " 작업 버튼은 라이브 모드(백엔드 기동)에서 활성화됩니다."}
                  </span>
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>

      {tipOpen && (
        <TipModal
          caseId={live.caseId}
          onClose={() => setTipOpen(false)}
          onSubmitted={() => {
            setTipOpen(false);
            loadLive();
          }}
        />
      )}
      {closeOpen && (
        <CloseModal
          caseId={live.caseId}
          onClose={() => setCloseOpen(false)}
          onClosed={() => {
            setCloseOpen(false);
            loadLive();
          }}
        />
      )}
    </div>
  );
}

function ActionBtn({
  color,
  border,
  title,
  sub,
  onClick,
  disabled,
}: {
  color: string;
  border: string;
  title: string;
  sub: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 3,
        alignItems: "flex-start",
        padding: "12px 13px",
        borderRadius: 9,
        background: "transparent",
        border: `1px solid ${border}`,
        cursor: disabled ? "not-allowed" : "pointer",
        textAlign: "left",
        opacity: disabled ? 0.45 : 1,
      }}
    >
      <span style={{ fontSize: 13, fontWeight: 600, color }}>{title}</span>
      <span style={{ fontSize: 10.5, color: "#8a90a6" }}>{sub}</span>
    </button>
  );
}
