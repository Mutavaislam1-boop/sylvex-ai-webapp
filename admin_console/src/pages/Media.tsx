import { useEffect, useState } from "react";
import { ApiError, errorText, post } from "../api";
import { useApp } from "../state";
import { getLang, t } from "../i18n";
import { ConfirmAction, Empty, ErrorNotice, fmtDate, fmtNum, Loading, Pager, StatusBadge, useAsync } from "../ui";
import LegacyReferences from "./Content";

// Media constructor: AI tools, video templates, photos and references and
// styles admins build here and users run on the website and in the Mini
// Apps (services/media_blocks.py). Models and their limits come from the
// live capability registry; the price is always the central tariff's.

type BlockType = "tool" | "video" | "photo" | "style";
type Field = { key: string; label: string; purpose: string; accept: "image" | "video"; required: boolean; input: "reference" | "start_image" };
type Config = {
  generation: "image" | "video"; ref_mode: "" | "A" | "B" | "C"; fields: Field[]; placements: string[];
  aspect: string; duration: number; resolution: string; extra_references: string[];
};
type Block = {
  id?: number; block_type: BlockType; name: string; description: string; prompt: string; model: string;
  preview_url: string; source_url: string; published?: boolean; sort_order: number; config: Config;
  created_at?: string; updated_at?: string;
};
type Model = {
  id: string; label: string; generation: "image" | "video"; provider: string; accepts_images: boolean; max_images: number;
  accepts_video: boolean; start_frame: boolean; ratios: string[]; durations: number[]; resolutions: string[]; available: boolean | null;
};
type Placement = { id: string; en: string; ru: string; types: BlockType[] };
type Catalog = { models: Model[]; placements: Placement[]; max_fields: number };
type Problem = { code: string; detail: string };
type Check = { cost: number | null; problems: Problem[] };

const LIMIT = 24;
const MAX_UPLOAD = 11 * 1024 * 1024;
const TABS: { key: BlockType | "legacy"; label: string }[] = [
  { key: "tool", label: "AI tools" },
  { key: "video", label: "Video templates" },
  { key: "photo", label: "Photos & references" },
  { key: "style", label: "Styles" },
  { key: "legacy", label: "Older references" },
];
const TYPE_HINT: Record<string, string> = {
  tool: "A tool runs one model with the prompt you write on what the user uploads.",
  video: "A video template repeats your reference video with the user's characters or objects.",
  photo: "A photo reference turns the user's photo into a picture like yours.",
  style: "A style applies your look (prompt and example images) to what the user uploads.",
};
const REF_MODE_CARDS: { key: "A" | "B" | "C"; title: string; text: string }[] = [
  { key: "A", title: "Mode A · Image as reference", text: "Your image goes to the model as a real reference; the prompt is optional." },
  { key: "B", title: "Mode B · Prompt only", text: "Your image only illustrates the block; the prompt alone drives the result." },
  { key: "C", title: "Mode C · Image + prompt", text: "Your image goes to the model together with the prompt." },
];
const PROBLEMS: Record<string, string> = {
  name_required: "Give the block a name.",
  cover_required: "Upload a cover (banner).",
  model_required: "Choose a model.",
  model_unknown: "This model is not in the catalog any more.",
  model_wrong_type: "The model does not make this kind of result.",
  field_label_required: "Every upload field needs a name.",
  prompt_required: "Write the prompt.",
  upload_field_required: "Add at least one required upload field for the user.",
  reference_image_required: "This mode needs your reference image.",
  reference_video_required: "Upload the reference video.",
  model_no_video_input: "The model does not accept a video.",
  model_no_image_input: "The model does not accept images.",
  too_many_images: "More images than the model accepts.",
  model_no_start_frame: "The model has no start frame input.",
  placement_required: "Choose where to publish the block.",
  model_disabled: "This model is turned off in Models. Choose another one or turn it back on.",
};

