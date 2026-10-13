import { useState } from "react";
import { errorText, post } from "../api";
import { useApp } from "../state";
import { ConfirmAction, Empty, ErrorNotice, fmtDate, fmtNum, Loading, Modal, Pager, StatusBadge, useAsync } from "../ui";

type Ref = {
  id: number; category: string; kind: "photo" | "video"; name: string; description: string; prompt: string; model: string;
  workflow: string; preview_url: string; source_url: string; published: boolean; sort_order: number; created_at: string; updated_at: string;
};
type Draft = Omit<Ref, "id" | "created_at" | "updated_at"> & { id?: number };

const LIMIT = 30;
// The JSON API body is capped at 16 MB; base64 adds a third.
const MAX_UPLOAD = 11 * 1024 * 1024;
const EMPTY: Draft = {
  category: "", kind: "photo", name: "", description: "", prompt: "", model: "", workflow: "",
  preview_url: "", source_url: "", published: false, sort_order: 0,
};

function readBase64(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.onerror = () => reject(new Error("Could not read the file."));
    reader.readAsDataURL(file);
  });
}

function Preview({ url, kind }: { url: string; kind: string }) {
  if (!url) return <div className="muted small">no media</div>;
  return kind === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(url)
    ? <video src={url} muted playsInline style={{ width: 72, height: 72, objectFit: "cover", borderRadius: 8 }} />
    : <img src={url} alt="" style={{ width: 72, height: 72, objectFit: "cover", borderRadius: 8 }} />;
}

