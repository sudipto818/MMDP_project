"""numpy-only statistics: logistic regression (IRLS), AUC, bootstrap CI, curve fit."""
import numpy as np
from scipy.optimize import curve_fit


def standardize_fit(X):
    return X.mean(0), X.std(0) + 1e-9


def standardize_apply(X, mu, sd):
    return (X - mu) / sd


def logistic_irls(X, y, l2=1.0, iters=50):
    """Newton / IRLS for L2-regularised logistic regression. Returns w (bias first)."""
    X1 = np.c_[np.ones(len(X)), X]
    w = np.zeros(X1.shape[1])
    reg = l2 * np.eye(len(w)); reg[0, 0] = 0.0                 # do not penalise the bias
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(X1 @ w, -30, 30)))
        W = p * (1 - p) + 1e-9
        step = np.linalg.solve(X1.T @ (X1 * W[:, None]) + reg, X1.T @ (p - y) + reg @ w)
        w -= step
        if np.linalg.norm(step) < 1e-6:
            break
    return w


def predict_proba(w, X):
    return 1.0 / (1.0 + np.exp(-np.clip(np.c_[np.ones(len(X)), X] @ w, -30, 30)))


def auc(scores, y):
    """Mann-Whitney AUC via ranks (ties get average rank). y in {0, 1}."""
    scores, y = np.asarray(scores, float), np.asarray(y)
    n1, n0 = int((y == 1).sum()), int((y == 0).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    order = np.argsort(scores, kind="mergesort")
    s = scores[order]
    ranks = np.empty(len(s))
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        ranks[i:j + 1] = (i + j) / 2.0 + 1
        i = j + 1
    r = np.empty(len(s)); r[order] = ranks
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def auc_boot_ci(scores, y, n_boot=1000, rng=None, pair_ids=None):
    """Percentile 95% CI of the AUC. If pair_ids is given, whole pairs are resampled together."""
    rng = rng or np.random.default_rng(0)
    scores, y = np.asarray(scores), np.asarray(y)
    if pair_ids is None:
        n = len(y)
        draws = [rng.integers(0, n, n) for _ in range(n_boot)]
    else:
        pair_ids = np.asarray(pair_ids)
        uniq = np.unique(pair_ids)
        groups = [np.flatnonzero(pair_ids == u) for u in uniq]
        draws = []
        for _ in range(n_boot):
            pick = rng.integers(0, len(uniq), len(uniq))
            draws.append(np.concatenate([groups[k] for k in pick]))
    vals = np.array([auc(scores[d], y[d]) for d in draws])
    vals = vals[~np.isnan(vals)]
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def _sigmoid_curve(x, c, s):
    return 0.5 + 0.5 / (1.0 + np.exp(-(x - c) / s))


def fit_auc_curve(x, y):
    """Fit AUC = 0.5 + 0.5 / (1 + exp(-(x - c)/s)). Returns (c, s, r2)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    p0 = [np.median(x), max(np.std(x) / 2, 0.05)]
    (c, s), _ = curve_fit(_sigmoid_curve, x, y, p0=p0, maxfev=20000)
    pred = _sigmoid_curve(x, c, s)
    ss_res, ss_tot = ((y - pred) ** 2).sum(), ((y - y.mean()) ** 2).sum()
    return float(c), float(abs(s)), float(1 - ss_res / ss_tot if ss_tot > 0 else 0.0)


def curve_value(x, c, s):
    return _sigmoid_curve(np.asarray(x, float), c, s)


def curve_inverse(a, c, s):
    """x at which the fitted curve equals AUC a (0.5 < a < 1)."""
    return c - s * np.log(0.5 / (a - 0.5) - 1.0)
