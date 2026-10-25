// 计时器：默认关闭；点开可以选倒计时（20/40/60 分钟或自定义）或正计时，计时中可以暂停、继续、关闭。
import { esc, local, toast, fmtTime } from "./util.js";

const CLOCK = `<svg viewBox="0 0 24 24"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2.5M9.5 2.5h5"/></svg>`;

export function timerHtml() {
  return `<div class="timer-wrap" id="timer-wrap">
    <button class="timer off" id="timer" title="计时">${CLOCK}<span id="timer-text">计时</span></button>
    <div class="timer-pop" id="timer-pop" hidden></div>
  </div>`;
}

// key: 保存计时状态的本地键（刷新页面后接着计）
export function createTimer(root, { key, defaultMin = 20 }) {
  const btn = root.querySelector("#timer");
  const text = root.querySelector("#timer-text");
  const pop = root.querySelector("#timer-pop");
  const wrap = root.querySelector("#timer-wrap");
  // 旧版计时器在这个键里存的是一个数字，格式不对就当成"没开计时"
  const saved = local.get(key, null);
  const valid = saved && typeof saved === "object" && ["off", "down", "up"].includes(saved.mode)
    && Number.isFinite(saved.elapsed) && Number.isFinite(saved.limit);
  let st = valid ? saved : { mode: "off", limit: 0, elapsed: 0, running: false };
  let frozen = false;
  let rang = st.mode === "down" && st.elapsed >= st.limit;

  const save = () => local.set(key, st);

  function render() {
    btn.classList.toggle("off", st.mode === "off");
    btn.classList.toggle("paused", st.mode !== "off" && !st.running);
    let over = false;
    if (st.mode === "off") text.textContent = "计时";
    else if (st.mode === "up") text.textContent = fmtTime(st.elapsed);
    else {
      const remain = st.limit - st.elapsed;
      over = remain < 0;
      text.textContent = remain >= 0 ? fmtTime(remain) : `+${fmtTime(-remain)}`;
    }
    btn.classList.toggle("over", over);
    btn.title = st.mode === "off" ? "开始计时" : st.running ? "计时中，点击暂停或设置" : "已暂停";
  }

  function menu() {
    const lastMin = local.get("timer-min", defaultMin);
    if (st.mode === "off") {
      pop.innerHTML = `<div class="tp-title">倒计时</div>
        <div class="tp-row">${[20, 40, 60].map((m) => `<button class="chip-btn ${m === lastMin ? "on" : ""}" data-min="${m}">${m} 分钟</button>`).join("")}</div>
        <div class="tp-row"><input class="text tp-input" id="tp-min" type="number" min="1" max="180" inputmode="numeric" value="${esc(lastMin)}"><span class="muted small">分钟</span>
          <button class="btn primary small" data-act="down">开始倒计时</button></div>
        <div class="tp-sep"></div>
        <button class="btn small tp-wide" data-act="up">正计时（不限时间）</button>`;
    } else {
      pop.innerHTML = `<div class="tp-title">${st.mode === "down" ? `倒计时 ${Math.round(st.limit / 60)} 分钟` : "正计时"} · 已用 ${fmtTime(st.elapsed)}</div>
        <div class="tp-row">
          <button class="btn small primary" data-act="toggle">${st.running ? "暂停" : "继续"}</button>
          <button class="btn small" data-act="reset">重新设置</button>
          <button class="btn small danger" data-act="off">关闭计时</button>
        </div>`;
    }
  }

  btn.onclick = () => {
    if (frozen) return;
    menu();
    pop.hidden = !pop.hidden;
  };
  pop.addEventListener("click", (e) => {
    const m = e.target.closest("[data-min]");
    if (m) {
      pop.querySelector("#tp-min").value = m.dataset.min;
      pop.querySelectorAll("[data-min]").forEach((b) => b.classList.toggle("on", b === m));
      return;
    }
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (!act) return;
    if (act === "down") {
      const min = Math.max(1, Math.min(180, parseInt(pop.querySelector("#tp-min").value, 10) || defaultMin));
      local.set("timer-min", min);
      st = { mode: "down", limit: min * 60, elapsed: 0, running: true };
      rang = false;
      toast(`开始倒计时 ${min} 分钟`);
    } else if (act === "up") {
      st = { mode: "up", limit: 0, elapsed: 0, running: true };
      toast("开始正计时");
    } else if (act === "toggle") {
      st.running = !st.running;
    } else if (act === "reset") {
      st = { mode: "off", limit: 0, elapsed: 0, running: false };
      menu();
      save(); render();
      return; // 保持弹窗打开，直接选新的时长
    } else if (act === "off") {
      st = { mode: "off", limit: 0, elapsed: 0, running: false };
    }
    pop.hidden = true;
    save(); render();
  });
  pop.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.id === "tp-min") pop.querySelector('[data-act="down"]').click(); });
  const outside = (e) => { if (!wrap.contains(e.target)) pop.hidden = true; };
  document.addEventListener("mousedown", outside);

  const tick = setInterval(() => {
    if (st.mode === "off" || !st.running || frozen) return;
    st.elapsed++;
    if (st.mode === "down" && st.elapsed >= st.limit && !rang) {
      rang = true;
      toast("时间到！可以继续做，超出的时间会显示为 +");
      try { navigator.vibrate?.(300); } catch { /* 忽略 */ }
    }
    if (st.elapsed % 5 === 0) save();
    render();
  }, 1000);

  render();
  return {
    // 用了多少秒；没开计时返回 null
    seconds: () => (st.mode === "off" ? null : st.elapsed),
    // 提交后停住
    freeze() { frozen = true; st.running = false; pop.hidden = true; local.del(key); render(); },
    // 重做：回到关闭状态
    reset() { frozen = false; st = { mode: "off", limit: 0, elapsed: 0, running: false }; local.del(key); render(); },
    destroy() { clearInterval(tick); document.removeEventListener("mousedown", outside); if (!frozen) save(); },
  };
}
