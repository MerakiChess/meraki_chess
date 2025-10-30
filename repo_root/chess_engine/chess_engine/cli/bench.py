from __future__ import annotations
import argparse, time, csv, os, threading, queue
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import psutil
import matplotlib.pyplot as plt
import chess
from ..io.fen_utils import to_board
from ..engine.searcher import Searcher

@dataclass
class Sample:
    t: float         # secs since monitor start
    cpu: float       # process CPU percent
    rss: int         # bytes

class Monitor:
    """Process-level CPU%/RSSをinterval_ms間隔でサンプリング"""
    def __init__(self, interval_ms: int = 100) -> None:
        self.interval = max(10, int(interval_ms)) / 1000.0
        self.proc = psutil.Process()
        self._stop = threading.Event()
        self._thr: Optional[threading.Thread] = None
        self._buf: List[Sample] = []

    def start(self) -> None:
        # 1回目の呼び出しで基準化（直後の値が0%にならないように）
        try:
            self.proc.cpu_percent(None)
        except Exception:
            pass
        self._stop.clear()
        self._buf.clear()
        t0 = time.perf_counter()

        def run() -> None:
            while not self._stop.is_set():
                try:
                    cpu = self.proc.cpu_percent(None)  # 前回からの%（プロセス）
                    rss = self.proc.memory_info().rss
                except Exception:
                    cpu, rss = 0.0, 0
                t = time.perf_counter() - t0
                self._buf.append(Sample(t=t, cpu=cpu, rss=rss))
                time.sleep(self.interval)
        self._thr = threading.Thread(target=run, daemon=True)
        self._thr.start()

    def stop(self) -> List[Sample]:
        self._stop.set()
        if self._thr:
            self._thr.join(timeout=2.0)
        return list(self._buf)

def _save_series_csv(path: str, samples: List[Sample]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_sec", "cpu_percent", "rss_bytes"])
        for s in samples:
            w.writerow([f"{s.t:.3f}", f"{s.cpu:.2f}", s.rss])

def _summarize(samples: List[Sample]) -> Dict[str, Any]:
    if not samples:
        return {"avg_cpu": 0.0, "max_cpu": 0.0, "avg_rss_mb": 0.0, "max_rss_mb": 0.0}
    avg_cpu = sum(s.cpu for s in samples) / len(samples)
    max_cpu = max(s.cpu for s in samples)
    avg_rss = sum(s.rss for s in samples) / len(samples)
    max_rss = max(s.rss for s in samples)
    to_mb = lambda b: b / (1024.0 * 1024.0)
    return {
        "avg_cpu": round(avg_cpu, 2),
        "max_cpu": round(max_cpu, 2),
        "avg_rss_mb": round(to_mb(avg_rss), 2),
        "max_rss_mb": round(to_mb(max_rss), 2),
    }

def _plot_xy(x, y, title, xlabel, ylabel, out_png: str) -> None:
    plt.figure()
    plt.plot(x, y, marker="o")  # 色は指定しない
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.tight_layout()
    plt.savefig(out_png)
    plt.close()

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fen", default="startpos")
    ap.add_argument("--dmin", type=int, default=2)
    ap.add_argument("--dmax", type=int, default=8)
    ap.add_argument("--time-ms", type=int, default=2000)
    ap.add_argument("--coeff", default=None)
    ap.add_argument("--out", default="bench_out")
    ap.add_argument("--interval-ms", type=int, default=100, help="CPU/Memサンプリング間隔(ms)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    base = to_board(args.fen)

    summary_rows = []
    depths = []
    times = []
    nps_list = []
    avg_cpu_list = []
    max_cpu_list = []
    avg_rss_list = []
    max_rss_list = []

    for d in range(args.dmin, args.dmax + 1):
        s = Searcher(coeff_path=args.coeff)
        b = base.copy()

        mon = Monitor(interval_ms=args.interval_ms)
        mon.start()
        t0 = time.perf_counter()
        mv = s.search(b, d, args.time_ms)
        dt = time.perf_counter() - t0
        samples = mon.stop()

        nps = int(s.nodes / max(1e-6, dt))
        summ = _summarize(samples)

        row = {
            "depth": d,
            "time_s": round(dt, 3),
            "nodes": s.nodes,
            "nps": nps,
            "move": mv.uci() if mv else "",
            "avg_cpu_percent": summ["avg_cpu"],
            "max_cpu_percent": summ["max_cpu"],
            "avg_rss_mb": summ["avg_rss_mb"],
            "max_rss_mb": summ["max_rss_mb"],
        }
        summary_rows.append(row)
        print(f"d{d}: {row}")

        # depthごとの時系列CSV
        series_path = os.path.join(args.out, f"series_depth{d}.csv")
        _save_series_csv(series_path, samples)

        # 可視化用配列
        depths.append(d)
        times.append(row["time_s"])
        nps_list.append(nps)
        avg_cpu_list.append(row["avg_cpu_percent"])
        max_cpu_list.append(row["max_cpu_percent"])
        avg_rss_list.append(row["avg_rss_mb"])
        max_rss_list.append(row["max_rss_mb"])

    # 要約CSV
    csv_path = os.path.join(args.out, "bench.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        w.writerows(summary_rows)

    # グラフ（単独プロット）
    _plot_xy(depths, times, "Time vs Depth", "Depth", "Time (s)", os.path.join(args.out, "time_vs_depth.png"))
    _plot_xy(depths, nps_list, "NPS vs Depth", "Depth", "Nodes/s", os.path.join(args.out, "nps_vs_depth.png"))
    _plot_xy(depths, avg_cpu_list, "Avg CPU% vs Depth", "Depth", "Avg CPU (%)", os.path.join(args.out, "cpu_vs_depth.png"))
    _plot_xy(depths, avg_rss_list, "Avg RSS vs Depth", "Depth", "Avg RSS (MB)", os.path.join(args.out, "rss_vs_depth.png"))

    print(f"saved: {csv_path}")

if __name__ == "__main__":
    main()