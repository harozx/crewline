import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor

from crewline.crew.models import Choice
from crewline.evals import kafka
from crewline.locate import baseline, rerank

W={"path":0.5,"history":3,"symbols":0.5,"mentions":3}
split, n, cli, model = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
rows=kafka.rankings(split)[:n]
tickets={t["key"]:t for t in kafka.load()}
idx=json.load(open(next((kafka.paths()[1]).glob("symbols-*.json"))))
ch=Choice(cli, model, "low" if cli=="codex" else None)
def one(r):
    fused=baseline.fuse(*[r[c] for c in W], weights=list(W.values()), k=30)
    t=tickets[r["key"]]
    rr=rerank.rerank(f'# {t["summary"]}\n\n{t["description"]}', fused, idx, ch)
    return fused, rr, r["gold"]
with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(one, rows))
fail=sum(1 for _,rr,_ in out if rr is None)
for k in (1,5,10):
    a=statistics.mean(kafka.recall(f,g,k) for f,_,g in out)
    b=statistics.mean(kafka.recall(rr or f,g,k) for f,rr,g in out)
    print(f"{model} {split} n={len(out)} fail={fail} r@{k}: fused {a:.3f} -> rerank {b:.3f}")
