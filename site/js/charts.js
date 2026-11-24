/* Tiny canvas chart library (no dependencies): line / band / stem charts and grouped bar charts. */
(function (g) {
  const WS = g.WS = g.WS || {};
  const registry = [];                                   // redraw callbacks (theme change, resize)

  function theme() {
    const cs = getComputedStyle(document.documentElement), v = n => cs.getPropertyValue(n).trim();
    return { fg: v("--fg"), muted: v("--muted"), grid: v("--grid"), bg: v("--card"), c1: v("--c1"), c2: v("--c2"), c3: v("--c3"), c4: v("--c4"), good: v("--good"), bad: v("--bad") };
  }

  function setup(canvas) {
    const dpr = window.devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    const ctx = canvas.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h); canvas._hits = [];
    return { ctx, w, h, th: theme() };
  }

  function niceTicks(lo, hi, n = 6) {
    const span = hi - lo, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) || raw;
    const out = []; for (let t = Math.ceil(lo / step - 1e-9) * step; t <= hi + 1e-9; t += step) out.push(+t.toFixed(10));
    return out;
  }

  function frame(S, o) {
    const { ctx, w, h, th } = S, m = { l: 56, r: 16, t: o.title ? 30 : 14, b: 46 };
    const px = v => m.l + (v - o.xmin) / (o.xmax - o.xmin) * (w - m.l - m.r);
    const py = v => h - m.b - (v - o.ymin) / (o.ymax - o.ymin) * (h - m.t - m.b);
    ctx.font = "12px Nunito, 'Segoe UI', system-ui, sans-serif"; ctx.textBaseline = "middle";
    ctx.strokeStyle = th.grid; ctx.fillStyle = th.muted; ctx.lineWidth = 1;
    for (const t of (o.yticks || niceTicks(o.ymin, o.ymax, 5))) {
      ctx.beginPath(); ctx.moveTo(m.l, py(t)); ctx.lineTo(w - m.r, py(t)); ctx.stroke();
      ctx.textAlign = "right"; ctx.fillText((o.yfmt || (x => +x.toFixed(3)))(t), m.l - 8, py(t));
    }
    for (const t of (o.xticks || niceTicks(o.xmin, o.xmax, 7))) {
      ctx.beginPath(); ctx.moveTo(px(t), m.t); ctx.lineTo(px(t), h - m.b); ctx.stroke();
      ctx.textAlign = "center"; ctx.fillText((o.xfmt || (x => +x.toFixed(3)))(t), px(t), h - m.b + 14);
    }
    ctx.strokeStyle = th.muted; ctx.beginPath(); ctx.moveTo(m.l, m.t); ctx.lineTo(m.l, h - m.b); ctx.lineTo(w - m.r, h - m.b); ctx.stroke();
    ctx.fillStyle = th.fg; ctx.textAlign = "center";
    if (o.xlabel) ctx.fillText(o.xlabel, (m.l + w - m.r) / 2, h - 10);
    if (o.ylabel) { ctx.save(); ctx.translate(14, (m.t + h - m.b) / 2); ctx.rotate(-Math.PI / 2); ctx.fillText(o.ylabel, 0, 0); ctx.restore(); }
    if (o.title) { ctx.textAlign = "left"; ctx.font = "600 13px Nunito, 'Segoe UI', system-ui, sans-serif"; ctx.fillText(o.title, m.l, 14); }
    ctx.font = "12px Nunito, 'Segoe UI', system-ui, sans-serif";
    return { px, py, m };
  }

  function legend(S, items, x, y) {
    const { ctx, th } = S; ctx.font = "12px Nunito, 'Segoe UI', system-ui, sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
    const wmax = Math.max(...items.map(i => ctx.measureText(i.label).width)) + 34, hh = items.length * 17 + 8;
    ctx.fillStyle = th.bg; ctx.globalAlpha = 0.88; ctx.fillRect(x, y, wmax + 8, hh); ctx.globalAlpha = 1;
    items.forEach((it, k) => {
      const yy = y + 12 + k * 17; ctx.strokeStyle = it.color; ctx.fillStyle = it.color; ctx.lineWidth = 2.2;
      if (it.dash) ctx.setLineDash(it.dash); ctx.beginPath(); ctx.moveTo(x + 6, yy); ctx.lineTo(x + 24, yy); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = th.fg; ctx.fillText(it.label, x + 30, yy);
    });
  }

  /** o: {xmin,xmax,ymin,ymax,xlabel,ylabel,title, bands:[{x0,x1,color,label}], hlines:[{y,label,color,dash}], vlines:[{x,label,color}],
          series:[{x,y,color,label,ci:[[lo,hi]...],dash,marker,width,fill}], stems:[{x,y,color,width}], curve:{f,x0,x1,color,label}, legendPos} */
  function lineChart(canvas, o) {
    const S = setup(canvas), { ctx, th } = S, F = frame(S, o);
    ctx.save(); ctx.beginPath(); ctx.rect(F.m.l, F.m.t, S.w - F.m.l - F.m.r, S.h - F.m.t - F.m.b); ctx.clip();
    for (const b of o.bands || []) { ctx.fillStyle = b.color; ctx.globalAlpha = b.alpha || 0.14; ctx.fillRect(F.px(b.x0), F.m.t, F.px(b.x1) - F.px(b.x0), S.h - F.m.t - F.m.b); ctx.globalAlpha = 1; }
    for (const b of o.hbands || []) { ctx.fillStyle = b.color; ctx.globalAlpha = b.alpha || 0.12; ctx.fillRect(F.m.l, F.py(b.y1), S.w - F.m.l - F.m.r, F.py(b.y0) - F.py(b.y1)); ctx.globalAlpha = 1; }
    for (const hl of o.hlines || []) { ctx.strokeStyle = hl.color || th.muted; ctx.setLineDash(hl.dash || [5, 4]); ctx.lineWidth = 1.2; ctx.beginPath(); ctx.moveTo(F.m.l, F.py(hl.y)); ctx.lineTo(S.w - F.m.r, F.py(hl.y)); ctx.stroke(); ctx.setLineDash([]); }
    for (const vl of o.vlines || []) { ctx.strokeStyle = vl.color || th.muted; ctx.setLineDash(vl.dash || [5, 4]); ctx.lineWidth = 1.4; ctx.beginPath(); ctx.moveTo(F.px(vl.x), F.m.t); ctx.lineTo(F.px(vl.x), S.h - F.m.b); ctx.stroke(); ctx.setLineDash([]); }
    ctx.restore();
    for (const b of o.bands || []) if (b.label) { ctx.fillStyle = th.fg; ctx.font = "11px Nunito, 'Segoe UI', system-ui, sans-serif"; ctx.textAlign = "center"; ctx.fillText(b.label, (F.px(b.x0) + F.px(b.x1)) / 2, F.m.t + 9 + (b.row || 0) * 13); }
    for (const b of o.hbands || []) if (b.label) { ctx.fillStyle = th.fg; ctx.font = "11px Nunito, 'Segoe UI', system-ui, sans-serif"; ctx.textAlign = b.align === "right" ? "right" : "left"; ctx.fillText(b.label, b.align === "right" ? S.w - F.m.r - 8 : F.m.l + 8, F.py(b.y0) - 8); }
    for (const hl of o.hlines || []) if (hl.label) { ctx.fillStyle = hl.color || th.muted; ctx.font = "11px Nunito, 'Segoe UI', system-ui, sans-serif"; ctx.textAlign = hl.align === "right" ? "right" : "left"; ctx.fillText(hl.label, hl.align === "right" ? S.w - F.m.r - 6 : F.m.l + 6, F.py(hl.y) + (hl.below ? 12 : -7)); }
    for (const vl of o.vlines || []) if (vl.label) { ctx.fillStyle = vl.color || th.muted; ctx.font = "11px Nunito, 'Segoe UI', system-ui, sans-serif"; ctx.textAlign = "left"; ctx.fillText(vl.label, F.px(vl.x) + 5, S.h - F.m.b - 10); }
    ctx.font = "12px Nunito, 'Segoe UI', system-ui, sans-serif";
    for (const s of o.series || []) {
      if (s.ci) { ctx.fillStyle = s.color; ctx.globalAlpha = 0.16; ctx.beginPath(); s.x.forEach((x, i) => ctx[i ? "lineTo" : "moveTo"](F.px(x), F.py(s.ci[i][1])));
        for (let i = s.x.length - 1; i >= 0; i--) ctx.lineTo(F.px(s.x[i]), F.py(s.ci[i][0])); ctx.closePath(); ctx.fill(); ctx.globalAlpha = 1; }
      if (s.line !== false) {
        ctx.strokeStyle = s.color; ctx.lineWidth = s.width || 2.2; ctx.setLineDash(s.dash || []); ctx.beginPath();
        s.x.forEach((x, i) => ctx[i ? "lineTo" : "moveTo"](F.px(x), F.py(s.y[i]))); ctx.stroke(); ctx.setLineDash([]);
      }
      if (s.marker !== false) s.x.forEach((x, i) => {
        ctx.fillStyle = s.color; ctx.beginPath(); ctx.arc(F.px(x), F.py(s.y[i]), 3.4, 0, 7); ctx.fill();
        canvas._hits.push({ x: F.px(x), y: F.py(s.y[i]), text: `${s.label || ""}: x = ${(+x).toFixed(2)}, y = ${(+s.y[i]).toFixed(3)}${s.ci ? ` (95% CI ${s.ci[i][0].toFixed(2)}–${s.ci[i][1].toFixed(2)})` : ""}` });
      });
    }
    if (o.curve) { const c = o.curve; ctx.strokeStyle = c.color; ctx.lineWidth = 2.2; ctx.setLineDash(c.dash || []); ctx.beginPath();
      for (let k = 0; k <= 240; k++) { const x = c.x0 + (c.x1 - c.x0) * k / 240; ctx[k ? "lineTo" : "moveTo"](F.px(x), F.py(c.f(x))); } ctx.stroke(); ctx.setLineDash([]); }
    for (const st of o.stems || []) { ctx.strokeStyle = st.color; ctx.lineWidth = st.width || 2; ctx.globalAlpha = st.alpha || 1; ctx.beginPath(); ctx.moveTo(F.px(st.x), F.py(0)); ctx.lineTo(F.px(st.x), F.py(st.y)); ctx.stroke();
      ctx.fillStyle = st.color; ctx.beginPath(); ctx.arc(F.px(st.x), F.py(st.y), 3, 0, 7); ctx.fill(); ctx.globalAlpha = 1; if (st.tip) canvas._hits.push({ x: F.px(st.x), y: F.py(st.y), text: st.tip }); }
    const leg = [...(o.series || []).filter(s => s.label).map(s => ({ label: s.label, color: s.color, dash: s.dash })), ...(o.curve && o.curve.label ? [{ label: o.curve.label, color: o.curve.color, dash: o.curve.dash }] : []), ...(o.legendExtra || [])];
    if (leg.length) legend(S, leg, o.legendPos === "left" ? F.m.l + 8 : S.w - F.m.r - 8 - (Math.max(...leg.map(i => ctx.measureText(i.label).width)) + 42), (o.legendY || F.m.t + 8) + (o.bands && o.bands.some(b => b.label) ? 14 : 0));
    attachTips(canvas);
    return F;
  }

  /** o: {groups:[labels], series:[{name,color,values,ci}], ymin,ymax,ylabel,hline} */
  function barChart(canvas, o) {
    const S = setup(canvas), { ctx, th } = S;
    const F = frame(S, { xmin: 0, xmax: o.groups.length, ymin: o.ymin ?? 0, ymax: o.ymax ?? 1, ylabel: o.ylabel, xticks: [], title: o.title });
    if (o.hline != null) { ctx.strokeStyle = th.muted; ctx.setLineDash([5, 4]); ctx.beginPath(); ctx.moveTo(F.m.l, F.py(o.hline)); ctx.lineTo(S.w - F.m.r, F.py(o.hline)); ctx.stroke(); ctx.setLineDash([]); }
    const ns = o.series.length, bw = 0.7 / ns;
    o.groups.forEach((gl, gi) => {
      ctx.fillStyle = th.fg; ctx.textAlign = "center"; ctx.font = "12px Nunito, 'Segoe UI', system-ui, sans-serif"; ctx.fillText(gl, F.px(gi + 0.5), S.h - F.m.b + 16);
      o.series.forEach((s, si) => {
        const x0 = gi + 0.15 + si * bw, v = s.values[gi];
        ctx.fillStyle = s.color; ctx.fillRect(F.px(x0), F.py(v), F.px(x0 + bw * 0.92) - F.px(x0), F.py(o.ymin ?? 0) - F.py(v));
        if (s.ci && s.ci[gi]) { const xc = F.px(x0 + bw * 0.46); ctx.strokeStyle = th.fg; ctx.lineWidth = 1.4; ctx.beginPath(); ctx.moveTo(xc, F.py(s.ci[gi][0])); ctx.lineTo(xc, F.py(s.ci[gi][1])); ctx.stroke(); }
        ctx.fillStyle = th.fg; ctx.textAlign = "center"; ctx.font = "11px Nunito, 'Segoe UI', system-ui, sans-serif"; ctx.fillText(v.toFixed(2), F.px(x0 + bw * 0.46), F.py(v) - 9);
        canvas._hits.push({ x: F.px(x0 + bw * 0.46), y: F.py(v), text: `${gl} - ${s.name}: ${v.toFixed(3)}${s.ci && s.ci[gi] ? ` (95% CI ${s.ci[gi][0].toFixed(2)}–${s.ci[gi][1].toFixed(2)})` : ""}` });
      });
    });
    legend(S, o.series.map(s => ({ label: s.name, color: s.color })), S.w - F.m.r - 8 - (Math.max(...o.series.map(s => ctx.measureText(s.name).width)) + 42), F.m.t + 6);
    if (o.hline != null) {                                           // label drawn last, on a small background, so bars never hide it
      const txt = o.hlineLabel || "chance", y = F.py(o.hline) + 12; ctx.font = "11px Nunito, 'Segoe UI', system-ui, sans-serif"; ctx.textAlign = "left";
      const w = ctx.measureText(txt).width + 8; ctx.fillStyle = th.bg; ctx.globalAlpha = 0.9; ctx.fillRect(F.m.l + 4, y - 9, w, 14); ctx.globalAlpha = 1;
      ctx.fillStyle = th.muted; ctx.fillText(txt, F.m.l + 8, y);
    }
    attachTips(canvas);
  }

  /* ----- hover tooltips ----- */
  let tip;
  function attachTips(canvas) {
    if (!tip) { tip = document.createElement("div"); tip.className = "tip"; document.body.appendChild(tip); }
    if (canvas._tipBound) return; canvas._tipBound = true;
    canvas.addEventListener("mousemove", e => {
      const r = canvas.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
      let best = null, bd = 14 * 14;
      for (const h of canvas._hits || []) { const d = (h.x - x) ** 2 + (h.y - y) ** 2; if (d < bd) { bd = d; best = h; } }
      if (best) { tip.textContent = best.text; tip.style.display = "block"; tip.style.left = e.clientX + 12 + "px"; tip.style.top = e.clientY + 12 + window.scrollY + "px"; }
      else tip.style.display = "none";
    });
    canvas.addEventListener("mouseleave", () => { tip.style.display = "none"; });
  }

  /** Register a draw function so it is repainted on resize / theme change. */
  function register(fn) { registry.push(fn); fn(); }
  function redrawAll() { registry.forEach(f => { try { f(); } catch (e) { console.error(e); } }); }
  let rt; window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(redrawAll, 120); });
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => setTimeout(redrawAll, 50));

  WS.charts = { theme, setup, frame, legend, lineChart, barChart, register, redrawAll, niceTicks };
})(window);
