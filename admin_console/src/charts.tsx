import { useState } from "react";
import { t } from "./i18n";
import { fmtNum } from "./ui";

// Small charts for the console's reports: stacked bars per day and ranked
// bars. Thin marks, a 2px gap between stacked segments, one axis, a legend
// whenever there are two series, a hover tooltip and a table view.

export type Series = { key: string; label: string; color: string };
type Day = { day: string; [key: string]: number | string };

const shortDay = (day: string) => {
  const d = new Date(`${day}T00:00:00`);
  return Number.isNaN(d.getTime()) ? day : d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
};

export function DayBars({ days, series, height = 180 }: { days: Day[]; series: Series[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const totals = days.map((d) => series.reduce((sum, s) => sum + Number(d[s.key] || 0), 0));
  const top = Math.max(1, ...totals);
  return (
    <div className="chart">
      <div className="chart-head">
        {series.length > 1 && (
          <div className="chart-legend">{series.map((s) => (
            <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>
          ))}</div>
        )}
        <span className="spacer" />
        <button className="btn small ghost" onClick={() => setTable(!table)}>{table ? t("Chart") : t("Table")}</button>
      </div>
      {!days.length ? <div className="muted small">{t("No data for this period")}</div> : table ? (
        <div className="table-wrap"><table>
          <thead><tr><th>{t("Date")}</th>{series.map((s) => <th key={s.key} className="right">{s.label}</th>)}</tr></thead>
          <tbody>{days.map((d) => (
            <tr key={d.day}><td>{shortDay(String(d.day))}</td>{series.map((s) => <td key={s.key} className="right">{fmtNum(Number(d[s.key] || 0))}</td>)}</tr>
          ))}</tbody>
        </table></div>
      ) : (
        <div className="chart-plot" style={{ height }} onMouseLeave={() => setHover(null)}>
          <div className="chart-axis"><span>{fmtNum(top)}</span><span>0</span></div>
          <div className="chart-bars">
            {days.map((d, i) => (
              <div key={d.day} className={`chart-col ${hover === i ? "on" : ""}`} onMouseEnter={() => setHover(i)} onClick={() => setHover(i)}>
                <div className="chart-stack" style={{ height: `${(totals[i] / top) * 100}%` }}>
                  {[...series].reverse().map((s) => {
                    const v = Number(d[s.key] || 0);
                    return v ? <div key={s.key} className="chart-seg" style={{ flexGrow: v, background: s.color }} /> : null;
                  })}
                </div>
                {hover === i && (
                  <div className={`chart-tip ${i > days.length / 2 ? "left" : ""}`}>
                    <b>{shortDay(String(d.day))}</b>
                    {series.map((s) => <div key={s.key}><i style={{ background: s.color }} />{s.label}: {fmtNum(Number(d[s.key] || 0))}</div>)}
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="chart-x"><span>{shortDay(String(days[0].day))}</span><span>{shortDay(String(days[days.length - 1].day))}</span></div>
        </div>
      )}
    </div>
  );
}

export type Rank = { key: string; label: string; value: number; note?: string; tone?: "bad" };

/** Ranked horizontal bars: label, bar, value (one series, no legend). */
export function RankBars({ rows, format = fmtNum, empty }: { rows: Rank[]; format?: (n: number) => string; empty?: string }) {
  const top = Math.max(1, ...rows.map((r) => r.value));
  if (!rows.length) return <div className="muted small">{empty || t("No data for this period")}</div>;
  return (
    <div className="stack" style={{ gap: 8 }}>
      {rows.map((r) => (
        <div key={r.key} className="bar-row rank-row" title={`${r.label}: ${format(r.value)}${r.note ? ` · ${r.note}` : ""}`}>
          <span className="rank-label">{r.label}</span>
          <div className="bar-track"><div className={`bar-fill ${r.tone === "bad" ? "bad" : "series"}`} style={{ width: `${(r.value / top) * 100}%` }} /></div>
          <span className="small right">{format(r.value)}{r.note && <span className="muted"> · {r.note}</span>}</span>
        </div>
      ))}
    </div>
  );
}

export type Period = { days: number; from?: string; to?: string };

/** 24 hours / 7 / 30 days / a custom range, as the report endpoints take it. */
export function PeriodPicker({ value, onChange }: { value: Period; onChange: (p: Period) => void }) {
  const custom = !!value.from;
  return (
    <div className="row">
      <div className="chips">
        {[[1, "24 hours"], [7, "7 days"], [30, "30 days"]].map(([d, label]) => (
          <button key={d} type="button" className={`chip ${!custom && value.days === d ? "on" : ""}`} onClick={() => onChange({ days: Number(d) })}>{t(String(label))}</button>
        ))}
        <button type="button" className={`chip ${custom ? "on" : ""}`}
          onClick={() => onChange({ days: 0, from: value.from || new Date(Date.now() - 13 * 864e5).toISOString().slice(0, 10), to: value.to || new Date().toISOString().slice(0, 10) })}>
          {t("Custom")}</button>
      </div>
      {custom && <>
        <input type="date" value={value.from} onChange={(e) => onChange({ ...value, from: e.target.value })} />
        <span className="muted">—</span>
        <input type="date" value={value.to} onChange={(e) => onChange({ ...value, to: e.target.value })} />
      </>}
    </div>
  );
}