const DEFAULT_PLACEMENT = { tool: "ai_tools", video: "video_styles", photo: "photo_references", style: "image_styles" };
const emptyConfig = (type: BlockType): Config => ({
  generation: type === "video" ? "video" : "image", ref_mode: type === "photo" || type === "style" ? "C" : "",
  fields: [{ key: "photo", label: "", purpose: "", accept: "image", required: true, input: "reference" }],
  placements: [DEFAULT_PLACEMENT[type]], aspect: "", duration: 0, resolution: "", extra_references: [],
});
const emptyBlock = (type: BlockType): Block => ({
  block_type: type, name: "", description: "", prompt: "", model: "", preview_url: "", source_url: "", sort_order: 0, config: emptyConfig(type),
});
const isVideoUrl = (url: string) => /\.(mp4|webm|mov)(\?|$)/i.test(url);
const placementName = (p: Placement) => (getLang() === "ru" ? p.ru : p.en);

function readBase64(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.onerror = () => reject(new Error(t("Could not read the file.")));
    reader.readAsDataURL(file);
  });
}

async function uploadMedia(file: File, slot: "preview" | "source") {
  if (file.size > MAX_UPLOAD) throw new Error(t("File is too large for the console (max 11 MB). Use the support bot for larger media."));
  const res = await post<{ url: string }>("/api/admin/references/upload-media", { content_base64: await readBase64(file), content_type: file.type, slot });
  return res.url;
}

function Thumb({ url, size = 72 }: { url: string; size?: number }) {
  const style = { width: size, height: size, objectFit: "cover" as const, borderRadius: 8, background: "var(--surface-2)" };
  if (!url) return <div style={{ ...style, display: "grid", placeItems: "center" }} className="muted small">—</div>;
  return isVideoUrl(url) ? <video src={url} muted playsInline style={style} /> : <img src={url} alt="" style={style} />;
}

