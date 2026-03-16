import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  spring,
} from "remotion";

/* ── helpers ───────────────────────────────────────── */

const mono = "'JetBrains Mono','SF Mono','Fira Code',monospace";
const sans = "'Inter','Helvetica Neue',sans-serif";
const ACCENT = "#6366f1";
const GLOW = "rgba(99,102,241,0.35)";

/* ── Typing line ───────────────────────────────────── */
const Line: React.FC<{
  text: string; start: number; speed?: number; frame: number;
  color?: string; prefix?: string; prefixColor?: string;
  bold?: boolean; indent?: number;
}> = ({ text, start, speed = 1.5, frame, color = "#c8d0e0", prefix, prefixColor, bold, indent = 0 }) => {
  const f = frame - start;
  if (f < 0) return null;
  const chars = Math.min(Math.floor(f * speed), text.length);
  return (
    <div style={{
      fontFamily: mono, fontSize: 13, lineHeight: 1.55, whiteSpace: "pre",
      color, fontWeight: bold ? 700 : 400, paddingLeft: indent,
      opacity: interpolate(f, [0, 4], [0, 1], { extrapolateRight: "clamp" }),
    }}>
      {prefix && <span style={{ color: prefixColor || "#6ec6ff" }}>{prefix}</span>}
      {text.slice(0, chars)}
    </div>
  );
};

/* ── Agent card (side panel) ───────────────────────── */
const AgentCard: React.FC<{
  name: string; role: string; status: string;
  color: string; start: number; y: number; frame: number; fps: number;
}> = ({ name, role, status, color, start, y, frame, fps }) => {
  const rel = frame - start;
  if (rel < 0) return null;
  const s = spring({ frame: rel, fps, config: { damping: 14, stiffness: 120 } });
  const pulse = status === "running" ? 0.6 + 0.4 * Math.sin(rel * 0.25) : 1;
  return (
    <div style={{
      position: "absolute", right: 16, top: y,
      width: 210, padding: "7px 10px",
      background: "rgba(20,20,45,0.85)",
      border: `1px solid ${color}44`, borderLeft: `3px solid ${color}`,
      borderRadius: 6, transform: `translateX(${(1 - s) * 240}px)`,
      opacity: s, fontFamily: mono, fontSize: 11,
    }}>
      <div style={{ color, fontWeight: 700, marginBottom: 2 }}>{name}</div>
      <div style={{ color: "#888", fontSize: 10 }}>{role}</div>
      <div style={{
        color: status === "done" ? "#34d399" : status === "running" ? "#fbbf24" : "#888",
        fontSize: 10, marginTop: 3, opacity: pulse,
      }}>
        {status === "running" ? "● " : status === "done" ? "✓ " : "○ "}{status}
      </div>
    </div>
  );
};

/* ── Progress bar ──────────────────────────────────── */
const Bar: React.FC<{
  start: number; dur: number; label: string; color?: string; frame: number;
}> = ({ start, dur, label, color = ACCENT, frame }) => {
  const f = frame - start;
  if (f < 0) return null;
  const p = Math.min(f / dur, 1);
  return (
    <div style={{ margin: "3px 0", fontFamily: mono, fontSize: 11 }}>
      <span style={{ color: "#777" }}>{label} </span>
      <span style={{ color: p >= 1 ? "#34d399" : "#fbbf24" }}>{Math.floor(p * 100)}%</span>
      <div style={{
        height: 4, width: "55%", background: "#1a1a3a",
        borderRadius: 2, overflow: "hidden", marginTop: 2,
      }}>
        <div style={{
          height: "100%", width: `${p * 100}%`,
          background: `linear-gradient(90deg, ${color}, #22d3ee)`, borderRadius: 2,
        }} />
      </div>
    </div>
  );
};

