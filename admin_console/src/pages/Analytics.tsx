import { useState } from "react";
import { post } from "../api";
import { t } from "../i18n";
import { Empty, ErrorNotice, fmtNum, Kpi, Loading, useAsync } from "../ui";
import { DayBars, Period, PeriodPicker, RankBars } from "../charts";

// How SYLVEX is used (services/usage_analytics.py): sections, models,
// tools / styles / templates / references, the funnel, returns and
// transitions - per platform, never mixed. Events carry ids only; no
// prompts or files are collected for these numbers.

type Section = { key: string; opens: number; visitors: number; avg_seconds: number | null };
type Platform = { key: string; opens: number | null; visitors: number | null; generations: number; generation_users: number };
type Model = { key: string; users: number; runs: number; completed: number; failed: number; share: number; selected: number };
type Tool = { key: string; label?: string; kind: string; opens: number; selects: number; generations: number };
type Data = {
  sections: Section[]; platforms: Platform[]; days: { day: string; opens: number; visitors: number }[];
  models: Model[]; tools: Tool[]; funnel: { key: string; unit: "visitors" | "users"; count: number }[];
  returning: { visitors: number; returning: number }; transitions: { from: string; to: string; count: number }[];
};

const SECTION_LABELS: Record<string, string> = {
  home: "Home",
  pro_studio: "Pro Studio",
  grid: "Grid Mode",
  edit: "Edit",
  media: "Media",
  tools: "All Tools",
  shop: "Shop",
  music: "Music",
  voice: "Voice",
  profile: "Profile",
  settings: "Settings",
  history: "History",
  community: "Community",
  assistant: "Assistant",
  docs: "Docs",
  auth: "Sign-in",
};
const PLATFORM_LABELS: Record<string, string> = {
  website: "Website",
  browser_miniapp: "Browser Mini App",
  telegram_miniapp: "Telegram Mini App",
  bot: "Telegram bot",
};
const KIND_LABELS: Record<string, string> = {
  tool: "Tool",
  block: "Media block",
  style: "Style",
  template: "Template",
  reference: "Reference",
  effect: "Effect",
  object: "Object",
};
const FUNNEL_LABELS: Record<string, string> = {
  opened: "Opened a section",
  chose: "Chose a model, tool or reference",
  started: "Started a generation",
  result: "Got a result",
  downloaded: "Downloaded",
};
const KIND_TABS = ["", "tool", "style", "template", "reference"];
const sectionName = (k: string) => t(SECTION_LABELS[k] || k);
const platformName = (k: string) => (k ? t(PLATFORM_LABELS[k] || k) : t("Not recorded"));
const secs = (n: number | null) => (n == null ? "—" : n < 90 ? `${fmtNum(Math.round(n))} ${t("s")}` : `${fmtNum(Math.round(n / 6) / 10)} ${t("min")}`);

