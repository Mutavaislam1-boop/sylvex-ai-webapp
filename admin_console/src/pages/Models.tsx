import { useState } from "react";
import { post } from "../api";
import { useApp } from "../state";
import { t } from "../i18n";
import { ConfirmAction, ErrorNotice, fmtDate, fmtNum, Loading, useAsync } from "../ui";
import { Period, PeriodPicker } from "../charts";

// AI models and providers (services/model_control.py): provider state from
// real data only ("No data" when nothing is known), and turning a model off
// for user generations without touching its settings or results.

type Provider = {
  key: string; configured: boolean | null; state: "working" | "errors" | "no_data" | "not_configured";
  runs: number; completed: number; failed: number; avg_seconds: number | null; cost_usd_estimate: number;
  models: string[]; last_success: string | null; last_error: string | null;
};
type Model = {
  id: string; label: string; category: string; provider: string; in_registry: boolean; disabled: boolean; reason: string;
  changed_at: string | null; runs: number; completed: number; failed: number; avg_seconds: number | null;
};

const STATE_LABELS: Record<string, string> = {
  working: "Working",
  errors: "Errors",
  no_data: "No data",
  not_configured: "Not configured",
};
const CATEGORY_LABELS: Record<string, string> = {
  image: "Images",
  video: "Video",
  music: "Music",
  voice: "Voice",
  text: "Text",
};
const tone = { working: "good", errors: "bad", no_data: "", not_configured: "warn" };
const secs = (n: number | null) => (n == null ? "—" : `${fmtNum(Math.round(n * 10) / 10)} ${t("s")}`);

export default function Models() {
  const { can, toast } = useApp();
  const [period, setPeriod] = useState<Period>({ days: 7 });
  const [category, setCategory] = useState("");
  const [query, setQuery] = useState("");
  const [toggling, setToggling] = useState<Model | null>(null);
  const { data, error, loading, reload } = useAsync(
    () => post<{ models: Model[]; providers: Provider[] }>("/api/admin/models/overview", period), [JSON.stringify(period)]);
  const canEdit = can("models.edit");

  if (error) return <ErrorNotice message={error} onRetry={reload} />;
  if (loading && !data) return <Loading />;
  if (!data) return null;
  const models = data.models.filter((m) => (!category || m.category === category)
    && (!query || `${m.id} ${m.label} ${m.provider}`.toLowerCase().includes(query.toLowerCase())));
  const off = data.models.filter((m) => m.disabled).length;

  return (
    <div className="stack">
      <div className="card"><PeriodPicker value={period} onChange={setPeriod} /></div>
      <div className="card stack">
        <h3>{t("Providers")}</h3>
        <div className="muted small">{t("State comes from real generations and from whether the provider's keys are set. Nothing is assumed: without data the state is “No data”.")}</div>
        <div className="table-wrap"><table>
          <thead><tr><th>{t("Provider")}</th><th>{t("State")}</th><th>{t("Keys")}</th><th className="right">{t("Successful")}</th><th className="right">{t("Errors")}</th>
            <th className="right">{t("Average time")}</th><th className="right">{t("AI costs (est.)")}</th><th>{t("Models used")}</th><th>{t("Last success / error")}</th></tr></thead>
          <tbody>{data.providers.map((p) => (
            <tr key={p.key}>
              <td>{p.key === "—" ? t("Not recorded") : p.key}</td>
              <td><span className={`badge ${tone[p.state]}`}>{t(STATE_LABELS[p.state])}</span></td>
              <td className="small">{p.configured == null ? t("No data") : p.configured ? t("set") : t("missing")}</td>
              <td className="right">{fmtNum(p.completed)}</td>
              <td className="right">{fmtNum(p.failed)}</td>
              <td className="right">{secs(p.avg_seconds)}</td>
              <td className="right">{p.cost_usd_estimate ? `$${p.cost_usd_estimate.toFixed(2)}` : "—"}</td>
              <td className="small" style={{ maxWidth: 260 }}>{p.models.join(", ") || "—"}</td>
              <td className="small">{fmtDate(p.last_success)}<div className="cell-sub">{fmtDate(p.last_error)}</div></td>
            </tr>
          ))}</tbody>
        </table></div>
        <div className="muted small">{t("AI costs are estimated from the tariff: credits = provider cost × 1.5 × 100.")}</div>
      </div>
      <div className="card stack">
        <div className="row">
          <h3 style={{ margin: 0 }}>{t("Models")}</h3>
          {off > 0 && <span className="badge warn">{t("Turned off: {n}", { n: off })}</span>}
          <span className="spacer" />
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">{t("All types")}</option>
            {Object.keys(CATEGORY_LABELS).map((k) => <option key={k} value={k}>{t(CATEGORY_LABELS[k])}</option>)}
          </select>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("Search by name")} style={{ width: 180 }} />
        </div>
        <div className="muted small">{t("A turned-off model keeps its settings and results; users see it as unavailable and cannot start new generations with it.")}</div>
        <div className="table-wrap"><table>
          <thead><tr><th>{t("Model")}</th><th>{t("Model type")}</th><th>{t("Provider")}</th><th className="right">{t("Runs")}</th><th className="right">{t("Errors")}</th>
            <th className="right">{t("Average time")}</th><th>{t("For users")}</th><th></th></tr></thead>
          <tbody>{models.map((m) => (
            <tr key={m.id}>
              <td><div className="cell-main">{m.label}</div><div className="cell-sub mono">{m.id}</div></td>
              <td className="small">{t(CATEGORY_LABELS[m.category] || m.category || "—")}</td>
              <td className="small">{m.provider || "—"}</td>
              <td className="right">{fmtNum(m.runs)}</td>
              <td className="right">{fmtNum(m.failed)}</td>
              <td className="right">{secs(m.avg_seconds)}</td>
              <td>{m.disabled
                ? <><span className="badge bad">{t("Turned off")}</span>{m.reason && <div className="cell-sub">{m.reason}</div>}</>
                : <span className="badge good">{t("On")}</span>}</td>
              <td className="right">{canEdit && (
                <button className={`btn small ${m.disabled ? "" : "danger"}`} onClick={() => setToggling(m)}>{m.disabled ? t("Turn on") : t("Turn off")}</button>
              )}</td>
            </tr>
          ))}</tbody>
        </table></div>
      </div>
      {toggling && (
        <ConfirmAction
          title={toggling.disabled ? t("Turn the model back on") : t("Turn the model off")}
          confirmLabel={toggling.disabled ? t("Turn on") : t("Turn off")}
          danger={!toggling.disabled}
          needReason={!toggling.disabled}
          description={<><b>{toggling.label}</b> · {toggling.disabled
            ? t("Users can choose it again; it uses its existing settings.")
            : t("Users will see it as unavailable and cannot start new generations with it. Settings, the integration and earlier results stay.")}</>}
          onConfirm={async (reason) => {
            await post("/api/admin/models/toggle", { model: toggling.id, disabled: !toggling.disabled, reason });
            toast(toggling.disabled ? t("Model turned on") : t("Model turned off"));
            reload();
          }}
          onClose={() => setToggling(null)}
        />
      )}
    </div>
  );
}
