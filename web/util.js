// 通用小工具：请求、转义、发音、提示、生词缓存

export const api = {
  async get(url) {
    const r = await fetch(url);
    return r.json();
  },
  async post(url, body) {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return r.json();
  },
  async del(url) {
    const r = await fetch(url, { method: "DELETE" });
    return r.json();
  },
};

const cache = {};
export async function getJSON(url) {
  if (!cache[url]) cache[url] = fetch(url).then((r) => r.json());
  return cache[url];
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// 发音：用系统自带的英语语音（离线可用）
let voice = null;
function pickVoice() {
  const vs = speechSynthesis.getVoices();
  voice = vs.find((v) => /en-GB/.test(v.lang) && /Daniel|Serena|Kate|Arthur|Martha/.test(v.name))
    || vs.find((v) => /en-GB/.test(v.lang))
    || vs.find((v) => /en-US/.test(v.lang) && /Samantha|Alex|Ava|Allison/.test(v.name))
    || vs.find((v) => /^en/.test(v.lang)) || null;
}
if ("speechSynthesis" in window) {
  pickVoice();
  speechSynthesis.onvoiceschanged = pickVoice;
}
export function speak(text, rate = 0.92) {
  if (!("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  if (voice) u.voice = voice;
  u.lang = voice ? voice.lang : "en-GB";
  u.rate = rate;
  speechSynthesis.speak(u);
}

let toastTimer;
export function toast(msg, action) {
  const t = document.getElementById("toast");
  t.innerHTML = `<span>${esc(msg)}</span>${action ? `<button>${esc(action.label)}</button>` : ""}`;
  t.hidden = false;
  if (action) t.querySelector("button").onclick = () => { t.hidden = true; action.run(); };
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), action ? 5000 : 2200);
}

// 生词列表缓存（用于在文章里标出生词）
let vocabPromise = null;
export function vocabCache() {
  if (!vocabPromise) vocabPromise = api.get("/api/vocab").then((r) => r.items);
  return vocabPromise;
}
export async function refreshVocab() {
  vocabPromise = null;
  return vocabCache();
}

export async function refreshBadge() {
  const s = await api.get("/api/stats");
  for (const id of ["due-badge", "due-badge-m"]) {
    const b = document.getElementById(id);
    b.hidden = !s.due;
    b.textContent = s.due > 99 ? "99+" : s.due;
  }
  return s;
}

// 本地存储（只用来记住草稿、上次位置这类小事，读写失败也没关系）
export const local = {
  get(k, d = null) {
    try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; }
  },
  set(k, v) {
    try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* 忽略 */ }
  },
  del(k) {
    try { localStorage.removeItem(k); } catch { /* 忽略 */ }
  },
};

export function fmtTime(sec) {
  const m = Math.floor(sec / 60), s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function ago(ts) {
  const d = (Date.now() / 1000 - ts);
  if (d < 60) return "刚刚";
  if (d < 3600) return `${Math.floor(d / 60)} 分钟前`;
  if (d < 86400) return `${Math.floor(d / 3600)} 小时前`;
  if (d < 86400 * 30) return `${Math.floor(d / 86400)} 天前`;
  return new Date(ts * 1000).toLocaleDateString("zh-CN");
}
