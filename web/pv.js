// 短语书单元：把转写好的文字（content-src/pv/NN.md）渲染成讲解 + 可以直接作答的练习。
//
// 格式说明（每行一种）：
//   ## A  标题                  讲解的小节（A、B、C…）
//   ## Exercises                练习从这里开始（电脑上放在右栏）
//   ### 6.1  说明                一道练习（题号 + 说明）
//   ### 标题 / #### 标题          小标题
//   普通一行                     段落；**粗体** *斜体* ++下划线++ ~~删除线~~，<br> 换行
//   1. 句子 {_} 句子             带编号的小题；{_} 是填空，{__} 是一整行的作答框
//   a) 选项                      选择题选项（紧跟在小题后面）
//   - 要点                       项目符号
//   | a | b |                    表格，第一行是表头
//   > 文字                       方框（故事、对话、TIP、FOLLOW UP），方框里面也可以用上面所有格式
//   [[up | down | out]]         词库方框
//   @img 10 0.2 0.7 0.8 0.9     原书插图：页码 + 左、上、右、下的位置（占整页的比例）
//
// 判分（gradeKey）：key.md 里这道题的答案是 "1 apart · 2 around/round" 这种短答案时自动判对错。
// 填空对应第几小题：小题里只有一个空 → 小题号；空后面紧跟 (3) → 第 3 小题。其他题只显示答案对照。

import { esc } from "./util.js";

const PAGE_W = 1036, PAGE_H = 1400; // 原书页面图片的尺寸

export function fmt(s) {
  return esc(s)
    .replace(/&lt;br&gt;/g, "<br>")
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/\+\+(.+?)\+\+/g, "<u>$1</u>")
    .replace(/~~(.+?)~~/g, "<s>$1</s>")
    .replace(/\*(.+?)\*/g, "<i>$1</i>");
}

