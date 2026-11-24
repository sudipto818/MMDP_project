/* Radix-2 FFT (1-D and 2-D, in place). Classic script: defines window.WS.fft */
(function (g) {
  const WS = g.WS = g.WS || {};
  const cache = {};

  function plan(n) {
    if (cache[n]) return cache[n];
    const rev = new Uint32Array(n);
    let bits = 0; while ((1 << bits) < n) bits++;
    for (let i = 0; i < n; i++) {
      let x = i, r = 0;
      for (let b = 0; b < bits; b++) { r = (r << 1) | (x & 1); x >>= 1; }
      rev[i] = r;
    }
    const cos = new Float64Array(n / 2), sin = new Float64Array(n / 2);
    for (let k = 0; k < n / 2; k++) { cos[k] = Math.cos(2 * Math.PI * k / n); sin[k] = -Math.sin(2 * Math.PI * k / n); }
    return (cache[n] = { rev, cos, sin });
  }

  /** In-place FFT of the complex sequence (re[off + k*stride], im[...]) of length n. */
  function fft1(re, im, n, off, stride) {
    const { rev, cos, sin } = plan(n);
    const tr = new Float64Array(n), ti = new Float64Array(n);
    for (let i = 0; i < n; i++) { tr[rev[i]] = re[off + i * stride]; ti[rev[i]] = im[off + i * stride]; }
    for (let size = 2; size <= n; size <<= 1) {
      const half = size >> 1, step = n / size;
      for (let start = 0; start < n; start += size) {
        for (let k = 0; k < half; k++) {
          const wr = cos[k * step], wi = sin[k * step];
          const a = start + k, b = a + half;
          const xr = tr[b] * wr - ti[b] * wi, xi = tr[b] * wi + ti[b] * wr;
          tr[b] = tr[a] - xr; ti[b] = ti[a] - xi;
          tr[a] += xr; ti[a] += xi;
        }
      }
    }
    for (let i = 0; i < n; i++) { re[off + i * stride] = tr[i]; im[off + i * stride] = ti[i]; }
  }

  /** 2-D FFT of an n x n image stored row-major in re/im (in place). */
  function fft2(re, im, n) {
    for (let r = 0; r < n; r++) fft1(re, im, n, r * n, 1);
    for (let c = 0; c < n; c++) fft1(re, im, n, c, n);
  }

  WS.fft = { fft1, fft2 };
})(window);
