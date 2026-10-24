// 英语学习网站：路由 + 各个页面
import { api, getJSON, esc, speak, toast, local, fmtTime, ago, refreshBadge, refreshVocab, vocabCache } from "./util.js";
import { initLookup, highlightVocab, closeLookup } from "./lookup.js";
import { renderQuestions, answerKind } from "./questions.js";
import { toolbarHtml, createMarker, bindToolbar, currentTool } from "./marks.js";
import { timerHtml, createTimer } from "./timer.js";
import { renderPV, gradeKey, checkAnswer } from "./pv.js";

const app = document.getElementById("app");
initLookup(app);

// ================================================================ 路由

const routes = [
  [/^\/?$/, homeView],
  [/^\/library$/, libraryView],
  [/^\/read\/([\w-]+)$/, practiceView],
  [/^\/write\/([\w-]+)$/, writingView],
  [/^\/vocab$/, vocabView],
  [/^\/review$/, reviewView],
  [/^\/phrases$/, phrasesView],
  [/^\/phrases\/(\d+)$/, phraseUnitView],
  [/^\/phrases\/(\d+)\/book$/, phraseBookView],
  [/^\/records$/, recordsView],
];

let cleanup = null;
async function route() {
  if (cleanup) { cleanup(); cleanup = null; }
  const path = location.hash.replace(/^#/, "") || "/";
  document.body.className = "";
  delete document.body.dataset.tool;
  window.scrollTo(0, 0);
  const nav = path.split("/")[1] || "home";
  const navKey = { read: "library", write: "library", records: "home" }[nav] || nav;
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === navKey));
  for (const [re, fn] of routes) {
    const m = path.match(re);
    if (m) {
      try {
        cleanup = (await fn(...m.slice(1))) || null;
      } catch (err) {
        console.error(err);
        app.innerHTML = `<div class="page"><div class="empty"><div class="big">😵</div>页面出错了：${esc(err.message)}</div></div>`;
      }
      return;
    }
  }
  app.innerHTML = `<div class="page"><div class="empty">没有这个页面</div></div>`;
}
addEventListener("hashchange", route);

// ================================================================ 数据

const getLibrary = () => getJSON("/content/library.json");
const getPV = () => getJSON("/content/phrasal-verbs.json");

async function unitIndex() {
  const lib = await getLibrary();
  const idx = {};
  for (const b of lib.books) for (const t of b.tests) {
    for (const r of t.reading) idx[r.id] = { ...r, kind: "reading", book: b, test: t.n };
    for (const w of t.writing) idx[w.id] = { ...w, kind: "writing", book: b, test: t.n, title: `Writing Task ${w.task}` };
  }
  return idx;
}

function unitName(u) {
  if (!u) return "";
  return `${u.book.short} Test ${u.test} · ${u.kind === "writing" ? `Writing Task ${u.task}` : u.label}`;
}

async function attemptsByUnit() {
  const { items } = await api.get("/api/attempts");
  const latest = {};
  for (const a of items) if (!latest[a.unit]) latest[a.unit] = a; // 已按时间倒序
  return { latest, items };
}

function scoreClass(score, total) {
  const r = score / total;
  return r >= 0.8 ? "good" : r >= 0.6 ? "mid" : "bad";
}

// 雅思阅读原始分 -> 分数（常用换算表）
function band(raw, type) {
  const A = [[39, 9], [37, 8.5], [35, 8], [33, 7.5], [30, 7], [27, 6.5], [23, 6], [19, 5.5], [15, 5], [13, 4.5], [10, 4], [8, 3.5], [6, 3], [4, 2.5]];
  const G = [[40, 9], [39, 8.5], [37, 8], [36, 7.5], [34, 7], [32, 6.5], [30, 6], [27, 5.5], [23, 5], [19, 4.5], [15, 4], [12, 3.5], [9, 3], [6, 2.5]];
  for (const [min, b] of type === "G" ? G : A) if (raw >= min) return b;
  return raw > 0 ? 2 : 0;
}

function attemptRow(a, idx) {
  const u = idx[a.unit];
  return `<a class="list-item" href="#/read/${a.unit}">
    <span class="score-pill ${scoreClass(a.score, a.total)}">${a.score}/${a.total}</span>
    <span style="flex:1;min-width:0"><span class="unit-title" style="display:block">${esc(u ? u.title : a.unit)}</span>
    <span class="muted small">${esc(unitName(u))} · ${a.seconds != null ? `用时 ${fmtTime(a.seconds)}` : "未计时"}</span></span>
    <span class="muted small">${ago(a.created_at)}</span></a>`;
}

// ================================================================ 首页

async function homeView() {
  const [stats, idx, { items }] = await Promise.all([refreshBadge(), unitIndex(), api.get("/api/attempts")]);
  const lastUnit = local.get("last-unit");
  const hour = new Date().getHours();
  const hi = hour < 5 ? "夜深了" : hour < 11 ? "早上好" : hour < 14 ? "中午好" : hour < 18 ? "下午好" : "晚上好";
  const done = new Set(items.map((a) => a.unit));
  const next = Object.values(idx).find((u) => u.kind === "reading" && u.book.type === "A" && !done.has(u.id));
  const last = lastUnit && idx[lastUnit];
  app.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>${hi}</h1><p class="muted">今天也读一点、记一点。</p></div></div>
    <div class="hero">
      <a class="card review-cta" href="#/review">
        <div><div class="small" style="opacity:.85">今天要复习的生词</div><div class="num">${stats.due}</div></div>
        <span class="btn">${stats.due ? "开始复习" : "暂时没有，去生词本看看"}</span>
      </a>
      <div class="stats-col">
        <a class="card stat" href="#/vocab" style="color:inherit"><span class="muted small">生词本</span><span class="num">${stats.vocab}</span></a>
        <a class="card stat" href="#/records" style="color:inherit"><span class="muted small">做题次数</span><span class="num">${stats.attempts}</span></a>
      </div>
    </div>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(260px,1fr));margin-top:14px">
      ${last ? `<a class="card" href="#/${last.kind === "writing" ? "write" : "read"}/${lastUnit}" style="color:inherit">
        <div class="muted small">继续上次</div><h3 style="margin-top:6px">${esc(last.title)}</h3>
        <div class="muted small" style="margin-top:4px">${esc(unitName(last))}</div></a>` : ""}
      ${next ? `<a class="card" href="#/read/${next.id}" style="color:inherit">
        <div class="muted small">下一篇没做过的 · A 类</div><h3 style="margin-top:6px">${esc(next.title)}</h3>
        <div class="muted small" style="margin-top:4px">${esc(unitName(next))}</div></a>` : ""}
      <a class="card" href="#/phrases" style="color:inherit"><div class="muted small">短语学习</div>
        <h3 style="margin-top:6px">English Phrasal Verbs in Use</h3><div class="muted small" style="margin-top:4px">70 个单元 · 近 800 个短语动词</div></a>
    </div>
    <div class="section">
      <div class="row" style="margin-bottom:8px"><h2>最近做题</h2><span class="spacer"></span>${items.length ? '<a href="#/records" class="small">全部记录 →</a>' : ""}</div>
      ${items.length ? `<div class="card" style="padding:4px 14px"><div class="list">${items.slice(0, 6).map((a) => attemptRow(a, idx)).join("")}</div></div>`
        : `<div class="card empty" style="padding:30px">还没有做题记录。<br><a href="#/library">去题库挑一篇 →</a></div>`}
    </div>
  </div>`;
}

async function recordsView() {
  const [idx, { items }] = await Promise.all([unitIndex(), api.get("/api/attempts")]);
  app.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>做题记录</h1><p class="muted">共 ${items.length} 次。点进去可以看到当时的答案和对错。</p></div></div>
    ${items.length ? `<div class="card" style="padding:4px 14px"><div class="list">${items.map((a) => attemptRow(a, idx)).join("")}</div></div>`
      : `<div class="card empty">还没有记录</div>`}
  </div>`;
}

