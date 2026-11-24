/* Play layer: progress (XP, check marks), the check-your-answer sheet, sound, confetti, multiple-choice cards,
   the hero moiré toy and the draggable "phone on a track" stage. Presentation only: it never changes a number or a result.
   It is loaded before main.js, which calls WS.play.* and fires "ws:sim" / "ws:mtf" events. Everything degrades gracefully without it. */
(function () {
  const WS = window.WS = window.WS || {};
  const D = window.DATA;
  const $ = id => document.getElementById(id);
  const reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const KEY = "ws.progress.v1", THEME_KEY = "ws.theme.v1";
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private window or file:// restrictions */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* ignore */ } },
  };

  /* ---------------- state ---------------- */
  const REQUIRED = { 1: ["g1"], 2: ["m2a", "m2b", "m2c"], 3: ["p3"], 4: ["p4", "m4a"], 5: ["quiz"], 6: ["p6"] };
  const ALL = Object.values(REQUIRED).flat();
  /* Every visit starts from the original state: nothing is saved between visits. (Older versions saved progress; wipe it.) */
  store.del(KEY); store.del(THEME_KEY);
  let st = { xp: 0, done: {}, sound: false };
  let streak = 0;
  const save = () => {};

  /* ---------------- theme ---------------- */
  const root = document.documentElement;
  const isDark = () => root.getAttribute("data-theme") === "dark" || (!root.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
  function toggleTheme() {
    const next = isDark() ? "light" : "dark";
    root.setAttribute("data-theme", next);
    setTimeout(() => { if (WS.charts) WS.charts.redrawAll(); const s = $("stage"); if (s) drawStage(); }, 30);
  }

  /* ---------------- mascot: a tiny screen with three subpixel bars ---------------- */
  function mascot(mood) {
    const mouth = mood === "sad" ? "M23 46 Q32 39 41 46" : mood === "happy" ? "M23 41 Q32 51 41 41" : "M24 43 Q32 47 40 43";
    const brow = mood === "sad" ? '<path d="M20 20 L27 23 M44 20 L37 23" stroke="#1d2a36" stroke-width="2.5" stroke-linecap="round"/>' : "";
    return `<svg viewBox="0 0 64 64" aria-hidden="true"><rect x="2" y="4" width="60" height="54" rx="16" fill="#2a3a4a"/>
      <clipPath id="mc${mood}"><rect x="7" y="9" width="50" height="44" rx="11"/></clipPath>
      <g clip-path="url(#mc${mood})"><rect x="7" y="9" width="17" height="44" fill="#ff6b6b"/><rect x="23" y="9" width="18" height="44" fill="#58cc02"/><rect x="40" y="9" width="17" height="44" fill="#1cb0f6"/><rect x="7" y="9" width="50" height="44" fill="#fff" opacity=".18"/></g>
      <circle cx="24" cy="28" r="6.5" fill="#fff"/><circle cx="40" cy="28" r="6.5" fill="#fff"/>
      <circle cx="${mood === "sad" ? 24 : 25}" cy="${mood === "sad" ? 30 : 28}" r="3" fill="#1d2a36"/><circle cx="${mood === "sad" ? 40 : 41}" cy="${mood === "sad" ? 30 : 28}" r="3" fill="#1d2a36"/>
      ${brow}<path d="${mouth}" fill="none" stroke="#1d2a36" stroke-width="3" stroke-linecap="round"/><rect x="24" y="58" width="16" height="4" rx="2" fill="#2a3a4a"/></svg>`;
  }

  /* ---------------- audio (Web Audio; only created after a click) ---------------- */
  let actx = null, master = null;
  function audio() {
    if (!actx) {
      const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return null;
      actx = new AC(); master = actx.createGain(); master.gain.value = 0.55; master.connect(actx.destination);
    }
    if (actx.state === "suspended") actx.resume();
    return actx;
  }
  function blip(freq, t0, dur, vol, type) {
    const a = audio(); if (!a) return;
    const o = a.createOscillator(), g = a.createGain(), t = a.currentTime + t0;
    o.type = type || "sine"; o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol || 0.2, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(master); o.start(t); o.stop(t + dur + 0.05);
  }
  function sfx(kind) {
    if (!st.sound) return;
    if (kind === "ok") { blip(523.25, 0, 0.16, 0.2); blip(659.25, 0.09, 0.16, 0.2); blip(783.99, 0.18, 0.28, 0.2); }
    else if (kind === "no") { blip(220, 0, 0.2, 0.18, "triangle"); blip(165, 0.12, 0.3, 0.18, "triangle"); }
    else if (kind === "xp") { blip(880, 0, 0.1, 0.12); blip(1174.7, 0.07, 0.16, 0.12); }
  }
  /* sustained tone sets, one per key ("moire", "emit", "cam"); smooth glides when the sliders move */
  const tones = {};
  function setTones(key, list) {
    const a = audio(); if (!a) return; const bank = tones[key] || (tones[key] = []);
    while (bank.length < list.length) {
      const o = a.createOscillator(), g = a.createGain(); o.type = "sine"; g.gain.value = 0; o.frequency.value = 440; o.connect(g); g.connect(master); o.start();
      bank.push({ o, g });
    }
    bank.forEach((n, i) => {
      const t = list[i], now = a.currentTime;
      if (t) { n.o.frequency.setTargetAtTime(Math.max(30, Math.min(6000, t.f)), now, 0.04); n.g.gain.setTargetAtTime(Math.min(0.3, t.g), now, 0.05); }
      else n.g.gain.setTargetAtTime(0, now, 0.05);
    });
  }
  function stopTones(key) {
    const bank = tones[key]; if (!bank || !actx) return;
    const now = actx.currentTime; bank.forEach(n => n.g.gain.setTargetAtTime(0, now, 0.06));
    setTimeout(() => { bank.forEach(n => { try { n.o.stop(); n.o.disconnect(); n.g.disconnect(); } catch (e) { /* already stopped */ } }); delete tones[key]; }, 400);
  }

  /* ---------------- confetti ---------------- */
  let confCv, confCtx, parts = [], confRun = false;
  function confetti(n) {
    if (reduce) return;
    confCv = confCv || $("confetti"); if (!confCv) return;
    confCv.width = innerWidth; confCv.height = innerHeight; confCtx = confCv.getContext("2d");
    const cols = ["#ff6b6b", "#58cc02", "#1cb0f6", "#ffc800", "#ce82ff", "#ff9600"];
    for (let i = 0; i < (n || 60); i++) parts.push({ x: innerWidth / 2 + (Math.random() - .5) * 120, y: innerHeight * 0.75, vx: (Math.random() - .5) * 11, vy: -8 - Math.random() * 9, w: 6 + Math.random() * 6, h: 4 + Math.random() * 6, c: cols[i % cols.length], r: Math.random() * 6, vr: (Math.random() - .5) * .4, life: 1 });
    if (!confRun) { confRun = true; requestAnimationFrame(stepConf); }
  }
  function stepConf() {
    confCtx.clearRect(0, 0, confCv.width, confCv.height);
    parts = parts.filter(p => p.life > 0 && p.y < confCv.height + 20);
    for (const p of parts) { p.x += p.vx; p.y += p.vy; p.vy += 0.38; p.vx *= 0.99; p.r += p.vr; p.life -= 0.009; confCtx.save(); confCtx.globalAlpha = Math.max(0, p.life); confCtx.translate(p.x, p.y); confCtx.rotate(p.r); confCtx.fillStyle = p.c; confCtx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h); confCtx.restore(); }
    if (parts.length) requestAnimationFrame(stepConf); else { confRun = false; confCtx.clearRect(0, 0, confCv.width, confCv.height); }
  }

  /* ---------------- HUD, progress, awards ---------------- */
  function refresh() {
    $("xpN").textContent = st.xp; $("streakN").textContent = streak;
    document.querySelectorAll("li[data-m]").forEach(li => li.classList.toggle("done", !!st.done[li.dataset.m]));
    document.querySelectorAll("nav.top a").forEach(a => { const n = +a.getAttribute("href").slice(3), req = REQUIRED[n]; a.classList.toggle("done", !!req && req.every(id => st.done[id])); });
    const k = ALL.filter(id => st.done[id]).length; $("progBar").style.width = (100 * k / ALL.length) + "%";
    $("soundBtn").textContent = st.sound ? "🔊" : "🔇"; $("soundBtn").setAttribute("aria-pressed", st.sound); $("soundBtn").setAttribute("aria-label", st.sound ? "Turn sound effects off" : "Turn sound effects on");
    const hs = $("heroSound"); if (hs) { hs.textContent = "Sound: " + (st.sound ? "on" : "off"); hs.setAttribute("aria-pressed", st.sound); }
  }
  function bump(el) { el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump"); }
  function addXP(n) { st.xp += n; save(); refresh(); bump($("xpPill")); }
  function award(id, xp) {
    if (st.done[id]) return false;
    st.done[id] = 1; st.xp += xp; save(); refresh(); bump($("xpPill")); confetti(48);
    if (!st.sound) return true; sfx("ok"); return true;
  }
  const has = id => !!st.done[id];
  function setStreak(ok) { streak = ok ? streak + 1 : 0; refresh(); if (ok) bump($("streakPill")); }
  function toggleSound() { st.sound = !st.sound; save(); refresh(); if (st.sound) { audio(); sfx("xp"); } }

  /* ---------------- check sheet ---------------- */
  let fbCb = null;
  function feedback(o) {
    const bar = $("fbar"); bar.className = "fbar show " + (o.ok ? "ok" : "no");
    $("fbT").textContent = o.title; $("fbB").innerHTML = o.body || "";
    const m = $("fbMascot"); m.innerHTML = mascot(o.ok ? "happy" : "sad"); m.className = "fb-mascot mascot"; void m.offsetWidth; m.classList.add(o.ok ? "hop" : "oops");
    $("fbBtn").textContent = o.btn || "Continue"; fbCb = o.onContinue || null;
    document.body.classList.add("has-fbar"); sfx(o.ok ? "ok" : "no");
    setTimeout(() => $("fbBtn").focus({ preventScroll: true }), 120);
  }
  function hideFeedback() { $("fbar").classList.remove("show"); document.body.classList.remove("has-fbar"); const cb = fbCb; fbCb = null; if (cb) cb(); }

  /* ---------------- multiple-choice card ---------------- */
  function mc(el, cfg) {
    if (!el) return;
    let sel = -1;
    const render = (solved) => {
      el.className = "mc" + (solved ? " solved" : "");
      el.innerHTML = `<div class="qhead"><span>Predict it</span><span class="xpt">${solved ? '<span class="tag-done">✓ done</span>' : "+" + cfg.xp + " XP"}</span></div><h4>${cfg.q()}</h4>
        <div class="opts">${cfg.opts().map((t, i) => `<button class="opt${solved && i === cfg.ans() ? " right" : ""}" data-i="${i}"><span class="key">${i + 1}</span><span>${t}</span></button>`).join("")}</div>
        <div class="foot">${solved ? '<button class="again">Try again</button>' : '<button class="btn" disabled>Check</button>'}</div>`;
      if (solved) { el.querySelector(".again").onclick = () => { sel = -1; render(false); }; return; }
      const btns = [...el.querySelectorAll(".opt")], chk = el.querySelector(".foot .btn");
      const pick = i => { sel = i; btns.forEach((b, j) => b.classList.toggle("sel", j === i)); btns.forEach(b => b.classList.remove("wrong")); chk.disabled = false; };
      btns.forEach((b, i) => b.onclick = () => pick(i));
      el.onkeydown = e => { const n = +e.key; if (n >= 1 && n <= btns.length) { pick(n - 1); } else if (e.key === "Enter" && sel >= 0 && document.activeElement && document.activeElement.classList.contains("opt")) { e.preventDefault(); chk.click(); } };
      chk.onclick = () => {
        if (sel < 0) return;
        if (sel === cfg.ans()) {
          setStreak(true); const first = award(cfg.id, cfg.xp); render(true); el.classList.add("solved");
          feedback({ ok: true, title: first ? `Correct! +${cfg.xp} XP` : "Correct!", body: cfg.explain() });
        } else {
          setStreak(false); btns[sel].classList.remove("sel"); btns[sel].classList.add("wrong"); chk.disabled = true; sel = -1;
          feedback({ ok: false, title: "Not quite", body: cfg.hint ? cfg.hint() : "Have another look and try again.", btn: "Try again" });
        }
      };
    };
    render(false);
  }

  /* ---------------- hero toy: two stripe grids make moiré ---------------- */
  (function hero() {
    const cv = $("heroToy"); if (!cv) return;
    const ctx = cv.getContext("2d"); let W = 0, H = 0, dpr = 1, mx = 0.5, my = 0.5, active = false, vis = true, t0 = performance.now();
    const size = () => { dpr = Math.min(2, devicePixelRatio || 1); W = cv.clientWidth; H = cv.clientHeight; cv.width = W * dpr; cv.height = H * dpr; };
    function draw(now) {
      const t = (now - t0) / 1000, ax = active ? mx : 0.5 + 0.3 * Math.sin(t * 0.5), ay = active ? my : 0.5 + 0.25 * Math.cos(t * 0.37);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.fillStyle = "#0e1b3d"; ctx.fillRect(0, 0, W, H);
      const p = 12;
      ctx.globalAlpha = 0.9;
      for (let x = 0; x < W; x += p) { ctx.fillStyle = "#ff5a5a"; ctx.fillRect(x, 0, p / 3 - 1, H); ctx.fillStyle = "#58cc02"; ctx.fillRect(x + p / 3, 0, p / 3 - 1, H); ctx.fillStyle = "#3aa8ff"; ctx.fillRect(x + 2 * p / 3, 0, p / 3 - 1, H); }
      ctx.globalAlpha = 1; ctx.save(); ctx.translate(W / 2, H / 2); ctx.rotate((ax - 0.5) * 0.5); ctx.strokeStyle = "rgba(14,27,61,.78)"; ctx.lineWidth = 5.2;
      const q = p * (0.88 + ay * 0.26), n = Math.ceil(Math.hypot(W, H) / q / 2) + 2;
      ctx.beginPath(); for (let i = -n; i <= n; i++) { ctx.moveTo(i * q, -H * 2); ctx.lineTo(i * q, H * 2); } ctx.stroke(); ctx.restore();
    }
    function loop(now) { if (vis) draw(now); if (!reduce) requestAnimationFrame(loop); }
    size(); draw(performance.now()); if (!reduce) requestAnimationFrame(loop);
    addEventListener("resize", () => { size(); draw(performance.now()); });
    const move = e => { const r = cv.getBoundingClientRect(); mx = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)); my = Math.max(0, Math.min(1, (e.clientY - r.top) / r.height)); active = true; if (reduce) draw(performance.now()); };
    cv.addEventListener("pointermove", move); cv.addEventListener("pointerdown", move);
    cv.addEventListener("pointerleave", () => { active = false; });
    if ("IntersectionObserver" in window) new IntersectionObserver(es => { vis = es[0].isIntersecting; }).observe(cv);
  })();

  /* ---------------- stage: drag the phone, see one camera pixel against the screen's pixels ---------------- */
  let stageInfo = null;
  /* stage geometry: side by side on wide screens, stacked on phones */
  function geom(W, H) {
    if (W < 520) { const topH = H * 0.5; return { narrow: true, topH, trackL: 30, trackR: W - 62, y0: topH * 0.5, zx: 10, zy: topH + 4, zw: W - 20, zh: H - topH - 14 }; }
    const split = W * 0.56; return { narrow: false, topH: H, trackL: 38, trackR: split - 62, y0: H * 0.55, zx: split + 10, zy: 12, zw: W - split - 20, zh: H - 24 };
  }
  function drawStage() {
    const cv = $("stage"); if (!cv) return;
    const dpr = Math.min(2, devicePixelRatio || 1), W = cv.clientWidth, H = cv.clientHeight; if (!W) return;
    if (cv.width !== Math.round(W * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
    const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
    const cs = getComputedStyle(root), fg = cs.getPropertyValue("--fg").trim(), muted = cs.getPropertyValue("--muted").trim(), line = cs.getPropertyValue("--line").trim();
    const info = stageInfo || { layout: "lcd_rgb", r: 0.5, dist: 25, custom: false, th: 0 };
    const G = geom(W, H), trackL = G.trackL, trackR = G.trackR, y0 = G.y0;
    ctx.font = "800 12px Nunito, system-ui, sans-serif"; ctx.textBaseline = "middle";
    /* track + ruler */
    ctx.strokeStyle = line; ctx.lineWidth = 6; ctx.lineCap = "round"; ctx.beginPath(); ctx.moveTo(trackL, y0 + 42); ctx.lineTo(trackR, y0 + 42); ctx.stroke();
    ctx.fillStyle = muted; ctx.textAlign = "center";
    for (let d = 10; d <= 60; d += 10) { const x = trackR - (d - 8) / 52 * (trackR - trackL); ctx.fillRect(x - 1, y0 + 47, 2, 6); ctx.fillText(d, x, y0 + 62); }
    ctx.textAlign = "left"; if (!G.narrow || H > 300) ctx.fillText("cm from the screen", trackL, y0 + 80);
    /* screen on the right end of the track */
    const sx = trackR + 18, sw = 22, sh = Math.min(G.topH * 0.62, 120);
    ctx.fillStyle = "#26303a"; roundRect(ctx, sx, y0 - sh / 2 + 4, sw, sh, 6); ctx.fill();
    const cols = info.layout === "pentile" ? ["#2ee66b", "#ff5a5a", "#4a8bff"] : ["#ff5a5a", "#58cc02", "#3aa8ff"];
    for (let i = 0; i < 3; i++) { ctx.fillStyle = cols[i]; ctx.fillRect(sx + 4 + i * 5.4, y0 - sh / 2 + 12, 4, sh - 16); }
    /* phone */
    const x = trackR - (info.dist - 8) / 52 * (trackR - trackL), pw = 34, ph = 62; info._px = x;
    ctx.save(); ctx.translate(x, y0 + 4);
    ctx.fillStyle = "#35414d"; roundRect(ctx, -pw / 2, -ph / 2, pw, ph, 9); ctx.fill();
    ctx.fillStyle = "#1c2630"; roundRect(ctx, -pw / 2 + 3, -ph / 2 + 3, pw - 6, ph - 6, 6); ctx.fill();
    ctx.fillStyle = "#58cc02"; ctx.beginPath(); ctx.arc(pw / 2 - 8, -ph / 2 + 10, 4.5, 0, 7); ctx.fill();
    ctx.restore();
    /* beam + distance label */
    ctx.setLineDash([5, 5]); ctx.strokeStyle = "#58cc02"; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.moveTo(x + pw / 2 + 2, y0 + 4); ctx.lineTo(sx - 3, y0 + 4); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = fg; ctx.textAlign = "center"; ctx.font = "900 15px Nunito, system-ui, sans-serif";
    ctx.fillText(info.custom ? "custom r" : Math.round(info.dist) + " cm", (x + sx) / 2, y0 - 16);
    ctx.font = "800 12px Nunito, system-ui, sans-serif";
    /* zoom panel: one camera pixel on the screen's pixel lattice */
    const zx = G.zx, zw = G.zw, zh = G.zh, zy = G.zy;
    ctx.fillStyle = "#10151b"; roundRect(ctx, zx, zy, zw, zh, 16); ctx.fill();
    ctx.save(); roundRect(ctx, zx, zy, zw, zh, 16); ctx.clip();
    const c = Math.min(30, zh / 4.2), cx0 = zx + zw / 2, cy0 = zy + zh / 2, nx = Math.ceil(zw / c / 2) + 2, ny = Math.ceil(zh / c / 2) + 2;
    for (let i = -nx; i <= nx; i++) for (let j = -ny; j <= ny; j++) {
      const px = cx0 + (i - 0.5) * c, py = cy0 + (j - 0.5) * c;
      if (info.layout === "pentile") {
        ctx.fillStyle = "#2ee66b"; ctx.beginPath(); ctx.arc(px + c * 0.5, py + c * 0.5, c * 0.14, 0, 7); ctx.fill();
        ctx.fillStyle = ((i + j) & 1) ? "#ff5a5a" : "#4a8bff"; ctx.beginPath(); ctx.arc(px + c * 0.5 + c * 0.0, py + c * 0.5 - c * 0.28, c * 0.17, 0, 7); ctx.fill();
      } else {
        const w = c / 3 - 1.2; ctx.fillStyle = "#ff5a5a"; ctx.fillRect(px + 1, py + 2, w, c * 0.82); ctx.fillStyle = "#58cc02"; ctx.fillRect(px + 1 + c / 3, py + 2, w, c * 0.82); ctx.fillStyle = "#3aa8ff"; ctx.fillRect(px + 1 + 2 * c / 3, py + 2, w, c * 0.82);
      }
    }
    const fs = info.r * c;
    ctx.translate(cx0, cy0); ctx.rotate(info.th * Math.PI / 180);
    ctx.strokeStyle = "rgba(255,255,255,.35)"; ctx.lineWidth = 1.5; ctx.setLineDash([4, 4]);
    for (let i = -3; i <= 3; i++) for (let j = -3; j <= 3; j++) if (i || j) ctx.strokeRect(-fs / 2 + i * fs, -fs / 2 + j * fs, fs, fs);
    ctx.setLineDash([]); ctx.fillStyle = "rgba(255,255,255,.18)"; ctx.fillRect(-fs / 2, -fs / 2, fs, fs);
    ctx.strokeStyle = "#ff4b4b"; ctx.lineWidth = 3.5; ctx.strokeRect(-fs / 2, -fs / 2, fs, fs);
    ctx.restore();
    const cap = W < 520 ? "one camera pixel (red)" : "one camera pixel (red) on the screen's pixels", rt = "r = " + info.r.toFixed(2);
    ctx.textAlign = "left"; const cw = ctx.measureText(cap).width;
    ctx.fillStyle = "rgba(10,15,22,.82)"; roundRect(ctx, zx + 8, zy + zh - 30, cw + 20, 22, 11); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.fillText(cap, zx + 18, zy + zh - 19);
    ctx.font = "900 15px Nunito, system-ui, sans-serif"; const rw = ctx.measureText(rt).width;
    ctx.fillStyle = "rgba(10,15,22,.82)"; roundRect(ctx, zx + zw - rw - 28, zy + 8, rw + 20, 24, 12); ctx.fill();
    ctx.textAlign = "right"; ctx.fillStyle = "#ffd36b"; ctx.fillText(rt, zx + zw - 18, zy + 20);
  }
  function roundRect(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  (function stageDrag() {
    const cv = $("stage"); if (!cv) return; let drag = false;
    const setFrom = e => {
      if (!stageInfo || stageInfo.custom) return;
      const r = cv.getBoundingClientRect(), x = e.clientX - r.left, G = geom(cv.clientWidth, cv.clientHeight), trackL = G.trackL, trackR = G.trackR;
      const d = Math.max(8, Math.min(60, Math.round(8 + (trackR - x) / (trackR - trackL) * 52))), el = $("dist");
      if (+el.value !== d) { el.value = d; el.dispatchEvent(new Event("input", { bubbles: true })); }
    };
    cv.addEventListener("pointerdown", e => { const r = cv.getBoundingClientRect(), G = geom(cv.clientWidth, cv.clientHeight); if (G.narrow ? (e.clientY - r.top > G.topH) : (e.clientX - r.left > G.zx - 4)) return; drag = true; cv.classList.add("drag"); cv.setPointerCapture(e.pointerId); setFrom(e); });
    cv.addEventListener("pointermove", e => { if (drag) setFrom(e); });
    const up = () => { drag = false; cv.classList.remove("drag"); }; cv.addEventListener("pointerup", up); cv.addEventListener("pointercancel", up);
    addEventListener("resize", drawStage);
  })();

  /* ---------------- missions + sound reacting to the live simulator ---------------- */
  let touched = false;
  const ch2 = $("ch2"); if (ch2) ["input", "pointerdown", "keydown"].forEach(ev => ch2.addEventListener(ev, e => { if (e.target && e.target.closest && e.target.closest(".controls, #stage")) touched = true; }, true));
  const ch4 = $("ch4"); let touched4 = false; if (ch4) ["input", "click"].forEach(ev => ch4.addEventListener(ev, e => { if (e.target && e.target.closest && e.target.closest(".controls, #devBtns")) touched4 = true; }, true));
  const moire = { on: false, timer: 0 };
  addEventListener("ws:sim", e => {
    const d = e.detail; stageInfo = Object.assign(stageInfo || {}, { layout: d.p.layout, r: d.r, dist: d.distCm, custom: d.p.dev === "custom", th: d.p.thetaDeg }); drawStage();
    if (touched) {
      if (d.p.dev === "laptop_lcd" && d.auc >= 0.9 && award("m2a", 10)) sfx("xp");
      if (d.p.dev === "phone_oled" && d.cam === "binned" && d.auc < 0.6 && award("m2b", 10)) sfx("xp");
      if (d.p.dev === "phone_oled" && d.cam === "full" && d.auc >= 0.9 && award("m2c", 15)) sfx("xp");
    }
    if (moire.on && !d.peaks.length) setTones("moire", []);
    else if (moire.on) {
      const vol = 0.3 * Math.pow(Math.max(0, (d.auc - 0.5) * 2), 1.2), seen = [], list = [];
      for (const pk of d.peaks) {
        const f = 200 + 1600 * Math.hypot(pk.fxf, pk.fyf); if (seen.some(s => Math.abs(s - f) / f < 0.015)) continue; seen.push(f);
        list.push({ f, g: vol * (pk.amp / d.peaks[0].amp) / (list.length + 1) }); if (list.length >= 3) break;
      }
      setTones("moire", list);
    }
  });
  addEventListener("ws:mtf", e => { const d = e.detail; if (touched4 && d.dev === "phone_oled" && d.mtf1 >= 0.5) award("m4a", 15); });
  function stopMoire() { moire.on = false; clearTimeout(moire.timer); stopTones("moire"); const b = $("hearMoire"); if (b) { b.classList.remove("playing"); b.setAttribute("aria-pressed", "false"); b.textContent = "🔊 Hear the moiré"; } }
  const hm = $("hearMoire"); if (hm) hm.onclick = () => {
    if (moire.on) { stopMoire(); return; }
    if (!audio()) { hm.textContent = "Audio not supported here"; return; }
    moire.on = true; hm.classList.add("playing"); hm.setAttribute("aria-pressed", "true"); hm.textContent = "⏹ Stop"; touched = true;
    moire.timer = setTimeout(stopMoire, 30000);
    if (WS.requestSim) WS.requestSim();
  };

  /* ---------------- chapter 3 additive synth: what the screen emits vs what the camera records ---------------- */
  (function harmonics() {
    const T = WS.theory; if (!T || !D) return; let mode = null, timer = 0;
    const btn = { emit: $("hearEmit"), cam: $("hearCam") };
    function tonesFor(kind) {
      const lay = $("aLay").value, r = +$("aR").value, sig = +$("aS").value, ss = T.sigmaScreen(r, sig), H = D.harmonics[lay], list = []; let a0max = 0;
      for (let k = 0; k < H.fx.length; k++) if (H.fy[k] === 0 && H.fx[k] > 0 && H.fx[k] <= 4) a0max = Math.max(a0max, H.amp[k]);
      for (let k = 0; k < H.fx.length; k++) {
        if (H.fy[k] !== 0 || H.fx[k] <= 0 || H.fx[k] > 4) continue;
        const fu = r * H.fx[k], a1 = H.amp[k] * T.mtf(H.fx[k], ss);
        const f = kind === "emit" ? 1000 * Math.abs(fu) : 1000 * Math.abs(T.fold(fu)), a = kind === "emit" ? H.amp[k] : a1;
        if (f > 5200) continue; list.push({ f: f < 40 ? 40 : f, g: f < 40 ? 0 : 0.28 * a / a0max });
      }
      return list.sort((x, y) => y.g - x.g).slice(0, 8);
    }
    function stop() { if (!mode) return; stopTones(mode); clearTimeout(timer); for (const k in btn) { btn[k].classList.remove("playing"); btn[k].setAttribute("aria-pressed", "false"); } btn.emit.textContent = "▶ Hear what the screen emits"; btn.cam.textContent = "▶ Hear what the camera records"; mode = null; }
    function start(kind) {
      if (mode === kind) { stop(); return; } stop(); if (!audio()) return;
      mode = kind; btn[kind].classList.add("playing"); btn[kind].setAttribute("aria-pressed", "true"); btn[kind].textContent = "⏹ Stop"; timer = setTimeout(stop, 20000);
      setTones(kind, tonesFor(kind)); if (award("h3", 5)) sfx("xp");
    }
    ["aLay", "aR", "aS"].forEach(id => $(id).addEventListener("input", () => { if (mode) setTones(mode, tonesFor(mode)); }));
    btn.emit.onclick = () => start("emit"); btn.cam.onclick = () => start("cam");
  })();

  /* ---------------- chrome: nav buttons, range fill, reveal, reset ---------------- */
  function paintRange(el) { const mn = +el.min || 0, mx = +el.max || 100; el.style.setProperty("--p", (100 * (+el.value - mn) / (mx - mn)) + "%"); }
  document.addEventListener("input", e => { if (e.target && e.target.type === "range") paintRange(e.target); }, true);
  document.querySelectorAll("input[type=range]").forEach(paintRange);
  $("themeBtn").onclick = toggleTheme; $("soundBtn").onclick = toggleSound; if ($("heroSound")) $("heroSound").onclick = toggleSound;
  $("startBtn").onclick = () => $("ch1").scrollIntoView({ behavior: reduce ? "auto" : "smooth" });
  $("fbBtn").onclick = hideFeedback;
  document.addEventListener("keydown", e => { if (e.key === "Escape" && $("fbar").classList.contains("show")) hideFeedback(); });
  $("resetBtn").onclick = () => location.reload();
  addEventListener("pageshow", e => { if (e.persisted) location.reload(); });   /* back/forward cache: start fresh too */
  if ("IntersectionObserver" in window && !reduce) {
    const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { rootMargin: "0px 0px -6% 0px" });
    document.querySelectorAll("section.chapter > *").forEach(el => { el.classList.add("reveal"); io.observe(el); });
  }

  /* make the pieces main.js needs available */
  WS.play = { award, has, addXP, setStreak, feedback, hideFeedback, mc, sfx, confetti, mascot, refresh, drawStage, REQUIRED };
  refresh();
})();
