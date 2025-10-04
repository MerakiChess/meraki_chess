from future import annotations
import argparse, time, csv, os
import chess, matplotlib.pyplot as plt
from ..io.fen_utils import to_board
from ..engine.searcher import Searcher

def main()->None:
ap=argparse.ArgumentParser()
ap.add_argument("--fen", default="startpos")
ap.add_argument("--dmin", type=int, default=2)
ap.add_argument("--dmax", type=int, default=8)
ap.add_argument("--time-ms", type=int, default=2000)
ap.add_argument("--coeff", default=None)
ap.add_argument("--out", default="bench_out")
args=ap.parse_args()
os.makedirs(args.out, exist_ok=True)
base=to_board(args.fen)
rows=[]
for d in range(args.dmin, args.dmax+1):
s=Searcher(coeff_path=args.coeff)
b=base.copy()
t0=time.time()
mv=s.search(b, d, args.time_ms)
dt=time.time()-t0
nps=int(s.nodes/max(1e-6,dt))
rows.append({"depth":d,"time_s":round(dt,3),"nodes":s.nodes,"nps":nps,"move": mv.uci()})
print(f"d{d}: {rows[-1]}")
csv_path=os.path.join(args.out,"bench.csv")
with open(csv_path,"w",newline="") as f:
w=csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
depths=[r["depth"] for r in rows]; times=[r["time_s"] for r in rows]; nps=[r["nps"] for r in rows]
plt.figure(); plt.plot(depths,times,marker="o"); plt.title("Time vs Depth"); plt.xlabel("Depth"); plt.ylabel("Time (s)"); plt.savefig(os.path.join(args.out,"time_vs_depth.png"))
plt.figure(); plt.plot(depths,nps,marker="o"); plt.title("NPS vs Depth"); plt.xlabel("Depth"); plt.ylabel("Nodes/s"); plt.savefig(os.path.join(args.out,"nps_vs_depth.png"))
print(f"saved: {csv_path}")

if name=="main":
main()