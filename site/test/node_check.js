// Checks the JavaScript port against numbers computed by the Python reference (stored in data.js -> DATA.reference).
// Run from the site folder:  node test/node_check.js
const fs = require("fs"), vm = require("vm"), path = require("path");
const root = path.join(__dirname, "..");
global.window = global;                       // run the browser scripts in the normal global scope (vm contexts make global lookups very slow)
for (const f of ["data/data.js", "js/fft.js", "js/theory.js", "js/sim.js"]) vm.runInThisContext(fs.readFileSync(path.join(root, f), "utf8"), { filename: f });
const { DATA, WS } = global, T = WS.theory, S = WS.sim, F = WS.fft;
let fails = 0, checks = 0;
const ok = (cond, msg) => { checks++; if (!cond) { fails++; console.log("FAIL:", msg); } };
const close = (a, b, tol) => Math.abs(a - b) <= tol * Math.max(1, Math.abs(b));

// 1. FFT: impulse -> flat; sinusoid -> two bins; Parseval
{
  const n = 128, re = new Float64Array(n * n), im = new Float64Array(n * n);
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) re[r * n + c] = Math.cos(2 * Math.PI * (5 * c + 3 * r) / n);
  const e0 = re.reduce((s, x) => s + x * x, 0);
  F.fft2(re, im, n);
  const mag = Array.from(re, (x, i) => Math.hypot(x, im[i]));
  const big = mag.map((m, i) => [m, i]).sort((a, b) => b[0] - a[0]).slice(0, 2).map(x => x[1]);
  ok(big.includes(3 * n + 5) && big.includes(((n - 3) % n) * n + (n - 5) % n), "fft2 sinusoid peak bins");
  const e1 = mag.reduce((s, x) => s + x * x, 0) / (n * n);
  ok(close(e1, e0, 1e-9), "fft2 Parseval");
}
// 2. normal CDF
ok(close(S.ndtr(0), 0.5, 1e-7) && close(S.ndtr(1.96), 0.9750021, 1e-6) && close(S.ndtr(-3), 0.0013499, 1e-5), "ndtr values");
// 3. rint / fold
ok(T.rint(0.5) === 0 && T.rint(1.5) === 2 && T.rint(-0.5) === -0 && T.rint(2.4) === 2, "rint half-to-even");
ok(close(T.fold(0.6), -0.4, 1e-12) && close(T.fold(-0.6), 0.4, 1e-12), "fold");
// 4. masks: counts must match Python
if (DATA.reference_masks) {
  let n = 0; for (const v of T.MASK) n += v;
  ok(n === DATA.reference_masks.sum, `mask sum ${n} vs python ${DATA.reference_masks.sum}`);
  ok(T.nRing === DATA.reference_masks.n_ring, `rings ${T.nRing} vs ${DATA.reference_masks.n_ring}`);
}
// 5. predicted peaks and theory amplitude vs Python
let nPeak = 0;
for (const ref of DATA.reference) {
  if (ref.render) continue;
  const th = ref.theta * Math.PI / 180, p = T.predictedPeaks(ref.layout, ref.r, th, ref.sigma, 6);
  // amplitudes must agree one by one; peaks strictly stronger than the 6th must be the same bins
  // (equal-amplitude +/- pairs may come in a different order, and a tie at the cut-off may pick either member)
  const a6 = ref.amp[ref.amp.length - 1], key = (r, c) => r * 1000 + c;
  const pyStrong = new Set(), jsStrong = new Set();
  ref.rows.forEach((r, k) => { if (ref.amp[k] > a6 * (1 + 1e-9)) pyStrong.add(key(r, ref.cols[k])); });
  p.forEach(e => { if (e.amp > a6 * (1 + 1e-9)) jsStrong.add(key(e.row, e.col)); });
  for (let k = 0; k < ref.rows.length; k++) { nPeak++; ok(p[k] && close(p[k].amp, ref.amp[k], 1e-6), `peak amp ${k} ${ref.layout} r=${ref.r}: js ${p[k] && p[k].amp} vs py ${ref.amp[k]}`); }
  ok(pyStrong.size === jsStrong.size && [...pyStrong].every(x => jsStrong.has(x)), `strong peak bins ${ref.layout} r=${ref.r}: js ${[...jsStrong]} vs py ${[...pyStrong]}`);
  ok(close(T.theoryAmp(ref.layout, ref.r, ref.sigma, th), ref.theory_amp, 1e-6), `theory_amp ${ref.layout} r=${ref.r}`);
}
// 6. renderer vs Python render_screen
let nProbe = 0;
for (const ref of DATA.reference) {
  if (!ref.render) continue;
  const L = S.renderScreen(0, ref.layout, ref.r, ref.theta * Math.PI / 180, ref.sigma), N = DATA.meta.out;
  for (const [a, b, rgb] of ref.probe) for (let c = 0; c < 3; c++) { nProbe++; ok(close(L[(a * N + b) * 3 + c], rgb[c], 0.02), `render ${ref.layout} (${a},${b}) ch${c}: js ${L[(a * N + b) * 3 + c].toFixed(4)} vs py ${rgb[c].toFixed(4)}`); }
  let m = [0, 0, 0]; for (let i = 0; i < N * N; i++) for (let c = 0; c < 3; c++) m[c] += L[i * 3 + c] / (N * N);
  for (let c = 0; c < 3; c++) ok(close(m[c], ref.mean[c], 0.01), `render mean ch${c} ${ref.layout}: js ${m[c].toFixed(4)} vs py ${ref.mean[c].toFixed(4)}`);
}
// 7. a full capture runs and gives a clearly higher peakiness for a resolved screen than for the scene
{
  const cap = S.capture({ scene: 0, layout: "lcd_rgb", r: 0.4, thetaDeg: 2, sigma: 0.3 });
  ok(cap.peakScr > cap.peakDir + 1, `LCD at r=0.4: screen peakiness ${cap.peakScr.toFixed(2)} should exceed scene ${cap.peakDir.toFixed(2)} by > 1`);
  const cap2 = S.capture({ scene: 0, layout: "pentile", r: 2.0, thetaDeg: 2, sigma: 0.4 });
  ok(Math.abs(cap2.peakScr - cap2.peakDir) < 1.0, `PenTile at r=2: peakiness ${cap2.peakScr.toFixed(2)} vs ${cap2.peakDir.toFixed(2)} should be close`);
  const t0 = Date.now(); for (let i = 0; i < 3; i++) S.capture({ scene: 0, layout: "pentile", r: 1.8, thetaDeg: 3, sigma: 0.5 });
  console.log(`capture time at r=1.8: ${((Date.now() - t0) / 3).toFixed(0)} ms (node)`);
}
console.log(`${checks - fails}/${checks} checks passed (${nPeak} peak comparisons, ${nProbe} render probes)`);
process.exit(fails ? 1 : 0);