// ================================================================ 题库

async function libraryView() {
  const [lib, { latest }] = await Promise.all([getLibrary(), attemptsByUnit()]);
  const filter = local.get("lib-filter", "A");
  const books = lib.books.filter((b) => filter === "all" || b.type === filter);
  app.innerHTML = `<div class="page">
    <div class="page-head">
      <div><h1>题库</h1><p class="muted">文章可以点词查询；题目是原书页面；答题卡自动判分。</p></div>
      <div class="seg" id="lib-filter">
        <button data-f="A" class="${filter === "A" ? "on" : ""}">A 类</button>
        <button data-f="G" class="${filter === "G" ? "on" : ""}">G 类</button>
        <button data-f="all" class="${filter === "all" ? "on" : ""}">全部</button>
      </div>
    </div>
    ${books.map((b) => `<div class="book">
      <div class="book-head"><h2>${esc(b.title)}</h2><span class="chip ${b.type === "A" ? "accent" : ""}">${b.type === "A" ? "Academic" : "General Training"}</span></div>
      <div class="tests">${b.tests.map((t) => testCard(b, t, latest)).join("")}</div>
    </div>`).join("")}
  </div>`;
  app.querySelector("#lib-filter").onclick = (e) => {
    const f = e.target.dataset.f;
    if (f) { local.set("lib-filter", f); libraryView(); }
  };
}

function testCard(b, t, latest) {
  const scores = t.reading.map((r) => latest[r.id]);
  const all = scores.every(Boolean);
  const raw = all ? scores.reduce((s, a) => s + a.score, 0) : 0;
  return `<div class="card test-card">
    <h3>Test ${t.n} ${all ? `<span class="chip ok" title="三篇最近一次成绩相加">${raw}/40 · 约 ${band(raw, b.type)} 分</span>` : ""}</h3>
    ${t.reading.map((r) => {
      const a = latest[r.id];
      return `<a class="unit-link" href="#/read/${r.id}">
        <span class="unit-no">${b.type === "A" ? "P" : "S"}${r.n}</span>
        <span class="unit-title">${esc(r.title)}</span>
        ${a ? `<span class="score-pill ${scoreClass(a.score, a.total)}">${a.score}/${a.total}</span>` : `<span class="muted small">${r.q[0]}–${r.q[1]}</span>`}
      </a>`;
    }).join("")}
    ${t.writing.map((w) => `<a class="unit-link" href="#/write/${w.id}"><span class="unit-no">W${w.task}</span><span class="unit-title">Writing Task ${w.task}</span><span class="muted small">写作</span></a>`).join("")}
  </div>`;
}

// ================================================================ 做题

