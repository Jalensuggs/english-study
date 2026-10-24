// 做题页的工具：学习笔（点词翻译）、记号笔（划词，可选颜色和样式）、橡皮擦。
// 标记按"第几个文字块 + 字符位置"保存在服务器上（kv: marks:<篇章id>），下次打开还在。
import { api, local, toast } from "./util.js";

export const COLORS = {
  yellow: "#f7d94c",
  green: "#8fd694",
  pink: "#f4a0c0",
  blue: "#8cc3f2",
  orange: "#f6b26b",
};

const ICONS = {
  none: `<svg viewBox="0 0 24 24"><path d="M5 3.5l13 7.2-5.6 1.5 3.3 5.8-2.6 1.5-3.3-5.8L6 18z"/></svg>`,
  pen: `<svg viewBox="0 0 24 24"><path d="M4 20l1.2-4.6L15.6 5a2 2 0 0 1 2.8 0l.6.6a2 2 0 0 1 0 2.8L8.6 18.8z"/><path d="M13.5 7l3.5 3.5"/><path d="M15 20h5"/></svg>`,
  marker: `<svg viewBox="0 0 24 24"><path d="M9.5 15.5l-2 2 1 1-1.5 1.5H3l2.5-2.5 1-1 2-2"/><path d="M8.5 14.5l7-9a2 2 0 0 1 3 0l1 1a2 2 0 0 1 0 3l-9 7z"/></svg>`,
  eraser: `<svg viewBox="0 0 24 24"><path d="M8 20h12"/><path d="M5.5 15.5l9-9a2 2 0 0 1 2.8 0l2.2 2.2a2 2 0 0 1 0 2.8L12 19H8.5z"/><path d="M10 11l5 5"/></svg>`,
};

const state = {
  tool: "none",                       // none（鼠标）/ pen / marker / eraser；每次打开做题页都从鼠标开始
  color: local.get("mark-color", "yellow"),
  style: local.get("mark-style", "hl"), // hl 荧光底色 / ul 下划线
};
export const currentTool = () => state.tool;

// ---------------------------------------------------------------- 工具栏

export function toolbarHtml() {
  return `<div class="tools" id="tools">
    <button class="tool" data-tool="none" title="鼠标：不用任何笔，可以正常选择、复制文字">${ICONS.none}<span>鼠标</span></button>
    <button class="tool" data-tool="pen" title="学习笔：点单词翻译，拖选查短语">${ICONS.pen}<span>学习笔</span></button>
    <button class="tool" data-tool="marker" title="记号笔：划词、划句子">${ICONS.marker}<span>记号笔</span><i class="swatch"></i></button>
    <button class="tool" data-tool="eraser" title="橡皮擦：点标记擦掉，或拖选一段擦掉">${ICONS.eraser}<span>橡皮擦</span></button>
    <div class="palette" id="palette" hidden>
      <div class="palette-row">${Object.entries(COLORS).map(([k, c]) => `<button class="dot" data-color="${k}" style="--c:${c}" aria-label="${k}"></button>`).join("")}</div>
      <div class="palette-row seg"><button data-style="hl">荧光笔</button><button data-style="ul">下划线</button></div>
      <div class="palette-row"><button class="btn small ghost danger" data-clear>清除本篇标记</button></div>
    </div>
  </div>`;
}

function syncToolbar(root) {
  document.body.dataset.tool = state.tool;
  root.querySelectorAll(".tool").forEach((b) => b.classList.toggle("on", b.dataset.tool === state.tool));
  const sw = root.querySelector(".swatch");
  if (sw) {
    sw.style.background = COLORS[state.color];
    sw.classList.toggle("ul", state.style === "ul");
  }
  root.querySelectorAll(".dot").forEach((d) => d.classList.toggle("on", d.dataset.color === state.color));
  root.querySelectorAll("[data-style]").forEach((d) => d.classList.toggle("on", d.dataset.style === state.style));
}

// ---------------------------------------------------------------- 标记数据

function textNodes(el) {
  const out = [];
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) out.push(w.currentNode);
  return out;
}

// 选区端点在元素里的字符位置
function offsetIn(el, node, off) {
  const r = document.createRange();
  r.selectNodeContents(el);
  try { r.setEnd(node, off); } catch { return -1; }
  return r.toString().length;
}

