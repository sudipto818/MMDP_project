# Which Screen Was It?

DA3021 final project (IIT Guwahati). **Why do screen-photo detectors miss phone (OLED) screens, and when can a photo of a screen reveal what kind of screen it shows?** Answered with the sampling theorem, the convolution theorem and a simulated screen + camera. CPU only, no recording, no participants. The only download is the 24 Kodak test images.

## Open the website
Double-click `site/index.html` (works offline, from `file://`, in any current browser). Chapter 2 is the live demo: move distance, angle and blur and watch moiré appear and vanish, with the **theory-predicted peaks drawn as circles** on the spectrum.

## Results (measured; full run, seed 0)
| | Result |
|---|---|
| **E1** photos at 15–40 cm | AUC laptop LCD **0.97**, monitor LCD **1.00**, phone OLED **0.57** (95% CI 0.52–0.62). Training on phone-screen photos too (detector B) does not help: 0.57 vs 0.56. |
| **E2** matched r (control) | Both layouts ≥ 0.98 at r ≈ 0.5 and at chance (≈ 0.5) for r ≥ 0.9. AUC < 0.9 at r₉₀ = **0.61** (LCD), **0.69** (PenTile). PenTile survives slightly longer, so the curves do not overlap exactly. |
| **E3** theory vs measurement | One logistic curve for both layouts, R² = **0.993** (lens × Bayer-demosaic theory; this variant was picked *after* seeing the fits), 0.958 (lens only), **0.989 with r alone**: the theory axis is only marginally better than r (the blur varies over a narrow range), but it predicts the thresholds without fitting (predicted r₉₀ 0.70/0.66 vs measured 0.61/0.69) and the moiré peak positions (in a diagnostic on one image at r = 0.3 and 0.6, the strongest predicted peaks were among the 1st–7th strongest of 400–500 measured local maxima, for both layouts). |
| **E4** which screen? | Logistic on a spectral signature (scene-grouped CV): **99–100%** at r ≤ 0.5, 90% at 0.68, 72% at 0.89, **70% at 1.12** (n = 80 per point), chance (48–56%) by r ≈ 1.4–1.8. The signal beyond r ≈ 0.9 is in **colour**: chroma signature alone 78% at 0.89 and 65% at 1.12, luma alone 49% and 53% (Bayer colour moiré outlives the luma lattice). Template at *known* geometry (no training): 94–98% at r ≤ 0.5. Free-search template: **chance (51%) – a negative result** (multiple-comparison problem; see below). |
| **E7** does an LCD-trained detector transfer? | Yes, in simulation. Detector A (trained only on LCD-device photos), scored on test scenes at matched r (n = 40 pairs per point): AUC on LCD / PenTile = 1.00 / 1.00 at r ≈ 0.5, 0.85 / **0.97** at 0.7, 0.56 / **0.82** at 0.9, 0.44 / 0.63 at 1.1, chance beyond. So a layout mismatch does not hide OLED-style screens; only small pixels do. |
| **E5** defence rule | Detectable only within **12 cm** (phone OLED, binned camera) / **23 cm** (full-res); laptop LCD 33 / 66 cm; monitor 51 / 102 cm. Depends on assumed pixel pitches and focal length. |
| **E6** robustness | Sharpening (0.5) and strong JPEG (q 55–70) do **not** bring traces back beyond r ≈ 0.9 (AUC 0.55–0.60 at r = 0.9, ≈ 0.5 beyond). |

## Real-photo check (34 photos, Motorola Edge main camera, 24 Nov 2026)
Two pictures (parrots, a house) shown in a window on an **HP Victus 15 laptop** (15.6" 1920×1080 IPS LCD, 141 ppi, pitch 0.180 mm) and on a **Moto G32** (6.5" 1080×2400 IPS **LCD**, about 405 ppi, pitch 0.063 mm: *an LCD, not an OLED*), photographed at 12, 20, 35 and 50 cm (laptop) / 12, 20, 35 cm (G32), 2 shots each, plus 6 ordinary scenes. All JPEG, 4096×1842, default camera settings (HDR not switched off), never resized. Only the displayed picture's region is analysed (found automatically for 27 photos, placed by hand for 5: `data/real/roi_overrides.csv`; every box was checked by eye). Because both screens are LCD stripes, the real test varies **pixel size at fixed layout**; it does not test OLED or PenTile.

**Step 1, calibrate the camera from the photos themselves** (`analyze_real.py`): at 12 and 20 cm the laptop's lattice is resolved, and a template fit (known layout, free r and angle) gives r = 0.25-0.33 and 0.46-0.51. The ratio 1.71 matches the thin-lens prediction (d - f), 1.70, and both distances give the same effective camera pixel, **2.45 and 2.47 µm** (the EXIF-based guess, 1.95 µm, was 20% low). **Step 2:** r for every condition from distance, the real pixel pitches and that pixel. **Step 3:** compare with the simulation.