const TF = { T: "TRUE", F: "FALSE", NG: "NOT GIVEN", Y: "YES", N: "NO", "NOT-GIVEN": "NOT GIVEN" };
function norm(s) {
  let v = String(s || "").toLowerCase().replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/\s+/g, " ").trim();
  v = v.replace(/^[\s"'.,;:]+|[\s"'.,;:]+$/g, "");
  v = v.replace(/(\d),(?=\d{3}\b)/g, "$1").replace(/(\d)\s+(?=[a-z%])/g, "$1"); // 1,000 kg = 1000kg
  const up = v.toUpperCase();
  if (TF[up]) return TF[up].toLowerCase();
  return v;
}

// 判分：返回 { n: {ok, user, correct} }
function grade(unit, answers) {
  const res = {};
  for (const [k, v] of Object.entries(unit.answers)) {
    if (k.includes("&")) {
      // 顺序不限的多选：每选对一个字母得一分
      const nums = k.split("&");
      const pool = v.any.map((x) => x.toUpperCase());
      const used = new Set();
      for (const n of nums) {
        const u = String(answers[n] || "").trim().toUpperCase();
        const ok = pool.includes(u) && !used.has(u);
        if (ok) used.add(u);
        res[n] = { ok, user: answers[n] || "", correct: pool.join(" / "), group: nums };
      }
    } else {
      const ok = v.some((alt) => norm(alt) === norm(answers[k]));
      res[k] = { ok, user: answers[k] || "", correct: v[0] + (v.length > 1 ? `（也可：${v.slice(1).join(" / ")}）` : "") };
    }
  }
  return res;
}

function questionRows(unit) {
  const rows = [];
  for (const [k, v] of Object.entries(unit.answers)) {
    if (k.includes("&")) {
      const nums = k.split("&");
      nums.forEach((n, i) => rows.push({ n, kind: "letter", group: i === 0 ? nums : null }));
    } else rows.push({ n: k, kind: answerKind(v) });
  }
  return rows.sort((a, b) => a.n - b.n);
}

async function practiceView(id) {
  const [unit, idx] = await Promise.all([getJSON(`/content/units/${id}.json`), unitIndex()]);
  const meta = idx[id];
  local.set("last-unit", id);
  document.body.className = "practice immersive";
  const draftKey = `draft:${id}`;
  let answers = local.get(draftKey, {});
  let result = null;
  let usedSeconds = null; // 这次用了多少秒（没开计时就是 null）
  const ids = Object.keys(idx).filter((k) => idx[k].kind === "reading");
  const nextId = ids[ids.indexOf(id) + 1];
  const rows = questionRows(unit);
  const total = rows.length;

  let mid = 0;
  const source = `${meta.book.short} Test ${meta.test} ${meta.label}`;
  const passageHtml = unit.blocks.map((b) => {
    const m = `data-mid="p${mid++}"`;
    if (b.type === "title") return `<h1 class="p-title text-sel" ${m}>${esc(b.text)}</h1>`;
    if (b.type === "sub") return `<p class="p-sub text-sel" ${m}>${esc(b.text)}</p>`;
    if (b.type === "h") return `<p class="p-heading text-sel" ${m}>${esc(b.text)}</p>`;
    if (b.type === "note") return `<p class="p-note text-sel" ${m}>${esc(b.text)}</p>`;
    return b.label
      ? `<div class="p-para"><span class="p-label">${b.label}</span><p class="text-sel" style="flex:1" ${m}>${esc(b.text)}</p></div>`
      : `<p class="text-sel" ${m}>${esc(b.text)}</p>`;
  }).join("");

  // 题目：有转写好的文字就用文字，没有就退回原书图片 + 答题卡
  const qHtml = unit.questions
    ? renderQuestions(unit.questions, unit)
    : `<div class="qpages">${unit.qpages.map((p) => `<img loading="lazy" src="/content/pages/${unit.book}/${p}.jpg" alt="题目第 ${p} 页">`).join("")}</div>
       <section class="qgroup"><h3 class="qg-title">答题卡</h3>${rows.map((r) => `<div class="q"><span class="qn">${r.n}</span><div class="q-body">${
         r.kind === "tfng" || r.kind === "ynng"
           ? `<span class="tf">${(r.kind === "tfng" ? ["TRUE", "FALSE", "NOT GIVEN"] : ["YES", "NO", "NOT GIVEN"]).map((o) => `<button class="opt" data-n="${r.n}" data-v="${o}">${o}</button>`).join("")}</span>`
           : `<input class="blank" data-n="${r.n}" placeholder="${r.n}" autocomplete="off" autocapitalize="none" spellcheck="false">`}</div></div>`).join("")}</section>`;

  app.innerHTML = `
    <div class="practice-bar">
      <a class="btn ghost small" href="#/library" aria-label="返回">←</a>
      <span class="title">${esc(meta.book.short)} T${meta.test} ${esc(meta.label)}<span class="muted title-sub" style="font-weight:400"> · ${esc(unit.title)}</span></span>
      <span class="spacer"></span>
      ${toolbarHtml()}
      ${timerHtml()}
      <button class="btn primary small" id="submit">提交</button>
    </div>
    <div class="mobile-seg"><div class="seg" id="mseg">
      <button data-p="passage" class="on">文章</button><button data-p="questions">题目 <span id="progress-m" class="muted small"></span></button>
    </div></div>
    <div class="split">
      <section class="pane pane-left show" id="pane-passage">
        <article class="passage" data-source="${esc(source)}" data-link="#/read/${id}">
          ${passageHtml || '<p class="muted">这一篇没有提取到文字，请看原页。</p>'}
          <details class="orig"><summary class="muted">看原书页面（文字识别可能有个别错误，以原书为准）</summary>
            <div class="qpages" style="padding:12px 0">${unit.pages.filter((p) => !unit.qpages.includes(p)).map((p) => `<img loading="lazy" src="/content/pages/${unit.book}/${p}.jpg" alt="第 ${p} 页">`).join("")}</div>
          </details>
        </article>
      </section>
      <section class="pane pane-right" id="pane-right">
        <div class="qhead"><span id="progress"></span><span class="spacer"></span><span class="muted small">第 ${unit.q[0]}–${unit.q[1]} 题</span></div>
        <div id="result"></div>
        <div class="questions" id="questions" data-source="${esc(source + " 题目")}" data-link="#/read/${id}">${qHtml}
          ${unit.questions ? `<details class="orig"><summary class="muted">看原书题目页</summary><div class="qpages" style="padding:12px 0">${unit.qpages.map((p) => `<img loading="lazy" src="/content/pages/${unit.book}/${p}.jpg" alt="题目第 ${p} 页">`).join("")}</div></details>` : ""}
        </div>
      </section>
    </div>`;

  const $ = (s) => app.querySelector(s);
  const qbox = $("#questions");
  const marker = createMarker({ root: app, unitId: id });
  const unbindTools = bindToolbar(app, marker);

  // ---- 把答案填回题目里
  function fill() {
    qbox.querySelectorAll("input.blank, select.blank").forEach((i) => { i.value = answers[i.dataset.n] || ""; i.disabled = !!result; });
    qbox.querySelectorAll(".opt[data-n]").forEach((b) => { b.classList.toggle("on", norm(answers[b.dataset.n]) === b.dataset.v.toLowerCase()); b.disabled = !!result; });
    qbox.querySelectorAll(".radio[data-n]").forEach((b) => b.classList.toggle("on", String(answers[b.dataset.n] || "").toUpperCase() === b.dataset.v));
    qbox.querySelectorAll(".radio[data-pick]").forEach((b) => {
      const nums = b.dataset.pick.split(",");
      b.classList.toggle("on", nums.some((n) => String(answers[n] || "").toUpperCase() === b.dataset.v));
    });
    const done = rows.filter((r) => String(answers[r.n] || "").trim()).length;
    $("#progress").innerHTML = result ? "" : `已答 <b>${done}</b>/${total}`;
    $("#progress-m").textContent = result ? "" : `${done}/${total}`;
  }
  function setAnswer(n, v) {
    if (result) return;
    answers[n] = v;
    local.set(draftKey, answers);
    fill();
  }
  qbox.addEventListener("input", (e) => { const n = e.target.dataset?.n; if (n) { answers[n] = e.target.value; local.set(draftKey, answers); fill(); } });
  qbox.addEventListener("change", (e) => { const n = e.target.dataset?.n; if (n) setAnswer(n, e.target.value); });
  qbox.addEventListener("click", (e) => {
    const opt = e.target.closest(".opt[data-n]");
    if (opt) return setAnswer(opt.dataset.n, answers[opt.dataset.n] === opt.dataset.v ? "" : opt.dataset.v);
    // 选择题：点圆圈，或者没用工具时点整行
    const row = e.target.closest(".mcq-opt");
    if (!row || result) return;
    const tool = currentTool();
    const radio = e.target.closest(".radio") || (tool === "none" || !e.target.closest(".text-sel") ? row.querySelector(".radio") : null);
    if (!radio) return;
    if (radio.dataset.n) return setAnswer(radio.dataset.n, answers[radio.dataset.n] === radio.dataset.v ? "" : radio.dataset.v);
    // 选两个：选中的字母依次放进这几题
    const nums = radio.dataset.pick.split(",");
    let chosen = nums.map((n) => answers[n]).filter(Boolean);
    chosen = chosen.includes(radio.dataset.v) ? chosen.filter((x) => x !== radio.dataset.v) : [...chosen, radio.dataset.v];
    if (chosen.length > nums.length) { toast(`只能选 ${nums.length} 个`); return; }
    chosen.sort();
    nums.forEach((n, i) => { answers[n] = chosen[i] || ""; });
    local.set(draftKey, answers);
    fill();
  });

  // ---- 判分结果显示在题目里
  function showResult() {
    const score = Object.values(result).filter((r) => r.ok).length;
    $("#result").innerHTML = `<div class="result-box"><span class="num">${score}/${total}</span>
      <div><div style="font-weight:650">${score === total ? "全对！" : score / total >= 0.8 ? "很不错" : score / total >= 0.6 ? "还可以，看看错在哪" : "多看看错题的原文"}</div>
      <div class="muted small">${usedSeconds != null ? `用时 ${fmtTime(usedSeconds)} · ` : ""}绿色是对的，红色的后面写了正确答案</div></div>
      <span class="spacer"></span><button class="btn small" id="redo">重做</button></div>`;
    qbox.querySelectorAll(".ans-chip").forEach((x) => x.remove());
    qbox.querySelectorAll(".right, .wrong").forEach((x) => x.classList.remove("right", "wrong"));
    const shown = new Set();
    for (const [n, r] of Object.entries(result)) {
      const els = qbox.querySelectorAll(`[data-n="${n}"]`);
      const q = qbox.querySelector(`.q[data-q="${n}"]`);
      const target = els.length ? (els[0].matches(".opt, .radio") ? els[0].parentElement : els[0]) : null;
      if (q) q.classList.add(r.ok ? "right" : "wrong");
      els.forEach((el) => { if (el.matches("input, select")) el.classList.add(r.ok ? "right" : "wrong"); });
      if (!r.ok && target && !shown.has(r.group ? r.group.join() : n)) {
        shown.add(r.group ? r.group.join() : n);
        target.insertAdjacentHTML("afterend", `<span class="ans-chip">${r.group ? `${r.group.join("、")}：` : `${n}：`}${esc(r.correct)}</span>`);
      }
      if (r.group) {
        const box = qbox.querySelector(`.mcq[data-pick="${r.group.join(",")}"]`);
        if (box && !box.querySelector(".ans-chip")) box.insertAdjacentHTML("beforeend", `<span class="ans-chip ${r.ok ? "ok" : ""}">第 ${r.group.join("、")} 题答案：${esc(r.correct)}</span>`);
      }
    }
    // 选择题：把正确的选项标绿
    for (const [k, v] of Object.entries(unit.answers)) {
      if (k.includes("&")) {
        for (const L of v.any) qbox.querySelectorAll(`.radio[data-pick="${k.split("&").join(",")}"][data-v="${L.toUpperCase()}"]`).forEach((b) => b.classList.add("correct"));
      } else {
        qbox.querySelectorAll(`.radio[data-n="${k}"][data-v="${String(v[0]).toUpperCase()}"]`).forEach((b) => b.classList.add("correct"));
        qbox.querySelectorAll(`.opt[data-n="${k}"]`).forEach((b) => b.classList.toggle("correct", b.dataset.v === String(v[0]).toUpperCase()));
      }
    }
    fill();
  }

  app.addEventListener("click", (e) => {
    if (e.target.id !== "redo") return;
    answers = {}; result = null; usedSeconds = null;
    local.del(draftKey);
    timer.reset();
    $("#result").innerHTML = "";
    qbox.querySelectorAll(".ans-chip").forEach((x) => x.remove());
    qbox.querySelectorAll(".right, .wrong, .correct").forEach((x) => x.classList.remove("right", "wrong", "correct"));
    $("#submit").textContent = "提交";
    $("#submit").onclick = submit;
    fill();
  });

  // ---- 手机：文章 / 题目切换
  const paneLeft = $("#pane-passage"), paneRight = $("#pane-right");
  function show(which) {
    paneLeft.classList.toggle("show", which === "passage");
    paneRight.classList.toggle("show", which !== "passage");
    app.querySelectorAll("#mseg button").forEach((b) => b.classList.toggle("on", b.dataset.p === which));
  }
  $("#mseg").onclick = (e) => { const b = e.target.closest("button"); if (b) show(b.dataset.p); };

  // ---- 计时（默认关闭，点开设置倒计时或正计时）
  const timer = createTimer(app, { key: `timer:${id}`, defaultMin: 20 });

  // ---- 提交
  async function submit() {
    if (result) return;
    const empty = rows.filter((r) => !String(answers[r.n] || "").trim()).length;
    if (empty && !confirm(`还有 ${empty} 题没填，确定提交吗？`)) return;
    result = grade(unit, answers);
    const score = Object.values(result).filter((r) => r.ok).length;
    usedSeconds = timer.seconds();
    timer.freeze();
    await api.post("/api/attempts", { unit: id, answers, results: result, score, total, seconds: usedSeconds });
    local.del(draftKey);
    $("#submit").textContent = nextId ? "下一篇 →" : "完成";
    $("#submit").onclick = () => { location.hash = nextId ? `#/read/${nextId}` : "#/library"; };
    showResult();
    show("questions");
    paneRight.scrollTo({ top: 0, behavior: "smooth" });
  }
  $("#submit").onclick = submit;

  // 做过的题：没有草稿时显示上一次的结果
  const { items } = await api.get(`/api/attempts?unit=${id}`);
  if (items.length && !Object.keys(answers).length) {
    const a = items[0];
    answers = a.answers; result = a.results; usedSeconds = a.seconds ?? null;
    $("#submit").textContent = "重做";
    $("#submit").onclick = () => app.querySelector("#redo")?.click();
    showResult();
  }
  fill();
  await marker.load();
  highlightVocab(app);
  const onVocab = () => highlightVocab(app);
  document.addEventListener("vocab-changed", onVocab);

  return () => {
    timer.destroy();
    unbindTools();
    delete document.body.dataset.tool;
    document.removeEventListener("vocab-changed", onVocab);
    if (window.CSS && CSS.highlights) CSS.highlights.delete("vocab");
  };
}

// ================================================================ 写作

async function writingView(id) {
  const [unit, idx] = await Promise.all([getJSON(`/content/units/${id}.json`), unitIndex()]);
  const meta = idx[id];
  local.set("last-unit", id);
  const saved = (await api.get(`/api/kv?key=${encodeURIComponent("write:" + id)}`)).value || { text: "" };
  const minWords = unit.task === 1 ? 150 : 250;
  app.innerHTML = `<div class="page" style="max-width:1200px">
    <div class="page-head"><div><a href="#/library" class="small">← 题库</a><h1 style="margin-top:6px">${esc(unitName(meta))}</h1>
      <p class="muted">建议用时 ${unit.task === 1 ? "20" : "40"} 分钟，至少 ${minWords} 词。写的内容会自动保存。</p></div></div>
    <div class="write-wrap">
      <div>
        <div class="card" style="padding:10px"><div class="qpages" style="padding:0">${unit.pages.map((p) => `<img src="/content/pages/${unit.book}/${p}.jpg" alt="题目">`).join("")}</div></div>
        ${unit.samplePages.length ? `<details class="card" style="margin-top:12px"><summary style="cursor:pointer;font-weight:600">看书后范文（写完再看）</summary>
          <div class="qpages" style="padding:12px 0 0">${unit.samplePages.map((p) => `<img loading="lazy" src="/content/pages/${unit.book}/${p}.jpg" alt="范文">`).join("")}</div></details>` : ""}
      </div>
      <div>
        <textarea class="text" id="essay" placeholder="在这里写…" spellcheck="true">${esc(saved.text)}</textarea>
        <div class="row" style="margin-top:8px"><span id="wc" class="muted small"></span><span class="spacer"></span><span id="savestate" class="muted small"></span></div>
      </div>
    </div></div>`;
  const ta = app.querySelector("#essay"), wc = app.querySelector("#wc"), st = app.querySelector("#savestate");
  const count = () => {
    const n = (ta.value.match(/[A-Za-z]+(?:['’-][A-Za-z]+)*/g) || []).length;
    wc.innerHTML = `${n} 词 ${n >= minWords ? '<span class="chip ok">够字数了</span>' : `<span class="chip">还差 ${minWords - n}</span>`}`;
  };
  count();
  let t;
  ta.oninput = () => {
    count();
    st.textContent = "…";
    clearTimeout(t);
    t = setTimeout(async () => {
      await api.post("/api/kv", { key: "write:" + id, value: { text: ta.value, updated: Date.now() } });
      st.textContent = "已保存";
    }, 800);
  };
}

// ================================================================ 生词本

async function vocabView() {
  const { items, now } = await api.get("/api/vocab");
  let q = "", kind = local.get("vocab-kind", "all");
  app.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>生词本</h1><p class="muted">在文章里点词、选短语都能加进来。共 <b id="vcount">${items.length}</b> 个。</p></div>
      <a class="btn primary" href="#/review">复习</a></div>
    <div class="toolbar">
      <input class="text" id="vq" placeholder="搜索单词、释义、笔记">
      <div class="seg" id="vkind">
        <button data-k="all">全部</button><button data-k="word">单词</button><button data-k="phrase">短语</button><button data-k="due">待复习</button>
      </div>
      <span class="spacer"></span>
      <div class="row" style="gap:6px"><input class="text" id="vadd" placeholder="手动添加：输入单词或短语" style="max-width:220px"><button class="btn" id="vaddbtn">添加</button></div>
    </div>
    <div class="card" style="padding:0" id="vlist"></div>
  </div>`;
  const list = app.querySelector("#vlist");

  function hl(sentence, word) {
    const s = esc(sentence);
    const w = word.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+(?:\\w+\\s+)?");
    try { return s.replace(new RegExp(`\\b(${w}\\w*)`, "i"), "<b>$1</b>"); } catch { return s; }
  }

  function render() {
    app.querySelectorAll("#vkind button").forEach((b) => b.classList.toggle("on", b.dataset.k === kind));
    const ql = q.toLowerCase();
    const shown = items.filter((v) =>
      (kind === "all" || (kind === "due" ? v.due <= now : v.kind === kind)) &&
      (!ql || [v.word, v.meaning, v.note, v.sentence].some((x) => (x || "").toLowerCase().includes(ql))));
    if (!shown.length) {
      list.innerHTML = `<div class="empty"><div class="big">📒</div>${items.length ? "没有符合条件的" : "生词本还是空的。<br>去题库读一篇文章，点不认识的词，按「＋ 生词本」。"}</div>`;
      return;
    }
    list.innerHTML = shown.map((v) => `<div class="vocab-item" data-id="${v.id}">
      <div class="vocab-word">${esc(v.word)} <span class="phon">${v.phonetic ? "/" + esc(v.phonetic) + "/" : ""}</span>
        <button class="speak" data-speak="${esc(v.word)}" aria-label="发音" style="width:26px;height:26px"><svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9zm12.5 3a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4z"/></svg></button>
        ${v.kind === "phrase" ? '<span class="chip accent">短语</span>' : ""}</div>
      <div class="vocab-mean">${esc((v.meaning || "").split("\n").slice(0, 3).join("\n"))}</div>
      <div class="vocab-actions">
        <button class="btn ghost small" data-act="note">笔记</button>
        <button class="btn ghost small danger" data-act="del">删除</button>
      </div>
      ${v.note ? `<div class="vocab-note">${esc(v.note)}</div>` : ""}
      ${v.sentence ? `<div class="vocab-sent">${hl(v.sentence, v.word)}</div>` : ""}
      <div class="vocab-meta">${v.source ? `<a href="${esc(v.source_link || "#")}">${esc(v.source)}</a>` : "手动添加"}
        <span>加入于 ${ago(v.added_at)}</span>
        <span>${v.reps ? `已复习 ${v.reps} 次` : "还没复习"}${v.due <= now ? ' · <span style="color:var(--err)">待复习</span>' : ` · 下次 ${new Date(v.due * 1000).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" })}`}</span></div>
    </div>`).join("");
  }
  render();

  app.querySelector("#vq").oninput = (e) => { q = e.target.value; render(); };
  app.querySelector("#vkind").onclick = (e) => { if (e.target.dataset.k) { kind = e.target.dataset.k; local.set("vocab-kind", kind); render(); } };
  const addManual = async () => {
    const inp = app.querySelector("#vadd");
    const word = inp.value.trim();
    if (!word) return;
    const r = await api.get(`/api/lookup?q=${encodeURIComponent(word)}`);
    const e = r.word || r.phrase || {};
    const res = await api.post("/api/vocab", {
      word: e.word || e.phrase || word, phonetic: e.phonetic || "",
      meaning: (e.translation || "").split("\n").slice(0, 4).join("\n"), kind: /\s/.test(word) ? "phrase" : "word",
    });
    inp.value = "";
    toast(res.existed ? "生词本里已经有了" : `已添加「${word}」`);
    await refreshVocab(); refreshBadge();
    vocabView();
  };
  app.querySelector("#vaddbtn").onclick = addManual;
  app.querySelector("#vadd").onkeydown = (e) => e.key === "Enter" && addManual();

  list.onclick = async (e) => {
    const sp = e.target.closest("[data-speak]");
    if (sp) return speak(sp.dataset.speak);
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const item = btn.closest(".vocab-item");
    const v = items.find((x) => x.id == item.dataset.id);
    if (btn.dataset.act === "del") {
      await api.del(`/api/vocab/${v.id}`);
      items.splice(items.indexOf(v), 1);
      app.querySelector("#vcount").textContent = items.length;
      render();
      refreshVocab(); refreshBadge();
      toast(`已删除「${v.word}」`, {
        label: "撤销", run: async () => {
          const r = await api.post("/api/vocab", { ...v });
          v.id = r.id; items.push(v); items.sort((a, b) => b.added_at - a.added_at);
          app.querySelector("#vcount").textContent = items.length;
          render(); refreshVocab(); refreshBadge();
        },
      });
    }
    if (btn.dataset.act === "note") {
      const note = prompt(`给「${v.word}」写个笔记（例句、近义词、自己的记法…）`, v.note || "");
      if (note === null) return;
      await api.post(`/api/vocab/${v.id}`, { note });
      v.note = note;
      render();
    }
  };
}

// ================================================================ 复习

async function reviewView() {
  const { items, total } = await api.get("/api/vocab/due?limit=200");
  const queue = items.slice();
  let done = 0, shown = false;
  document.body.classList.add("immersive");
  app.innerHTML = `<div class="page"><div class="flash" id="flash"></div></div>`;
  const box = app.querySelector("#flash");
  const hint = (g, c) => {
    if (g === 0) return "10 分钟";
    const days = g === 1 ? (c.reps ? Math.max(1, c.interval * 1.2) : 1)
      : c.reps === 0 ? (g === 2 ? 1 : 4) : c.reps === 1 ? (g === 2 ? 3 : 6) : c.interval * c.ease * (g === 3 ? 1.3 : 1);
    return days < 1.5 ? "1 天" : days < 30 ? `${Math.round(days)} 天` : `${Math.round(days / 30)} 个月`;
  };
  function hl(sentence, word) {
    const s = esc(sentence);
    const w = word.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+(?:\\w+\\s+)?");
    try { return s.replace(new RegExp(`\\b(${w}\\w*)`, "i"), "<b>$1</b>"); } catch { return s; }
  }
  function render() {
    if (!queue.length) {
      box.innerHTML = `<div class="card flash-card"><div class="big" style="font-size:44px">🎉</div>
        <h2>${done ? `复习完了 ${done} 个` : "现在没有要复习的词"}</h2>
        <p class="muted">${done ? "明天再来。" : "去文章里多查查词，加进生词本吧。"}</p>
        <div class="row" style="justify-content:center"><a class="btn" href="#/vocab">生词本</a><a class="btn primary" href="#/library">去做题</a></div></div>`;
      refreshBadge();
      return;
    }
    const c = queue[0];
    box.innerHTML = `<div class="progress"><div style="width:${(done / (done + queue.length)) * 100}%"></div></div>
      <div class="row muted small" style="margin-bottom:8px"><span>还剩 ${queue.length} 个</span><span class="spacer"></span><a href="#/vocab">退出</a></div>
      <div class="card flash-card">
        <div class="flash-word">${esc(c.word)}</div>
        <div class="row muted small" style="justify-content:center">${c.phonetic ? "/" + esc(c.phonetic) + "/" : ""}
          <button class="speak" data-speak="${esc(c.word)}" aria-label="发音"><svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9zm12.5 3a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4z"/></svg></button></div>
        ${c.sentence ? `<div class="flash-sent">${hl(c.sentence, c.word)}</div>` : ""}
        ${shown ? `<div class="flash-mean">${esc(c.meaning || "（没有释义）")}${c.note ? `<div class="vocab-note" style="margin-top:10px;text-align:left">${esc(c.note)}</div>` : ""}</div>` : ""}
      </div>
      ${shown ? `<div class="grades">
          <button class="btn g0" data-g="0">忘了<small>${hint(0, c)}</small></button>
          <button class="btn" data-g="1">模糊<small>${hint(1, c)}</small></button>
          <button class="btn" data-g="2">认识<small>${hint(2, c)}</small></button>
          <button class="btn" data-g="3">太简单<small>${hint(3, c)}</small></button></div>
          <p class="muted small" style="text-align:center;margin-top:10px">键盘：1 2 3 4</p>`
        : `<button class="btn primary" style="width:100%;height:50px;margin-top:14px" data-show>显示释义（空格）</button>`}`;
    if (!shown) speak(c.word);
  }
  async function gradeCard(g) {
    const c = queue.shift();
    await api.post(`/api/vocab/${c.id}/review`, { grade: g });
    if (g === 0) queue.splice(Math.min(queue.length, 4), 0, c); // 忘了的过几张再出现
    else done++;
    shown = false;
    render();
  }
  box.onclick = (e) => {
    const sp = e.target.closest("[data-speak]");
    if (sp) return speak(sp.dataset.speak);
    if (e.target.closest("[data-show]")) { shown = true; render(); }
    const g = e.target.closest("[data-g]");
    if (g) gradeCard(+g.dataset.g);
  };
  const onKey = (e) => {
    if (!queue.length) return;
    if (e.key === " " && !shown) { e.preventDefault(); shown = true; render(); }
    else if (shown && ["1", "2", "3", "4"].includes(e.key)) gradeCard(+e.key - 1);
  };
  document.addEventListener("keydown", onKey);
  render();
  return () => document.removeEventListener("keydown", onKey);
}

// ================================================================ 短语

async function phrasesView() {
  const pv = await getPV();
  const doneSet = new Set((await api.get("/api/kv?key=pv-done")).value || []);
  const groups = [];
  for (const u of pv.units) {
    if (!groups.length || groups[groups.length - 1].name !== u.group) groups.push({ name: u.group, units: [] });
    groups[groups.length - 1].units.push(u);
  }
  app.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>短语学习</h1><p class="muted">English Phrasal Verbs in Use · 已学 ${doneSet.size}/70 单元</p></div></div>
    <input class="text" id="pq" placeholder="搜索短语动词，例如 give up、look after" style="max-width:420px;margin-bottom:14px">
    <div class="pv-results" id="pres"></div>
    <div id="units">${groups.map((g) => `<div class="unit-sec">${esc(g.name || "")}</div>
      <div class="units">${g.units.map((u) => `<a class="unit-card ${doneSet.has(u.n) ? "done" : ""}" href="#/phrases/${u.n}">
        <span class="unit-no">${doneSet.has(u.n) ? "✓" : u.n}</span><span class="unit-title">${esc(u.title)}</span>
        <span class="muted small">${u.phrases.length}</span></a>`).join("")}</div>`).join("")}</div>
  </div>`;
  const res = app.querySelector("#pres");
  const keys = Object.keys(pv.entries);
  app.querySelector("#pq").oninput = async (e) => {
    const q = e.target.value.trim().toLowerCase();
    if (q.length < 2) { res.innerHTML = ""; return; }
    const hits = keys.filter((k) => k.includes(q)).sort((a, b) => (a.startsWith(q) ? 0 : 1) - (b.startsWith(q) ? 0 : 1) || a.length - b.length).slice(0, 12);
    const tr = hits.length ? await api.post("/api/phrases", { keys: hits }) : {};
    res.innerHTML = hits.length ? hits.map((k) => {
      const e = pv.entries[k];
      return `<a class="pv-hit" href="#/phrases/${e.units[0]}"><span class="ph">${esc(k)}</span>
        <span class="tr">${esc((tr[k] || "").split("\n")[0] || e.def)}</span><span class="muted small">第 ${e.units.join("、")} 单元</span></a>`;
    }).join("") : `<div class="muted small">书里没有这个短语。可以在任意文章里选中它查询。</div>`;
  };
}

async function phraseUnitView(n) {
  n = +n;
  const pv = await getPV();
  const u = pv.units[n - 1];
  if (!u) throw new Error("没有这个单元");
  const doneList = (await api.get("/api/kv?key=pv-done")).value || [];
  const vocab = await vocabCache();
  const savedMap = new Map(vocab.map((v) => [v.word.toLowerCase(), v.id]));
  const tr = u.phrases.length ? await api.post("/api/phrases", { keys: u.phrases.map((p) => p.key) }) : {};
  let tab = local.get("pv-tab", "list");
  if (tab === "book" && u.text) tab = "list"; // 讲解和练习是单独的页面
  const doc = u.text || u.hasKey ? await getJSON(`/content/pv/${String(n).padStart(2, "0")}.json`) : null;
  app.innerHTML = `<div class="page">
    <div class="row small" style="margin-bottom:10px"><a href="#/phrases">← 全部单元</a><span class="spacer"></span>
      ${n > 1 ? `<a href="#/phrases/${n - 1}">← 第 ${n - 1} 单元</a>` : ""}${n < 70 ? `<a href="#/phrases/${n + 1}" style="margin-left:14px">第 ${n + 1} 单元 →</a>` : ""}</div>
    <div class="page-head"><div><div class="muted small">${esc(u.group || "")} · Unit ${n}</div><h1 style="margin-top:4px">${esc(u.title)}</h1></div>
      <button class="btn ${doneList.includes(n) ? "" : "primary"}" id="done">${doneList.includes(n) ? "✓ 已学完" : "标记为学完"}</button></div>
    <div class="seg" id="ptab" style="margin-bottom:16px">
      <button data-t="list">本单元短语 ${u.phrases.length}</button><button data-t="book">讲解和练习</button><button data-t="key">练习答案</button>
    </div>
    <div id="pbody"></div>
  </div>`;
  const pbody = app.querySelector("#pbody");
  function render() {
    app.querySelectorAll("#ptab button").forEach((b) => b.classList.toggle("on", b.dataset.t === tab));
    if (tab === "list") {
      pbody.innerHTML = u.phrases.length ? `<div class="card" style="padding:0" data-source="短语书 Unit ${n} ${esc(u.title)}" data-link="#/phrases/${n}">
        ${u.phrases.map((p) => {
          const saved = savedMap.get(p.key.toLowerCase());
          const zh = (tr[p.key] || "").split("\n").slice(0, 2).join("；");
          return `<div class="vocab-item">
            <div class="vocab-word">${esc(p.key)}
              <button class="speak" data-speak="${esc(p.key)}" aria-label="发音" style="width:26px;height:26px"><svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9zm12.5 3a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4z"/></svg></button>
              <span class="muted small" style="font-family:var(--sans);font-weight:400">${esc(p.phrase !== p.key ? p.phrase : "")}</span></div>
            <div class="vocab-mean">${zh ? esc(zh) : '<span class="muted">（词典里没有中文释义）</span>'}</div>
            <div class="vocab-actions"><button class="btn small add-btn ${saved ? "saved" : ""}" data-key="${esc(p.key)}" data-saved="${saved || ""}">${saved ? "✓ 已加入" : "＋ 生词本"}</button></div>
            <div class="vocab-sent text-sel" style="border-left-color:var(--accent-soft);font-size:14.5px">${esc(p.def)}</div>
          </div>`;
        }).join("")}</div>
        <p class="muted small" style="margin-top:10px">短语清单来自书后的 Mini dictionary；英文释义里的词也可以点击查询。</p>`
        : `<div class="card empty">这个单元没有整理出短语清单，请看「原书讲解和练习」。</div>`;
    } else if (tab === "book") {
      pbody.innerHTML = `<div class="qpages" style="padding:0">${u.pages.map((p) => `<img src="/content/pages/phrasal-verbs/${p}.jpg" alt="第 ${p} 页">`).join("")}</div>`;
    } else if (doc?.key) {
      pbody.innerHTML = `<div class="card pv-keydoc" data-source="短语书 Unit ${n} 答案" data-link="#/phrases/${n}">${renderPV(doc.key, { prefix: "k" }).left}
        <details class="orig"><summary class="muted">看原书答案页</summary><div class="qpages" style="padding:12px 0">${u.keyPages.map((p) => `<img loading="lazy" src="/content/pages/phrasal-verbs/${p}.jpg" alt="答案 第 ${p} 页">`).join("")}</div></details></div>`;
    } else {
      pbody.innerHTML = u.keyPages.length ? `<p class="muted small">答案页上也有其他单元的答案，找 Unit ${n}。</p><div class="qpages" style="padding:0">${u.keyPages.map((p) => `<img loading="lazy" src="/content/pages/phrasal-verbs/${p}.jpg" alt="答案 第 ${p} 页">`).join("")}</div>`
        : `<div class="card empty">没找到这个单元的答案页</div>`;
    }
  }
  render();
  app.querySelector("#ptab").onclick = (e) => {
    const t = e.target.dataset.t;
    if (!t) return;
    if (t === "book" && u.text) { location.hash = `#/phrases/${n}/book`; return; }
    tab = t; local.set("pv-tab", tab); render();
  };
  app.querySelector("#done").onclick = async (e) => {
    const list = new Set((await api.get("/api/kv?key=pv-done")).value || []);
    list.has(n) ? list.delete(n) : list.add(n);
    await api.post("/api/kv", { key: "pv-done", value: [...list] });
    e.target.textContent = list.has(n) ? "✓ 已学完" : "标记为学完";
    e.target.classList.toggle("primary", !list.has(n));
    if (list.has(n)) toast(`第 ${n} 单元学完了`);
  };
  pbody.addEventListener("click", async (e) => {
    const sp = e.target.closest("[data-speak]");
    if (sp) return speak(sp.dataset.speak);
    const b = e.target.closest(".add-btn");
    if (!b) return;
    const key = b.dataset.key;
    if (b.dataset.saved) {
      await api.del(`/api/vocab/${b.dataset.saved}`);
      b.dataset.saved = "";
      toast(`已从生词本删除「${key}」`);
    } else {
      const p = u.phrases.find((x) => x.key === key);
      const r = await api.post("/api/vocab", {
        word: key, kind: "phrase", meaning: [(tr[key] || "").split("\n").slice(0, 3).join("\n"), p.def].filter(Boolean).join("\n"),
        sentence: "", source: `短语书 Unit ${n} ${u.title}`, source_link: `#/phrases/${n}`,
      });
      b.dataset.saved = r.id;
      toast(`已加入生词本「${key}」`);
    }
    b.classList.toggle("saved", !!b.dataset.saved);
    b.textContent = b.dataset.saved ? "✓ 已加入" : "＋ 生词本";
    await refreshVocab(); refreshBadge();
  });
}

// 原书讲解（左）+ 练习（右），和题库一样可以点词、标记，练习直接作答
async function phraseBookView(n) {
  n = +n;
  const pv = await getPV();
  const u = pv.units[n - 1];
  if (!u) throw new Error("没有这个单元");
  if (!u.text) { location.replace(`#/phrases/${n}`); return; }
  const doc = await getJSON(`/content/pv/${String(n).padStart(2, "0")}.json`);
  document.body.className = "practice immersive";
  const draftKey = `pv-draft:${n}`;
  const saveKey = `pv-ex:${n}`;
  let answers = local.get(draftKey, {});
  let submitted = false;
  const { left, right } = renderPV(doc.doc, { unit: n });
  const source = `短语书 Unit ${n} ${u.title}`;
  const origPages = (pages) => `<details class="orig"><summary class="muted">看原书页面（转写难免有个别错误，以原书为准）</summary>
    <div class="qpages" style="padding:12px 0">${pages.map((p) => `<img loading="lazy" src="/content/pages/phrasal-verbs/${p}.jpg" alt="第 ${p} 页">`).join("")}</div></details>`;

  app.innerHTML = `
    <div class="practice-bar">
      <a class="btn ghost small" href="#/phrases/${n}" aria-label="返回">←</a>
      <span class="title">Unit ${n}<span class="muted title-sub" style="font-weight:400"> · ${esc(u.title)}</span></span>
      <span class="spacer"></span>
      ${toolbarHtml()}
      <button class="btn primary small" id="submit">对答案</button>
    </div>
    <div class="mobile-seg"><div class="seg" id="mseg">
      <button data-p="passage" class="on">讲解</button><button data-p="questions">练习</button>
    </div></div>
    <div class="split">
      <section class="pane pane-left show" id="pane-passage">
        <article class="passage pv-doc" data-source="${esc(source)}" data-link="#/phrases/${n}/book">
          <div class="muted small" style="font-family:var(--sans)">${esc(u.group || "")} · Unit ${n}</div>
          <h1 class="p-title">${esc(u.title)}</h1>
          ${left}
          ${origPages([u.pages[0]])}
        </article>
      </section>
      <section class="pane pane-right" id="pane-right">
        <div class="qhead"><b>Exercises</b><span class="spacer"></span><span id="progress" class="muted small"></span></div>
        <div id="result"></div>
        <div class="questions pv-exs" id="questions" data-source="${esc(source + " 练习")}" data-link="#/phrases/${n}/book">${right}
          ${origPages([u.pages[1]])}
        </div>
      </section>
    </div>`;

  const $ = (s) => app.querySelector(s);
  const qbox = $("#questions");
  const marker = createMarker({ root: app, unitId: `pv-${n}` });
  const unbindTools = bindToolbar(app, marker);
  const grow = (el) => { if (el.tagName === "TEXTAREA") { el.style.height = "auto"; el.style.height = el.scrollHeight + 2 + "px"; } };

  const inputs = () => [...qbox.querySelectorAll("[data-b]")];
  const choiceKey = (ex, q) => `c:${ex}:${q}`;
  function fill() {
    inputs().forEach((i) => { i.value = answers[i.dataset.b] || ""; i.disabled = submitted; grow(i); });
    qbox.querySelectorAll(".radio[data-v]").forEach((b) => b.classList.toggle("on", answers[choiceKey(b.dataset.ex, b.dataset.n)] === b.dataset.v));
    const total = inputs().length + new Set([...qbox.querySelectorAll(".radio[data-v]")].map((b) => choiceKey(b.dataset.ex, b.dataset.n))).size;
    const done = Object.values(answers).filter((v) => String(v).trim()).length;
    $("#progress").textContent = total ? `已填 ${Math.min(done, total)}/${total}` : "";
  }
  function save() { local.set(draftKey, answers); fill(); }
  qbox.addEventListener("input", (e) => { const b = e.target.dataset?.b; if (b) { answers[b] = e.target.value; local.set(draftKey, answers); grow(e.target); } });
  qbox.addEventListener("change", () => fill());
  qbox.addEventListener("click", (e) => {
    const row = e.target.closest(".mcq-opt");
    if (!row || submitted) return;
    const tool = currentTool();
    const radio = e.target.closest(".radio") || (tool === "none" || !e.target.closest(".text-sel") ? row.querySelector(".radio") : null);
    if (!radio) return;
    const k = choiceKey(radio.dataset.ex, radio.dataset.n);
    answers[k] = answers[k] === radio.dataset.v ? "" : radio.dataset.v;
    save();
  });

  // ---- 对答案：能自动判的标对错，每道练习下面显示原书答案
  function showResult() {
    let ok = 0, graded = 0;
    qbox.querySelectorAll(".ans-chip, .pv-key").forEach((x) => x.remove());
    qbox.querySelectorAll(".right, .wrong, .correct").forEach((x) => x.classList.remove("right", "wrong", "correct"));
    for (const sec of qbox.querySelectorAll(".pv-ex")) {
      const ex = sec.dataset.ex;
      const md = doc.keyEx[ex];
      const key = gradeKey(md);
      if (key) {
        for (const [q, alts] of Object.entries(key)) {
          const els = sec.querySelectorAll(`[data-b][data-n="${q}"]`);
          const radios = sec.querySelectorAll(`.radio[data-n="${q}"]`);
          if (els.length === 1 && !radios.length) {
            const good = checkAnswer(answers[els[0].dataset.b], alts);
            graded++; if (good) ok++;
            els[0].classList.add(good ? "right" : "wrong");
            if (!good) els[0].insertAdjacentHTML("afterend", `<span class="ans-chip">${esc(alts.join(" / "))}</span>`);
          } else if (!els.length && alts.parts && sec.querySelectorAll(`.pv-q[data-q="${q}"] [data-b]`).length === alts.parts.length) {
            // 一个小题几个空：按顺序对答案里用逗号分开的几个
            sec.querySelectorAll(`.pv-q[data-q="${q}"] [data-b]`).forEach((el, i) => {
              const good = checkAnswer(answers[el.dataset.b], alts.parts[i]);
              graded++; if (good) ok++;
              el.classList.add(good ? "right" : "wrong");
              if (!good) el.insertAdjacentHTML("afterend", `<span class="ans-chip">${esc(alts.parts[i].join(" / "))}</span>`);
            });
          } else if (radios.length) {
            const good = checkAnswer(answers[choiceKey(ex, q)], alts);
            graded++; if (good) ok++;
            radios.forEach((r) => { if (alts.includes(r.dataset.v)) r.classList.add("correct"); });
            sec.querySelector(`.pv-q[data-q="${q}"]`)?.classList.add(good ? "right" : "wrong");
          }
        }
      }
      if (md) sec.insertAdjacentHTML("beforeend", `<div class="pv-key"><div class="pv-key-h">答案</div>${renderPV(md, { prefix: `k${ex}-` }).left}</div>`);
    }
    $("#result").innerHTML = `<div class="result-box">${graded ? `<span class="num">${ok}/${graded}</span>` : ""}
      <div><div style="font-weight:650">${graded ? (ok === graded ? "全对！" : "看看红色的地方") : "答案已显示"}</div>
      <div class="muted small">${graded ? "填空和选择自动判分；" : ""}每道练习下面有原书答案，写句子的题自己对照</div></div>
      <span class="spacer"></span><button class="btn small" id="redo">重做</button></div>`;
    $("#submit").textContent = "重做";
    return { ok, graded };
  }
  async function submit() {
    if (submitted) { redo(); return; }
    submitted = true;
    fill();
    const { ok, graded } = showResult();
    await api.post("/api/kv", { key: saveKey, value: { answers, ok, graded, at: Date.now() } });
    local.del(draftKey);
    show("questions");
    $("#pane-right").scrollTo({ top: 0, behavior: "smooth" });
  }
  function redo() {
    submitted = false; answers = {};
    local.del(draftKey);
    api.post("/api/kv", { key: saveKey, value: null });
    $("#result").innerHTML = "";
    qbox.querySelectorAll(".ans-chip, .pv-key").forEach((x) => x.remove());
    qbox.querySelectorAll(".right, .wrong, .correct").forEach((x) => x.classList.remove("right", "wrong", "correct"));
    $("#submit").textContent = "对答案";
    fill();
  }
  $("#submit").onclick = submit;
  $("#result").addEventListener("click", (e) => { if (e.target.id === "redo") redo(); });

  // ---- 手机：讲解 / 练习切换
  const paneLeft = $("#pane-passage"), paneRight = $("#pane-right");
  function show(which) {
    paneLeft.classList.toggle("show", which === "passage");
    paneRight.classList.toggle("show", which !== "passage");
    app.querySelectorAll("#mseg button").forEach((b) => b.classList.toggle("on", b.dataset.p === which));
  }
  $("#mseg").onclick = (e) => { const b = e.target.closest("button"); if (b) show(b.dataset.p); };

  // 做过的：没有草稿时显示上一次对答案的结果
  const last = (await api.get(`/api/kv?key=${encodeURIComponent(saveKey)}`)).value;
  if (last && !Object.keys(answers).length) {
    answers = last.answers || {};
    submitted = true;
    fill();
    showResult();
  }
  fill();
  await marker.load();
  highlightVocab(app);
  const onVocab = () => highlightVocab(app);
  document.addEventListener("vocab-changed", onVocab);

  return () => {
    unbindTools();
    delete document.body.dataset.tool;
    document.removeEventListener("vocab-changed", onVocab);
    if (window.CSS && CSS.highlights) CSS.highlights.delete("vocab");
  };
}

// ================================================================ 启动
route();
refreshBadge();
setInterval(refreshBadge, 5 * 60 * 1000);