export function createMarker({ root, unitId }) {
  const key = `marks:${unitId}`;
  let marks = {}; // mid -> [{s, e, c, st}]
  const original = new Map(); // mid -> 原始 HTML
  let saveTimer;

  const els = () => root.querySelectorAll(".text-sel[data-mid]");
  function remember() {
    for (const el of els()) if (!original.has(el.dataset.mid)) original.set(el.dataset.mid, el.innerHTML);
  }

  // 把一个元素的标记画出来：在文字节点外面包 <span class="mk">
  function paint(el) {
    const mid = el.dataset.mid;
    if (original.has(mid)) el.innerHTML = original.get(mid);
    const list = marks[mid] || [];
    list.forEach((m, i) => {
      let pos = 0;
      for (const n of textNodes(el)) {
        const len = n.nodeValue.length;
        const a = Math.max(m.s, pos), b = Math.min(m.e, pos + len);
        if (a < b) {
          let node = n;
          if (a > pos) node = node.splitText(a - pos);
          if (b < pos + len) node.splitText(b - a);
          const span = document.createElement("span");
          span.className = `mk mk-${m.st}`;
          span.style.setProperty("--mk", COLORS[m.c] || COLORS.yellow);
          span.dataset.mk = `${mid}:${i}`;
          node.parentNode.insertBefore(span, node);
          span.appendChild(node);
        }
        pos += len;
      }
    });
  }
  function paintAll() { for (const el of els()) paint(el); }

  function save() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => api.post("/api/kv", { key, value: marks }), 400);
  }

  // 选区覆盖到的每个文字块：[元素, 起, 止]
  function pieces(range) {
    const out = [];
    for (const el of els()) {
      if (!range.intersectsNode(el)) continue;
      const total = el.textContent.length;
      let s = 0, e = total;
      if (el.contains(range.startContainer)) s = offsetIn(el, range.startContainer, range.startOffset);
      if (el.contains(range.endContainer)) e = offsetIn(el, range.endContainer, range.endOffset);
      if (s < 0) s = 0;
      if (e < 0) e = total;
      // 去掉两头的空格
      const txt = el.textContent;
      while (s < e && /\s/.test(txt[s])) s++;
      while (e > s && /\s/.test(txt[e - 1])) e--;
      if (e > s) out.push([el, s, e]);
    }
    return out;
  }

  function addMark(range) {
    const ps = pieces(range);
    for (const [el, s, e] of ps) {
      const mid = el.dataset.mid;
      // 同一位置重复划：去掉被完全覆盖的旧标记
      marks[mid] = (marks[mid] || []).filter((m) => !(m.s >= s && m.e <= e));
      marks[mid].push({ s, e, c: state.color, st: state.style });
      paint(el);
    }
    if (ps.length) save();
  }

  function eraseRange(range) {
    const ps = pieces(range);
    for (const [el, s, e] of ps) {
      const mid = el.dataset.mid;
      const out = [];
      for (const m of marks[mid] || []) {
        if (m.e <= s || m.s >= e) { out.push(m); continue; }
        if (m.s < s) out.push({ ...m, e: s });
        if (m.e > e) out.push({ ...m, s: e });
      }
      marks[mid] = out;
      paint(el);
    }
    if (ps.length) save();
  }

  function eraseAt(span) {
    const [mid, i] = span.dataset.mk.split(":");
    (marks[mid] || []).splice(+i, 1);
    const el = root.querySelector(`.text-sel[data-mid="${mid}"]`);
    if (el) paint(el);
    save();
  }

  // 点一下记号笔：标出点中的这个词
  function wordRangeAt(x, y) {
    const r = document.caretRangeFromPoint ? document.caretRangeFromPoint(x, y) : null;
    if (!r || r.startContainer.nodeType !== 3) return null;
    const node = r.startContainer, text = node.nodeValue;
    let a = r.startOffset, b = r.startOffset;
    while (a > 0 && /[A-Za-z'’-]/.test(text[a - 1])) a--;
    while (b < text.length && /[A-Za-z'’-]/.test(text[b])) b++;
    if (a === b) return null;
    const range = document.createRange();
    range.setStart(node, a);
    range.setEnd(node, b);
    return range;
  }

  function onPointerUp(e) {
    if (state.tool !== "marker" && state.tool !== "eraser") return;
    if (!e.target.closest(".text-sel")) return;
    setTimeout(() => {
      const sel = getSelection();
      if (sel && !sel.isCollapsed && sel.toString().trim()) {
        const range = sel.getRangeAt(0);
        state.tool === "marker" ? addMark(range) : eraseRange(range);
        sel.removeAllRanges();
        return;
      }
      if (state.tool === "eraser") {
        const span = e.target.closest(".mk");
        if (span) eraseAt(span);
      } else {
        const r = wordRangeAt(e.clientX, e.clientY);
        if (r) addMark(r);
      }
    }, 10);
  }
  root.addEventListener("mouseup", onPointerUp);
  root.addEventListener("touchend", (e) => {
    const t = e.changedTouches[0];
    // 手机：长按选中后松手才会有选区，稍等一下
    setTimeout(() => onPointerUp({ target: e.target, clientX: t.clientX, clientY: t.clientY }), 250);
  });

  return {
    async load() {
      remember();
      marks = (await api.get(`/api/kv?key=${encodeURIComponent(key)}`)).value || {};
      paintAll();
    },
    // 内容重新渲染后（比如提交后），重新记住原始 HTML 再画
    refresh() {
      original.clear();
      remember();
      paintAll();
    },
    clear() {
      marks = {};
      paintAll();
      save();
    },
  };
}

// ---------------------------------------------------------------- 工具栏行为

export function bindToolbar(root, marker) {
  state.tool = "none";
  const bar = root.querySelector("#tools");
  const pal = root.querySelector("#palette");
  syncToolbar(root);
  bar.addEventListener("click", (e) => {
    const t = e.target.closest(".tool");
    if (t) {
      const tool = t.dataset.tool;
      if (tool === "marker" && state.tool === "marker") {
        pal.hidden = !pal.hidden; // 记号笔已选中时再点：打开/收起颜色
      } else {
        state.tool = tool;
        pal.hidden = !(tool === "marker" && !local.get("palette-seen", false));
        if (tool === "marker") local.set("palette-seen", true);
      }
      syncToolbar(root);
      getSelection().removeAllRanges();
      return;
    }
    const d = e.target.closest("[data-color]");
    if (d) { state.color = d.dataset.color; local.set("mark-color", state.color); syncToolbar(root); }
    const s = e.target.closest("[data-style]");
    if (s) { state.style = s.dataset.style; local.set("mark-style", state.style); syncToolbar(root); }
    if (e.target.closest("[data-clear]") && confirm("清除这一篇的所有标记？")) { marker.clear(); pal.hidden = true; }
  });
  const close = (e) => { if (!bar.contains(e.target)) pal.hidden = true; };
  document.addEventListener("mousedown", close);
  return () => document.removeEventListener("mousedown", close);
}