| Condition (4 photos each) | r | Simulated AUC at that r | Peakiness mean (range) | Photos above the largest ordinary photo |
|---|---|---|---|---|
| ordinary photos (6) | | | 2.15 (1.55-2.48) | |
| laptop 12 cm | 0.28 | 1.00 | **3.95** (3.29-4.33) | 4/4 |
| laptop 20 cm | 0.48 | 0.98 | **3.32** (2.80-3.93) | 4/4 |
| laptop 35 cm | 0.85 | 0.57 | 2.06 (1.92-2.16) | 0/4 |
| laptop 50 cm | 1.22 | 0.51 | 1.97 (1.76-2.11) | 0/4 |
| G32 12 cm | 0.81 | 0.63 | 2.35 (2.21-2.49) | 1/4 (borderline) |
| G32 20 cm | 1.37 | 0.49 | 1.95 (1.77-2.30) | 0/4 |
| G32 35 cm | 2.43 | 0.49 | 1.88 (1.61-2.22) | 0/4 |

**Reading.** The laptop at 12 and 20 cm (used for the calibration) shows the lattice and clear spectral spots. The **other five conditions were predicted** from distance, pixel pitch and the calibrated pixel, and the real outcome agrees with the simulated AUC in every one of them (`figs/real_vs_sim.png`: the real peakiness values sit on the simulated curve and inside the simulated band). A pixel-size ratio of about 3 between the two LCDs (141 vs 405 ppi) is what separates "lattice visible" from "not visible" at the same distance. **Caveats:** one camera, two pictures, n = 4 per condition, no confidence intervals; r depends on nominal distances (string, ±1 cm) and on the assumed laptop and G32 pixel pitches (from spec sheets); the ordinary photos show different content from the screen photos (a printed copy of the same picture, the right control, was not taken); a template-fit baseline gives 6.8/12 predicted peaks on bright bins for resolved lattices against 4.7/12 for images without one (counts overlap, so the fit score, 2.3 vs 1.2, is the better statistic and `figs/real_peaks.png` is diagnostic only). **The frozen detector's probability is not reliable on real photos:** ordinary photos get P(screen) of about 0.56 and the 35-50 cm screen photos score *below* them (a domain gap: real noise, HDR/sharpening, textured real scenes); the raw spectral feature and the spectra are the trustworthy evidence. Nothing was retuned to fit these photos.

## Run it
```
pip install -r requirements.txt
python get_data.py                 # 24 Kodak images, ~1 min (internet needed once)
python -m pytest -q                # 35 tests, ~35 s
python precompute.py               # experiments E1-E7 + site export; 4 worker processes
python report_figs.py              # figures -> figs/
node site/test/node_check.js       # optional: checks the JavaScript port against the Python reference (needs Node)
python score_real.py               # real photos (folders in data/real/): picture-region finder + frozen detector
python analyze_real.py             # camera calibration from the photos, r per condition, real vs simulation
```
Measured on a Core i5-13420H laptop (4 performance + 4 efficiency cores, CPU only):

| Step | Wall-clock time |
|---|---|
| `get_data.py` | ≈ 1 min (network) |
| `pytest` | ≈ 35 s |
| `precompute.py` full (900 + 640 + 540 + 640 = 2,720 image pairs, 4 jobs) | **586 s (9 min 46 s)** in the final from-scratch run (E1 154 s, E2 134 s, E6 100 s, E7 131 s, analysis + export ≈ 60 s); an earlier run without E7 took 465 s |
| `precompute.py --quick` (~⅓ of the data) | ≈ 165 s |
| `report_figs.py` | ≈ 10 s |
| Everything from scratch | ≈ 12–13 min |

`--jobs 4` is the measured optimum here; more workers are slower (memory-bound renderer on 4P+4E cores). Per image pair: ≈ 0.2 s wall clock with 4 jobs, ≈ 0.7 s on one core. **Reproducibility:** a from-scratch rerun (`--force`) with the final code reproduced all 917 numbers of E1–E6 exactly (`python dev/compare_runs.py <old results.json> <new results.json>`).

