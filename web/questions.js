// 把转写好的题目文字（content-src/questions/*.md）渲染成可以直接作答的题目。
//
// 格式说明（每行一种）：
//   ## Questions 1–3            题组标题（新的一组）
//   普通一行                      说明文字，**加粗**
//   ### 标题                     居中的小标题（如表格/笔记的标题）
//   1. 句子 {1} 句子              带题号的题；{1} 是第 1 题的填空
//   - 要点 {5}                   项目符号（前面每多两个空格缩进一级）
//   A. 选项内容                   选择题选项（紧跟在题目后）
//   > **List of Headings**       方框里的列表（标题列表、人名列表、词库）
//   > i. xxx                   （方框里：### 标题、普通文字是段落、- 是要点）
//   | 表头 | 表头 |              表格；单元格里用 <br> 换行，"• " 开头是要点
//   [flow] ... [/flow]           流程图，每行一个方框
//   @options A-G                 这一组的选项范围（填空变成下拉框、匹配题用）
//   @pick 20,21                  "选两个"：后面的选项是多选，选中的字母依次给这几题
//   @tfng / @ynng [views]        插入 TRUE/FALSE/NOT GIVEN 或 YES/NO/NOT GIVEN 说明

import { esc } from "./util.js";

const ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"];

function range(spec) {
  const [a, b] = spec.split(/\s*[-–]\s*/);
  if (/^[A-Z]$/.test(a)) {
    const out = [];
    for (let c = a.charCodeAt(0); c <= b.charCodeAt(0); c++) out.push(String.fromCharCode(c));
    return out;
  }
  return ROMAN.slice(ROMAN.indexOf(a), ROMAN.indexOf(b) + 1);
}

export function answerKind(alts) {
  if (!alts) return "text";
  if (alts.any) return "pick";
  const a = alts.map((x) => x.toUpperCase());
  if (a.some((x) => ["TRUE", "FALSE"].includes(x)) || (a[0] === "NOT GIVEN" && !a.includes("YES"))) return "tfng";
  if (a.some((x) => ["YES", "NO"].includes(x))) return "ynng";
  if (a.every((x) => /^[A-L]$/.test(x))) return "letter";
  if (a.every((x) => ROMAN.includes(x.toLowerCase()))) return "roman";
  return "text";
}

