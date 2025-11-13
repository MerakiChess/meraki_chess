# file: monitor_resources.py
# 依存: pip install psutil matplotlib
from __future__ import annotations
import argparse
import csv
import os
import time
from datetime import datetime
from typing import Optional, List, Dict, Any

import psutil
import matplotlib.pyplot as plt

# GPUは任意（無ければスキップ）
try:
    import pynvml  # pip install nvidia-ml-py3
    _HAVE_NVML = True
except Exception:
    _HAVE_NVML = False


def _init_process(pid: Optional[int]) -> Optional[psutil.Process]:
    if pid is None:
        p = psutil.Process()
    else:
        p = psutil.Process(pid)
    # 最初の呼び出しで基準化（直後の%が0にならないように）
    try:
        p.cpu_percent(None)
    except Exception:
        pass
    return p


def _init_nvml() -> bool:
    if not _HAVE_NVML:
        return False
    try:
        pynvml.nvmlInit()
        return True
    except Exception:
        return False


def _read_gpu() -> Dict[str, Any]:
    """全GPUの平均utilと合計メモリ使用(MiB)を返す。NVML未初期化なら空。"""
    out = {"gpu_util_avg": None, "gpu_mem_used_mib": None}
    if not _HAVE_NVML:
        return out
    try:
        count = pynvml.nvmlDeviceGetCount()
        if count == 0:
            return out
        utils = []
        mems = []
        for i in range(count):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            util = pynvml.nvmlDeviceGetUtilizationRates(h).gpu  # %
            mem = pynvml.nvmlDeviceGetMemoryInfo(h).used / (1024 * 1024)  # MiB
            utils.append(util)
            mems.append(mem)
        out["gpu_util_avg"] = sum(utils) / len(utils)
        out["gpu_mem_used_mib"] = sum(mems)  # 合計MiB
    except Exception:
        pass
    return out


def _plot_xy(x, y, title, xlabel, ylabel, out_png: str):
    plt.figure()
    plt.plot(x, y)  # 色指定なし、単独プロット
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.tight_layout()
    plt.savefig(out_png)
    plt.close()


def main():
    ap = argparse.ArgumentParser(description="CPU/Memory/(GPU) monitoring to CSV and PNG.")
    ap.add_argument("--pid", type=int, default=None, help="対象プロセスPID（未指定なら自プロセス）")
    ap.add_argument("--interval-ms", type=int, default=200, help="サンプリング間隔[ms]")
    ap.add_argument("--duration-s", type=float, default=30.0, help="計測時間[s]")
    ap.add_argument("--outdir", default="monitor_out", help="出力先ディレクトリ")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(args.outdir, f"monitor_{stamp}.csv")

    proc = _init_process(args.pid)
    have_nvml = _init_nvml()

    # system CPUの初期化
    psutil.cpu_percent(None)

    interval = max(10, args.interval_ms) / 1000.0
    t0 = time.perf_counter()

    rows: List[Dict[str, Any]] = []
    # 事前に列を定義（GPU列は None 許容）
    fieldnames = [
        "t_sec",
        "proc_cpu_percent",
        "proc_rss_mb",
        "sys_cpu_percent",
        "sys_mem_percent",
        "gpu_util_avg",
        "gpu_mem_used_mib",
    ]

    # 収集ループ
    while True:
        now = time.perf_counter()
        t = now - t0
        if t > args.duration_s:
            break

        # system
        sys_cpu = psutil.cpu_percent(None)
        sys_mem = psutil.virtual_memory().percent

        # process
        proc_cpu = None
        proc_rss_mb = None
        if proc is not None:
            try:
                proc_cpu = proc.cpu_percent(None)
                proc_rss_mb = proc.memory_info().rss / (1024 * 1024)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                proc = None  # プロセスが消えたら以降None

        # gpu
        gpu = _read_gpu() if have_nvml else {"gpu_util_avg": None, "gpu_mem_used_mib": None}

        rows.append({
            "t_sec": round(t, 3),
            "proc_cpu_percent": None if proc_cpu is None else round(proc_cpu, 2),
            "proc_rss_mb": None if proc_rss_mb is None else round(proc_rss_mb, 3),
            "sys_cpu_percent": round(sys_cpu, 2),
            "sys_mem_percent": round(sys_mem, 2),
            "gpu_util_avg": None if gpu["gpu_util_avg"] is None else round(gpu["gpu_util_avg"], 2),
            "gpu_mem_used_mib": None if gpu["gpu_mem_used_mib"] is None else round(gpu["gpu_mem_used_mib"], 2),
        })

        # 待機
        sleep_left = interval - (time.perf_counter() - now)
        if sleep_left > 0:
            time.sleep(sleep_left)

    # CSV保存
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # グラフ（列ごとに個別PNG）
    x = [r["t_sec"] for r in rows]

    # プロセスCPU
    y = [r["proc_cpu_percent"] for r in rows if r["proc_cpu_percent"] is not None]
    x_p = [r["t_sec"] for r in rows if r["proc_cpu_percent"] is not None]
    if y:
        _plot_xy(x_p, y, "Process CPU% vs Time", "Time (s)", "Process CPU (%)",
                 os.path.join(args.outdir, f"proc_cpu_{stamp}.png"))

    # システムCPU
    _plot_xy(x, [r["sys_cpu_percent"] for r in rows], "System CPU% vs Time", "Time (s)", "System CPU (%)",
             os.path.join(args.outdir, f"sys_cpu_{stamp}.png"))

    # プロセスRSS
    y = [r["proc_rss_mb"] for r in rows if r["proc_rss_mb"] is not None]
    x_p = [r["t_sec"] for r in rows if r["proc_rss_mb"] is not None]
    if y:
        _plot_xy(x_p, y, "Process RSS vs Time", "Time (s)", "RSS (MiB)",
                 os.path.join(args.outdir, f"proc_rss_{stamp}.png"))

    # システムメモリ%
    _plot_xy(x, [r["sys_mem_percent"] for r in rows], "System Memory% vs Time", "Time (s)", "System Mem (%)",
             os.path.join(args.outdir, f"sys_mem_{stamp}.png"))

    # GPU（任意）
    y = [r["gpu_util_avg"] for r in rows if r["gpu_util_avg"] is not None]
    x_g = [r["t_sec"] for r in rows if r["gpu_util_avg"] is not None]
    if y:
        _plot_xy(x_g, y, "GPU Util% vs Time", "Time (s)", "GPU Util (%)",
                 os.path.join(args.outdir, f"gpu_util_{stamp}.png"))

    y = [r["gpu_mem_used_mib"] for r in rows if r["gpu_mem_used_mib"] is not None]
    x_g = [r["t_sec"] for r in rows if r["gpu_mem_used_mib"] is not None]
    if y:
        _plot_xy(x_g, y, "GPU Memory Used vs Time", "Time (s)", "MiB",
                 os.path.join(args.outdir, f"gpu_mem_{stamp}.png"))

    print(f"[OK] CSV: {csv_path}")
    print(f"[OK] PNGs saved in: {args.outdir}")


if __name__ == "__main__":
    main()
