"""Compare two results.json files (e.g. before / after a from-scratch rerun) number by number."""
import json
import sys
import numpy as np

a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))


def flat(x, prefix=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from flat(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(x, list):
        try:
            arr = np.asarray(x, dtype=float)
            for i, v in enumerate(arr.ravel()):
                yield f"{prefix}[{i}]", float(v)
        except (ValueError, TypeError):
            for i, v in enumerate(x):
                yield from flat(v, f"{prefix}[{i}]")
    elif isinstance(x, (int, float)) and not isinstance(x, bool):
        yield prefix, float(x)


fa, fb = dict(flat(a)), dict(flat(b))
common = [k for k in fa if k in fb and not k.startswith("_run")]
diffs = [(k, fa[k], fb[k]) for k in common if not (np.isnan(fa[k]) and np.isnan(fb[k])) and abs(fa[k] - fb[k]) > 1e-9 * max(1, abs(fa[k]))]
print(f"{len(common)} numbers compared, {len(diffs)} differ; only in old: {len([k for k in fa if k not in fb and not k.startswith('_run')])}, only in new: {len([k for k in fb if k not in fa and not k.startswith('_run')])}")
for k, x, y in diffs[:15]:
    print(f"  {k}: {x:.6g} -> {y:.6g}")