export default function Analytics() {
  const [period, setPeriod] = useState<Period>({ days: 7 });
  const [platform, setPlatform] = useState("");
  const [section, setSection] = useState("");
  const [model, setModel] = useState("");
  const [item, setItem] = useState("");
  const [kind, setKind] = useState("");
  const query = { ...period, platform, section, model, item };
  const { data, error, loading, reload } = useAsync(() => post<Data>("/api/admin/analytics", query), [JSON.stringify(query)]);

  const filters = (
    <div className="card stack" style={{ gap: 10 }}>
      <PeriodPicker value={period} onChange={setPeriod} />
      <div className="row">
        <select value={platform} onChange={(e) => setPlatform(e.target.value)}>
          <option value="">{t("All platforms")}</option>
          {Object.keys(PLATFORM_LABELS).map((k) => <option key={k} value={k}>{platformName(k)}</option>)}
        </select>
        <select value={section} onChange={(e) => setSection(e.target.value)}>
          <option value="">{t("All sections")}</option>
          {Object.keys(SECTION_LABELS).map((k) => <option key={k} value={k}>{sectionName(k)}</option>)}
        </select>
        <select value={model} onChange={(e) => setModel(e.target.value)}>
          <option value="">{t("All models")}</option>
          {(data?.models || []).filter((m) => m.key !== "—").map((m) => <option key={m.key} value={m.key}>{m.key}</option>)}
        </select>
        <select value={item} onChange={(e) => setItem(e.target.value)}>
          <option value="">{t("All tools")}</option>
          {(data?.tools || []).map((x) => <option key={x.key} value={x.key}>{x.label || x.key}</option>)}
        </select>
      </div>
    </div>
  );
  if (error) return <div className="stack">{filters}<ErrorNotice message={error} onRetry={reload} /></div>;
  if (loading && !data) return <div className="stack">{filters}<Loading /></div>;
  if (!data) return null;

  const opens = data.sections.reduce((n, s) => n + s.opens, 0);
  const first = data.funnel[0]?.count || 0;
  const tools = data.tools.filter((x) => !kind || x.kind === kind || (kind === "tool" && x.kind === "block"));
  const bot = platform === "bot";
  return (
    <div className="stack">
      {filters}
      <div className="muted small">{t("Only ids and counts are collected for these numbers: no prompts, files or personal content.")}</div>
      <div className="grid kpis">
        <Kpi label={t("Visitors")} value={bot ? "—" : fmtNum(data.returning.visitors)} sub={t("unique, by device")} />
        <Kpi label={t("Section opens")} value={bot ? "—" : fmtNum(opens)} />
        <Kpi label={t("Returning visitors")} value={data.returning.visitors ? `${Math.round((data.returning.returning / data.returning.visitors) * 100)}%` : "—"}
          sub={t("came back on another day: {n}", { n: fmtNum(data.returning.returning) })} />
        <Kpi label={t("Generations")} value={fmtNum(data.platforms.reduce((n, p) => n + p.generations, 0))} />
      </div>
      <div className="card stack">
        <h3>{t("By platform")}</h3>
        <div className="table-wrap"><table>
          <thead><tr><th>{t("Platform")}</th><th className="right">{t("Section opens")}</th><th className="right">{t("Visitors")}</th><th className="right">{t("Generations")}</th><th className="right">{t("Users who generated")}</th></tr></thead>
          <tbody>{data.platforms.length ? data.platforms.map((p) => (
            <tr key={p.key}><td>{platformName(p.key)}</td><td className="right">{p.opens == null ? "—" : fmtNum(p.opens)}</td>
              <td className="right">{p.visitors == null ? "—" : fmtNum(p.visitors)}</td><td className="right">{fmtNum(p.generations)}</td><td className="right">{fmtNum(p.generation_users)}</td></tr>
          )) : <tr><td colSpan={5} className="muted">{t("No data for this period")}</td></tr>}</tbody>
        </table></div>
        <div className="muted small">{t("The Telegram bot has no sections: only its generations are counted.")}</div>
      </div>
      <div className="card stack">
        <h3>{t("Section opens per day")}</h3>
        <DayBars days={data.days} series={[{ key: "opens", label: t("Section opens"), color: "var(--series-1)" }]} />
      </div>
      <div className="grid two">
        <div className="card stack"><h3>{t("Popular sections")}</h3>
          <RankBars rows={data.sections.map((s) => ({ key: s.key, label: sectionName(s.key), value: s.opens,
            note: `${t("{n} visitors", { n: fmtNum(s.visitors) })} · ${secs(s.avg_seconds)}` }))} /></div>
        <div className="card stack"><h3>{t("Funnel")}</h3>
          {data.funnel.map((f) => (
            <div key={f.key} className="bar-row rank-row">
              <span className="rank-label">{t(FUNNEL_LABELS[f.key] || f.key)}</span>
              <div className="bar-track"><div className="bar-fill series" style={{ width: `${first ? Math.min(100, (f.count / first) * 100) : 0}%` }} /></div>
              <span className="small right">{fmtNum(f.count)} <span className="muted">{f.unit === "users" ? t("users") : t("visitors")}</span></span>
            </div>
          ))}
          <div className="muted small">{t("Generation steps count signed-in users; the other steps count visitors (devices).")}</div>
        </div>
      </div>
      <div className="card stack">
        <h3>{t("AI models")}</h3>
        {data.models.length ? <div className="table-wrap"><table>
          <thead><tr><th>{t("Model")}</th><th className="right">{t("Users")}</th><th className="right">{t("Runs")}</th><th className="right">{t("Successful")}</th>
            <th className="right">{t("Errors")}</th><th className="right">{t("Share")}</th><th className="right">{t("Chosen in the picker")}</th></tr></thead>
          <tbody>{data.models.map((m) => (
            <tr key={m.key}><td>{m.key}</td><td className="right">{fmtNum(m.users)}</td><td className="right">{fmtNum(m.runs)}</td><td className="right">{fmtNum(m.completed)}</td>
              <td className="right">{fmtNum(m.failed)}</td><td className="right">{m.share}%</td><td className="right">{fmtNum(m.selected)}</td></tr>
          ))}</tbody>
        </table></div> : <Empty>{t("No data for this period")}</Empty>}
      </div>
      <div className="card stack">
        <h3>{t("Tools, styles, templates and references")}</h3>
        <div className="chips">{KIND_TABS.map((k) => (
          <button key={k} className={`chip ${kind === k ? "on" : ""}`} onClick={() => setKind(k)}>{k ? t(KIND_LABELS[k]) : t("All")}</button>
        ))}</div>
        {tools.length ? <div className="table-wrap"><table>
          <thead><tr><th>{t("Name")}</th><th>{t("Kind")}</th><th className="right">{t("Opened")}</th><th className="right">{t("Chosen")}</th><th className="right">{t("Generations")}</th></tr></thead>
          <tbody>{tools.map((x) => (
            <tr key={x.key}><td className="small">{x.label ? <>{x.label} <span className="muted mono">{x.key}</span></> : <span className="mono">{x.key}</span>}</td><td className="small">{t(KIND_LABELS[x.kind] || x.kind)}</td><td className="right">{fmtNum(x.opens)}</td>
              <td className="right">{fmtNum(x.selects)}</td><td className="right">{fmtNum(x.generations)}</td></tr>
          ))}</tbody>
        </table></div> : <Empty>{t("No data for this period")}</Empty>}
      </div>
      <div className="card stack">
        <h3>{t("Moves between sections")}</h3>
        {data.transitions.length ? <RankBars rows={data.transitions.map((x) => ({ key: `${x.from}>${x.to}`, label: `${sectionName(x.from)} → ${sectionName(x.to)}`, value: x.count }))} />
          : <div className="muted small">{t("No data for this period")}</div>}
      </div>
    </div>
  );
}
