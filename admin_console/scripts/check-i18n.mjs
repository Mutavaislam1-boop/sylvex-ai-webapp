// Fails when a UI string has no Russian translation: every literal
// t("...") key, plus the strings the code translates dynamically
// (menu labels, roles, channels, statuses, tools, server error messages).
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const src = new URL("../src/", import.meta.url).pathname;
const files = [...readdirSync(src).map((f) => join(src, f)), ...readdirSync(join(src, "pages")).map((f) => join(src, "pages", f))]
  .filter((f) => /\.tsx?$/.test(f) && !f.endsWith("i18n_ru.ts"));
const ru = readFileSync(join(src, "i18n_ru.ts"), "utf8");
const have = new Set([...ru.matchAll(/^\s*"((?:[^"\\]|\\.)*)":/gm)].map((m) => JSON.parse(`"${m[1]}"`)));

const need = new Map();
const add = (key, where) => need.has(key) || need.set(key, where);
for (const file of files) {
  const code = readFileSync(file, "utf8");
  for (const m of code.matchAll(/\bt\(\s*"((?:[^"\\]|\\.)*)"/g)) add(JSON.parse(`"${m[1]}"`), file);
  // Dynamic keys: string values of the tables below are passed through t().
  const tables = [/label: "([^"]+)"/g, /^\s+[a-z_]+: "([^"]+)",?$/gm];
  if (/Layout\.tsx$|Users\.tsx$/.test(file)) for (const m of code.matchAll(tables[0])) add(m[1], file);
  if (/api\.ts$/.test(file)) {
    const block = code.slice(code.indexOf("const MESSAGES"), code.indexOf("};", code.indexOf("const MESSAGES")));
    for (const m of block.matchAll(tables[1])) add(m[1], file);
  }
  if (/i18n\.tsx$/.test(file)) for (const m of code.matchAll(/(?:[a-z_]+): "([^"]+)"/g)) add(m[1], file);
  for (const m of code.matchAll(/const (?:MODES|STATUSES) = \[([^\]]+)\]/g))
    for (const v of m[1].split(",").map((x) => x.trim().replace(/^"|"$/g, "")).filter(Boolean)) add(v, file);
}
for (const s of ["completed", "active", "success", "ok", "published", "resolved", "failed", "error", "cancelled", "revoked", "banned",
  "expired", "queued", "processing", "running", "pending", "provider_processing", "suspended", "open", "draft",
  "low", "medium", "high", "critical", "website", "telegram", "monthly", "yearly", "unknown"]) add(s, "statuses");

const missing = [...need].filter(([k]) => !have.has(k));
if (missing.length) {
  console.error(`Missing Russian translations (${missing.length}):`);
  for (const [k, f] of missing) console.error(`  ${JSON.stringify(k)}  <- ${f.replace(src, "src/")}`);
  process.exit(1);
}
console.log(`i18n: ${need.size} strings, all translated to Russian.`);