/* ── Counter widget ────────────────────────────────── */
const Counter: React.FC<{
  start: number; dur: number; from: number; to: number;
  label: string; x: number; y: number; color?: string; frame: number;
}> = ({ start, dur, from, to, label, x, y, color = "#fff", frame }) => {
  const f = frame - start;
  if (f < 0) return null;
  const t = Math.min(f / dur, 1);
  const val = Math.floor(from + (to - from) * t);
  const s = interpolate(f, [0, 6], [0.7, 1], { extrapolateRight: "clamp" });
  return (
    <div style={{
      position: "absolute", left: x, top: y,
      fontFamily: sans, textAlign: "center",
      transform: `scale(${s})`, opacity: s,
    }}>
      <div style={{ fontSize: 28, fontWeight: 800, color }}>{val.toLocaleString()}</div>
      <div style={{ fontSize: 10, color: "#888", marginTop: -2 }}>{label}</div>
    </div>
  );
};

/* ── Phase badge ───────────────────────────────────── */
const Phase: React.FC<{ text: string; start: number; frame: number; fps: number }> = ({ text, start, frame, fps }) => {
  const rel = frame - start;
  if (rel < 0) return null;
  const s = spring({ frame: rel, fps, config: { damping: 12 } });
  return (
    <div style={{
      position: "absolute", top: 12, right: 14,
      background: `linear-gradient(135deg, ${ACCENT}, #8b5cf6)`,
      color: "#fff", padding: "6px 14px", borderRadius: 6,
      fontSize: 12, fontWeight: 700, fontFamily: sans,
      transform: `scale(${s})`, boxShadow: `0 4px 20px ${GLOW}`,
    }}>
      {text}
    </div>
  );
};

/* ── Scenes ────────────────────────────────────────── */

const S = 110; // frames per scene

type SceneDef = {
  badge: string;
  render: (b: number, f: number, fps: number) => React.ReactNode;
};