function Editor({ initial, onClose, onSaved }: { initial: Draft; onClose: () => void; onSaved: () => void }) {
  const { toast } = useApp();
  const [d, setD] = useState<Draft>(initial);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));

  const upload = async (slot: "preview" | "source", file: File | undefined) => {
    if (!file) return;
    if (file.size > MAX_UPLOAD) { setError("File is too large for the console (max 11 MB). Use the support bot for larger media."); return; }
    setBusy(slot);
    setError("");
    try {
      const res = await post<{ url: string }>("/api/admin/references/upload-media", {
        content_base64: await readBase64(file), content_type: file.type, slot,
      });
      set(slot === "preview" ? "preview_url" : "source_url", res.url);
      toast("Uploaded");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  };
  const save = async () => {
    setBusy("save");
    setError("");
    try {
      if (d.id) await post("/api/admin/references/update", d);
      else await post("/api/admin/references/create", d);
      toast(d.id ? "Reference updated" : "Reference created");
      onSaved();
      onClose();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  };

  return (
    <Modal title={d.id ? `Edit reference #${d.id}` : "New reference"} onClose={onClose} actions={<>
      <button className="btn" onClick={onClose} disabled={!!busy}>Cancel</button>
      <button className="btn primary" disabled={!!busy || !d.name.trim() || !d.category.trim()} onClick={save}>
        {busy === "save" && <span className="spinner" />}Save
      </button>
    </>}>
      <div className="stack">
        <div className="grid two" style={{ gap: 10 }}>
          <label className="field">Name<input value={d.name} onChange={(e) => set("name", e.target.value)} /></label>
          <label className="field">Category<input value={d.category} onChange={(e) => set("category", e.target.value)} placeholder="e.g. portraits" /></label>
          <label className="field">Kind
            <select value={d.kind} onChange={(e) => set("kind", e.target.value as Draft["kind"])}><option value="photo">Photo</option><option value="video">Video</option></select>
          </label>
          <label className="field">Sort order<input type="number" value={d.sort_order} onChange={(e) => set("sort_order", Number(e.target.value) || 0)} /></label>
          <label className="field">Model<input value={d.model} onChange={(e) => set("model", e.target.value)} /></label>
          <label className="field">Workflow<input value={d.workflow} onChange={(e) => set("workflow", e.target.value)} /></label>
        </div>
        <label className="field">Description<textarea rows={2} value={d.description} onChange={(e) => set("description", e.target.value)} /></label>
        <label className="field">Prompt<textarea rows={4} value={d.prompt} onChange={(e) => set("prompt", e.target.value)} /></label>
        {(["preview", "source"] as const).map((slot) => {
          const field = slot === "preview" ? "preview_url" : "source_url";
          return (
            <div key={slot} className="row">
              <Preview url={d[field]} kind={d.kind} />
              <label className="field" style={{ flex: 1 }}>{slot === "preview" ? "Preview media URL" : "Source media URL"}
                <input value={d[field]} onChange={(e) => set(field, e.target.value)} />
              </label>
              <label className="btn small">
                {busy === slot ? <span className="spinner" /> : "Upload"}
                <input type="file" accept="image/*,video/*" hidden onChange={(e) => upload(slot, e.target.files?.[0])} />
              </label>
            </div>
          );
        })}
        <label className="row small"><input type="checkbox" checked={d.published} onChange={(e) => set("published", e.target.checked)} /> Published (visible to users)</label>
        {error && <div className="notice bad">{error}</div>}
      </div>
    </Modal>
  );
}

export default function Content() {
  const { toast } = useApp();
  const [kind, setKind] = useState("");
  const [published, setPublished] = useState<"" | "yes" | "no">("");
  const [category, setCategory] = useState("");
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<Draft | null>(null);
  const [deleting, setDeleting] = useState<Ref | null>(null);
  const { data, error, loading, reload } = useAsync(
    () => post<{ items: Ref[]; total: number }>("/api/admin/references/list", {
      kind, category: category.trim(), limit: LIMIT, offset,
      ...(published ? { published: published === "yes" } : {}),
    }),
    [kind, published, category, offset],
  );
  const togglePublish = async (r: Ref) => {
    try {
      await post("/api/admin/references/publish", { id: r.id, published: !r.published });
      toast(r.published ? "Unpublished" : "Published");
      reload();
    } catch (e) {
      toast(errorText(e), true);
    }
  };

  return (
    <div className="stack">
      <div className="card row">
        <select value={kind} onChange={(e) => { setKind(e.target.value); setOffset(0); }}>
          <option value="">Photo & video</option><option value="photo">Photo</option><option value="video">Video</option>
        </select>
        <select value={published} onChange={(e) => { setPublished(e.target.value as typeof published); setOffset(0); }}>
          <option value="">Any state</option><option value="yes">Published</option><option value="no">Drafts</option>
        </select>
        <input value={category} onChange={(e) => { setCategory(e.target.value); setOffset(0); }} placeholder="Category" style={{ width: 160 }} />
        <span className="spacer" />
        <button className="btn primary" onClick={() => setEditing({ ...EMPTY })}>+ New reference</button>
      </div>
      {error ? <ErrorNotice message={error} onRetry={reload} /> : loading && !data ? <Loading /> : data && (
        <div className="card">
          <div className="muted small" style={{ marginBottom: 8 }}>{fmtNum(data.total)} references — generation templates shown in the Mini App catalog.</div>
          {data.items.length ? (
            <div className="table-wrap"><table>
              <thead><tr><th></th><th>Name</th><th>Category</th><th>Model</th><th>State</th><th>Updated</th><th></th></tr></thead>
              <tbody>{data.items.map((r) => (
                <tr key={r.id}>
                  <td><Preview url={r.preview_url} kind={r.kind} /></td>
                  <td><div className="cell-main">{r.name}</div><div className="cell-sub">{r.kind} · #{r.id} · order {r.sort_order}</div></td>
                  <td>{r.category}</td>
                  <td className="small">{r.model || "—"}</td>
                  <td><StatusBadge status={r.published ? "published" : "draft"} /></td>
                  <td className="small">{fmtDate(r.updated_at || r.created_at)}</td>
                  <td className="right"><div className="row" style={{ justifyContent: "flex-end" }}>
                    <button className="btn small" onClick={() => togglePublish(r)}>{r.published ? "Unpublish" : "Publish"}</button>
                    <button className="btn small" onClick={() => setEditing({ ...r })}>Edit</button>
                    <button className="btn small danger" onClick={() => setDeleting(r)}>Delete</button>
                  </div></td>
                </tr>
              ))}</tbody>
            </table></div>
          ) : <Empty>No references yet.</Empty>}
          <Pager offset={offset} limit={LIMIT} total={data.total} onChange={setOffset} />
        </div>
      )}
      {editing && <Editor initial={editing} onClose={() => setEditing(null)} onSaved={reload} />}
      {deleting && (
        <ConfirmAction
          title="Delete reference"
          confirmLabel="Delete"
          danger
          needReason={false}
          description={<>Permanently delete <b>{deleting.name}</b>? Users will no longer see it.</>}
          onConfirm={async () => {
            await post("/api/admin/references/delete", { id: deleting.id });
            toast("Reference deleted");
            reload();
          }}
          onClose={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