/** One upload slot for the admin's own media (cover, source, extra refs). */
function MediaSlot({ label, hint, url, accept, slot, onChange }: {
  label: string; hint?: string; url: string; accept: string; slot: "preview" | "source"; onChange: (url: string) => void;
}) {
  const { toast } = useApp();
  const [busy, setBusy] = useState(false);
  const pick = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    try {
      onChange(await uploadMedia(file, slot));
    } catch (e) {
      toast(errorText(e), true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="media-slot">
      <Thumb url={url} />
      <div className="stack" style={{ gap: 4, flex: 1, minWidth: 0 }}>
        <b className="small">{label}</b>
        {hint && <span className="muted small">{hint}</span>}
        <div className="row">
          <label className="btn small">{busy ? <span className="spinner" /> : url ? t("Replace") : t("Upload")}
            <input type="file" accept={accept} hidden onChange={(e) => pick(e.target.files?.[0])} />
          </label>
          {url && <button className="btn small ghost" onClick={() => onChange("")}>{t("Remove")}</button>}
        </div>
      </div>
    </div>
  );
}

/** The block as users will see it in the catalog and when they open it. */
function BlockPreview({ block, cost }: { block: Block; cost: number | null }) {
  const cover = block.preview_url;
  const video = block.block_type === "video" && block.source_url;
  return (
    <div className="block-preview">
      <div className="bp-card">
        <div className="bp-media">
          {video ? <video src={block.source_url} poster={cover || undefined} muted autoPlay loop playsInline />
            : cover ? (isVideoUrl(cover) ? <video src={cover} muted autoPlay loop playsInline /> : <img src={cover} alt="" />)
              : <div className="bp-empty">{t("Cover")}</div>}
          {cost != null && <span className="bp-cost">⚡ {fmtNum(cost)}</span>}
        </div>
        <div className="bp-title">{block.name || t("Block name")}</div>
        {block.description && <div className="bp-desc">{block.description}</div>}
      </div>
      <div className="bp-run">
        {block.config.fields.map((f) => (
          <div key={f.key} className="bp-drop">
            <span className="bp-plus">+</span>
            <span><b>{f.label || t("Upload field")}</b>{f.required && <span className="bp-req"> *</span>}
              <span className="bp-sub">{f.purpose || (f.accept === "video" ? t("Video") : t("Photo"))}</span></span>
          </div>
        ))}
        <button className="bp-go" disabled>{t("Generate")}{cost != null ? ` · ⚡ ${fmtNum(cost)}` : ""}</button>
      </div>
    </div>
  );
}

function FieldBuilder({ fields, max, generation, model, onChange }: {
  fields: Field[]; max: number; generation: string; model?: Model; onChange: (f: Field[]) => void;
}) {
  const set = (i: number, patch: Partial<Field>) => onChange(fields.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  const move = (i: number, d: number) => {
    const next = [...fields];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    onChange(next);
  };
  const add = (patch: Partial<Field>) => onChange([...fields, {
    key: `file_${Date.now().toString(36).slice(-4)}`, label: "", purpose: "", accept: "image", required: true, input: "reference", ...patch,
  }]);
  const characters = fields.filter((f) => f.accept === "image").length;
  return (
    <div className="stack">
      {fields.map((f, i) => (
        <div key={f.key} className="field-row">
          <div className="field-row-head">
            <span className="badge">{i + 1}</span>
            <input value={f.label} placeholder={t("Field name the user sees, e.g. “Your photo”")} onChange={(e) => set(i, { label: e.target.value })} />
            <button className="btn small ghost" disabled={i === 0} onClick={() => move(i, -1)} aria-label={t("Move up")}>↑</button>
            <button className="btn small ghost" disabled={i === fields.length - 1} onClick={() => move(i, 1)} aria-label={t("Move down")}>↓</button>
            <button className="btn small ghost danger" onClick={() => onChange(fields.filter((_, j) => j !== i))} aria-label={t("Remove")}>✕</button>
          </div>
          <div className="field-row-body">
            <input value={f.purpose} placeholder={t("Purpose: what to upload, e.g. “A clear face photo”")} onChange={(e) => set(i, { purpose: e.target.value })} />
            <select value={f.accept} onChange={(e) => set(i, { accept: e.target.value as Field["accept"] })}>
              <option value="image">{t("Photo")}</option>
              <option value="video" disabled={!!model && !model.accepts_video}>{t("Video")}</option>
            </select>
            {generation === "video" && (
              <select value={f.input} onChange={(e) => set(i, { input: e.target.value as Field["input"] })}>
                <option value="reference">{t("Model input: reference")}</option>
                <option value="start_image" disabled={!!model && !model.start_frame}>{t("Model input: start frame")}</option>
              </select>
            )}
            <label className="row small"><input type="checkbox" checked={f.required} onChange={(e) => set(i, { required: e.target.checked })} />{t("Required")}</label>
          </div>
        </div>
      ))}
      <div className="row">
        <button className="btn small" disabled={fields.length >= max} onClick={() => add({})}>+ {t("Photo field")}</button>
        {model?.accepts_video && <button className="btn small" disabled={fields.length >= max} onClick={() => add({ accept: "video" })}>+ {t("Video field")}</button>}
        {generation === "video" && (
          <button className="btn small" disabled={fields.length >= max} onClick={() => add({
            key: `character_${characters + 1}`, label: t("Character {n}", { n: characters + 1 }), purpose: t("Photo of who replaces character {n}", { n: characters + 1 }),
          })}>+ {t("Replaceable character")}</button>
        )}
        <span className="muted small">{t("{n} of {max} fields", { n: fields.length, max })}</span>
      </div>
    </div>
  );
}

function ModelInfo({ model }: { model: Model }) {
  const facts = [
    model.accepts_images ? t("up to {n} images", { n: model.max_images }) : t("no image input"),
    model.generation === "video" && (model.accepts_video ? t("accepts a video") : t("no video input")),
    model.start_frame && t("start frame"),
    model.ratios.length && model.ratios.join(" · "),
    model.durations.length && `${model.durations[0]}–${model.durations[model.durations.length - 1]} ${t("s")}`,
    model.resolutions.length && model.resolutions.join(" · "),
  ].filter(Boolean);
  return (
    <div className="row small">
      <span className={`badge ${model.available === false ? "bad" : model.available ? "good" : ""}`}>
        {model.available === false ? t("Provider not configured") : model.available ? t("Available") : t("No data on availability")}
      </span>
      <span className="muted">{facts.join(" · ")}</span>
    </div>
  );
}

function Editor({ initial, catalog, onClose, onSaved }: { initial: Block; catalog: Catalog; onClose: () => void; onSaved: (b: Block) => void }) {
  const { toast, can } = useApp();
  const [b, setB] = useState<Block>(initial);
  const [check, setCheck] = useState<Check | null>(null);
  const [busy, setBusy] = useState("");
  const [dirty, setDirty] = useState(false);
  const [confirm, setConfirm] = useState<"" | "unpublish" | "delete">("");
  const set = (patch: Partial<Block>) => { setDirty(true); setB((x) => ({ ...x, ...patch })); };
  const setConfig = (patch: Partial<Config>) => { setDirty(true); setB((x) => ({ ...x, config: { ...x.config, ...patch } })); };
  const type = b.block_type;
  const c = b.config;
  const models = catalog.models.filter((m) => m.generation === c.generation);
  const model = catalog.models.find((m) => m.id === b.model);
  const placements = catalog.placements.filter((p) => p.types.includes(type));
  const ownImages = ((type === "photo" || type === "style") && (c.ref_mode === "A" || c.ref_mode === "C") ? 1 : 0) + c.extra_references.length;
  const imageCount = ownImages + c.fields.filter((f) => f.accept === "image").length;

  // Price and readiness, recomputed by the server as the admin edits.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      post<Check>("/api/admin/media/check", b).then(setCheck).catch(() => setCheck(null));
    }, 350);
    return () => window.clearTimeout(timer);
  }, [b]);

  // `quiet`: saving on the way to publishing; the parent hears about the
  // block once it is published (a new block's editor reopens at its id).
  const save = async (quiet = false) => {
    setBusy("save");
    try {
      const res = b.id ? await post<{ item: Block }>("/api/admin/references/update", b) : await post<{ item: Block }>("/api/admin/references/create", b);
      setB(res.item);
      setDirty(false);
      if (!quiet) {
        toast(t("Draft saved"));
        onSaved(res.item);
      }
      return res.item;
    } catch (e) {
      toast(errorText(e), true);
      return null;
    } finally {
      setBusy("");
    }
  };
  const publish = async (published: boolean, reason = "") => {
    const saved = dirty || !b.id ? await save(true) : b;
    if (!saved?.id) return;
    setBusy("publish");
    try {
      await post("/api/admin/references/publish", { id: saved.id, published, reason });
      const next = { ...saved, published };
      setB(next);
      onSaved(next);
      toast(published ? t("Published: users see it now") : t("Unpublished"));
    } catch (e) {
      toast(e instanceof ApiError && e.code === "block_not_ready" ? t("Fix the problems below before publishing.") : errorText(e), true);
      onSaved(saved);
    } finally {
      setBusy("");
    }
  };
  const ready = check ? check.problems.length === 0 : false;
  const canPublish = can("content.publish");

  return (
    <div className="media-editor">
      <div className="stack">
        <div className="row between">
          <button className="btn small ghost" onClick={onClose}>← {t("All blocks")}</button>
          <div className="row">
            {b.id && <StatusBadge status={b.published ? "published" : "draft"} />}
            {dirty && <span className="muted small">{t("Unsaved changes")}</span>}
          </div>
        </div>

        <section className="card stack">
          <h3>{t("Basics")}</h3>
          <div className="muted small">{t(TYPE_HINT[type])}</div>
          <label className="field">{t("Name")}<input value={b.name} maxLength={200} onChange={(e) => set({ name: e.target.value })} /></label>
          <label className="field">{t("Description")}<textarea rows={2} value={b.description} maxLength={2000} onChange={(e) => set({ description: e.target.value })} /></label>
          <MediaSlot label={t("Cover (banner)")} hint={t("Shown on the block card in the catalog.")} url={b.preview_url} accept="image/*,video/*" slot="preview"
            onChange={(url) => set({ preview_url: url })} />
          <div className="field"><span>{t("Where to publish")}</span>
            <div className="chips">{placements.map((p) => {
              const on = c.placements.includes(p.id);
              return <button key={p.id} type="button" className={`chip ${on ? "on" : ""}`}
                onClick={() => setConfig({ placements: on ? c.placements.filter((x) => x !== p.id) : [...c.placements, p.id] })}>{placementName(p)}</button>;
            })}</div>
            <span className="muted small">{t("Shown on the website and in both Mini Apps (browser and Telegram).")}</span>
          </div>
          <label className="field" style={{ maxWidth: 160 }}>{t("Sort order")}<input type="number" value={b.sort_order} onChange={(e) => set({ sort_order: Number(e.target.value) || 0 })} /></label>
        </section>

        <section className="card stack">
          <h3>{t("Model")}</h3>
          {type === "tool" && (
            <div className="chips">{(["image", "video"] as const).map((g) => (
              <button key={g} className={`chip ${c.generation === g ? "on" : ""}`} onClick={() => { setConfig({ generation: g }); set({ model: "" }); }}>
                {g === "image" ? t("Makes an image") : t("Makes a video")}</button>
            ))}</div>
          )}
          <label className="field">{t("Model")}
            <select value={b.model} onChange={(e) => set({ model: e.target.value })}>
              <option value="">{t("Choose a model")}</option>
              {models.map((m) => <option key={m.id} value={m.id}>{m.label}{m.available === false ? ` (${t("not configured")})` : ""}</option>)}
            </select>
          </label>
          {model && <ModelInfo model={model} />}
          {model && c.generation === "video" && (
            <div className="grid three-cols">
              <label className="field">{t("Aspect ratio")}<select value={c.aspect} onChange={(e) => setConfig({ aspect: e.target.value })}>
                <option value="">{t("Default")}</option>{model.ratios.map((r) => <option key={r}>{r}</option>)}</select></label>
              <label className="field">{t("Duration")}<select value={c.duration} onChange={(e) => setConfig({ duration: Number(e.target.value) })}>
                <option value={0}>{t("Default")}</option>{model.durations.map((d) => <option key={d} value={d}>{d} {t("s")}</option>)}</select></label>
              <label className="field">{t("Resolution")}<select value={c.resolution} onChange={(e) => setConfig({ resolution: e.target.value })}>
                <option value="">{t("Default")}</option>{model.resolutions.map((r) => <option key={r}>{r}</option>)}</select></label>
            </div>
          )}
          {model && c.generation === "image" && (
            <label className="field" style={{ maxWidth: 220 }}>{t("Aspect ratio")}<select value={c.aspect} onChange={(e) => setConfig({ aspect: e.target.value })}>
              <option value="">{t("Default")}</option>{["1:1", "3:4", "4:3", "9:16", "16:9", "2:3", "3:2"].map((r) => <option key={r}>{r}</option>)}</select></label>
          )}
        </section>

        <section className="card stack">
          <h3>{type === "video" ? t("Reference video and prompt") : t("Prompt and reference")}</h3>
          {(type === "photo" || type === "style") && (
            <div className="mode-cards">{REF_MODE_CARDS.map((m) => (
              <button key={m.key} className={`mode-card ${c.ref_mode === m.key ? "on" : ""}`} onClick={() => setConfig({ ref_mode: m.key })}>
                <b>{t(m.title)}</b><span>{t(m.text)}</span>
              </button>
            ))}</div>
          )}
          {(type === "photo" || type === "style") && c.ref_mode !== "B" && (
            <MediaSlot label={t("Your reference image")} hint={t("Goes to the model. Without it the cover is used.")} url={b.source_url} accept="image/*" slot="source"
              onChange={(url) => set({ source_url: url })} />
          )}
          {type === "video" && (
            <MediaSlot label={t("Reference video")} hint={t("The motion and scene users repeat with their characters.")} url={b.source_url} accept="video/*" slot="source"
              onChange={(url) => set({ source_url: url })} />
          )}
          <label className="field">{t("Prompt")}
            <textarea rows={4} value={b.prompt} maxLength={8000} onChange={(e) => set({ prompt: e.target.value })}
              placeholder={type === "photo" && c.ref_mode === "A" ? t("Optional in mode A: without it SYLVEX asks the model to recreate your reference with the user's photo.") : ""} />
          </label>
          {type === "style" && (
            <div className="field"><span>{t("Extra style references")}</span>
              <div className="row">
                {c.extra_references.map((u, i) => (
                  <div key={u} className="stack" style={{ gap: 4 }}><Thumb url={u} size={64} />
                    <button className="btn small ghost" onClick={() => setConfig({ extra_references: c.extra_references.filter((_, j) => j !== i) })}>{t("Remove")}</button></div>
                ))}
                {c.extra_references.length < 4 && <MediaSlot label={t("Add an example")} url="" accept="image/*" slot="source"
                  onChange={(url) => url && setConfig({ extra_references: [...c.extra_references, url] })} />}
              </div>
            </div>
          )}
        </section>

        <section className="card stack">
          <h3>{t("What the user uploads")}</h3>
          <div className="muted small">{model?.accepts_images
            ? t("Images going to the model: {n} of {max} it accepts (yours and the user's).", { n: imageCount, max: model.max_images })
            : t("Choose a model to see how many files it accepts.")}</div>
          <FieldBuilder fields={c.fields} max={catalog.max_fields} generation={c.generation} model={model} onChange={(fields) => setConfig({ fields })} />
        </section>
      </div>

      <aside className="media-side stack">
        <section className="card stack">
          <h3>{t("Preview")}</h3>
          <BlockPreview block={b} cost={check?.cost ?? null} />
        </section>
        <section className="card stack">
          <div className="price-line"><span className="muted small">{t("Price")}</span>
            <b>{check?.cost != null ? `⚡ ${fmtNum(check.cost)}` : b.model ? t("No price for this setup") : "—"}</b></div>
          <div className="muted small">{t("From the current tariff, same as in Pro Studio. It cannot be set by hand.")}</div>
          <h3>{t("Before publishing")}</h3>
          {!check ? <Loading /> : check.problems.length ? (
            <ul className="problems">{check.problems.map((p, i) => (
              <li key={i}>{t(PROBLEMS[p.code] || p.code)}{p.code === "too_many_images" ? ` (${t("max")} ${p.detail})` : ""}</li>
            ))}</ul>
          ) : <div className="notice good">{t("Everything is set. The block can be published.")}</div>}
          <div className="row">
            <button className="btn" disabled={!!busy || !b.name.trim()} onClick={() => save()}>{busy === "save" && <span className="spinner" />}{t("Save draft")}</button>
            {canPublish && (b.published
              ? <button className="btn" disabled={!!busy} onClick={() => setConfirm("unpublish")}>{t("Unpublish")}</button>
              : <button className="btn primary" disabled={!!busy || !ready} onClick={() => publish(true)}>{busy === "publish" && <span className="spinner" />}{t("Publish")}</button>)}
            {canPublish && b.id && <button className="btn danger" disabled={!!busy} onClick={() => setConfirm("delete")}>{t("Delete")}</button>}
          </div>
          {!canPublish && <div className="muted small">{t("Your role can save drafts; publishing needs the “Publish content” permission.")}</div>}
        </section>
      </aside>

      {confirm === "unpublish" && (
        <ConfirmAction title={t("Unpublish block")} confirmLabel={t("Unpublish")}
          description={<>{t("Users will stop seeing this block on the website and in the Mini Apps.")} <b>{b.name}</b></>}
          onConfirm={async (reason) => publish(false, reason)} onClose={() => setConfirm("")} />
      )}
      {confirm === "delete" && (
        <ConfirmAction title={t("Delete block")} confirmLabel={t("Delete")} danger
          description={<>{t("Permanently delete this block? Users will no longer see it.")} <b>{b.name}</b></>}
          onConfirm={async (reason) => {
            await post("/api/admin/references/delete", { id: b.id, reason });
            toast(t("Block deleted"));
            onClose();
          }} onClose={() => setConfirm("")} />
      )}
    </div>
  );
}

