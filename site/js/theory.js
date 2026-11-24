/* JS port of core/theory.py, core/masks.py: lattice harmonics, aliasing fold, MTF, Bayer demosaic response,
   predicted moire peaks, geometry. Needs window.DATA (data/data.js). */
(function (g) {
  const WS = g.WS = g.WS || {};
  const D = g.DATA;
  const N = D.meta.out;                       // 128
  const SIG_AP = D.meta.sigma_aperture;       // 0.29
  const LUMA = [0.299, 0.587, 0.114];

  /* ----- helpers ----- */
  function rint(x) {                          // round half to even, like numpy.rint
    const f = Math.floor(x), d = x - f;
    if (d < 0.5) return f; if (d > 0.5) return f + 1;
    return (f % 2 === 0) ? f : f + 1;
  }
  const mod = (a, n) => ((a % n) + n) % n;
  const fold = f => mod(f + 0.5, 1) - 0.5;
  const mtf = (fmag, ss) => Math.exp(-2 * Math.PI * Math.PI * ss * ss * fmag * fmag);
  const sigmaScreen = (r, sigCam) => r * Math.hypot(sigCam, SIG_AP);

  /* ----- masks (rows = fy, cols = fx; DC at N/2) ----- */
  const moddist = (a, b) => { const d = Math.abs(a - b); return Math.min(d, N - d); };
  const MASK = new Uint8Array(N * N), RING = new Int32Array(N * N);
  let nRing = 0;
  for (let r = 0; r < N; r++) for (let c = 0; c < N; c++) {
    const fy = r - N / 2, fx = c - N / 2, rad = Math.hypot(fy, fx);
    let m = rad < 4;
    for (let a = -4; a < 4 && !m; a++) for (let b = -4; b < 4 && !m; b++) {
      const cr = mod(N / 2 + a * N / 8, N), cc = mod(N / 2 + b * N / 8, N);
      if (moddist(r, cr) <= 1 && moddist(c, cc) <= 1) m = true;
    }
    if (!m) for (const [cr, cc] of [[0, 0], [0, N / 2], [N / 2, 0]]) if (moddist(r, cr) <= 2 && moddist(c, cc) <= 2) m = true;
    MASK[r * N + c] = m ? 1 : 0;
    RING[r * N + c] = rint(rad); nRing = Math.max(nRing, RING[r * N + c] + 1);
  }

  /* ----- harmonics ----- */
  function demosaicResponse(fx, fy) {
    const cx = Math.cos(2 * Math.PI * fx), cy = Math.cos(2 * Math.PI * fy);
    const rb = (1 + cx) * (1 + cy) / 4, gg = 0.5 + (cx + cy) / 4;
    return [rb, gg, rb];
  }

  function toCameraFreq(fx, fy, r, th) {
    const c = Math.cos(th), s = Math.sin(th);
    return [r * (fx * c + fy * s), r * (-fx * s + fy * c)];
  }

  /** All harmonics of a layout with predicted amplitude at (r, theta [rad], sigma_cam). */
  function harmonicTable(layout, r, th, sigCam, bayer) {
    const H = D.harmonics[layout], K = H.fx.length, ss = sigmaScreen(r, sigCam);
    const out = new Array(K);
    for (let k = 0; k < K; k++) {
      const [fxc, fyc] = toCameraFreq(H.fx[k], H.fy[k], r, th);
      const fxf = fold(fxc), fyf = fold(fyc);
      const m = mtf(Math.hypot(H.fx[k], H.fy[k]), ss);
      let a;
      if (!bayer) a = H.amp[k] * m;
      else {
        const h = demosaicResponse(fxf, fyf);
        let sr = 0, si = 0;
        for (let c = 0; c < 3; c++) { sr += LUMA[c] * h[c] * H.re[k][c]; si += LUMA[c] * h[c] * H.im[k][c]; }
        a = Math.hypot(sr, si) * m;
      }
      const row = mod(N / 2 + rint(fyf * N), N), col = mod(N / 2 + rint(fxf * N), N);
      out[k] = { fxs: H.fx[k], fys: H.fy[k], fxf, fyf, row, col, amp: a, masked: MASK[row * N + col] === 1 };
    }
    return out;
  }

  /** Predicted peaks: strongest first, duplicates merged (max), masked bins dropped. */
  function predictedPeaks(layout, r, th, sigCam, top, masked = true, bayer = true) {
    let t = harmonicTable(layout, r, th, sigCam, bayer);
    if (masked) t = t.filter(e => !e.masked);
    t.sort((a, b) => b.amp - a.amp);
    const seen = new Set(), out = [];
    for (const e of t) {
      const key = e.row * N + e.col;
      if (seen.has(key)) continue;
      seen.add(key); out.push(e);
      if (top && out.length >= top) break;
    }
    return out;
  }

  const theoryAmp = (layout, r, sigCam, th = 0, masked = true, bayer = true) => {
    const p = predictedPeaks(layout, r, th, sigCam, 1, masked, bayer);
    return p.length ? p[0].amp : 0;
  };

  /* ----- geometry ----- */
  const rFromGeometry = (pitchMm, fMm, dMm, pxUm) => (pxUm / 1000) / (pitchMm * (fMm / (dMm - fMm)));
  const distanceFromR = (pitchMm, fMm, r, pxUm) => fMm + r * pitchMm * fMm / (pxUm / 1000);

  /* ----- fitted AUC curve (E3) ----- */
  const sigmoidCurve = (x, c, s) => 0.5 + 0.5 / (1 + Math.exp(-(x - c) / s));
  function predictedAUC(layout, r, sigCam, th) {
    const e3 = D.results.E3, p = e3[e3.primary];
    const bay = !!e3.primary_bayer;                                          // the variant whose fit is stored in E3
    let a = theoryAmp(layout, r, sigCam, th, true, bay);
    // Coincidence guard: at r = 1/4, 1/2 ... every harmonic folds exactly onto a masked bin (JPEG 8x8 grid / Bayer frequencies), so the
    // "strongest surviving peak" collapses although the moire is plainly there. Only in that case use the best amplitude within +-6 % of r.
    if (a < 0.3 * theoryAmp(layout, r, sigCam, th, false, bay)) {
      for (const k of [0.94, 0.97, 1.03, 1.06]) a = Math.max(a, theoryAmp(layout, r * k, sigCam, th, true, bay));
    }
    return sigmoidCurve(Math.log10(Math.max(a, 1e-6)), p.c, p.s);
  }

  WS.theory = { N, rint, fold, mtf, sigmaScreen, MASK, RING, nRing, demosaicResponse, toCameraFreq, harmonicTable,
                predictedPeaks, theoryAmp, rFromGeometry, distanceFromR, predictedAUC, sigmoidCurve, LUMA };
})(window);
