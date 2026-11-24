import os
for v in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"): os.environ.setdefault(v,"1")
import time, sys, numpy as np
from multiprocessing import Pool
import config as C
from core.sample import run_task, random_params

def tasks(n):
    out=[]
    for k in range(n):
        rng=np.random.default_rng(k)
        layout=C.LAYOUT_NAMES[k%2]; r=[0.4,0.9,1.6,2.2][k%4]
        p=random_params(rng,r)
        out.append({"layout":layout,"scene":int(rng.integers(1,25)),**p,"seed":k})
    return out

if __name__=="__main__":
    T=tasks(48)
    for jobs in (1,4,8,11):
        t=time.time()
        if jobs==1: [run_task(x) for x in T]
        else:
            with Pool(jobs) as p: list(p.imap(run_task,T,chunksize=2))
        print(f"jobs={jobs:2d}: {time.time()-t:6.1f}s for 48 pairs -> {(time.time()-t)/48*1000:.0f} ms/pair", flush=True)