const SCENES: SceneDef[] = [
  // ── 0: Init ──
  {
    badge: "Phase 0 — Init",
    render: (b, f, fps) => (
      <>
        <Line frame={f} start={b} text="python -m cc_layer.cli.sim_init \" prefix="$ " prefixColor="#34d399" color="#a0e0a0" />
        <Line frame={f} start={b+2} text="  --profile @session/profile.json --form @session/form.json" color="#666" speed={3} />
        <Line frame={f} start={b+18} text="" />
        <Line frame={f} start={b+20} text="Loading candidate profile..." color="#6ec6ff" speed={2} />
        <Line frame={f} start={b+32} text={'  name: "K"  age: 37  income: 2500\u4E07'} color="#e0e0e0" speed={2.5} />
        <Line frame={f} start={b+42} text="  role: CEO / Founder @ AI Brain Partners" color="#e0e0e0" speed={2.5} />
        <Line frame={f} start={b+52} text="  skills: [PdM, BizDev, DataSci, AI/ML, CRM, Web3]" color="#e0e0e0" speed={2.5} />
        <Line frame={f} start={b+65} text="" />
        <Line frame={f} start={b+68} text={"CareerState initialized \u2713"} color="#34d399" bold speed={2} />
        <Bar frame={f} start={b+20} dur={50} label="profile" />
      </>
    ),
  },

  // ── 1: Path Design ──
  {
    badge: "Phase 1a — PathDesigner",
    render: (b, f, fps) => (
      <>
        <Line frame={f} start={b} text="Spawning SubAgent: PathDesignerAgent (Sonnet)" color="#6ec6ff" speed={2} />
        <Line frame={f} start={b+12} text="Designing 5 divergent career paths..." color="#888" speed={2} />
        <Line frame={f} start={b+25} text="" />
        <Line frame={f} start={b+28} text={"  \u25A0 Path A  AI Brain Partners Scale-up (IPO/M&A)"} color="#fbbf24" speed={2.5} />
        <Line frame={f} start={b+38} text={"  \u25A0 Path B  Big Tech Entry (Google/MS AI Division)"} color="#34d399" speed={2.5} />
        <Line frame={f} start={b+48} text={"  \u25A0 Path C  VC/CVC Transition (Investor Side)"} color="#f472b6" speed={2.5} />
        <Line frame={f} start={b+58} text={"  \u25A0 Path D  Multi-Business Portfolio Management"} color="#fb923c" speed={2.5} />
        <Line frame={f} start={b+68} text={"  \u25A0 Path E  Global Expansion (SEA / US Market)"} color="#a78bfa" speed={2.5} />
        <Line frame={f} start={b+82} text="" />
        <Line frame={f} start={b+84} text={"5 paths designed \u2713  path_designs.json"} color="#34d399" bold speed={2} />
        <AgentCard frame={f} fps={fps} name="PathDesigner" role="Sonnet SubAgent" status={f < b+84 ? "running" : "done"} color="#6366f1" start={b+3} y={50} />
      </>
    ),
  },

  // ── 2: Path Expand x5 PARALLEL ──
  {
    badge: "Phase 1b — 5x Parallel Expand",
    render: (b, f, fps) => (
      <>
        <Line frame={f} start={b} text="Spawning 5 SubAgents in parallel..." color="#6ec6ff" bold speed={2} />
        <Line frame={f} start={b+8} text="" />
        <Line frame={f} start={b+10} text={"  [A] Expanding: 10yr \u00D7 4 scenarios (best/likely/base/worst)"} color="#fbbf24" speed={3} />
        <Line frame={f} start={b+14} text={"  [B] Expanding: 10yr \u00D7 4 scenarios (best/likely/base/worst)"} color="#34d399" speed={3} />
        <Line frame={f} start={b+18} text={"  [C] Expanding: 10yr \u00D7 4 scenarios (best/likely/base/worst)"} color="#f472b6" speed={3} />
        <Line frame={f} start={b+22} text={"  [D] Expanding: 10yr \u00D7 4 scenarios (best/likely/base/worst)"} color="#fb923c" speed={3} />
        <Line frame={f} start={b+26} text={"  [E] Expanding: 10yr \u00D7 4 scenarios (best/likely/base/worst)"} color="#a78bfa" speed={3} />
        <Bar frame={f} start={b+10} dur={70} label="Path A" color="#fbbf24" />
        <Bar frame={f} start={b+14} dur={65} label="Path B" color="#34d399" />
        <Bar frame={f} start={b+18} dur={60} label="Path C" color="#f472b6" />
        <Bar frame={f} start={b+22} dur={58} label="Path D" color="#fb923c" />
        <Bar frame={f} start={b+26} dur={55} label="Path E" color="#a78bfa" />
        <Line frame={f} start={b+88} text="" />
        <Line frame={f} start={b+90} text={"20 trajectories generated \u2713  (5 \u00D7 4 scenarios)"} color="#34d399" bold speed={2.5} />
        <AgentCard frame={f} fps={fps} name="Expander-A" role="Sonnet" status={f < b+80 ? "running" : "done"} color="#fbbf24" start={b+3} y={44} />
        <AgentCard frame={f} fps={fps} name="Expander-B" role="Sonnet" status={f < b+78 ? "running" : "done"} color="#34d399" start={b+5} y={92} />
        <AgentCard frame={f} fps={fps} name="Expander-C" role="Sonnet" status={f < b+76 ? "running" : "done"} color="#f472b6" start={b+7} y={140} />
        <AgentCard frame={f} fps={fps} name="Expander-D" role="Sonnet" status={f < b+74 ? "running" : "done"} color="#fb923c" start={b+9} y={188} />
        <AgentCard frame={f} fps={fps} name="Expander-E" role="Sonnet" status={f < b+72 ? "running" : "done"} color="#a78bfa" start={b+11} y={236} />
      </>
    ),
  },

  // ── 3: Score + Rank ──
  {
    badge: "Phase 2 — Score & Rank",
    render: (b, f, fps) => (
      <>
        <Line frame={f} start={b} text="python -m cc_layer.cli.path_score --top-n 5" prefix="$ " prefixColor="#34d399" color="#a0e0a0" />
        <Line frame={f} start={b+15} text="" />
        <Line frame={f} start={b+17} text="Scoring 20 trajectories..." color="#6ec6ff" speed={2} />
        <Line frame={f} start={b+28} text="  weights: salary=0.25 satisfaction=0.25 wlb=0.20 cash=0.15 stress=0.15" color="#666" speed={3} />
        <Line frame={f} start={b+42} text="" />
        <Line frame={f} start={b+44} text={"  #1  Path B  0.7823  Google AI \u2192 VP      \u00A56000\u4E07 / sat 90%"} color="#34d399" speed={2.5} />
        <Line frame={f} start={b+54} text={"  #2  Path A  0.7456  IPO/M&A exit        \u00A512000\u4E07 / sat 78%"} color="#fbbf24" speed={2.5} />
        <Line frame={f} start={b+64} text={"  #3  Path E  0.7102  SEA expansion       \u00A55500\u4E07 / sat 82%"} color="#a78bfa" speed={2.5} />
        <Line frame={f} start={b+74} text={"  #4  Path D  0.6847  Portfolio CEO        \u00A55000\u4E07 / sat 80%"} color="#fb923c" speed={2.5} />
        <Line frame={f} start={b+84} text={"  #5  Path C  0.6523  VC partner           \u00A54000\u4E07 / sat 75%"} color="#f472b6" speed={2.5} />
        <Line frame={f} start={b+96} text="" />
        <Line frame={f} start={b+98} text={"multipath_result.json \u2713"} color="#34d399" bold speed={2} />
      </>
    ),
  },

  // ── 4: Swarm — THE BIG ONE ──
  {
    badge: "Phase 3-4 — Agent Swarm (30 agents)",
    render: (b, f, fps) => {
      const agentNames = [
        "Ryan Cho", "Yuki Tanaka", "Mika Chen", "Sato Kenji",
        "Priya Nair", "Alex Kim", "Nishimura Yu", "Fujiwara Mei",
        "Takeshi Ono", "Hashimoto Ai", "Dev Patel", "Suzuki Ren",
      ];
      const roles = [
        "SaaS Founder", "Google SWE", "VC Partner", "HR Director",
        "Angel Investor", "McKinsey Alum", "CTO", "Career Coach",
        "Serial Entrepreneur", "PE Associate", "Tech Lead", "Product VP",
      ];
      const roundNum = f >= b ? Math.min(Math.floor((f - b) / 2.2), 40) : 0;
      const actionCount = Math.min(Math.floor(roundNum * 12.1), 483);
      const visibleAgents = Math.min(Math.floor((f - b) / 3), 8);
      const colors = ["#fbbf24","#34d399","#f472b6","#fb923c","#a78bfa","#6ec6ff","#ef4444","#14b8a6"];

      return (
        <>
          <Line frame={f} start={b} text="Spawning 30 AI agents with diverse backgrounds..." color="#6ec6ff" bold speed={2} />
          <Line frame={f} start={b+12} text="Starting swarm discussion: 40 rounds..." color="#6ec6ff" speed={2} />
          <Line frame={f} start={b+20} text="" />
          {roundNum > 0 && (
            <Line frame={f} start={b+22}
              text={`  Round ${String(roundNum).padStart(2)}/40  |  ${actionCount} actions  |  posts + comments + reactions`}
              color={roundNum >= 40 ? "#34d399" : "#fbbf24"} speed={99} />
          )}
          {roundNum >= 5 && <Line frame={f} start={b+33} text={"  \u25B8 heated debate: Path A startup risk vs Path B stability"} color="#888" speed={3} />}
          {roundNum >= 15 && <Line frame={f} start={b+45} text={"  \u25B8 consensus: Path B offers best risk-adjusted returns"} color="#888" speed={3} />}
          {roundNum >= 25 && <Line frame={f} start={b+57} text={"  \u25B8 contrarian view: Path A upside is 12000\u4E07"} color="#888" speed={3} />}
          {roundNum >= 35 && <Line frame={f} start={b+70} text={"  \u25B8 final take: 60% favor B, 25% favor A, 15% split C/D/E"} color="#888" speed={3} />}
          {roundNum >= 40 && (
            <>
              <Line frame={f} start={b+85} text="" />
              <Line frame={f} start={b+87} text={"483 actions / 30 agents / 40 rounds \u2713"} color="#34d399" bold speed={2} />
            </>
          )}

          {agentNames.slice(0, visibleAgents).map((name, i) => (
            <AgentCard key={i} frame={f} fps={fps}
              name={name} role={roles[i]}
              status={roundNum >= 40 ? "done" : "running"}
              color={colors[i % 8]} start={b + 8 + i * 3} y={44 + i * 48}
            />
          ))}

          <Counter frame={f} start={b+15} dur={75} from={0} to={30} label="Agents" x={480} y={380} color="#6ec6ff" />
          <Counter frame={f} start={b+15} dur={75} from={0} to={483} label="Actions" x={560} y={380} color="#fbbf24" />
          <Counter frame={f} start={b+15} dur={75} from={0} to={40} label="Rounds" x={645} y={380} color="#34d399" />
        </>
      );
    },
  },

  // ── 5: Fact Check + Macro ──
  {
    badge: "Phase 5-7 — Verify & Enrich",
    render: (b, f, fps) => (
      <>
        <Line frame={f} start={b} text="Spawning 3 SubAgents in parallel..." color="#6ec6ff" bold speed={2} />
        <Line frame={f} start={b+10} text="" />
        <Line frame={f} start={b+12} text="  [FactChecker]   Extracting 24 salary/market claims..." color="#22d3ee" speed={2.5} />
        <Line frame={f} start={b+22} text="  [FactChecker]   Verifying against Tavily search results..." color="#22d3ee" speed={2.5} />
        <Line frame={f} start={b+35} text="  [MacroTrend]    Analyzing 8 industry trends..." color="#a78bfa" speed={2.5} />
        <Line frame={f} start={b+45} text="  [MacroTrend]    AI industry CAGR, remote work adoption..." color="#a78bfa" speed={2.5} />
        <Line frame={f} start={b+55} text="  [SalaryBench]   Benchmarking 12 market data points..." color="#fbbf24" speed={2.5} />
        <Line frame={f} start={b+68} text="" />
        <Line frame={f} start={b+70} text={"  22/24 claims verified \u2713   2 adjusted"} color="#34d399" speed={2.5} />
        <Line frame={f} start={b+80} text={"  8 macro trends \u2713   12 salary benchmarks \u2713"} color="#34d399" speed={2.5} />
        <Line frame={f} start={b+92} text="" />
        <Line frame={f} start={b+94} text={"Enrichment complete \u2713"} color="#34d399" bold speed={2} />
        <AgentCard frame={f} fps={fps} name="FactChecker" role="Sonnet + Tavily" status={f < b+68 ? "running" : "done"} color="#22d3ee" start={b+5} y={44} />
        <AgentCard frame={f} fps={fps} name="MacroTrend" role="Sonnet + Web" status={f < b+72 ? "running" : "done"} color="#a78bfa" start={b+8} y={92} />
        <AgentCard frame={f} fps={fps} name="SalaryBench" role="Haiku" status={f < b+65 ? "running" : "done"} color="#fbbf24" start={b+11} y={140} />
      </>
    ),
  },

  // ── 6: Report Gen ──
  {
    badge: "Phase 8 — Report",
    render: (b, f, fps) => (
      <>
        <Line frame={f} start={b} text="python -m cc_layer.cli.pipeline_run --phase report" prefix="$ " prefixColor="#34d399" color="#a0e0a0" />
        <Line frame={f} start={b+15} text="" />
        <Line frame={f} start={b+17} text="[1/3] Normalizing SubAgent outputs..." color="#6ec6ff" speed={2} />
        <Line frame={f} start={b+27} text={"  multipath_result.json  \u2192  canonical \u2713"} color="#888" speed={3} />
        <Line frame={f} start={b+34} text={"  swarm_agents.json      \u2192  canonical \u2713"} color="#888" speed={3} />
        <Line frame={f} start={b+41} text={"  swarm/40 rounds        \u2192  canonical \u2713"} color="#888" speed={3} />
        <Line frame={f} start={b+50} text="[2/3] Validating..." color="#6ec6ff" speed={2} />
        <Line frame={f} start={b+56} text={"  Validation OK \u2713"} color="#34d399" speed={2} />
        <Line frame={f} start={b+63} text="[3/3] Generating HTML report..." color="#6ec6ff" speed={2} />
        <Bar frame={f} start={b+63} dur={25} label="report_html" color={ACCENT} />
        <Line frame={f} start={b+90} text="" />
        <Line frame={f} start={b+92} text={"report.html  3,800 lines  10 sections  self-contained \u2713"} color="#34d399" bold speed={2.5} />
        <Counter frame={f} start={b+5} dur={85} from={0} to={5} label="Paths" x={490} y={340} color="#fbbf24" />
        <Counter frame={f} start={b+5} dur={85} from={0} to={20} label="Scenarios" x={560} y={340} color="#34d399" />
        <Counter frame={f} start={b+5} dur={85} from={0} to={483} label="Swarm Acts" x={645} y={340} color="#a78bfa" />
        <Counter frame={f} start={b+5} dur={85} from={0} to={3800} label="HTML Lines" x={740} y={340} color="#6ec6ff" />
      </>
    ),
  },
];

