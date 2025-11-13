import wx
import wx.lib.plot as plot  # またはmatplotlibの埋め込みを使用
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.figure import Figure
import psutil
import time
from datetime import datetime
import os
import csv
from typing import Optional, List, Dict, Any

# GPUは任意（無ければスキップ）
try:
    import pynvml  # pip install nvidia-ml-py3
    _HAVE_NVML = True
except Exception:
    _HAVE_NVML = False

class MonitorGUI(wx.Frame):
    def __init__(self, parent):
        super().__init__(parent, title="Resource Monitor", size=(1000, 700))
        
        self.proc = None
        self.have_nvml = _init_nvml()
        self.monitoring = False
        self.rows: List[Dict[str, Any]] = []
        self.t0 = 0
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self.timer)
        
        self._build_ui()
        self._init_figure()

    def _build_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Input controls
        input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        input_sizer.Add(wx.StaticText(panel, label="PID (None for self):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.pid_ctrl = wx.TextCtrl(panel, value="", size=(100, -1))
        input_sizer.Add(self.pid_ctrl, 0, wx.ALL, 5)
        input_sizer.Add(wx.StaticText(panel, label="Interval (ms):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.interval_ctrl = wx.TextCtrl(panel, value="200", size=(100, -1))
        input_sizer.Add(self.interval_ctrl, 0, wx.ALL, 5)
        input_sizer.Add(wx.StaticText(panel, label="Duration (s):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.duration_ctrl = wx.TextCtrl(panel, value="30.0", size=(100, -1))
        input_sizer.Add(self.duration_ctrl, 0, wx.ALL, 5)
        main_sizer.Add(input_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.start_btn = wx.Button(panel, label="Start Monitoring")
        self.start_btn.Bind(wx.EVT_BUTTON, self._on_start)
        btn_sizer.Add(self.start_btn, 0, wx.ALL, 5)
        self.stop_btn = wx.Button(panel, label="Stop Monitoring")
        self.stop_btn.Bind(wx.EVT_BUTTON, self._on_stop)
        self.stop_btn.Enable(False)
        btn_sizer.Add(self.stop_btn, 0, wx.ALL, 5)
        self.save_btn = wx.Button(panel, label="Save CSV & PNG")
        self.save_btn.Bind(wx.EVT_BUTTON, self._on_save)
        btn_sizer.Add(self.save_btn, 0, wx.ALL, 5)
        main_sizer.Add(btn_sizer, 0, wx.ALL, 5)
        
        # Log
        main_sizer.Add(wx.StaticText(panel, label="Log:"), 0, wx.ALL, 5)
        self.log_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 100))
        main_sizer.Add(self.log_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        
        # Graph
        main_sizer.Add(wx.StaticText(panel, label="Real-time Graphs:"), 0, wx.ALL, 5)
        self.graph_panel = wx.Panel(panel, size=(-1, 300))
        main_sizer.Add(self.graph_panel, 1, wx.EXPAND | wx.ALL, 5)
        
        panel.SetSizer(main_sizer)

    def _init_figure(self):
        self.figure = Figure()
        self.ax1 = self.figure.add_subplot(221)  # Process CPU
        self.ax2 = self.figure.add_subplot(222)  # System CPU
        self.ax3 = self.figure.add_subplot(223)  # Memory
        self.ax4 = self.figure.add_subplot(224)  # GPU (if available)
        self.canvas = FigureCanvas(self.graph_panel, -1, self.figure)

    def _on_start(self, event):
        try:
            pid = int(self.pid_ctrl.GetValue()) if self.pid_ctrl.GetValue() else None
            interval_ms = int(self.interval_ctrl.GetValue())
            duration_s = float(self.duration_ctrl.GetValue())
        except ValueError:
            wx.MessageBox("Invalid input values.", "Error", wx.ICON_ERROR)
            return
        
        self.proc = _init_process(pid)
        psutil.cpu_percent(None)  # System CPU init
        self.rows = []
        self.t0 = time.perf_counter()
        self.monitoring = True
        self.start_btn.Enable(False)
        self.stop_btn.Enable(True)
        self.timer.Start(interval_ms)
        self.log_ctrl.AppendText(f"Monitoring started. PID: {pid}, Interval: {interval_ms}ms, Duration: {duration_s}s\n")

    def _on_stop(self, event):
        self.monitoring = False
        self.timer.Stop()
        self.start_btn.Enable(True)
        self.stop_btn.Enable(False)
        self.log_ctrl.AppendText("Monitoring stopped.\n")
        self._update_graph()

    def _on_timer(self, event):
        now = time.perf_counter()
        t = now - self.t0
        duration_s = float(self.duration_ctrl.GetValue())
        if t > duration_s:
            self._on_stop(None)
            return
        
        # Collect data
        sys_cpu = psutil.cpu_percent(None)
        sys_mem = psutil.virtual_memory().percent
        
        proc_cpu = None
        proc_rss_mb = None
        if self.proc:
            try:
                proc_cpu = self.proc.cpu_percent(None)
                proc_rss_mb = self.proc.memory_info().rss / (1024 * 1024)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.proc = None
        
        gpu = _read_gpu() if self.have_nvml else {"gpu_util_avg": None, "gpu_mem_used_mib": None}
        
        self.rows.append({
            "t_sec": round(t, 3),
            "proc_cpu_percent": None if proc_cpu is None else round(proc_cpu, 2),
            "proc_rss_mb": None if proc_rss_mb is None else round(proc_rss_mb, 3),
            "sys_cpu_percent": round(sys_cpu, 2),
            "sys_mem_percent": round(sys_mem, 2),
            "gpu_util_avg": None if gpu["gpu_util_avg"] is None else round(gpu["gpu_util_avg"], 2),
            "gpu_mem_used_mib": None if gpu["gpu_mem_used_mib"] is None else round(gpu["gpu_mem_used_mib"], 2),
        })
        
        self._update_graph()

    def _update_graph(self):
        if not self.rows:
            return
        x = [r["t_sec"] for r in rows]
        
        # Process CPU
        y = [r["proc_cpu_percent"] for r in self.rows if r["proc_cpu_percent"] is not None]
        x_p = [r["t_sec"] for r in self.rows if r["proc_cpu_percent"] is not None]
        self.ax1.clear()
        if y:
            self.ax1.plot(x_p, y)
            self.ax1.set_title("Process CPU%")
        
        # System CPU
        self.ax2.clear()
        self.ax2.plot(x, [r["sys_cpu_percent"] for r in self.rows])
        self.ax2.set_title("System CPU%")
        
        # Memory
        self.ax3.clear()
        self.ax3.plot(x, [r["sys_mem_percent"] for r in self.rows], label="Sys Mem%")
        y_mem = [r["proc_rss_mb"] for r in self.rows if r["proc_rss_mb"] is not None]
        x_mem = [r["t_sec"] for r in self.rows if r["proc_rss_mb"] is not None]
        if y_mem:
            self.ax3.plot(x_mem, y_mem, label="Proc RSS (MiB)")
        self.ax3.legend()
        self.ax3.set_title("Memory")
        
        # GPU
        self.ax4.clear()
        if self.have_nvml:
            y_gpu = [r["gpu_util_avg"] for r in self.rows if r["gpu_util_avg"] is not None]
            x_gpu = [r["t_sec"] for r in self.rows if r["gpu_util_avg"] is not None]
            if y_gpu:
                self.ax4.plot(x_gpu, y_gpu, label="GPU Util%")
            y_mem_gpu = [r["gpu_mem_used_mib"] for r in self.rows if r["gpu_mem_used_mib"] is not None]
            x_mem_gpu = [r["t_sec"] for r in self.rows if r["gpu_mem_used_mib"] is not None]
            if y_mem_gpu:
                self.ax4.plot(x_mem_gpu, y_mem_gpu, label="GPU Mem (MiB)")
            self.ax4.legend()
            self.ax4.set_title("GPU")
        else:
            self.ax4.text(0.5, 0.5, "GPU not available", ha="center", va="center", transform=self.ax4.transAxes)
        
        self.canvas.draw()

    def _on_save(self, event):
        if not self.rows:
            wx.MessageBox("No data to save.", "Error", wx.ICON_ERROR)
            return
        
        outdir = "monitor_out"
        os.makedirs(outdir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = os.path.join(outdir, f"monitor_{stamp}.csv")
        
        fieldnames = [
            "t_sec", "proc_cpu_percent", "proc_rss_mb", "sys_cpu_percent", "sys_mem_percent",
            "gpu_util_avg", "gpu_mem_used_mib"
        ]
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(self.rows)
        
        png_path = os.path.join(outdir, f"graphs_{stamp}.png")
        self.figure.savefig(png_path)
        
        self.log_ctrl.AppendText(f"CSV saved: {csv_path}\nPNG saved: {png_path}\n")

def _init_process(pid: Optional[int]) -> Optional[psutil.Process]:
    if pid is None:
        p = psutil.Process()
    else:
        p = psutil.Process(pid)
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
            util = pynvml.nvmlDeviceGetUtilizationRates(h).gpu
            mem = pynvml.nvmlDeviceGetMemoryInfo(h).used / (1024 * 1024)
            utils.append(util)
            mems.append(mem)
        out["gpu_util_avg"] = sum(utils) / len(utils)
        out["gpu_mem_used_mib"] = sum(mems)
    except Exception:
        pass
    return out

if __name__ == "__main__":
    app = wx.App()
    frame = MonitorGUI(None)
    frame.Show()
    app.MainLoop()