function BlockList({ type, onOpen }: { type: BlockType; onOpen: (id: number | "new") => void }) {
  const [state, setState] = useState<"" | "yes" | "no">("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useAsync(
    () => post<{ items: Block[]; total: number }>("/api/admin/references/list", {
      block_type: type, query: query.trim(), limit: LIMIT, offset, ...(state ? { published: state === "yes" } : {}),
    }),
    [type, state, query, offset],
  );
  return (
    <div className="stack">
      <div className="card row">
        <span className="muted small" style={{ flex: "1 1 260px" }}>{t(TYPE_HINT[type])}</span>
        <select value={state} onChange={(e) => { setState(e.target.value as typeof state); setOffset(0); }}>
          <option value="">{t("Any state")}</option><option value="yes">{t("Published")}</option><option value="no">{t("Drafts")}</option>
        </select>
        <input value={query} onChange={(e) => { setQuery(e.target.value); setOffset(0); }} placeholder={t("Search by name")} style={{ width: 180 }} />
        <button className="btn primary" onClick={() => onOpen("new")}>+ {t("New block")}</button>
      </div>
      {error ? <ErrorNotice message={error} onRetry={reload} /> : loading && !data ? <Loading /> : data && (data.items.length ? <>
        <div className="block-grid">{data.items.map((item) => (
          <button key={item.id} className="block-tile" onClick={() => onOpen(item.id!)}>
            <Thumb url={item.preview_url} size={200} />
            <div className="row between" style={{ marginTop: 8 }}><b className="cell-main">{item.name}</b><StatusBadge status={item.published ? "published" : "draft"} /></div>
            <div className="cell-sub">{item.model || t("No model")} · {t("{n} fields", { n: item.config?.fields?.length || 0 })}</div>
            <div className="cell-sub">{fmtDate(item.updated_at || item.created_at)}</div>
          </button>
        ))}</div>
        <Pager offset={offset} limit={LIMIT} total={data.total} onChange={setOffset} />
      </> : <Empty>{t("No blocks here yet. Create the first one.")}</Empty>)}
    </div>
  );
}

