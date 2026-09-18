"""tkinter 图形界面：选文件 -> 选目标格式 -> 转换。"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import converter
from formats import FORMATS, audio_formats, video_formats

FILE_TYPES = [
    ("媒体文件", "*.mp3 *.wav *.flac *.aac *.m4a *.ogg *.opus *.wma "
                "*.mp4 *.mkv *.avi *.mov *.flv *.webm *.wmv *.mpeg *.mpg *.ts"),
    ("所有文件", "*.*"),
]


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Media Converter —— 音视频格式转换")
        self.root.geometry("720x560")
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.files: list[str] = []
        self._build_ui()
        self.root.after(100, self._drain_queue)

    # ---- 界面 ----
    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # 文件列表
        file_frame = ttk.LabelFrame(main, text="待转换文件", padding=5)
        file_frame.pack(fill=tk.BOTH, expand=True)
        self.file_list = tk.Listbox(file_frame, selectmode=tk.EXTENDED)
        self.file_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(file_frame, orient=tk.VERTICAL, command=self.file_list.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_list.configure(yscrollcommand=scroll.set)

        btns = ttk.Frame(main)
        btns.pack(fill=tk.X, pady=5)
        ttk.Button(btns, text="添加文件", command=self.add_files).pack(side=tk.LEFT)
        ttk.Button(btns, text="移除选中", command=self.remove_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="清空", command=self.clear_files).pack(side=tk.LEFT)

        # 输出设置
        out = ttk.LabelFrame(main, text="输出设置", padding=5)
        out.pack(fill=tk.X)

        ttk.Label(out, text="目标格式:").grid(row=0, column=0, sticky=tk.W)
        self.fmt_var = tk.StringVar(value="mp3")
        self.fmt_box = ttk.Combobox(
            out, textvariable=self.fmt_var, state="readonly", width=10,
            values=audio_formats() + video_formats(),
        )
        self.fmt_box.grid(row=0, column=1, sticky=tk.W)
        self.fmt_box.bind("<<ComboboxSelected>>", lambda _e: self._sync_enabled())

        ttk.Label(out, text="输出目录:").grid(row=0, column=2, sticky=tk.W, padx=(15, 0))
        self.outdir_var = tk.StringVar()
        ttk.Entry(out, textvariable=self.outdir_var, width=35).grid(row=0, column=3, sticky=tk.W)
        ttk.Button(out, text="浏览", command=self.pick_outdir, width=6).grid(row=0, column=4)

        ttk.Label(out, text="音频码率:").grid(row=1, column=0, sticky=tk.W)
        self.ab_var = tk.StringVar(value="192k")
        ttk.Combobox(out, textvariable=self.ab_var, width=10,
                     values=["", "96k", "128k", "192k", "256k", "320k"]).grid(row=1, column=1, sticky=tk.W)

        ttk.Label(out, text="视频质量 CRF:").grid(row=1, column=2, sticky=tk.W, padx=(15, 0))
        self.crf_var = tk.StringVar(value="23")
        self.crf_spin = ttk.Spinbox(out, from_=0, to=51, textvariable=self.crf_var, width=8)
        self.crf_spin.grid(row=1, column=3, sticky=tk.W)

        ttk.Label(out, text="分辨率(可选):").grid(row=2, column=0, sticky=tk.W)
        self.res_var = tk.StringVar()
        self.res_box = ttk.Combobox(out, textvariable=self.res_var, width=10,
                                    values=["", "3840x2160", "1920x1080", "1280x720", "854x480", "640x360"])
        self.res_box.grid(row=2, column=1, sticky=tk.W)

        ttk.Label(out, text="采样率:").grid(row=2, column=2, sticky=tk.W, padx=(15, 0))
        self.sr_var = tk.StringVar()
        ttk.Combobox(out, textvariable=self.sr_var, width=8,
                     values=["", "48000", "44100", "22050", "16000", "8000"]).grid(row=2, column=3, sticky=tk.W)

        ttk.Label(out, text="背景图(音频转视频):").grid(row=3, column=0, sticky=tk.W)
        self.bg_var = tk.StringVar()
        self.bg_entry = ttk.Entry(out, textvariable=self.bg_var, width=28)
        self.bg_entry.grid(row=3, column=1, columnspan=2, sticky=tk.W)
        ttk.Button(out, text="选择", command=self.pick_bg, width=6).grid(row=3, column=3, sticky=tk.W)

        # 进度与日志
        self.progress = ttk.Progressbar(main, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(10, 2))
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(main, textvariable=self.status_var).pack(anchor=tk.W)

        self.log = tk.Text(main, height=10, state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True)

        actions = ttk.Frame(main)
        actions.pack(fill=tk.X, pady=5)
        self.convert_btn = ttk.Button(actions, text="开始转换", command=self.start_convert)
        self.convert_btn.pack(side=tk.RIGHT)
        ttk.Button(actions, text="退出", command=self.root.destroy).pack(side=tk.RIGHT, padx=5)

        self._sync_enabled()

    def _sync_enabled(self) -> None:
        is_video = FORMATS[self.fmt_var.get()].kind == "video"
        for widget in (self.crf_spin, self.res_box, self.bg_entry):
            widget.configure(state=tk.NORMAL if is_video else tk.DISABLED)

    # ---- 交互 ----
    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(title="选择媒体文件", filetypes=FILE_TYPES)
        for path in paths:
            if path not in self.files:
                self.files.append(path)
                self.file_list.insert(tk.END, Path(path).name)
        if paths and not self.outdir_var.get():
            self.outdir_var.set(str(Path(paths[0]).parent / "converted"))

    def remove_selected(self) -> None:
        for index in reversed(self.file_list.curselection()):
            self.file_list.delete(index)
            self.files.pop(index)

    def clear_files(self) -> None:
        self.file_list.delete(0, tk.END)
        self.files.clear()

    def pick_outdir(self) -> None:
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            self.outdir_var.set(directory)

    def pick_bg(self) -> None:
        path = filedialog.askopenfilename(
            title="选择背景图片", filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp"), ("所有文件", "*.*")]
        )
        if path:
            self.bg_var.set(path)

    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def start_convert(self) -> None:
        if not self.files:
            messagebox.showwarning("提示", "请先添加要转换的文件")
            return
        outdir = self.outdir_var.get().strip()
        if not outdir:
            messagebox.showwarning("提示", "请选择输出目录")
            return
        if self.worker and self.worker.is_alive():
            return

        self.convert_btn.configure(state=tk.DISABLED)
        self.progress["value"] = 0
        self._append_log(f"=== 开始转换 {len(self.files)} 个文件 ===")
        # tkinter 变量只能在主线程读取，这里先把参数取好再交给工作线程
        snapshot = (list(self.files), self.fmt_var.get(), self._options())
        self.worker = threading.Thread(
            target=self._convert_worker, args=(outdir, *snapshot), daemon=True
        )
        self.worker.start()

    def _options(self) -> converter.ConvertOptions:
        return converter.ConvertOptions(
            audio_bitrate=self.ab_var.get().strip() or None,
            crf=int(self.crf_var.get()) if self.crf_var.get().strip() else None,
            resolution=self.res_var.get().strip() or None,
            sample_rate=int(self.sr_var.get()) if self.sr_var.get().strip() else None,
            background=self.bg_var.get().strip() or None,
        )

    def _convert_worker(
        self,
        outdir: str,
        files: list[str],
        fmt: str,
        options: converter.ConvertOptions,
    ) -> None:
        total = len(files)
        for index, src in enumerate(files, 1):
            source = Path(src)
            dst = Path(outdir) / f"{source.stem}.{fmt}"
            self.messages.put(("status", f"[{index}/{total}] {source.name}"))
            try:
                def on_progress(p: float, index=index, total=total) -> None:
                    overall = ((index - 1) + p / 100) / total * 100
                    self.messages.put(("progress", overall))

                result = converter.convert(
                    source, dst, fmt, options,
                    progress=on_progress,
                    log=lambda line: self.messages.put(("log", line)),
                )
                self.messages.put(("log", f"完成: {result}"))
            except Exception as exc:  # 单个文件失败不影响后续
                self.messages.put(("log", f"失败: {source.name}: {exc}"))
        self.messages.put(("done", total))

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "progress":
                    self.progress["value"] = float(payload)
                elif kind == "done":
                    self.status_var.set(f"全部完成（共 {payload} 个文件）")
                    self.progress["value"] = 100
                    self.convert_btn.configure(state=tk.NORMAL)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_queue)


def launch() -> int:
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(launch())
