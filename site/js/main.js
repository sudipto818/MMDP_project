/* Page logic: wires every chapter to window.DATA (data/data.js) and the live simulator. */
(function () {
  const D = window.DATA, WS = window.WS, T = WS.theory, S = WS.sim, CH = WS.charts;
  const R = D.results, M = D.meta, N = M.out;
  const $ = id => document.getElementById(id);
  /* presentation layer (js/play.js): XP, check sheet, sound. The stub keeps the page working if it is missing. */
  const P = WS.play || { award() { return false; }, has() { return false; }, addXP() {}, setStreak() {}, feedback() {}, hideFeedback() {}, mc() {}, drawStage() {} };
  const emit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }));
  const f2 = (x, d = 2) => Number.isFinite(x) ? x.toFixed(d) : "n/a";
  const DEV = Object.keys(M.devices);
  const SHORT = { laptop_lcd: "Laptop LCD", monitor_lcd: "Monitor LCD", phone_oled: "Phone OLED" };
  const LAYLABEL = { lcd_rgb: "LCD stripes", pentile: "OLED PenTile" };
  const DEVCOL = () => { const t = CH.theme(); return { laptop_lcd: t.c1, monitor_lcd: t.c4, phone_oled: t.c3 }; };
  const LAYCOL = () => { const t = CH.theme(); return { lcd_rgb: t.c1, pentile: t.c2 }; };
  const E1 = R.E1.devices, E2 = R.E2, E3 = R.E3, E4 = R.E4, E5 = R.E5, E6 = R.E6;
  const r90 = { lcd_rgb: E2.lcd_rgb.r90_measured, pentile: E2.pentile.r90_measured };

  /* ================= chapter 1: stat cards + guessing game ================= */
  const lap = E1.laptop_lcd, mon = E1.monitor_lcd, pho = E1.phone_oled;
  const iNear = (target) => E4.r.reduce((b, v, i) => Math.abs(v - target) < Math.abs(E4.r[b] - target) ? i : b, 0);
  const phoClass = pho.auc_B < 0.6 ? "bad" : "good";
  $("statCards").innerHTML = [
    ["good", f2(lap.auc_B), `Laptop LCD screen photos caught at typical distances (AUC, 1.0 = perfect; r ${f2(lap.r_min)}–${f2(lap.r_max)})`],
    [phoClass, f2(pho.auc_B), `Phone OLED screen photos, same detector, trained on all three screens (0.5 = chance; r ${f2(pho.r_min)}–${f2(pho.r_max)})`],
    ["", `${f2(r90.lcd_rgb)} / ${f2(r90.pentile)}`, "r where detection drops below AUC 0.9 in the matched-r control (LCD / PenTile)"],
    ["", `${Math.round(100 * Math.max(...E4.acc_logistic.slice(0, 3)))}%`, `accuracy of telling LCD from PenTile when the lattice survives (r ≤ 0.7); still ${Math.round(100 * E4.acc_logistic[iNear(1.1)])}% at r ≈ 1.1 (from colour structure), chance (50%) by r ≈ 1.4–1.8`],
  ].map(([c, big, lbl]) => `<div class="stat"><div class="big ${c}">${big}</div><div class="lbl">${lbl}</div></div>`).join("");

  (function guess() {
    /* a round = a random LCD example (clearly resolved lattice) and a random side for the screen photo; "Try another" starts a new round */
    const pool = D.examples.filter(e => e.layout === "lcd_rgb" && e.r <= 0.5);
    let ex, screenFirst, imgs, specs, truth, showSpec, answered;
    const draw = () => { $("guess").innerHTML = imgs.map((n, i) => `<div class="fig${answered && i === truth ? " win" : ""}"><img class="px" src="img/${showSpec ? specs[i] : n}.png" alt=""><div class="cap"><b>${"AB"[i]}</b>${showSpec ? " spectrum" : ""}${answered && i === truth ? " · the screen" : ""}</div></div>`).join(""); };
    function newRound() {
      ex = pool.length ? pool[Math.floor(Math.random() * pool.length)] : D.examples[2];
      screenFirst = Math.random() < 0.5; truth = screenFirst ? 0 : 1;
      imgs = screenFirst ? [ex.id + "_rec", ex.id + "_dir"] : [ex.id + "_dir", ex.id + "_rec"];
      specs = screenFirst ? [ex.id + "_spec", ex.id + "_specdir"] : [ex.id + "_specdir", ex.id + "_spec"];
      showSpec = false; answered = false; draw();
      $("guessMsg").textContent = ""; $("guessAgain").hidden = true;
      document.querySelectorAll("#ch1 button[data-g]").forEach(b => { b.disabled = false; });
    }
    document.querySelectorAll("#ch1 button[data-g]").forEach(b => b.onclick = () => {
      if (answered) return; answered = true; const pick = +b.dataset.g, ok = pick === truth;
      $("guessMsg").textContent = ok ? "Correct. Did you see any difference by eye?" : `Not quite: the photo of the screen is ${"AB"[truth]}. It is hard to tell by eye.`;
      showSpec = true; draw(); $("guessAgain").hidden = false;
      document.querySelectorAll("#ch1 button[data-g]").forEach(x => { x.disabled = true; });
      P.setStreak(ok); const first = P.award("g1", ok ? 15 : 5);
      P.feedback({ ok, title: ok ? (first ? "Correct! +15 XP" : "Correct!") : "Not quite", body: ok ? "Did you see any difference by eye? The spectra now show the screen's bright moiré spots." : `The photo of the screen is <b>${"AB"[truth]}</b>. Look at the spectra: only the screen photo has isolated bright spots.`, btn: "Continue" });
    });
    $("guessAgain").onclick = newRound;
    $("guessReveal").onclick = () => { showSpec = !showSpec; draw(); };
    newRound();
  })();

  /* ================= chapter 2: live simulator ================= */
  const sc = $("scn"); S.scenes.forEach((s, i) => sc.add(new Option(`${s.name} (${s.w}×${s.h})`, i)));
  const dev = $("dev");
  let pending = false, last = null;

  function params() {
    const th = +$("th").value, sigma = +$("sg").value, scene = +$("scn").value, d = dev.value, custom = d === "custom";
    const layout = custom ? $("lay").value : M.devices[d].layout;
    let r, note = "";
    if (custom) r = +$("rr").value;
    else {
      const px = M.camera.px_um[$("cam").value];
      r = T.rFromGeometry(M.devices[d].pitch_mm, M.camera.f_mm, +$("dist").value * 10, px);
    }
    const rmax = S.maxR(th * Math.PI / 180, sigma, S.scenes[scene].h) * 0.995;
    if (r > rmax) { r = rmax; note = " (clamped)"; }
    if (r < 0.15) { r = 0.15; note = " (clamped)"; }
    return { layout, r, thetaDeg: th, sigma, scene, note, dev: d };
  }

  function putImage(canvas, rgb) {
    const ctx = canvas.getContext("2d"), im = ctx.createImageData(N, N);
    for (let i = 0; i < N * N; i++) { im.data[i * 4] = rgb[i * 3] * 255; im.data[i * 4 + 1] = rgb[i * 3 + 1] * 255; im.data[i * 4 + 2] = rgb[i * 3 + 2] * 255; im.data[i * 4 + 3] = 255; }
    ctx.putImageData(im, 0, 0);
  }
  function putSpectrum(canvas, Rr) { const im = new ImageData(S.spectrumImage(Rr), N, N); canvas.getContext("2d").putImageData(im, 0, 0); }

  function drawOverlay(cv, peaks) {
    const ctx = cv.getContext("2d"); ctx.clearRect(0, 0, 256, 256);
    if (!peaks) return;
    peaks.forEach((p, k) => { ctx.strokeStyle = k < 3 ? "#3ee8ff" : "rgba(62,232,255,.65)"; ctx.lineWidth = k < 3 ? 2.2 : 1.4; ctx.beginPath(); ctx.arc(p.col * 2 + 1, p.row * 2 + 1, 8, 0, 7); ctx.stroke(); });
  }

  function drawSubpixels(layout, scene) {
    const cv = $("cvSub"), ctx = cv.getContext("2d"), sc = S.scenes[scene], n = 12, cell = 20, o = Math.floor(sc.h / 2) - 6;
    ctx.fillStyle = "#000"; ctx.fillRect(0, 0, cv.width, cv.height);
    const subs = D.layouts[layout];
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) for (const sp of subs) {
      if (sp.parity !== null && ((i + j) & 1) !== sp.parity) continue;
      const v = S.lin2srgb(sc.lin[((o + i) * sc.w + (o + j)) * 3 + sp.channel]) * 255;
      ctx.fillStyle = `rgb(${sp.channel === 0 ? v : 0},${sp.channel === 1 ? v : 0},${sp.channel === 2 ? v : 0})`;
      ctx.fillRect(j * cell + sp.x0 * cell, i * cell + sp.y0 * cell, (sp.x1 - sp.x0) * cell, (sp.y1 - sp.y0) * cell);
    }
  }

  function update() {
    pending = false;
    const p = params(), cap = S.capture(p), th = p.thetaDeg * Math.PI / 180;
    last = { p, cap };
    putImage($("cvScr"), cap.scr); putImage($("cvDir"), cap.dir); putSpectrum($("cvSpecScr"), cap.specScr); putSpectrum($("cvSpecDir"), cap.specDir);
    const peaks8 = T.predictedPeaks(p.layout, p.r, th, p.sigma, 8, true, true);
    last.peaks8 = peaks8;
    const peaks = $("peaks").checked ? peaks8.map(e => ({ row: e.row, col: e.col })) : null;
    drawOverlay($("ovScr"), peaks);
    drawSubpixels(p.layout, p.scene);
    const ss = T.sigmaScreen(p.r, p.sigma), auc = T.predictedAUC(p.layout, p.r, p.sigma, th);
    const verdict = auc >= 0.9 ? ["good", "Predicted: this photo of a screen would be caught (the lattice survives the lens)."] :
      auc >= 0.6 ? ["mid", "Predicted: borderline. Some trace survives."] : ["bad", "Predicted: invisible. The lens removed the screen's lattice before the camera sampled it."];
    $("readout").innerHTML = `
      <div class="row"><span>r = camera pixel / screen pixel</span><b>${f2(p.r, 3)}${p.note}</b></div>
      <div class="row"><span>lens + aperture blur σ<sub>s</sub> (screen px)</span><b>${f2(ss, 3)}</b></div>
      <div class="row"><span>lens response at the lattice frequency (f = 1)</span><b>${(100 * T.mtf(1, ss)).toPrecision(2)}%</b></div>
      <div class="row"><span>strongest surviving moiré (theory)</span><b>${f2(T.theoryAmp(p.layout, p.r, p.sigma, th, true, !!E3.primary_bayer), 4)}</b></div>
      <div class="row"><span>predicted detection AUC (fit E3)</span><b>${f2(auc)}</b></div>
      <div class="row"><span>peakiness: screen photo / real scene</span><b>${f2(cap.peakScr)} / ${f2(cap.peakDir)}</b></div>
      <div class="verdict ${verdict[0]}">${verdict[1]}</div>`;
    $("vDist").textContent = $("dist").value + " cm"; $("vR").textContent = f2(+$("rr").value); $("vTh").textContent = $("th").value + "°"; $("vSg").textContent = f2(+$("sg").value);
    emit("ws:sim", { p, auc, r: p.r, cam: $("cam").value, distCm: +$("dist").value, peaks: peaks8 });
  }
  const schedule = () => { if (!pending) { pending = true; requestAnimationFrame(() => setTimeout(update, 0)); } };
  WS.requestSim = schedule;

  /* hover / tap the screen photo's spectrum: which harmonic made the spot under the pointer? (pure read-out of the same theory table) */
  (function probe() {
    const box = $("stackScr"), hint = $("specHint"), idle = hint.innerHTML;
    const show = e => {
      if (!last) return;
      const rc = box.getBoundingClientRect(), col = Math.floor((e.clientX - rc.left) / rc.width * N), row = Math.floor((e.clientY - rc.top) / rc.height * N);
      const u = (col - N / 2) / N, v = (row - N / 2) / N;
      let best = null, bd = 1e9; for (const pk of last.peaks8 || []) { const d = Math.hypot(pk.col - col, pk.row - row); if (d < bd) { bd = d; best = pk; } }
      if (best && bd <= 4.5) {
        const raw = T.toCameraFreq(best.fxs, best.fys, last.p.r, last.p.thetaDeg * Math.PI / 180), beyond = Math.max(Math.abs(raw[0]), Math.abs(raw[1])) > 0.5;
        hint.innerHTML = `<b>Predicted spot.</b> Screen harmonic (${f2(best.fxs, 2)}, ${f2(best.fys, 2)}) cycles per screen pixel lands at (${f2(raw[0], 2)}, ${f2(raw[1], 2)}) cycles per camera pixel` + (beyond ? ` — beyond Nyquist (±0.5), so aliasing folds it to <b>(${f2(best.fxf, 2)}, ${f2(best.fyf, 2)})</b>.` : `, inside the camera band: no folding needed.`) + ` Predicted strength ${f2(best.amp, 4)}.`;
      } else hint.innerHTML = `Frequency (${f2(u, 2)}, ${f2(v, 2)}) cycles per camera pixel: none of the 8 strongest predicted harmonics lands here.`;
    };
    box.addEventListener("pointermove", show); box.addEventListener("pointerdown", show);
    box.addEventListener("pointerleave", () => { hint.innerHTML = idle; });
  })();
  function syncVisibility() {
    const c = dev.value === "custom";
    $("lblDist").style.display = c ? "none" : ""; $("lblCam").style.display = c ? "none" : "";
    $("lblR").style.display = c ? "" : "none"; $("lblLay").style.display = c ? "" : "none";
  }
  ["dev", "cam", "dist", "lay", "rr", "th", "sg", "scn", "peaks"].forEach(id => $(id).addEventListener("input", () => { syncVisibility(); schedule(); }));
  syncVisibility(); update();

  /* ================= chapter 3: aliasing picture ================= */
  function drawAlias() {
    const lay = $("aLay").value, r = +$("aR").value, sig = +$("aS").value, ss = T.sigmaScreen(r, sig), H = D.harmonics[lay], th = CH.theme();
    $("vAr").textContent = f2(r); $("vAs").textContent = f2(sig);
    const stems = []; let ymax = 0;
    for (let k = 0; k < H.fx.length; k++) {
      if (H.fy[k] !== 0 || H.fx[k] === 0 || Math.abs(H.fx[k]) > 4) continue;
      const fu = r * H.fx[k], a0 = H.amp[k], a1 = a0 * T.mtf(Math.abs(H.fx[k]), ss), ff = T.fold(fu); ymax = Math.max(ymax, a0);
      if (Math.abs(fu) > 4.2) continue;
      stems.push({ x: fu, y: a0, color: th.muted, alpha: 0.45, width: 2, tip: `harmonic f = ${H.fx[k]} cycles/screen px → ${f2(fu)} cycles/camera px, before the lens: ${f2(a0, 3)}` });
      const inside = Math.abs(fu) <= 0.5;
      stems.push({ x: fu, y: a1, color: inside ? th.c1 : th.bad, width: 3.2, tip: `after the lens: ${f2(a1, 4)} (${inside ? "inside" : "beyond"} the Nyquist band)` });
      if (!inside) stems.push({ x: ff, y: a1, color: th.c2, width: 3.2, alpha: 0.95, tip: `aliased copy of f = ${H.fx[k]}: folds to ${f2(ff, 3)} cycles/camera px (amplitude ${f2(a1, 4)})` });
    }
    CH.lineChart($("cvAlias"), { xmin: -4, xmax: 4, ymin: 0, ymax: Math.max(ymax * 1.12, 0.1), xlabel: "camera frequency (cycles per camera pixel), x-axis only",
      ylabel: "harmonic amplitude", bands: [{ x0: -0.5, x1: 0.5, color: th.good, alpha: 0.16, label: "camera Nyquist band" }], stems,
      legendExtra: [{ label: "before the lens", color: th.muted }, { label: "after lens, inside band", color: th.c1 }, { label: "after lens, beyond Nyquist", color: th.bad }, { label: "alias folded back inside", color: th.c2 }], legendPos: "left" });
  }
  ["aLay", "aR", "aS"].forEach(id => $(id).addEventListener("input", () => CH.redrawAll()));
  CH.register(drawAlias);

  /* ================= chapter 4 ================= */
  const devBtns = $("devBtns"); let dev4 = "laptop_lcd";
  DEV.forEach(k => { const b = document.createElement("button"); b.textContent = M.devices[k].label; b.dataset.k = k; b.onclick = () => { dev4 = k; CH.redrawAll(); }; devBtns.appendChild(b); });
  ["d4", "cam4"].forEach(id => $(id).addEventListener("input", () => CH.redrawAll()));
  function drawMtf() {
    const th = CH.theme(), d = M.devices[dev4], dist = +$("d4").value, px = M.camera.px_um[$("cam4").value];
    document.querySelectorAll("#devBtns button").forEach(b => b.classList.toggle("on", b.dataset.k === dev4));
    $("vD4").textContent = dist + " cm";
    const r = T.rFromGeometry(d.pitch_mm, M.camera.f_mm, dist * 10, px), ss = T.sigmaScreen(r, 0.4), H = D.harmonics[d.layout];
    const order = [...H.amp.keys()].filter(k => H.fx[k] * H.fx[k] + H.fy[k] * H.fy[k] > 0).sort((a, b) => H.amp[b] - H.amp[a]);
    const seen = new Set(), stems = [];
    for (const k of order) {
      const f = +Math.hypot(H.fx[k], H.fy[k]).toFixed(4); if (seen.has(f) || f > 3.2) continue; seen.add(f);
      stems.push({ x: f, y: H.amp[k], color: th.muted, alpha: 0.5, width: 2, tip: `harmonic |f| = ${f2(f, 2)}: ${f2(H.amp[k], 3)} before the lens` });
      stems.push({ x: f, y: H.amp[k] * T.mtf(f, ss), color: DEVCOL()[dev4], width: 3.2, tip: `after the lens: ${f2(H.amp[k] * T.mtf(f, ss), 4)}` });
      if (seen.size >= 9) break;
    }
    CH.lineChart($("cvMtf"), { xmin: 0, xmax: 3.2, ymin: 0, ymax: 1.0, xlabel: "frequency (cycles per screen pixel)", ylabel: "amplitude / lens response",
      curve: { f: x => T.mtf(x, ss), x0: 0, x1: 3.2, color: th.c4, label: "lens response (MTF)" }, stems,
      legendExtra: [{ label: "harmonic before the lens", color: th.muted }, { label: "harmonic after the lens", color: DEVCOL()[dev4] }] });
    emit("ws:mtf", { dev: dev4, mtf1: T.mtf(1, ss), cam: $("cam4").value });
    $("mtfText").innerHTML = `<b>${d.label}</b> at ${dist} cm, ${dev4 === "phone_oled" ? $("cam4").value + " camera pixels" : "same phone camera (" + $("cam4").value + " pixels)"}: r = <b>${f2(r, 2)}</b>, σ<sub>s</sub> = ${f2(ss, 2)} screen px. The lens passes <b>${(100 * T.mtf(1, ss)).toPrecision(2)}%</b> of the pixel-frequency harmonic (f = 1) and ${(100 * T.mtf(0.5, ss)).toPrecision(2)}% at f = ½.`;
  }
  CH.register(drawMtf);

  CH.register(function drawE1() {
    const th = CH.theme();
    CH.barChart($("cvE1"), { groups: DEV.map(k => SHORT[k]), ymin: 0.4, ymax: 1.08, ylabel: "AUC (test scenes)", hline: 0.5, hlineLabel: "chance",
      series: [{ name: "A: trained on LCD only", color: th.c1, values: DEV.map(k => E1[k].auc_A), ci: DEV.map(k => E1[k].ci_A) },
               { name: "B: trained on all three", color: th.c2, values: DEV.map(k => E1[k].auc_B), ci: DEV.map(k => E1[k].ci_B) }] });
    $("e1Text").innerHTML = `Test AUC of a small logistic detector on photos taken at 15–40 cm. Phone OLED screens land at r ≈ ${f2(pho.r_min)}–${f2(pho.r_max)}, laptop LCD at ${f2(lap.r_min)}–${f2(lap.r_max)}. ` +
      (pho.auc_B < 0.6 ? `Even detector B, which saw phone-screen photos in training, stays close to chance (${f2(pho.auc_B)}, CI ${f2(pho.ci_B[0])}–${f2(pho.ci_B[1])}): very little is left to learn from.` : `Detector B reaches ${f2(pho.auc_B)} on phone screens.`) + ` n = ${pho.n_test} test pairs per device; bars show 95% bootstrap CIs.`;
  });

  CH.register(function drawE2() {
    const th = CH.theme(), L = LAYCOL();
    const bands = DEV.map((k, i) => ({ x0: E1[k].r_min, x1: E1[k].r_max, color: DEVCOL()[k], alpha: 0.13, label: SHORT[k], row: i }));
    CH.lineChart($("cvE2"), { xmin: 0.1, xmax: 2.5, ymin: 0.4, ymax: 1.05, xlabel: "r = camera pixel / screen pixel", ylabel: "AUC (screen photo vs real photo)", bands,
      hlines: [{ y: 0.5, label: "chance" }, { y: 0.9, label: "AUC 0.9" }],
      series: [...["lcd_rgb", "pentile"].map(l => ({ x: E2[l].r, y: E2[l].auc, ci: E2[l].r.map((_, i) => [E2[l].ci_lo[i], E2[l].ci_hi[i]]), color: L[l], label: LAYLABEL[l] })),
        ...(R.E7 ? ["lcd_rgb", "pentile"].map(l => ({ x: R.E7.r, y: R.E7.auc_A[l], color: L[l], dash: [5, 4], width: 1.6, label: "LCD-trained detector on " + LAYLABEL[l] })) : [])], legendY: 52 });
    $("e2Text").innerHTML = `Same simulator, same r, both layouts (${E2.lcd_rgb.n[0]} pairs per point). AUC falls below 0.9 at r ≈ <b>${f2(r90.lcd_rgb)}</b> (LCD) and <b>${f2(r90.pentile)}</b> (PenTile). The coloured bands show where real devices' photos fall in E1: phone photos sit entirely beyond the threshold.` +
      (R.E7 ? ` Dashed: detector A, trained only on LCD-device photos, scored on test scenes (n = ${R.E7.n[0]} pairs per point): at r ≈ ${f2(R.E7.r[1])} it reaches AUC ${f2(R.E7.auc_A.lcd_rgb[1])} on LCD and <b>${f2(R.E7.auc_A.pentile[1])}</b> on PenTile, so an LCD-trained detector ${R.E7.auc_A.pentile[1] > 0.9 ? 'does transfer' : 'only partly transfers'} to the OLED-style layout while the lattice is resolved.` : "");
  });

  CH.register(function drawE3() {
    const th = CH.theme(), L = LAYCOL(), p = E3[E3.primary], lg = a => a.map(v => Math.log10(Math.max(v, 1e-6)));
    const ampKey = E3.primary_bayer ? "theory_amp_bayer" : "theory_amp_mtf";
    const series = ["lcd_rgb", "pentile"].map(l => ({ x: lg(E2[l][ampKey]), y: E2[l].auc, color: L[l], label: LAYLABEL[l], line: false }));
    const xs = series.flatMap(s => s.x), xmin = Math.min(...xs) - 0.2, xmax = Math.max(...xs) + 0.2;
    CH.lineChart($("cvE3"), { xmin, xmax, ymin: 0.4, ymax: 1.05, xlabel: "log10 of predicted strongest moiré amplitude (lens × Bayer demosaic theory)", ylabel: "measured AUC",
      series, curve: { f: x => T.sigmoidCurve(x, p.c, p.s), x0: xmin, x1: xmax, color: th.fg, dash: [6, 4], label: "one fitted curve" }, hlines: [{ y: 0.5, label: "chance" }] });
    const rr = k => f2(E3[k].r2, 3), P = E3[E3.primary], thr = E3.thresholds_from_theory || {};
    const close = Math.abs(E3[E3.primary].r2 - E3.r_only.r2) < 0.01;
    $("e3Text").innerHTML = `One logistic curve fitted to both layouts' 16 points: R² = <b>${rr(E3.primary)}</b> for the better theory axis (${E3.primary_bayer ? "lens response × Bayer demosaic response" : "lens response only"}; LCD ${f2(P.r2_lcd_rgb, 3)}, PenTile ${f2(P.r2_pentile, 3)}), against ${rr("r_only")} for r alone and ${rr(E3.primary_bayer ? "theory_mtf" : "theory_bayer")} for the other theory variant. `
      + (close ? "<b>Honest reading:</b> r alone describes the curve about as well, because the lens blur varies over a narrow range; the theory's value here is that it predicts <i>where</i> the boundary is and where the peaks land without fitting. " : "The theory axis explains the curve better than r alone. ")
      + `Predicted r<sub>90</sub> from the fitted curve: LCD ${f2(thr.r_at_auc90_lcd_rgb)}, PenTile ${f2(thr.r_at_auc90_pentile)}; measured: ${f2(r90.lcd_rgb)} and ${f2(r90.pentile)}. The better variant was chosen after seeing the fits, and r alone fits almost as well, so nothing hinges on that choice. With 8 points per layout these are descriptive fits, not a strict test.`;
  });

  CH.register(function drawE1d() {
    const DC = DEVCOL();
    CH.lineChart($("cvE1d"), { xmin: 12, xmax: 43, ymin: 0.4, ymax: 1.05, xlabel: "distance (cm)", ylabel: "AUC (raw peakiness, no training)", hlines: [{ y: 0.5, label: "chance" }],
      series: DEV.map(k => ({ x: E1[k].by_distance.map(b => (b.d_lo + b.d_hi) / 2), y: E1[k].by_distance.map(b => b.auc), ci: E1[k].by_distance.map(b => b.ci), color: DC[k], label: SHORT[k] })), legendY: 60 });
  });

  /* ================= chapter 5 ================= */
  const exOf = () => D.examples.filter(e => e.layout === $("xLay").value);
  function drawExample() {
    const list = exOf(), ex = list[+$("xR").value], th = CH.theme();
    $("vXr").textContent = f2(ex.r);
    $("xSub").src = `img/${ex.id}_sub.png`; $("xRec").src = `img/${ex.id}_rec.png`; $("xSpec").src = `img/${ex.id}_spec.png`;
    const ctx = $("xOv").getContext("2d"); ctx.clearRect(0, 0, 256, 256);
    ex.peaks.slice(0, 8).forEach((p, k) => { ctx.strokeStyle = k < 3 ? "#3ee8ff" : "rgba(62,232,255,.65)"; ctx.lineWidth = k < 3 ? 2.2 : 1.4; ctx.beginPath(); ctx.arc(p[1] * 2 + 1, p[0] * 2 + 1, 8, 0, 7); ctx.stroke(); });
    const half = ex.layout === "pentile";
    $("xText").innerHTML = `<b>${LAYLABEL[ex.layout]}</b>, r = ${f2(ex.r)}: strongest predicted peak amplitude ${f2(ex.peaks[0][2], 3)}; peakiness of the screen photo ${f2(ex.peakiness_screen)} against ${f2(ex.peakiness_direct)} for the real scene; detector probability "screen" = ${f2(ex.p_detect_screen)} (real scene: ${f2(ex.p_detect_direct)}). ` +
      (ex.r > 0.9 ? "Beyond r ≈ 0.9 the lens has erased the luma lattice: the spectrum looks like an ordinary photo. A little colour (chroma) structure can still hint at the layout up to r ≈ 1.1, but not reliably." : half ? "The PenTile checkerboard produces peaks at half-integer harmonics ((±½, ±½) cycles per screen pixel) that an LCD never has." : "The LCD's stripes repeat once per pixel: only integer harmonics.");
  }
  ["xLay", "xR"].forEach(id => $(id).addEventListener("input", drawExample)); drawExample();

  CH.register(function drawE4() {
    const th = CH.theme(), ci = k => E4.r.map((_, i) => E4["ci_" + k][i]);
    CH.lineChart($("cvE4"), { xmin: 0.2, xmax: 2.5, ymin: 0.2, ymax: 1.05, xlabel: "r", ylabel: "accuracy (LCD vs PenTile)", hlines: [{ y: 0.5, label: "chance" }],
      series: [{ x: E4.r, y: E4.acc_logistic, ci: ci("logistic"), color: th.c1, label: "logistic on spectral signature" },
               { x: E4.r, y: E4.acc_known, ci: ci("known"), color: th.c4, label: "template at known geometry (no training)" },
               { x: E4.r, y: E4.acc_template, color: th.c3, dash: [5, 4], label: "free-search template (negative result)" },
               ...(E4.acc_chroma ? [{ x: E4.r, y: E4.acc_chroma, color: th.c2, dash: [2, 3], width: 1.6, marker: false, label: "logistic, chroma signature only" }, { x: E4.r, y: E4.acc_luma, color: th.muted, dash: [2, 3], width: 1.6, marker: false, label: "logistic, luma signature only" }] : [])], legendY: 50 });
    const ia = iNear(0.9), ib = iNear(1.1);
    $("e4Text").innerHTML = `Logistic: grouped 3-fold cross-validation by scene. Known-geometry template: r and θ taken from the device specs, no training. The free-search template, which also searches over r and θ, is no better than chance (${Math.round(100 * E4.overall_template)}% overall): with 4,653 hypotheses and 12 peaks each, strong spectral content matches any layout. Logistic accuracy is ${Math.round(100 * E4.acc_logistic[ia])}% at r ≈ ${f2(E4.r[ia], 1)} and ${Math.round(100 * E4.acc_logistic[ib])}% at r ≈ ${f2(E4.r[ib], 1)} (n = ${E4.n[0]} per point), above chance after the luma peaks have gone` + (E4.acc_chroma ? `: the chroma signature alone reaches ${Math.round(100 * E4.acc_chroma[ia])}% and ${Math.round(100 * E4.acc_chroma[ib])}%, the luma signature alone ${Math.round(100 * E4.acc_luma[ia])}% and ${Math.round(100 * E4.acc_luma[ib])}%. Colour moiré from the Bayer sampling outlives the luma lattice a little` : "") + `. By r ≈ 1.4–1.8 it is chance.`;
  });

  (function quiz() {
    /* a round = every quiz spectrum once, in random order; +5 XP per correct answer, a bonus for finishing */
    let order = [], i = 0, score = 0, done = false;
    const total = D.quiz.length, shuffle = a => { for (let k = a.length - 1; k > 0; k--) { const j = Math.floor(Math.random() * (k + 1)); [a[k], a[j]] = [a[j], a[k]]; } return a; };
    const bar = () => `<div style="height:12px;border-radius:99px;background:var(--grid);overflow:hidden"><i style="display:block;height:100%;width:${100 * i / total}%;background:var(--green);border-radius:99px;transition:width .3s"></i></div><div style="margin-top:4px">Question ${Math.min(i + 1, total)} of ${total} · score ${score}</div>`;
    const show = () => { done = false; $("qImg").src = D.quiz[order[i]].img; $("qProg").innerHTML = bar(); $("qMsg").textContent = "Which screen made these moiré spots? (stripe LCD or diamond PenTile)"; };
    const start = () => { order = shuffle([...D.quiz.keys()]); i = 0; score = 0; show(); };
    function next() {
      i++;
      if (i >= total) {
        const good = score >= 0.7 * total, first = P.award("quiz", good ? 20 : 10);
        $("qProg").innerHTML = bar();
        P.feedback({ ok: good, title: `Round complete: ${score} / ${total}`, body: good ? `${first ? "+" + (good ? 20 : 10) + " XP. " : ""}You can read the screen layout from its moiré. Remember it fades by r ≈ 1.` : `${first ? "+10 XP. " : ""}Look for spots at half-integer positions (PenTile) versus integer ones only (LCD), then try again.`, btn: "Play again", onContinue: start });
      } else show();
    }
    document.querySelectorAll("button[data-q]").forEach(b => b.onclick = () => {
      if (done) return; done = true; const q = D.quiz[order[i]], ok = b.dataset.q === q.answer; if (ok) { score++; P.addXP(5); }
      P.setStreak(ok);
      const why = q.answer === "pentile" ? "Look for spots at half-integer positions." : "Only integer harmonics.";
      $("qMsg").innerHTML = `${ok ? "Correct" : "Not quite"}: it was <b>${LAYLABEL[q.answer]}</b> (r = ${f2(q.r)}). Score ${score}/${i + 1}. ${why}`;
      $("qProg").innerHTML = bar();
      P.feedback({ ok, title: ok ? "Correct! +5 XP" : "Not quite", body: `It was <b>${LAYLABEL[q.answer]}</b> (r = ${f2(q.r)}). ${why}`, btn: i + 1 >= total ? "Finish" : "Continue", onContinue: next });
    });
    $("qNext").onclick = () => { if ($("fbar").classList.contains("show")) { P.hideFeedback(); return; } if (!done) { done = true; P.setStreak(false); next(); } };
    start();
  })();

  /* ================= challenges (presentation only): predict, then check against the same theory code ================= */
  (function challenges() {
    const pct = m => m < 0.01 ? "under 1%" : Math.round(100 * m) + "%";
    P.mc($("p3"), { id: "p3", xp: 10,
      q: () => "At <b>r = 0.70</b> the LCD's basic stripe harmonic (1 cycle per screen pixel) lands at 0.70 cycles per camera pixel, beyond the Nyquist limit of 0.5. Where does aliasing put its moiré spot (distance from the centre, in cycles per camera pixel)?",
      opts: () => ["0.70: it stays where it is", f2(Math.abs(T.fold(0.7)), 2), "0.50: it stops at the edge of the band", "0: it disappears"],
      ans: () => 1,
      explain: () => `fold(0.70) = ((0.70 + ½) mod 1) − ½ = <b>${f2(T.fold(0.7), 2)}</b>, so the spot sits at ${f2(Math.abs(T.fold(0.7)), 2)}. Set <i>r</i> = 0.70 above and find the orange stem.`,
      hint: () => "Use the fold rule from the equation above: fold(f) = ((f + ½) mod 1) − ½." });

    const phoR = T.rFromGeometry(M.devices.phone_oled.pitch_mm, M.camera.f_mm, 250, M.camera.px_um.binned), lapR = T.rFromGeometry(M.devices.laptop_lcd.pitch_mm, M.camera.f_mm, 250, M.camera.px_um.binned);
    const mPho = T.mtf(1, T.sigmaScreen(phoR, 0.4)), mLap = T.mtf(1, T.sigmaScreen(lapR, 0.4));
    P.mc($("p4"), { id: "p4", xp: 10,
      q: () => "Photograph a laptop screen and a phone OLED screen from the same 25 cm with the same binned phone camera. The phone's pixels are far smaller compared with the camera's. What happens to the lens response at the pixel-frequency harmonic (f = 1)?",
      opts: () => ["About the same as for the laptop", "It collapses to a tiny fraction of the laptop's", "It gets stronger: smaller pixels look sharper", "Unchanged: the lens does not care about pixel size"],
      ans: () => 1,
      explain: () => `At 25 cm, <i>r</i> ≈ ${f2(phoR, 2)} for the phone against ${f2(lapR, 2)} for the laptop (blur σ = 0.4), so the lens passes about <b>${pct(mPho)}</b> of the f = 1 harmonic for the phone and <b>${pct(mLap)}</b> for the laptop.`,
      hint: () => "The blur is fixed in camera pixels, so it covers more of each screen pixel when the screen pixels are smaller. Check the MTF chart." });

    const e5p = E5.devices.phone_oled;
    P.mc($("p6"), { id: "p6", xp: 10,
      q: () => `An ID-verification app wants to catch someone photographing a <b>phone</b> screen. In this study's simulation the lattice is detectable only within about ${f2(e5p.binned.max_detect_cm, 0)} cm (binned camera) or ${f2(e5p.full.max_detect_cm, 0)} cm (full resolution). Which capture rule helps most?`,
      opts: () => ["Ask users to hold the phone farther away", "Sharpen the photo more before analysing it", "Use the full-resolution camera and ask users to move closer", "Compress the photo harder"],
      ans: () => 2,
      explain: () => `Only geometry brings the lattice back: a smaller <i>r</i> (full-resolution pixels, shorter distance). Sharpening and strong JPEG do not (E6). These distances depend on the assumed pixel pitches and focal length.`,
      hint: () => "Think about r = camera pixel / screen pixel. What makes it smaller? E6 says sharpening and strong JPEG do not bring the traces back." });

    /* distance gauge */
    const gDev = $("gDev"); DEV.forEach(k => gDev.add(new Option(SHORT[k], k))); gDev.value = "phone_oled";
    function gauge() {
      const k = gDev.value, cam = $("gCam").value, d = +$("gDist").value, mx = E5.devices[k][cam].max_detect_cm, d0 = M.devices[k];
      const r = T.rFromGeometry(d0.pitch_mm, M.camera.f_mm, d * 10, M.camera.px_um[cam]), ok = d <= mx;
      $("vG").textContent = d + " cm";
      $("gSafe").style.width = Math.max(0, Math.min(100, (mx - 8) / 52 * 100)) + "%";
      $("gKnob").style.left = ((d - 8) / 52 * 100) + "%";
      $("gOut").innerHTML = [["", f2(mx, 0) + " cm", `farthest distance at which a ${SHORT[k]} photo is still detectable (AUC ≥ 0.9)`], [ok ? "good" : "bad", ok ? "caught" : "missed", `at ${d} cm the camera pixel is r = ${f2(r, 2)} screen pixels`]]
        .map(([c, big, lbl]) => `<div class="stat"><div class="big ${c}">${big}</div><div class="lbl">${lbl}</div></div>`).join("");
    }
    ["gDev", "gCam", "gDist"].forEach(id => $(id).addEventListener("input", gauge)); gauge();
  })();

  /* ================= chapter 6 ================= */
  CH.register(function drawE5() {
    const th = CH.theme(), DC = DEVCOL(), series = [];
    DEV.forEach(k => { const d = E5.devices[k];
      series.push({ x: d.dist_cm, y: d.binned.r, color: DC[k], label: `${SHORT[k]}, binned 2 µm`, marker: false });
      series.push({ x: d.dist_cm, y: d.full.r, color: DC[k], dash: [6, 4], label: `${SHORT[k]}, full-res 1 µm`, marker: false }); });
    const hl = Math.max(r90.lcd_rgb, r90.pentile);
    CH.lineChart($("cvE5"), { xmin: 10, xmax: 60, ymin: 0, ymax: 2.6, xlabel: "distance from screen to phone camera (cm)", ylabel: "r = camera pixel / screen pixel", series,
      hbands: [{ y0: 0, y1: Math.max(r90.lcd_rgb, r90.pentile), color: th.good, alpha: 0.13, label: "screen photo detectable (AUC ≥ 0.9): below the dashed lines", align: "right" }],
      hlines: [{ y: r90.pentile, label: `r₉₀ PenTile = ${f2(r90.pentile)}`, color: th.c2, dash: [6, 4], align: "right" }, { y: r90.lcd_rgb, label: `r₉₀ LCD = ${f2(r90.lcd_rgb)}`, color: th.c1, dash: [6, 4], align: "right", below: true }], legendPos: "left", legendY: 14 });
    $("e5Table").innerHTML = `<table><tr><th>Device</th><th>binned 2 µm</th><th>full-res 1 µm</th></tr>${DEV.map(k => `<tr><td>${SHORT[k]}</td><td>${f2(E5.devices[k].binned.max_detect_cm, 0)} cm</td><td>${f2(E5.devices[k].full.max_detect_cm, 0)} cm</td></tr>`).join("")}</table>`;
    $("e5Text").innerHTML = `Largest distance at which a screen photo is still detectable (AUC ≥ 0.9), from the measured threshold r₉₀ (LCD ${f2(r90.lcd_rgb)}, PenTile ${f2(r90.pentile)}) and the thin-lens geometry. <b>Rule:</b> to catch a phone-screen attack the camera must be within about ${f2(E5.devices.phone_oled.binned.max_detect_cm, 0)} cm in binned mode (${f2(E5.devices.phone_oled.full.max_detect_cm, 0)} cm at full resolution); a laptop screen is caught up to ${f2(E5.devices.laptop_lcd.binned.max_detect_cm, 0)} cm. These distances depend on the assumed pixel pitches and focal length.`;
  });

  (function e6() {
    const rows = []; ["lcd_rgb", "pentile"].forEach(l => E6.conditions.forEach((c, ci) => rows.push(`<tr><td>${LAYLABEL[l]} · ${c}</td>${E6.auc[l][ci].map(v => `<td>${f2(v)}</td>`).join("")}</tr>`)));
    $("e6Table").innerHTML = `<table><tr><th>AUC at r =</th>${E6.r.map(r => `<th>${r}</th>`).join("")}</tr>${rows.join("")}</table>`;
    const shp = E6.auc.pentile[1].concat(E6.auc.lcd_rgb[1]), base = E6.auc.pentile[0].concat(E6.auc.lcd_rgb[0]);
    const gain = Math.max(...shp.map((v, i) => v - base[i]));
    $("e6Text").innerHTML = `Sharpening (0.5) ${gain > 0.1 ? "can bring back traces" : "does not bring traces back"} beyond r ≈ 0.9 (largest AUC change ${f2(gain)}). Strong JPEG (q 55–70) lowers detection near the boundary (PenTile at r = 0.5: ${f2(E6.auc.pentile[2][0])}).`;
  })();

  $("runInfo").textContent = `Run: ${M.quick ? "QUICK (reduced) " : "full "}experiment data.`;

  /* ================= nav highlight ================= */
  const links = [...document.querySelectorAll("nav.top a")];
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) links.forEach(a => a.classList.toggle("active", a.getAttribute("href") === "#" + e.target.id)); }), { rootMargin: "-40% 0px -55% 0px" });
  document.querySelectorAll("section.chapter").forEach(s => io.observe(s));
})();
