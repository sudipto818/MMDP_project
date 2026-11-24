/* Live simulator: JS port of core/render.py, core/camera.py (no noise, no JPEG) and the spectrum of core/features.py. */
(function (g) {
  const WS = g.WS = g.WS || {};
  const D = g.DATA, T = WS.theory, F = WS.fft;
  const N = D.meta.out;

  /* ---------- colour ---------- */
  const S2L = new Float32Array(256);
  for (let i = 0; i < 256; i++) { const x = i / 255; S2L[i] = x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }
  const lin2srgb = x => { x = x < 0 ? 0 : x > 1 ? 1 : x; return x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055; };
  const luma = (r, gg, b) => 0.299 * r + 0.587 * gg + 0.114 * b;

  /* ---------- scenes (embedded as base64: file:// pages cannot read pixels from <img>) ---------- */
  const scenes = D.scenes.map(s => {
    const bin = atob(s.b64), lin = new Float32Array(s.w * s.h * 3);
    for (let i = 0; i < lin.length; i++) lin[i] = S2L[bin.charCodeAt(i)];
    return { name: s.name, w: s.w, h: s.h, lin };
  });

  /* ---------- normal CDF (Abramowitz & Stegun 7.1.26, |err| < 1.5e-7) ---------- */
  function ndtr(z) {
    const x = z / Math.SQRT2, ax = Math.abs(x), t = 1 / (1 + 0.3275911 * ax);
    const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-ax * ax);
    return 0.5 * (1 + (x < 0 ? -y : y));
  }

  /* ---------- geometry of the camera footprint ---------- */
  const halfwin = sig => Math.ceil(3.2 * sig) + 1;
  function requiredCrop(r, th, sigCam) {
    const sig = T.sigmaScreen(r, sigCam);
    return Math.ceil(2 * (r * (N / 2) * (Math.abs(Math.cos(th)) + Math.abs(Math.sin(th))) + halfwin(sig) + 3));
  }
  function maxR(th, sigCam, sceneSide) {          // largest r whose footprint fits the embedded scene
    let lo = 0.1, hi = 6;
    for (let i = 0; i < 30; i++) { const m = (lo + hi) / 2; if (requiredCrop(m, th, sigCam) <= sceneSide) lo = m; else hi = m; }
    return lo;
  }

  /** Photograph of the SCREEN showing the scene: linear radiance, Float32Array N*N*3 (before exposure). */
  function renderScreen(sceneIdx, layout, r, th, sigCam) {
    const sc = scenes[sceneIdx], W = sc.w, side = requiredCrop(r, th, sigCam);
    if (side > sc.h) throw new Error("camera footprint larger than the embedded scene");
    const off = Math.floor((sc.h - side) / 2), cx = side / 2, cy = side / 2;
    const sig = T.sigmaScreen(r, sigCam), K = halfwin(sig), subs = D.layouts[layout];
    const out = new Float32Array(N * N * 3), c0 = (N - 1) / 2, ct = Math.cos(th), st = Math.sin(th);
    const nK = 2 * K + 1, bx = new Float64Array(nK), by = new Float64Array(nK);
    for (let v = 0; v < N; v++) for (let u = 0; u < N; u++) {
      const du = u - c0, dv = v - c0;
      const X = cx + r * (ct * du - st * dv), Y = cy + r * (st * du + ct * dv);
      const j0 = Math.floor(X), i0 = Math.floor(Y);
      for (const sp of subs) {
        for (let k = 0; k < nK; k++) {
          const relx = X - (j0 + k - K), rely = Y - (i0 + k - K);
          bx[k] = ndtr((relx - sp.x0) / sig) - ndtr((relx - sp.x1) / sig);
          by[k] = ndtr((rely - sp.y0) / sig) - ndtr((rely - sp.y1) / sig);
        }
        let acc = 0;
        for (let di = 0; di < nK; di++) {
          const i = i0 + di - K; if (i < 0 || i >= side) continue;
          let row = 0;
          for (let dj = 0; dj < nK; dj++) {
            const j = j0 + dj - K; if (j < 0 || j >= side) continue;
            if (sp.parity !== null && ((i + j) & 1) !== sp.parity) continue;
            row += sc.lin[((off + i) * W + (off + j)) * 3 + sp.channel] * bx[dj];
          }
          acc += row * by[di];
        }
        out[(v * N + u) * 3 + sp.channel] += sp.gain * acc;
      }
    }
    return out;
  }

  /** Photograph of the real SCENE (no screen): Gaussian blur, then bilinear sampling on the same camera grid. */
  function renderScene(sceneIdx, r, th, sigCam) {
    const sc = scenes[sceneIdx], W = sc.w, side = requiredCrop(r, th, sigCam), off = Math.floor((sc.h - side) / 2);
    const sig = T.sigmaScreen(r, sigCam), R = Math.max(1, Math.ceil(3 * sig));
    const ker = new Float32Array(2 * R + 1); let s = 0;
    for (let k = -R; k <= R; k++) { ker[k + R] = Math.exp(-k * k / (2 * sig * sig)); s += ker[k + R]; }
    for (let k = 0; k < ker.length; k++) ker[k] /= s;
    const tmp = new Float32Array(side * side * 3), blur = new Float32Array(side * side * 3);
    const cl = (i) => i < 0 ? 0 : i >= side ? side - 1 : i;
    for (let i = 0; i < side; i++) for (let j = 0; j < side; j++) for (let c = 0; c < 3; c++) {
      let a = 0; for (let k = -R; k <= R; k++) a += ker[k + R] * sc.lin[((off + i) * W + off + cl(j + k)) * 3 + c];
      tmp[(i * side + j) * 3 + c] = a;
    }
    for (let i = 0; i < side; i++) for (let j = 0; j < side; j++) for (let c = 0; c < 3; c++) {
      let a = 0; for (let k = -R; k <= R; k++) a += ker[k + R] * tmp[(cl(i + k) * side + j) * 3 + c];
      blur[(i * side + j) * 3 + c] = a;
    }
    const out = new Float32Array(N * N * 3), c0 = (N - 1) / 2, ct = Math.cos(th), st = Math.sin(th), cx = side / 2;
    for (let v = 0; v < N; v++) for (let u = 0; u < N; u++) {
      const du = u - c0, dv = v - c0;
      const X = cx + r * (ct * du - st * dv) - 0.5, Y = cx + r * (st * du + ct * dv) - 0.5;
      const j = Math.floor(X), i = Math.floor(Y), fx = X - j, fy = Y - i;
      for (let c = 0; c < 3; c++) {
        const a = blur[(cl(i) * side + cl(j)) * 3 + c], b = blur[(cl(i) * side + cl(j + 1)) * 3 + c];
        const d = blur[(cl(i + 1) * side + cl(j)) * 3 + c], e = blur[(cl(i + 1) * side + cl(j + 1)) * 3 + c];
        out[(v * N + u) * 3 + c] = (a * (1 - fx) + b * fx) * (1 - fy) + (d * (1 - fx) + e * fx) * fy;
      }
    }
    return out;
  }

  /* ---------- camera: exposure, Bayer RGGB mosaic, bilinear demosaic, gamma, 8 bit ---------- */
  const mir = i => i < 0 ? -i : i >= N ? 2 * N - 2 - i : i;
  function camera(L, gain) {
    const mos = [new Float32Array(N * N), new Float32Array(N * N), new Float32Array(N * N)];
    for (let v = 0; v < N; v++) for (let u = 0; u < N; u++) {
      const c = (v & 1) === 0 ? ((u & 1) === 0 ? 0 : 1) : ((u & 1) === 0 ? 1 : 2);
      const x = Math.min(1, Math.max(0, L[(v * N + u) * 3 + c] * gain));
      mos[c][v * N + u] = x;
    }
    const out = new Float32Array(N * N * 3);
    const kG = [0, 1, 0, 1, 4, 1, 0, 1, 0], kRB = [1, 2, 1, 2, 4, 2, 1, 2, 1];
    for (let c = 0; c < 3; c++) {
      const k = c === 1 ? kG : kRB;
      for (let v = 0; v < N; v++) for (let u = 0; u < N; u++) {
        let a = 0;
        for (let dv = -1; dv <= 1; dv++) for (let du = -1; du <= 1; du++) a += k[(dv + 1) * 3 + du + 1] * mos[c][mir(v + dv) * N + mir(u + du)];
        out[(v * N + u) * 3 + c] = Math.round(lin2srgb(a / 4) * 255) / 255;
      }
    }
    return out;
  }

  /* ---------- spectrum (detrended log spectrum, masked), peakiness ---------- */
  const hann = new Float64Array(N); for (let k = 0; k < N; k++) hann[k] = 0.5 - 0.5 * Math.cos(2 * Math.PI * k / (N - 1));
  const ringIdx = Array.from({ length: T.nRing }, () => []);
  for (let i = 0; i < N * N; i++) ringIdx[T.RING[i]].push(i);
  function spectrum(rgb) {
    const gray = new Float64Array(N * N); let mean = 0;
    for (let i = 0; i < N * N; i++) { gray[i] = luma(rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2]); mean += gray[i]; }
    mean /= N * N;
    const re = new Float64Array(N * N), im = new Float64Array(N * N);
    for (let r = 0; r < N; r++) for (let c = 0; c < N; c++) re[r * N + c] = (gray[r * N + c] - mean) * hann[r] * hann[c];
    F.fft2(re, im, N);
    const L = new Float64Array(N * N);
    for (let r = 0; r < N; r++) for (let c = 0; c < N; c++) {
      const rs = (r + N / 2) % N, cs = (c + N / 2) % N;                      // fftshift
      L[rs * N + cs] = Math.log(Math.hypot(re[r * N + c], im[r * N + c]) + 1e-9);
    }
    const med = new Float64Array(T.nRing);
    for (let k = 0; k < T.nRing; k++) {
      const idx = ringIdx[k], a = Float64Array.from(idx, i => L[i]).sort();
      med[k] = 0.5 * (a[(a.length - 1) >> 1] + a[a.length >> 1]);
    }
    const R = new Float32Array(N * N);
    for (let i = 0; i < N * N; i++) R[i] = T.MASK[i] ? 0 : L[i] - med[T.RING[i]];
    const top = Float32Array.from(R).sort().subarray(N * N - 20);
    let pk = 0; for (const x of top) pk += x;
    return { R, peak: pk / 20 };
  }

  /* ---------- magma-like colour map ---------- */
  const KEYS = [[0, 0, 4], [40, 11, 84], [101, 21, 110], [159, 42, 99], [212, 72, 66], [245, 125, 21], [250, 193, 39], [252, 255, 164]];
  const LUT = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i++) {
    const t = i / 255 * (KEYS.length - 1), a = Math.min(KEYS.length - 2, Math.floor(t)), f = t - a;
    for (let c = 0; c < 3; c++) LUT[i * 3 + c] = KEYS[a][c] * (1 - f) + KEYS[a + 1][c] * f;
  }
  function spectrumImage(R) {                      // RGBA ImageData-ready bytes
    const px = new Uint8ClampedArray(N * N * 4);
    for (let i = 0; i < N * N; i++) {
      const v = Math.max(0, Math.min(255, Math.round((R[i] + 1) / 7 * 255)));
      px[i * 4] = LUT[v * 3]; px[i * 4 + 1] = LUT[v * 3 + 1]; px[i * 4 + 2] = LUT[v * 3 + 2]; px[i * 4 + 3] = 255;
    }
    return px;
  }

  /** Both photographs + spectra for one set of parameters. layout: 'lcd_rgb' | 'pentile'. theta in degrees. */
  function capture(p) {
    const th = p.thetaDeg * Math.PI / 180;
    const Ls = renderScreen(p.scene, p.layout, p.r, th, p.sigma);
    const Ld = renderScene(p.scene, p.r, th, p.sigma);
    let m = 0; for (let i = 0; i < N * N; i++) m += luma(Ld[i * 3], Ld[i * 3 + 1], Ld[i * 3 + 2]);
    const gain = 0.18 / Math.max(m / (N * N), 1e-6);          // one shared exposure gain, as in the experiments
    const scr = camera(Ls, gain), dir = camera(Ld, gain);
    const sS = spectrum(scr), sD = spectrum(dir);
    return { scr, dir, specScr: sS.R, specDir: sD.R, peakScr: sS.peak, peakDir: sD.peak, gain };
  }

  WS.sim = { scenes, ndtr, requiredCrop, maxR, renderScreen, renderScene, camera, spectrum, spectrumImage, capture, lin2srgb, luma };
})(window);