function OpenBlock({ type, id, catalog, onClose }: { type: BlockType; id: string; catalog: Catalog; onClose: () => void }) {
  const { go } = useApp();
  const { data, error, loading } = useAsync(async () => {
    if (id === "new") return emptyBlock(type);
    const res = await post<{ items: Block[] }>("/api/admin/references/list", { block_type: type, id: Number(id) || -1, limit: 1 });
    const found = res.items[0];
    if (!found) throw new Error(t("Block not found."));
    return { ...found, config: { ...emptyConfig(type), ...found.config } };
  }, [type, id]);
  if (error) return <ErrorNotice message={error} />;
  // Until the block of this address has loaded (not the previous one).
  const current = data && data.block_type === type && (id === "new" ? !data.id : String(data.id) === id);
  if (loading || !current) return <Loading />;
  return <Editor key={`${type}-${id}`} initial={data} catalog={catalog} onClose={onClose}
    onSaved={(b) => id === "new" && b.id && go(`content/${type}/${b.id}`)} />;
}

export default function Media({ route }: { route: string[] }) {
  const { go } = useApp();
  const [tabArg = "tool", openId = ""] = route;
  const tab = (TABS.some((x) => x.key === tabArg) ? tabArg : "tool") as BlockType | "legacy";
  const catalog = useAsync(() => post<Catalog>("/api/admin/media/catalog"), []);
  const body = tab === "legacy" ? <LegacyReferences />
    : !openId ? <BlockList key={tab} type={tab} onOpen={(id) => go(`content/${tab}/${id}`)} />
      : catalog.error ? <ErrorNotice message={catalog.error} onRetry={catalog.reload} />
        : !catalog.data ? <Loading />
          : <OpenBlock key={`${tab}-${openId}`} type={tab} id={openId} catalog={catalog.data} onClose={() => go(`content/${tab}`)} />;
  return (
    <div className="stack">
      <div className="tabs" style={{ marginBottom: 0 }}>
        {TABS.map((x) => (
          <button key={x.key} className={`tab ${tab === x.key ? "active" : ""}`} onClick={() => go(`content/${x.key}`)}>{t(x.label)}</button>
        ))}
      </div>
      {body}
    </div>
  );
}