// 返回 { left: 讲解 HTML, right: 练习 HTML }
export function renderPV(src, { prefix = "m", unit = 0 } = {}) {
  let mid = 0, bid = 0;
  let ex = "";

  const text = (s) => (s ? `<span class="text-sel" data-mid="${prefix}${mid++}">${fmt(s)}</span>` : "");

  // 一段文字 -> HTML；n 是它所在的小题号（这一段只有一个空时，这个空就是第 n 小题）
  function inline(s, n = "") {
    const parts = s.split(/(\{__?\})/);
    const count = parts.filter((p) => p === "{_}" || p === "{__}").length;
    let h = "";
    parts.forEach((p, i) => {
      if (p !== "{_}" && p !== "{__}") { h += text(p); return; }
      const m = (parts[i + 1] || "").match(/^\s*\((\d+)\)/);
      const num = m ? m[1] : count === 1 ? n : "";
      const attrs = `data-b="${prefix}b${bid++}" data-ex="${ex}" data-n="${num}" autocomplete="off" autocorrect="off" autocapitalize="none" spellcheck="false"`;
      h += p === "{__}"
        ? `<textarea class="blank long" rows="1" ${attrs}></textarea>`
        : `<input class="blank" ${attrs}>`;
    });
    return h;
  }

  function img(spec) {
    const [page, x0, y0, x1, y1] = spec.split(/\s+/).map(Number);
    const w = x1 - x0, hgt = y1 - y0;
    return `<div class="pv-img" style="aspect-ratio:${(w * PAGE_W).toFixed(0)}/${(hgt * PAGE_H).toFixed(0)}">
      <img loading="lazy" src="/content/pages/phrasal-verbs/${page}.jpg" alt="原书插图"
        style="width:${(100 / w).toFixed(3)}%;left:${(-x0 / w * 100).toFixed(3)}%;top:${(-y0 / hgt * 100).toFixed(3)}%"></div>`;
  }

  // 一串行 -> HTML（方框里面的内容也用它）
  function blocks(lines) {
    let html = "", open = null, buf = [], item = "";
    function flush() {
      if (open === "box") {
        html += `<div class="pv-box">${blocks(buf)}</div>`;
      } else if (open === "table") {
        const rows = buf.map((l) => l.replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
        html += `<div class="qtable-wrap"><table class="qtable pv-table">${rows.map((r, i) =>
          `<tr>${r.map((c) => `<${i ? "td" : "th"}>${inline(c)}</${i ? "td" : "th"}>`).join("")}</tr>`).join("")}</table></div>`;
      } else if (open === "mcq") {
        html += `<div class="mcq">${buf.map((l) => {
          const m = l.match(/^([a-h])\)\s+(.*)$/);
          return `<div class="mcq-opt"><button class="radio" data-ex="${ex}" data-n="${item}" data-v="${m[1]}">${m[1]}</button>${inline(m[2])}</div>`;
        }).join("")}</div>`;
      }
      open = null;
      buf = [];
    }
    for (const raw of lines) {
      const line = raw.replace(/\s+$/, "");
      const t = line.trim();
      if (open === "box" && !t.startsWith(">")) flush();
      if (!t) { flush(); continue; }
      if (t.startsWith(">")) {
        if (open !== "box") { flush(); open = "box"; }
        buf.push(t.replace(/^> ?/, ""));
        continue;
      }
      if (t.startsWith("|")) {
        if (open !== "table") { flush(); open = "table"; }
        if (!/^\|[\s:|-]+\|$/.test(t)) buf.push(t);
        continue;
      }
      const om = t.match(/^([a-h])\)\s+/);
      if (om && item && (open === "mcq" || om[1] === "a")) {
        if (open !== "mcq") { flush(); open = "mcq"; }
        buf.push(t);
        continue;
      }
      flush();
      if (t.startsWith("#### ")) { html += `<h4 class="pv-h4">${inline(t.slice(5))}</h4>`; continue; }
      if (t.startsWith("### ")) { html += `<h4 class="pv-h3">${inline(t.slice(4))}</h4>`; continue; }
      if (t.startsWith("@img ")) { html += img(t.slice(5)); continue; }
      const wb = t.match(/^\[\[(.*)\]\]$/);
      if (wb) { html += `<div class="pv-words">${wb[1].split("|").map((w) => `<span>${text(w.trim())}</span>`).join("")}</div>`; continue; }
      const qm = t.match(/^(\d+)\.\s+(.*)$/);
      if (qm) {
        item = qm[1];
        html += `<div class="q pv-q" data-ex="${ex}" data-q="${item}"><span class="qn">${item}</span><div class="q-body">${inline(qm[2], item)}</div></div>`;
        continue;
      }
      const lm = line.match(/^(\s*)[-•] (.*)$/);
      if (lm) { html += `<div class="q-li" style="--lv:${Math.floor(lm[1].length / 2)}">${inline(lm[2])}</div>`; continue; }
      html += `<p>${inline(t)}</p>`;
    }
    flush();
    return html;
  }

  // 顶层：按 ## 小节 和 ### 练习 切开
  let left = "", right = "", inEx = false, run = [], inSection = false;
  const put = (h) => { if (inEx) right += h; else left += h; };
  const flushRun = () => { if (run.length) put(blocks(run)); run = []; };
  const closeSection = () => { if (inSection) { put("</section>"); inSection = false; } };
  for (const raw of src.split("\n")) {
    const t = raw.trim();
    if (/^# /.test(t)) continue; // 单元标题，页面上已经有了
    let m;
    if ((m = t.match(/^## (.*)$/))) {
      flushRun(); closeSection();
      if (/^exercises$/i.test(m[1].trim())) { inEx = true; continue; }
      const s = m[1].match(/^([A-H])\s+(.*)$/);
      put(`<section class="pv-sec"><h2 class="pv-sec-title">${s ? `<span class="pv-letter">${s[1]}</span>${text(s[2])}` : text(m[1])}</h2>`);
      inSection = true;
      continue;
    }
    if ((m = t.match(/^### (\d{1,2}\.\d{1,2})\s*(.*)$/))) {
      flushRun(); closeSection();
      ex = m[1];
      put(`<section class="pv-ex" data-ex="${ex}"><h3 class="pv-ex-title"><span class="pv-exn">${ex}</span><span>${inline(m[2])}</span></h3>`);
      inSection = true;
      continue;
    }
    run.push(raw);
  }
  flushRun(); closeSection();
  return { left, right };
}

// ---------------------------------------------------------------- 判分

const norm = (s) => String(s || "").toLowerCase().replace(/[’‘]/g, "'").replace(/[.,!?;:]+$/, "").replace(/\s+/g, " ").trim();

// key.md 里一道题的答案 -> {小题号: [可接受的答案]}；不是短答案格式（需要自己对照）时返回 null
export function gradeKey(md) {
  if (!md) return null;
  const lines = md.split("\n").map((l) => l.trim()).filter(Boolean);
  if (!lines.length || lines.some((l) => /^[*|>]|suggested|possible/i.test(l))) return null;
  const out = {};
  for (const line of lines) {
    for (const part of line.split(/\s+·\s+/)) {
      const m = part.match(/^(\d+)\.?\s+(.+)$/);
      if (!m) return null;
      const ans = m[2].replace(/\([^)]*\)/g, " ").replace(/\*/g, "").trim();
      const alts = ans.split(/\s*\/\s*|\s+or\s+/).map(norm).filter(Boolean);
      if (!alts.length || alts.some((a) => a.split(" ").length > 4)) return null;
      out[m[1]] = alts;
    }
  }
  return out;
}

export function checkAnswer(given, alts) {
  const g = norm(given);
  return !!g && alts.some((a) => a === g);
}
