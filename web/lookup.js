// 划词查询：点一个词查单词（顺便识别它所在的短语），拖选几个词查短语。
import { api, esc, speak, toast, vocabCache, refreshVocab, refreshBadge } from "./util.js";

const WORD_RE = /[A-Za-z]+(?:['’-][A-Za-z]+)*/g;
const box = document.getElementById("lookup");
const body = document.getElementById("lookup-body");
const card = box.querySelector(".lookup-card");
const selBtn = document.getElementById("select-btn");
const isTouch = matchMedia("(pointer: coarse)").matches;
const isNarrow = () => matchMedia("(max-width: 760px)").matches;
let current = null; // { el, sentence, source, link }
let seq = 0;

// ---------------------------------------------------------------- 工具

function textNodes(el) {
  const out = [];
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) out.push(w.currentNode);
  return out;
}

// 元素内第 start~end 个字符 -> Range
export function rangeFromOffsets(el, start, end) {
  const r = document.createRange();
  let pos = 0, setStart = false;
  for (const n of textNodes(el)) {
    const len = n.nodeValue.length;
    if (!setStart && start <= pos + len) { r.setStart(n, start - pos); setStart = true; }
    if (setStart && end <= pos + len) { r.setEnd(n, end - pos); return r; }
    pos += len;
  }
  return setStart ? r : null;
}

function offsetIn(el, node, off) {
  let pos = 0;
  for (const n of textNodes(el)) {
    if (n === node) return pos + off;
    pos += n.nodeValue.length;
  }
  return -1;
}

function caretAt(x, y) {
  if (document.caretRangeFromPoint) {
    const r = document.caretRangeFromPoint(x, y);
    return r && { node: r.startContainer, offset: r.startOffset };
  }
  if (document.caretPositionFromPoint) {
    const p = document.caretPositionFromPoint(x, y);
    return p && { node: p.offsetNode, offset: p.offset };
  }
  return null;
}

// 段落文字里，包含 pos 的句子 [start, end)
function sentenceAround(text, pos) {
  const re = /[.!?]["'’”)]*\s+(?=["'‘“(]?[A-Z0-9])/g;
  let start = 0, m;
  while ((m = re.exec(text))) {
    const end = m.index + m[0].length;
    if (end > pos) return [start, m.index + m[0].trimEnd().length];
    start = end;
  }
  return [start, text.length];
}

function setHighlight(name, ranges) {
  if (!window.CSS || !CSS.highlights) return;
  if (!ranges || !ranges.length) CSS.highlights.delete(name);
  else CSS.highlights.set(name, new Highlight(...ranges));
}

function sourceOf(el) {
  const holder = el.closest("[data-source]");
  return holder ? { source: holder.dataset.source, link: holder.dataset.link || location.hash } : { source: "", link: location.hash };
}

// ---------------------------------------------------------------- 打开 / 关闭

function place(rect) {
  box.hidden = false;
  if (isNarrow()) return;
  const W = 380, margin = 12;
  const cardH = Math.min(card.offsetHeight || 300, innerHeight * 0.72);
  let left = Math.min(Math.max(margin, rect.left + rect.width / 2 - W / 2), innerWidth - W - margin);
  let top = rect.bottom + 10;
  if (top + cardH > innerHeight - margin) top = Math.max(margin, rect.top - cardH - 10);
  card.style.left = left + "px";
  card.style.top = top + "px";
}

export function closeLookup() {
  box.hidden = true;
  setHighlight("lookup", null);
  current = null;
}

box.addEventListener("click", (e) => {
  if (e.target.closest("[data-close]")) closeLookup();
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeLookup(); });
document.addEventListener("mousedown", (e) => {
  if (box.hidden || isNarrow()) return;
  if (!card.contains(e.target) && !e.target.closest(".text-sel")) closeLookup();
});
addEventListener("hashchange", closeLookup);

// ---------------------------------------------------------------- 卡片内容

function trLines(t, max = 6) {
  return esc((t || "").split("\n").slice(0, max).join("\n"));
}

function addBtn(item) {
  const saved = item.saved;
  return `<button class="btn small add-btn ${saved ? "saved" : ""}" data-add='${esc(JSON.stringify({
    word: item.word, kind: item.kind, phonetic: item.phonetic || "", meaning: item.meaning || "", saved: saved || null,
  }))}'>${saved ? "✓ 已加入" : "＋ 生词本"}</button>`;
}

function render(res) {
  let h = "";
  const w = res.word;
  if (w) {
    h += `<div class="lk-head">
      <div style="flex:1;min-width:0">
        <div class="lk-word">${esc(w.word)}</div>
        <div class="lk-phon">${w.phonetic ? `/${esc(w.phonetic)}/` : ""}
          <button class="speak" data-speak="${esc(w.word)}" aria-label="发音"><svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9zm12.5 3a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4z"/></svg></button>
          ${/ielts/.test(w.tag || "") ? '<span class="chip accent">雅思</span>' : ""}
          ${w.collins ? `<span class="chip">柯林斯 ${"★".repeat(w.collins)}</span>` : ""}
        </div>
      </div>
      ${addBtn({ word: w.word, kind: "word", phonetic: w.phonetic, meaning: w.translation, saved: w.saved })}
    </div>
    ${w.form ? `<div class="lk-form">${esc(w.form.word)} → ${esc(w.word)}${w.form.note ? `（${esc(w.form.note.split("\n")[0])}）` : ""}</div>` : ""}
    <div class="lk-tr">${trLines(w.translation)}</div>`;
  }
  const phrases = res.phrase ? [res.phrase] : res.phrases || [];
  if (phrases.length) {
    h += `<div class="${w ? "lk-sec" : ""}">${w ? '<div class="lk-sec-title">这里的短语</div>' : ""}`;
    for (const p of phrases) {
      h += `<div class="lk-phrase"><div class="body">
          <div class="row" style="gap:6px"><span class="ph">${esc(p.phrase)}</span>
          <button class="speak" data-speak="${esc(p.phrase)}" aria-label="发音" style="width:24px;height:24px"><svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9zm12.5 3a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4z"/></svg></button></div>
          <div class="tr">${trLines(p.translation, 4)}</div>
          ${p.def ? `<div class="tr" style="margin-top:4px;color:var(--muted)">${esc(p.def)}</div>` : ""}
          ${p.unit && p.unit.length ? `<div style="margin-top:4px"><a class="small" href="#/phrases/${p.unit[0]}">短语书 第 ${p.unit.join("、")} 单元 →</a></div>` : ""}
        </div>${addBtn({ word: p.phrase, kind: "phrase", phonetic: p.phonetic, meaning: p.translation, saved: p.saved })}</div>`;
    }
    h += `</div>`;
  }
  if (res.words && res.words.length) {
    h += `<div class="lk-sec-title">没有找到这个短语，逐词意思：</div>`;
    for (const x of res.words) {
      h += `<div style="margin-bottom:8px"><b>${esc(x.word)}</b> <span class="muted small">${x.phonetic ? "/" + esc(x.phonetic) + "/" : ""}</span><div class="small">${trLines(x.translation, 2)}</div></div>`;
    }
  }
  if (!w && !phrases.length && !(res.words || []).length) {
    h += `<div class="muted">词典里没有找到「${esc(res.query)}」</div>`;
  }
  if (res.related && res.related.length) {
    h += `<div class="lk-sec"><div class="lk-sec-title">短语书里相关的短语</div><div class="lk-related">${res.related
      .map((r) => `<button data-q="${esc(r.phrase)}">${esc(r.key)}</button>`).join("")}</div></div>`;
  }
  if (w && w.definition) {
    h += `<details class="lk-more lk-sec"><summary>英文释义</summary><div class="lk-def">${trLines(w.definition, 8)}</div></details>`;
  }
  body.innerHTML = h;
}

body.addEventListener("click", async (e) => {
  const sp = e.target.closest("[data-speak]");
  if (sp) return speak(sp.dataset.speak);
  const q = e.target.closest("[data-q]");
  if (q) return lookup({ q: q.dataset.q }, null);
  const add = e.target.closest("[data-add]");
  if (add) {
    const item = JSON.parse(add.dataset.add);
    if (item.saved) {
      await api.del(`/api/vocab/${item.saved}`);
      item.saved = null;
      toast(`已从生词本删除「${item.word}」`);
    } else {
      const r = await api.post("/api/vocab", {
        word: item.word, kind: item.kind, phonetic: item.phonetic,
        meaning: (item.meaning || "").split("\n").slice(0, 4).join("\n"),
        sentence: current?.sentence || "", source: current?.source || "", source_link: current?.link || "",
      });
      item.saved = r.id;
      toast(`已加入生词本「${item.word}」`);
    }
    add.dataset.add = JSON.stringify(item);
    add.classList.toggle("saved", !!item.saved);
    add.textContent = item.saved ? "✓ 已加入" : "＋ 生词本";
    await refreshVocab();
    refreshBadge();
    document.dispatchEvent(new CustomEvent("vocab-changed"));
  }
});

// ---------------------------------------------------------------- 查询

export async function lookup(params, rect) {
  const my = ++seq;
  if (rect) {
    body.innerHTML = `<div class="muted">查询中…</div>`;
    place(rect);
  }
  const qs = new URLSearchParams(params).toString();
  const res = await api.get(`/api/lookup?${qs}`);
  if (my !== seq) return;
  render(res);
  if (rect) place(rect);
  else box.hidden = false;
  return res;
}

// 有工具栏的页面（做题页）只有选了"学习笔"才查词；其他页面一直可以查
const penActive = () => !document.body.dataset.tool || document.body.dataset.tool === "pen";

// 点击一个词
async function onTap(e) {
  if (!penActive()) return;
  const el = e.target.closest(".text-sel");
  if (!el || e.target.closest("a, button, input, textarea, select")) return;
  const sel = getSelection();
  if (sel && !sel.isCollapsed && sel.toString().trim()) return; // 有选区时由 onSelect 处理
  const c = caretAt(e.clientX, e.clientY);
  if (!c || c.node.nodeType !== 3 || !el.contains(c.node)) return;
  const text = el.textContent;
  const pos = offsetIn(el, c.node, c.offset);
  if (pos < 0) return;
  // 找到点中的词
  let word = null;
  for (const m of text.matchAll(WORD_RE)) {
    if (m.index <= pos && pos <= m.index + m[0].length) { word = m; break; }
    if (m.index > pos) break;
  }
  if (!word) return closeLookup();
  const [ss, se] = sentenceAround(text, word.index);
  const sentence = text.slice(ss, se);
  let index = 0;
  for (const m of sentence.matchAll(WORD_RE)) {
    if (ss + m.index >= word.index) break;
    index++;
  }
  const wordRange = rangeFromOffsets(el, word.index, word.index + word[0].length);
  setHighlight("lookup", wordRange ? [wordRange] : null);
  current = { el, sentence: sentence.trim(), ...sourceOf(el) };
  const res = await lookup({ q: word[0], sentence, index }, wordRange.getBoundingClientRect());
  // 识别到短语：把整个短语标出来
  const p = res && res.phrases && res.phrases[0];
  if (p && current && current.el === el) {
    const toks = [...sentence.matchAll(WORD_RE)];
    const a = toks[p.span[0]], b = toks[p.span[1] - 1];
    if (a && b) {
      const ranges = [];
      for (let i = p.span[0]; i < p.span[1]; i++) {
        const t = toks[i];
        // 隔开的短语（put the meeting off）只标短语本身的词
        if (i === p.span[0] || i === p.span[1] - 1 || p.key.split(" ").length >= p.span[1] - p.span[0]) {
          const r = rangeFromOffsets(el, ss + t.index, ss + t.index + t[0].length);
          if (r) ranges.push(r);
        }
      }
      setHighlight("lookup", ranges);
    }
  }
}

// 选中几个词
function selectionInfo() {
  const sel = getSelection();
  if (!sel || sel.isCollapsed) return null;
  const text = sel.toString().replace(/\s+/g, " ").trim();
  if (!text || text.length > 120) return null;
  const node = sel.anchorNode;
  const el = node && (node.nodeType === 3 ? node.parentElement : node).closest(".text-sel");
  if (!el) return null;
  return { text, el, range: sel.getRangeAt(0) };
}

async function lookupSelection(info) {
  const { text, el, range } = info;
  const full = el.textContent;
  const start = offsetIn(el, range.startContainer, range.startOffset);
  const [ss, se] = sentenceAround(full, Math.max(0, start));
  current = { el, sentence: full.slice(ss, se).trim(), ...sourceOf(el) };
  setHighlight("lookup", [range.cloneRange()]);
  const rect = range.getBoundingClientRect();
  getSelection().removeAllRanges();
  selBtn.hidden = true;
  const words = text.match(WORD_RE) || [];
  if (words.length === 1) {
    let index = 0;
    for (const m of full.slice(ss, se).matchAll(WORD_RE)) { if (ss + m.index >= start) break; index++; }
    await lookup({ q: words[0], sentence: full.slice(ss, se), index }, rect);
  } else {
    await lookup({ q: text }, rect);
  }
}

export function initLookup(root) {
  root.addEventListener("click", onTap);
  // 电脑：拖选松开鼠标就查
  root.addEventListener("mouseup", (e) => {
    if (isTouch || !penActive()) return;
    setTimeout(() => {
      const info = selectionInfo();
      if (info && (info.text.match(WORD_RE) || []).length >= 1 && /\s/.test(info.text)) lookupSelection(info);
    }, 10);
  });
  // 手机：长按选中后出现"查询所选"按钮
  document.addEventListener("selectionchange", () => {
    if (!isTouch) return;
    const info = penActive() ? selectionInfo() : null;
    if (!info) { selBtn.hidden = true; return; }
    selBtn.hidden = false;
    selBtn.style.left = "50%";
    selBtn.style.transform = "translateX(-50%)";
    selBtn.style.bottom = `calc(var(--tabbar-h) + 24px + env(safe-area-inset-bottom))`;
  });
  selBtn.addEventListener("click", () => {
    const info = selectionInfo();
    if (info) lookupSelection(info);
  });
}

// ---------------------------------------------------------------- 生词高亮

export async function highlightVocab(container) {
  if (!window.CSS || !CSS.highlights) return;
  const items = await vocabCache();
  if (!items.length) { CSS.highlights.delete("vocab"); return; }
  const pats = [];
  for (const v of items) {
    const w = v.word.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (v.kind === "phrase" || w.includes(" ")) pats.push(w.replace(/\s+/g, "\\s+"));
    else pats.push(`${w}(?:s|es|ed|d|ing|ies)?`);
  }
  pats.sort((a, b) => b.length - a.length);
  const re = new RegExp(`\\b(?:${pats.join("|")})\\b`, "gi");
  const ranges = [];
  for (const el of container.querySelectorAll(".text-sel")) {
    const text = el.textContent;
    for (const m of text.matchAll(re)) {
      const r = rangeFromOffsets(el, m.index, m.index + m[0].length);
      if (r) ranges.push(r);
    }
  }
  setHighlight("vocab", ranges);
}