/* ── Main composition ──────────────────────────────── */

export const TerminalDemo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  const idx = Math.min(Math.floor(frame / S), SCENES.length - 1);
  const scene = SCENES[idx];
  const base = idx * S;
  const rel = frame - base;

  const fadeIn = interpolate(rel, [0, 6], [0, 1], { extrapolateRight: "clamp" });

  // Background particles
  const particles = Array.from({ length: 30 }, (_, i) => ({
    x: (i * 137 + frame * 0.3) % width,
    y: (i * 89 + frame * 0.5) % height,
    size: 1 + (i % 3),
    opacity: 0.05 + 0.05 * Math.sin(frame * 0.05 + i),
  }));

  return (
    <AbsoluteFill style={{
      background: "linear-gradient(155deg, #080818 0%, #0f0f2d 40%, #12122a 100%)",
    }}>
      {particles.map((p, i) => (
        <div key={i} style={{
          position: "absolute", left: p.x, top: p.y,
          width: p.size, height: p.size, borderRadius: "50%",
          background: ACCENT, opacity: p.opacity,
        }} />
      ))}

      {/* Ambient glow */}
      <div style={{
        position: "absolute", top: "30%", left: "50%",
        width: 400, height: 400,
        background: `radial-gradient(circle, ${GLOW} 0%, transparent 70%)`,
        transform: "translate(-50%, -50%)",
        opacity: 0.3 + 0.1 * Math.sin(frame * 0.03),
      }} />

      {/* Terminal window */}
      <div style={{
        position: "absolute", top: 24, left: 24, right: 24, bottom: 24,
        background: "rgba(12, 12, 30, 0.92)", borderRadius: 10,
        border: `1px solid ${ACCENT}33`,
        boxShadow: `0 0 80px ${GLOW}, 0 25px 70px rgba(0,0,0,0.6)`,
        overflow: "hidden", opacity: fadeIn,
      }}>
        {/* Title bar */}
        <div style={{
          height: 32, background: "rgba(25,25,50,0.9)",
          display: "flex", alignItems: "center", padding: "0 12px", gap: 7,
          borderBottom: `1px solid ${ACCENT}22`,
        }}>
          <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#ff5f57" }} />
          <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#febc2e" }} />
          <div style={{ width: 11, height: 11, borderRadius: "50%", background: "#28c840" }} />
          <span style={{ color: "#555", fontSize: 11, fontFamily: mono, marginLeft: 6 }}>
            MiroFish Career Simulator — Claude Code SubAgents
          </span>
        </div>

        {/* Content */}
        <div style={{ padding: "12px 16px", position: "relative", height: "calc(100% - 32px)" }}>
          <Phase text={scene.badge} start={base} frame={frame} fps={fps} />
          {scene.render(base, frame, fps)}
        </div>
      </div>

      {/* Scene indicators */}
      <div style={{
        position: "absolute", bottom: 6, left: 0, right: 0,
        display: "flex", justifyContent: "center", gap: 5,
      }}>
        {SCENES.map((_, i) => (
          <div key={i} style={{
            width: i === idx ? 22 : 7, height: 3, borderRadius: 2,
            background: i === idx ? ACCENT : i < idx ? "#4f46e5" : "#222",
          }} />
        ))}
      </div>
    </AbsoluteFill>
  );
};