export function renderQuestions(src, unit) {
  const kinds = {};
  for (const [k, v] of Object.entries(unit.answers)) {
    if (k.includes("&")) for (const n of k.split("&")) kinds[n] = "pick";
    else kinds[k] = answerKind(v);
  }
  // 题目里的 TRUE/FALSE/NOT GIVEN 有时其实是 YES/NO/NOT GIVEN，以题组声明为准
  let mid = 0;
  const nextMid = () => `q${mid++}`;
  let opts = null;       // 当前题组的选项范围
  let pick = null;       // 当前"选两个"
  let ynMode = null;     // 当前题组是 tfng 还是 ynng
  let html = "";
  let open = null;       // 正在拼的块：box / table / flow / list
  let buf = [];
  let lastQ = null;      // 上一个题号（后面跟着的 A. B. 是它的选项）

  // 一段带 **粗体** 和 {n} 空的文字 -> HTML（文字放在 .text-sel 里，方便划词和标记）
  function inline(text) {
    const parts = text.split(/(\{\d+\})/);
    let out = "";
    for (const p of parts) {
      const m = p.match(/^\{(\d+)\}$/);
      if (m) out += blank(m[1]);
      else if (p) out += `<span class="text-sel" data-mid="${nextMid()}">${fmt(p)}</span>`;
    }
    return out;
  }
  function fmt(s) {
    return esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\*(.+?)\*/g, "<i>$1</i>");
  }
  function blank(n) {
    const k = kinds[n];
    if ((k === "letter" || k === "roman") && opts) {
      return `<select class="blank sel" data-n="${n}"><option value="">${n}</option>${opts.map((o) => `<option>${o}</option>`).join("")}</select>`;
    }
    return `<input class="blank" data-n="${n}" placeholder="${n}" autocomplete="off" autocorrect="off" autocapitalize="none" spellcheck="false">`;
  }
  function tfButtons(n) {
    const list = (ynMode || (kinds[n] === "ynng" ? "ynng" : "tfng")) === "ynng" ? ["YES", "NO", "NOT GIVEN"] : ["TRUE", "FALSE", "NOT GIVEN"];
    return `<span class="tf">${list.map((o) => `<button class="opt" data-n="${n}" data-v="${o}">${o}</button>`).join("")}</span>`;
  }
  function legend(kind, word = "claims") {
    const rows = kind === "ynng"
      ? [["YES", `if the statement agrees with the ${word} of the writer`], ["NO", `if the statement contradicts the ${word} of the writer`], ["NOT GIVEN", "if it is impossible to say what the writer thinks about this"]]
      : [["TRUE", "if the statement agrees with the information"], ["FALSE", "if the statement contradicts the information"], ["NOT GIVEN", "if there is no information on this"]];
    return `<div class="legend">${rows.map(([a, b]) => `<div><b>${a}</b><span class="text-sel" data-mid="${nextMid()}">${esc(b)}</span></div>`).join("")}</div>`;
  }

  // 表格格子 / 流程图方框：<br> 换行，"• " 开头是要点，"**…**" 是小标题
  function cellHtml(c) {
    return c.split(/<br>/).map((seg) => {
      const t = seg.trim();
      if (t.startsWith("• ")) return `<div class="cell-li">${inline(t.slice(2))}</div>`;
      return `<div>${inline(t)}</div>`;
    }).join("");
  }

  function flush() {
    if (!open) return;
    if (open === "box") {
      html += `<div class="qbox">${buf.map((l) => {
        const m = l.match(/^([A-L]|[ivx]+)[.)]\s+(.*)$/);
        if (m) return `<div class="qbox-row"><span class="qbox-key">${m[1]}</span><span>${inline(m[2])}</span></div>`;
        if (l.startsWith("### ")) return `<div class="qbox-title">${inline(l.slice(4))}</div>`;
        if (/^\*\*[^*]+\*\*$/.test(l)) return `<div class="qbox-h">${inline(l.slice(2, -2))}</div>`;
        const li = l.match(/^(\s*)- (.*)$/);
        if (li) return `<div class="q-li" style="--lv:${Math.floor(li[1].length / 2)}">${inline(li[2])}</div>`;
        return `<p class="qbox-p">${inline(l)}</p>`;
      }).join("")}</div>`;
    } else if (open === "table") {
      const rows = buf.map((l) => l.replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
      html += `<div class="qtable-wrap"><table class="qtable">${rows.map((r, i) => `<tr>${r.map((c) => {
        const tag = i === 0 ? "th" : "td";
        if (c === "^") return ""; // 和上一行合并的格子（简单处理：留空）
        return `<${tag}>${cellHtml(c)}</${tag}>`;
      }).join("")}</tr>`).join("")}</table></div>`;
    } else if (open === "flow") {
      html += `<div class="qflow">${buf.map((l) => `<div class="qflow-box">${cellHtml(l)}</div>`).join('<div class="qflow-arrow">↓</div>')}</div>`;
    } else if (open === "pick") {
      const nums = pick.nums;
      html += `<div class="mcq pick" data-pick="${nums.join(",")}">${buf.map((l) => {
        const m = l.match(/^([A-L])[.)]\s+(.*)$/);
        return `<div class="mcq-opt" data-v="${m[1]}"><button class="radio check" data-pick="${nums.join(",")}" data-v="${m[1]}">${m[1]}</button>${inline(m[2])}</div>`;
      }).join("")}</div>`;
      pick = null;
    } else if (open === "mcq") {
      html += `<div class="mcq">${buf.map((l) => {
        const m = l.match(/^([A-L])[.)]\s+(.*)$/);
        return `<div class="mcq-opt" data-v="${m[1]}"><button class="radio" data-n="${lastQ}" data-v="${m[1]}">${m[1]}</button>${inline(m[2])}</div>`;
      }).join("")}</div>`;
    }
    open = null;
    buf = [];
  }

  for (const raw of src.split("\n")) {
    const line = raw.replace(/\s+$/, "");
    const t = line.trim();
    if (!t) { if (open !== "flow") flush(); continue; }
    if (t === "[flow]") { flush(); open = "flow"; continue; }
    if (t === "[/flow]") { flush(); continue; }
    if (open === "flow") { buf.push(t); continue; }

    if (t.startsWith("## ")) {
      flush();
      if (html) html += `</section>`;
      opts = null; ynMode = null; lastQ = null;
      html += `<section class="qgroup"><h3 class="qg-title">${esc(t.slice(3))}</h3>`;
      continue;
    }
    if (t.startsWith("@options ")) { opts = range(t.slice(9).trim()); continue; }
    if (t.startsWith("@pick ")) { flush(); pick = { nums: t.slice(6).split(",").map((x) => x.trim()) }; continue; }
    if (/^@(tfng|ynng)\b/.test(t)) { flush(); const [d, w] = t.slice(1).split(/\s+/); ynMode = d; html += legend(ynMode, w); continue; }
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
    const optm = t.match(/^([A-L])[.)]\s+(.*)$/);
    if (optm && (pick || open === "pick")) {
      if (open !== "pick") { flush(); open = "pick"; }
      buf.push(t);
      continue;
    }
    if (optm && lastQ && (open === "mcq" || kinds[lastQ] === "letter")) {
      if (open !== "mcq") { flush(); open = "mcq"; }
      buf.push(t);
      continue;
    }
    flush();
    if (t.startsWith("### ")) { html += `<h4 class="qg-sub">${inline(t.slice(4))}</h4>`; continue; }
    const qm = t.match(/^(\d+)\.\s+(.*)$/);
    if (qm) {
      const n = qm[1], body = qm[2];
      lastQ = n;
      const k = kinds[n];
      const hasBlank = /\{\d+\}/.test(body);
      let tail = "";
      if (!hasBlank && (k === "tfng" || k === "ynng")) tail = tfButtons(n);
      else if (!hasBlank && (k === "letter" || k === "roman") && opts) tail = blank(n);
      html += `<div class="q ${tail && k !== "tfng" && k !== "ynng" ? "q-match" : ""}" data-q="${n}"><span class="qn">${n}</span><div class="q-body">${inline(body)}${tail ? `<div class="q-tail">${tail}</div>` : ""}</div></div>`;
      continue;
    }
    const lm = line.match(/^(\s*)- (.*)$/);
    if (lm) {
      const level = Math.floor(lm[1].length / 2);
      html += `<div class="q-li" style="--lv:${level}">${inline(lm[2])}</div>`;
      continue;
    }
    html += `<p class="q-inst">${inline(t)}</p>`;
  }
  flush();
  if (html) html += `</section>`;
  return html;
}