> **The original photos are not in this repository** (they show the author's room and belongings). `data/real/README.md` describes the expected folder layout; `score_real.py` and `analyze_real.py` need those photos to re-run. Their outputs are kept in `cache/real_results.csv`, `cache/real_geometry.json`, `figs/real_*.png`, and the cropped examples in `site/img/`.

## Your own phone photos (optional, recommended)
Put original files (no WhatsApp re-compression, 1× zoom, no portrait/HDR-beauty modes) in `data/real/` and describe them in `data/real/meta.csv`:
```
file,kind,screen,distance_cm,phone_model,notes
laptop_25cm_01.jpg,screen,laptop_lcd,25,<model>,
direct_01.jpg,direct,none,,<model>,
```
`python score_real.py` applies the **frozen** detector (trained only on simulation) and writes `cache/real_results.csv` and `figs/real_scores.png`. Photos are never resized. Do not retune anything to fit them: if real photos disagree with the simulation, report the gap, then test phone sharpening in the simulator as a possible cause.

## Folder map
```
config.py            all constants and the (assumed) device geometry
get_data.py          Kodak download
core/                layouts, analytic renderer, camera, theory, masks, features, stats, pair generator
tests/               35 tests (renderer vs fine-grid reference, frequency convention, harmonics, exposure, guard against the zero-band bug, ...)
precompute.py        E1-E7, cache/*.npz, cache/results.json, site/data/data.js, site/img/*
report_figs.py       figs/fig1..fig8
score_real.py        frozen detector on real photos (folder layout, automatic picture region, manual overrides)
analyze_real.py      camera geometry from the photos, r per condition, real-vs-simulation figure
export_real_site.py  real-photo crops and results for the website's Lesson 7 (site/data/real.js, site/img/real_*.png)
site/                static website, 7 lessons (index.html, css/, js/, data/data.js, data/real.js, img/, test/node_check.js)
dev/                 small diagnostic scripts used while building (profiling, peak ranks)
```

## Method (one paragraph)
Each screen pixel emits light from small rectangles (RGB stripes, or diamond PenTile with a red/blue checkerboard). The lens blurs the emitted light with a Gaussian, computed exactly (box ⊛ Gaussian = a difference of normal CDFs); the camera samples it on a rotated lattice of pitch *r* (camera pixel / screen pixel), then applies shared auto-exposure, shot and read noise, a Bayer mosaic, bilinear demosaicing (a convolution), gamma, 8 bits and JPEG. A recapture and a direct photo of the same crop share every camera parameter and differ only in the screen. The feature is the "peakiness" of the log spectrum after removing each radial ring's median and masking low frequencies, the JPEG 8×8 grid and the Bayer frequencies. Theory: the layout's Fourier harmonics map to `f_cam = r·R(−θ)·f_screen`, fold into [−½, ½) (aliasing), and are scaled by the lens MTF `exp(−2π²σ²f²)` and by the per-channel demosaic response.

## Honest limits
* **Mostly simulation.** The central results are simulated; 34 real photos (one camera, two screens, both LCD) are consistent with them but do not prove them. Real phones sharpen, denoise, merge frames and use other OLED layouts; real OLED flicker banding is not modelled. Only two layouts are modelled.
* **The published gap is not reproduced from their data.** Trabelsi et al.'s OLED photos show a 15-inch laptop OLED screen taken with phone front cameras (Samsung S6/S8 phone OLED screens are in their test sets); the paper gives no pixel pitches or distances, so I cannot say which r their photos had. The mechanism here is a candidate explanation (small screen pixels relative to the camera's), shown in simulation, not a demonstrated cause of their result.
* **Assumed geometry**: pitches 0.179 mm (15.6" FHD laptop), 0.277 mm (24" FHD monitor), 0.055 mm (≈ 460 ppi phone); camera focal length 6 mm, pixel 2.0 µm (binned) or 1.0 µm (full). Verify against spec sheets before quoting distances.
* **The free-search template classifier fails** (≈ chance): maximising over 4,653 (r, θ) hypotheses × 12 peaks finds strong spectral content for any layout, and PenTile also contains the LCD's integer harmonics. With the geometry known the template test works.
* **E3**: with 8 points per layout the fits are descriptive. r alone fits almost as well as the theory axis.
* Pairs are generated from 24 Kodak scenes (train scenes 1–16, test 17–24 for E1; scene-grouped 3-fold CV for E4). Confidence intervals are bootstrap over pairs.
* The website's "predicted detection AUC" readout has a coincidence guard (`predictedAUC` in `site/js/theory.js`): at r = 1/4 or 1/2 every harmonic folds exactly onto a masked bin (JPEG 8x8 grid or Bayer frequencies), so the strongest surviving peak collapses although the moiré is plain; only then the best amplitude within ±6% of r is used. All other values are unchanged (0.92 at r = 0.7, 0.62 at r = 0.9, against measured 0.85 and 0.52).
* The live website demo omits noise and JPEG and uses bilinear interpolation for the direct photo; it is checked against the Python code (`node site/test/node_check.js`: peak bins identical, amplitudes within 1e-6, rendered pixels within 2%).
* A literature search cannot prove nothing exists. Known: recapture detection from moiré/aliasing, LCD-only datasets, OLED gap (Trabelsi et al., EURECOM). New here (to my knowledge): the sampling-theory explanation with a same-*r* control, layout identification from the moiré's reciprocal lattice, and the capture-distance rule.

## Data and references
Kodak Lossless True Colour Image Suite (r0k.us/graphics/kodak), free for research. Trabelsi et al., *Recapture detection to fight deep identity theft* (EURECOM); Thongkamwitoon, Muammar & Dragotti, IEEE TIFS 2015; domain-generalised recapture identification, arXiv 2407.17170; on-device multi-display recapture defence, arXiv 2604.12178.
