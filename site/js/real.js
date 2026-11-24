/* Lesson 7: real photos. Reads window.REAL (data/real.js, written by export_real_site.py). Only peakiness and spectra are shown:
   the trained detector's probability is not reliable on real photos, so it is not displayed as an accuracy. */
(function () {
  const REAL = window.REAL, WS = window.WS;
  if (!REAL || !WS || !document.getElementById("ch7")) return;
  const CH = WS.charts, $ = id => document.getElementById(id), f2 = (x, d = 2) => Number.isFinite(x) ? x.toFixed(d) : "n/a";
  const CONDS = REAL.conditions, ORD = REAL.ordinary, SIM = REAL.sim;
  const NAME = { laptop: "HP Victus laptop (141 ppi LCD)", phone: "Moto G32 (405 ppi LCD)" };
  const role = c => c.calibration ? "used to calibrate the camera" : "predicted, then compared";

  /* ---- cards ---- */
  const px = REAL.px_est_um, above = c => `${c.above}/${c.n}`;
  const l12 = CONDS.find(c => c.device === "laptop" && c.d === 12), l20 = CONDS.find(c => c.device === "laptop" && c.d === 20);
  $("realCards").innerHTML = [
    ["", `${f2(px["12.0"])} / ${f2(px["20.0"])} µm`, "effective camera pixel from the laptop's lattice at 12 and 20 cm (the EXIF-based guess was 1.95 µm)"],
    ["good", `${above(l12)} and ${above(l20)}`, "laptop photos at 12 and 20 cm above every ordinary photo (these two set the calibration)"],
    ["", "5 of 5", "other conditions predicted from distance and pixel pitch alone, and consistent with the simulation"],
  ].map(([c, big, lbl]) => `<div class="stat"><div class="big ${c}">${big}</div><div class="lbl">${lbl}</div></div>`).join("");

  /* ---- explorer ---- */
  const dev = $("rDev"), dist = $("rDist");
  [["laptop", NAME.laptop], ["phone", NAME.phone]].forEach(([v, t]) => dev.add(new Option(t, v)));
  function fillDist() {
    const cur = dist.value; dist.innerHTML = "";
    CONDS.filter(c => c.device === dev.value).forEach(c => dist.add(new Option(c.d + " cm", c.d)));
    if ([...dist.options].some(o => o.value === cur)) dist.value = cur; else dist.value = dist.options[0].value;
  }
  function show() {
    const c = CONDS.find(x => x.device === dev.value && String(x.d) === dist.value);
    $("rFig").innerHTML = [[`real_${c.tag}`, "photo of the screen"], [`real_${c.tag}_spec`, "its spectrum"], ["real_ordinary", "an ordinary photo"], ["real_ordinary_spec", "its spectrum"]]
      .map(([f, t]) => `<div class="fig"><img class="px" src="img/${f}.png" alt="${t}"><div class="cap"><b>${t}</b></div></div>`).join("");
    const state = c.above === c.n ? ["good", "The lattice leaves a clear trace: every photo is above the ordinary range."]
      : c.above === 0 ? ["bad", "No usable trace: the photos are inside the ordinary-photo range."]
      : ["mid", "At the edge: only a faint trace in some photos."];
    $("rRead").innerHTML = `
      <div class="row"><span>r = camera pixel / screen pixel</span><b>${f2(c.r, 2)}</b></div>
      <div class="row"><span>simulated AUC at that r</span><b>${f2(c.sim_auc)}</b></div>
      <div class="row"><span>peakiness of the 4 photos (mean, range)</span><b>${f2(c.mean)} (${f2(c.min)} to ${f2(c.max)})</b></div>
      <div class="row"><span>ordinary photos (${ORD.n}): range</span><b>${f2(ORD.min)} to ${f2(ORD.max)}</b></div>
      <div class="row"><span>photos above the largest ordinary photo</span><b>${above(c)}</b></div>
      <div class="row"><span>role in the analysis</span><b>${role(c)}</b></div>
      <div class="verdict ${state[0]}">${state[1]}</div>`;
    $("vRD").textContent = c.d + " cm";
  }
  dev.addEventListener("change", () => { fillDist(); show(); }); dist.addEventListener("change", show);
  fillDist(); show();

  /* ---- chart: real photos on the simulation's curve ---- */
  CH.register(function drawReal() {
    const th = CH.theme(), pts = (f, col, label) => {
      const rows = CONDS.filter(f), x = [], y = [];
      rows.forEach(c => c.peak.forEach((p, k) => { x.push(c.r + (k - 1.5) * 0.012); y.push(p); }));
      return { x, y, color: col, label, line: false };
    };
    CH.lineChart($("cvReal"), {
      xmin: 0.1, xmax: 2.6, ymin: 1.0, ymax: 5.6, xlabel: "r = camera pixel / screen pixel (from real pixel pitches and distances)", ylabel: "spectral peakiness",
      hbands: [{ y0: SIM.direct95[0], y1: SIM.direct95[1], color: th.muted, alpha: 0.16 }],
      hlines: [{ y: ORD.min, label: "real ordinary photos: range", color: th.fg, dash: [3, 3] }, { y: ORD.max, color: th.fg, dash: [3, 3] }],
      series: [{ x: SIM.r, y: SIM.median, ci: SIM.r.map((_, i) => [SIM.lo[i], SIM.hi[i]]), color: th.c1, label: "simulation: median and 10-90% (screen photos)", marker: false },
               pts(c => c.device === "laptop" && c.calibration, th.c4, "real laptop, 12 and 20 cm (used to calibrate)"),
               pts(c => c.device === "laptop" && !c.calibration, th.c2, "real laptop, 35 and 50 cm (predicted)"),
               pts(c => c.device === "phone", th.c3, "real Moto G32 (predicted)")],
      legendPos: "left", legendY: 40 });
    $("rChartText").innerHTML = `Each dot is one real photo. The grey band is where the <i>simulation's</i> ordinary photos fall; the dotted lines bracket the ${ORD.n} <i>real</i> ordinary photos. Only the laptop at 12 and 20 cm rises well above them. The two calibration points are not an independent test; the other five conditions are.`;
  });

  /* ---- table ---- */
  $("rTable").innerHTML = `<table><tr><th>Condition</th><th>r</th><th>sim. AUC</th><th>peakiness mean (range)</th><th>above ordinary max</th><th>role</th></tr>${
    CONDS.map(c => `<tr><td>${c.device === "laptop" ? "laptop" : "Moto G32"} ${c.d} cm</td><td>${f2(c.r)}</td><td>${f2(c.sim_auc)}</td><td>${f2(c.mean)} (${f2(c.min)}-${f2(c.max)})</td><td>${above(c)}</td><td>${c.calibration ? "calibration" : "prediction"}</td></tr>`).join("")}</table>`;
})();
