"""
Video to Script - offline desktop app.

Multi-job UI: add threads, pick video + output folder, transcribe with
cancelable progress. Runs entirely offline. Model is embedded when packaged.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

# Block any accidental Hugging Face / hub network use.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

MODEL_SIZE = "base"
REQUIRED_FILES = ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")
IS_FROZEN = getattr(sys, "frozen", False)
MEDIA_TYPES = (
    ("Media files", "*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.wav *.m4a *.aac *.flac"),
    ("All files", "*.*"),
)

# Visual system — charcoal + mint, matching the app icon.
C = {
    "bg": "#14171C",
    "surface": "#1C2129",
    "surface2": "#242B35",
    "border": "#323A46",
    "text": "#E8ECF1",
    "muted": "#8B95A5",
    "faint": "#5C6778",
    "accent": "#3DDC97",
    "accent_dim": "#2A9F6E",
    "accent_text": "#0B1220",
    "danger": "#F07178",
    "ok": "#3DDC97",
}


# ── paths / model ───────────────────────────────────────────────────────────


def app_dir() -> str:
    if IS_FROZEN:
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(*parts: str) -> str | None:
    bases: list[str] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bases.append(meipass)
    bases.append(app_dir())
    for base in bases:
        path = os.path.join(base, *parts)
        if os.path.isfile(path) or os.path.isdir(path):
            return path
    return None


def model_ready(path: str) -> bool:
    return all(os.path.isfile(os.path.join(path, name)) for name in REQUIRED_FILES)


def resolve_model_dir() -> str:
    candidates: list[str] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "models", MODEL_SIZE))
    candidates.append(os.path.join(app_dir(), "models", MODEL_SIZE))
    for path in candidates:
        if model_ready(path):
            return path
    return candidates[0]


MODEL_DIR = resolve_model_dir()


def missing_model_message() -> str:
    return (
        f"Offline speech model not found in:\n{MODEL_DIR}\n\n"
        "Rebuild the app with build.ps1 after running download_model.py."
    )


def format_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def open_folder(path: str) -> None:
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    if not folder or not os.path.isdir(folder):
        return
    if sys.platform == "win32":
        os.startfile(folder)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", folder])
    else:
        subprocess.Popen(["xdg-open", folder])


# ── device + shared engine ──────────────────────────────────────────────────


def detect_device() -> tuple[str, str, str]:
    """Always CPU — matches the original offline app (no CUDA toolkit required)."""
    return "cpu", "int8", "Processing device: CPU (int8)"


class SharedEngine:
    """One Whisper model for the whole app; only one job may run at a time."""

    def __init__(self) -> None:
        self.device, self.compute_type, self.label = detect_device()
        self._model = None
        self._lock = threading.Lock()
        self._model_lock = threading.Lock()
        self._holder: JobCard | None = None
        self._waiters: list[JobCard] = []

    def try_acquire(self, job: JobCard) -> bool:
        with self._lock:
            if self._holder is None:
                self._holder = job
                return True
            if job not in self._waiters:
                self._waiters.append(job)
            return False

    def release(self, job: JobCard) -> None:
        next_job: JobCard | None = None
        with self._lock:
            if job in self._waiters:
                self._waiters.remove(job)
            if self._holder is job:
                self._holder = None
                while self._waiters:
                    candidate = self._waiters.pop(0)
                    if candidate.wants_run:
                        self._holder = candidate
                        next_job = candidate
                        break
        if next_job is not None:
            # Never call Tk from a worker thread — wake the waiter via its queue.
            next_job.msgs.put(("begin_after_wait", None))
            next_job._ensure_poll()

    def cancel_wait(self, job: JobCard) -> None:
        with self._lock:
            if job in self._waiters:
                self._waiters.remove(job)

    def get_model(self, status: Callable[[str], None]):
        with self._model_lock:
            if self._model is not None:
                return self._model
            if not model_ready(MODEL_DIR):
                raise FileNotFoundError(missing_model_message())
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                if IS_FROZEN:
                    msg = (
                        "Speech engine failed to load from this package.\n"
                        "Re-copy the full VideoToScript folder (including _internal)."
                    )
                else:
                    msg = (
                        "Missing Python packages.\n\n"
                        "From this project folder run:\n"
                        "  powershell -ExecutionPolicy Bypass -File .\\setup.ps1\n"
                        "  powershell -ExecutionPolicy Bypass -File .\\run.ps1"
                    )
                raise RuntimeError(msg) from exc

            status("Loading speech model…")
            self._model = WhisperModel(
                MODEL_DIR,
                device=self.device,
                compute_type=self.compute_type,
                local_files_only=True,
            )
            return self._model


# ── job card ────────────────────────────────────────────────────────────────


class JobCard:
    _next_id = 1

    def __init__(self, app: App, parent: tk.Widget, engine: SharedEngine) -> None:
        self.app = app
        self.root = app.root
        self.engine = engine
        self.job_id = JobCard._next_id
        JobCard._next_id += 1

        self.video_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.progress_text = tk.StringVar(value="Ready")
        self.preview_text = tk.StringVar(value="")
        self.device_text = tk.StringVar(value=engine.label)

        self.msgs: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.wants_run = False
        self.running = False
        self.waiting = False
        self._poll_scheduled = False
        self._parts: list[str] = []

        self.frame = tk.Frame(
            parent,
            bg=C["surface"],
            highlightthickness=1,
            highlightbackground=C["border"],
        )
        self.frame.pack(fill="x", pady=(0, 12), padx=2)

        inner = tk.Frame(self.frame, bg=C["surface"], padx=16, pady=14)
        inner.pack(fill="x")

        head = tk.Frame(inner, bg=C["surface"])
        head.pack(fill="x")
        tk.Label(
            head,
            text=f"Job {self.job_id}",
            bg=C["surface"],
            fg=C["text"],
            font=("Segoe UI Semibold", 11),
        ).pack(side="left")
        self.remove_btn = ttk.Button(
            head, text="Remove", style="Ghost.TButton", command=self.remove
        )
        self.remove_btn.pack(side="right")

        self._row(inner, "Video file", self.video_path, self.browse_video)
        self._row(inner, "Output", self.output_dir, self.browse_output)

        tk.Label(
            inner,
            textvariable=self.device_text,
            bg=C["surface"],
            fg=C["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", pady=(10, 0))

        actions = tk.Frame(inner, bg=C["surface"])
        actions.pack(fill="x", pady=(12, 0))
        self.start_btn = ttk.Button(
            actions, text="Start", style="Accent.TButton", command=self.start
        )
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(
            actions, text="Cancel", style="Ghost.TButton", command=self.cancel
        )
        self.open_btn = ttk.Button(
            actions,
            text="Open Output Folder",
            style="Ghost.TButton",
            command=self.open_output,
        )

        prog_wrap = tk.Frame(inner, bg=C["surface"])
        prog_wrap.pack(fill="x", pady=(12, 0))
        self.progress = ttk.Progressbar(
            prog_wrap,
            style="App.Horizontal.TProgressbar",
            mode="determinate",
            maximum=1000,
            value=0,
        )
        self.progress.pack(fill="x")
        tk.Label(
            prog_wrap,
            textvariable=self.progress_text,
            bg=C["surface"],
            fg=C["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", pady=(6, 0))

        tk.Label(
            inner,
            textvariable=self.preview_text,
            bg=C["surface"],
            fg=C["faint"],
            font=("Segoe UI", 9),
            anchor="w",
            wraplength=720,
            justify="left",
        ).pack(fill="x", pady=(8, 0))

        self._set_idle_actions()

    def _row(
        self,
        parent: tk.Widget,
        label: str,
        var: tk.StringVar,
        browse: Callable[[], None],
    ) -> None:
        block = tk.Frame(parent, bg=C["surface"])
        block.pack(fill="x", pady=(10, 0))
        tk.Label(
            block,
            text=label,
            bg=C["surface"],
            fg=C["muted"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).pack(fill="x")
        row = tk.Frame(block, bg=C["surface"])
        row.pack(fill="x", pady=(4, 0))
        entry = tk.Entry(
            row,
            textvariable=var,
            bg=C["surface2"],
            fg=C["text"],
            insertbackground=C["accent"],
            relief="flat",
            font=("Segoe UI", 10),
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["accent"],
        )
        entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        ttk.Button(row, text="Browse…", style="Browse.TButton", command=browse).pack(
            side="right"
        )

    def _set_idle_actions(self) -> None:
        self.cancel_btn.pack_forget()
        self.open_btn.pack_forget()
        self.start_btn.pack(side="left")
        self.start_btn.config(state="normal")
        self.remove_btn.config(state="normal")

    def _set_running_actions(self) -> None:
        self.start_btn.pack_forget()
        self.cancel_btn.pack(side="left")
        self.open_btn.pack(side="left", padx=(10, 0))
        self.remove_btn.config(state="disabled")

    def browse_video(self) -> None:
        p = filedialog.askopenfilename(
            title="Select a video or audio file",
            filetypes=list(MEDIA_TYPES),
        )
        if not p:
            return
        self.video_path.set(p)
        if not self.output_dir.get().strip():
            self.output_dir.set(os.path.dirname(p))

    def browse_output(self) -> None:
        initial = self.output_dir.get().strip() or None
        p = filedialog.askdirectory(title="Select output folder", initialdir=initial)
        if p:
            self.output_dir.set(p)

    def open_output(self) -> None:
        out = self.output_dir.get().strip()
        if out:
            open_folder(out)

    def remove(self) -> None:
        if self.running or self.waiting:
            return
        self.engine.cancel_wait(self)
        self.frame.destroy()
        self.app.on_card_removed(self)

    def start(self) -> None:
        if self.running or self.waiting:
            return
        if not model_ready(MODEL_DIR):
            messagebox.showerror("Model missing", missing_model_message())
            return
        video = self.video_path.get().strip()
        if not os.path.isfile(video):
            messagebox.showwarning("No file", "Please choose a valid video or audio file.")
            return
        out = self.output_dir.get().strip()
        if not out:
            out = os.path.dirname(video)
            self.output_dir.set(out)
        if not os.path.isdir(out):
            messagebox.showwarning("Output", "Please choose a valid output folder.")
            return

        self.wants_run = True
        self.cancel_event.clear()
        self._parts = []
        self.preview_text.set("")
        self.progress.configure(value=0)
        self.progress_text.set("Starting…")
        self._ensure_poll()

        if self.engine.try_acquire(self):
            self._begin_work()
        else:
            self.waiting = True
            self._set_running_actions()
            self.progress_text.set("Waiting for another job…")

    def _begin_after_wait(self) -> None:
        if not self.wants_run or self.cancel_event.is_set():
            self.waiting = False
            self.wants_run = False
            self.engine.release(self)
            self._set_idle_actions()
            self.progress_text.set("Cancelled.")
            return
        self._begin_work()

    def _begin_work(self) -> None:
        self.waiting = False
        self.running = True
        self._set_running_actions()
        self.progress_text.set("Loading…")
        video = self.video_path.get().strip()
        out = self.output_dir.get().strip()
        threading.Thread(
            target=self._work, args=(video, out), daemon=True
        ).start()

    def cancel(self) -> None:
        self.wants_run = False
        self.cancel_event.set()
        # Waiting (or promoted-but-not-started): drop queue / release holder.
        if not self.running:
            self.waiting = False
            self.engine.cancel_wait(self)
            self.engine.release(self)
            self._set_idle_actions()
            self.progress_text.set("Cancelled.")
            self.progress.configure(value=0)

    def _ensure_poll(self) -> None:
        if not self._poll_scheduled:
            self._poll_scheduled = True
            self.root.after(100, self._poll)

    def _emit(self, kind: str, data=None) -> None:
        self.msgs.put((kind, data))

    def _work(self, video: str, out_dir: str) -> None:
        started = time.monotonic()
        try:
            model = self.engine.get_model(lambda s: self._emit("status", s))
            if self.cancel_event.is_set():
                self._emit("cancelled", None)
                return

            self._emit("status", "Transcribing…")
            segments, info = model.transcribe(video, vad_filter=True)
            duration = float(getattr(info, "duration", 0) or 0)

            for seg in segments:
                if self.cancel_event.is_set():
                    break
                text = (seg.text or "").strip()
                if text:
                    self._parts.append(text)
                    self._emit("preview", text)
                end = float(getattr(seg, "end", 0) or 0)
                if duration > 0:
                    pct = min(100.0, (end / duration) * 100.0)
                    self._emit(
                        "progress",
                        {
                            "pct": pct,
                            # Media position / media duration (not wall clock).
                            "position": end,
                            "total": duration,
                            "wall": time.monotonic() - started,
                        },
                    )
                else:
                    self._emit(
                        "progress",
                        {
                            "pct": 0.0,
                            "position": end,
                            "total": 0.0,
                            "wall": time.monotonic() - started,
                        },
                    )

            body = " ".join(self._parts).strip()
            stem = os.path.splitext(os.path.basename(video))[0] or "script"
            out_path = os.path.join(out_dir, f"{stem}.txt")

            if self.cancel_event.is_set():
                if body:
                    with open(out_path, "w", encoding="utf-8") as fh:
                        fh.write(body)
                    self._emit("cancelled_saved", out_path)
                else:
                    self._emit("cancelled", None)
                return

            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(body)
            self._emit(
                "done",
                {
                    "path": out_path,
                    "wall": time.monotonic() - started,
                    "total": duration,
                    "empty": not bool(body),
                },
            )
        except Exception as exc:  # noqa: BLE001
            self._emit("error", str(exc))
        finally:
            self.engine.release(self)

    def _poll(self) -> None:
        try:
            while True:
                kind, data = self.msgs.get_nowait()
                if kind == "status":
                    self.progress_text.set(str(data))
                elif kind == "begin_after_wait":
                    self._begin_after_wait()
                elif kind == "preview":
                    self.preview_text.set(str(data))
                elif kind == "progress":
                    pct = float(data["pct"])
                    position = float(data.get("position", data.get("elapsed", 0)))
                    total = float(data["total"])
                    self.progress.configure(value=int(pct * 10))
                    if total > 0:
                        self.progress_text.set(
                            f"Transcribing  {pct:.1f}%  "
                            f"{format_hms(position)} / {format_hms(total)}"
                        )
                    else:
                        wall = float(data.get("wall", position))
                        self.progress_text.set(f"Transcribing  {format_hms(wall)}")
                elif kind == "done":
                    self.running = False
                    self.wants_run = False
                    self.progress.configure(value=1000)
                    wall = float(data["wall"])
                    total = float(data["total"]) or wall
                    self.progress_text.set(
                        f"Done  100%  {format_hms(total)} / {format_hms(total)}"
                        f"  ({format_hms(wall)} wall)"
                    )
                    if data.get("empty"):
                        self.preview_text.set(
                            f"Saved empty script · {data['path']}"
                        )
                    else:
                        self.preview_text.set(f"Saved · {data['path']}")
                    self._set_idle_actions()
                    self.open_btn.pack(side="left", padx=(10, 0))
                elif kind == "cancelled_saved":
                    self.running = False
                    self.wants_run = False
                    self.progress_text.set("Cancelled - partial script saved.")
                    self.preview_text.set(f"Saved · {data}")
                    self._set_idle_actions()
                    self.open_btn.pack(side="left", padx=(10, 0))
                elif kind == "cancelled":
                    self.running = False
                    self.wants_run = False
                    self.progress.configure(value=0)
                    self.progress_text.set("Cancelled.")
                    self._set_idle_actions()
                elif kind == "error":
                    self.running = False
                    self.wants_run = False
                    self.progress_text.set("Error.")
                    self._set_idle_actions()
                    messagebox.showerror("Error", str(data))
        except queue.Empty:
            pass

        if self.running or self.waiting or not self.msgs.empty():
            self.root.after(100, self._poll)
        else:
            self._poll_scheduled = False


# ── main app ────────────────────────────────────────────────────────────────


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.engine = SharedEngine()
        self.cards: list[JobCard] = []
        self._icon_img = None

        root.title("Video to Script")
        root.geometry("900x720")
        root.minsize(700, 520)
        root.configure(bg=C["bg"])
        self._apply_icon()
        self._style()
        self._build()
        self.add_card()

    def _apply_icon(self) -> None:
        ico = resource_path("assets", "app.ico")
        png = resource_path("assets", "app.png")
        try:
            if ico and sys.platform == "win32":
                self.root.iconbitmap(ico)
            if png:
                self._icon_img = tk.PhotoImage(file=png)
                self.root.iconphoto(True, self._icon_img)
        except tk.TclError:
            pass

    def _style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background=C["bg"])
        style.configure(
            "Title.TLabel",
            background=C["bg"],
            foreground=C["text"],
            font=("Segoe UI Semibold", 18),
        )
        style.configure(
            "Subtitle.TLabel",
            background=C["bg"],
            foreground=C["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Accent.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(16, 8),
            background=C["accent"],
            foreground=C["accent_text"],
            borderwidth=0,
            focuscolor=C["accent"],
        )
        style.map(
            "Accent.TButton",
            background=[("active", C["accent_dim"]), ("disabled", C["border"])],
            foreground=[("disabled", C["faint"])],
        )
        style.configure(
            "Ghost.TButton",
            font=("Segoe UI Semibold", 9),
            padding=(12, 6),
            background=C["surface2"],
            foreground=C["text"],
            borderwidth=0,
            focuscolor=C["surface2"],
        )
        style.map(
            "Ghost.TButton",
            background=[("active", C["border"]), ("disabled", C["surface"])],
            foreground=[("disabled", C["faint"])],
        )
        style.configure(
            "Browse.TButton",
            font=("Segoe UI Semibold", 9),
            padding=(12, 6),
            background=C["surface2"],
            foreground=C["text"],
            borderwidth=0,
        )
        style.map("Browse.TButton", background=[("active", C["border"])])
        style.configure(
            "App.Horizontal.TProgressbar",
            troughcolor=C["surface2"],
            background=C["accent"],
            bordercolor=C["surface2"],
            lightcolor=C["accent"],
            darkcolor=C["accent"],
            thickness=6,
        )

    def _build(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame", padding=(24, 20, 24, 16))
        shell.pack(fill="both", expand=True)

        header = ttk.Frame(shell, style="App.TFrame")
        header.pack(fill="x", pady=(0, 14))

        left = ttk.Frame(header, style="App.TFrame")
        left.pack(side="left", fill="x", expand=True)

        title_row = ttk.Frame(left, style="App.TFrame")
        title_row.pack(anchor="w")
        ttk.Label(title_row, text="Video to Script", style="Title.TLabel").pack(
            side="left"
        )
        tk.Label(
            title_row,
            text="OFFLINE",
            bg=C["surface2"],
            fg=C["accent"],
            font=("Segoe UI Semibold", 8),
            padx=8,
            pady=3,
        ).pack(side="left", padx=(12, 0), pady=(4, 0))

        ttk.Label(
            left,
            text="Add jobs, choose output folders, and transcribe offline.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        right = ttk.Frame(header, style="App.TFrame")
        right.pack(side="right")
        ttk.Button(
            right, text="Add Thread", style="Accent.TButton", command=self.add_card
        ).pack(anchor="e")
        tk.Label(
            right,
            text=self.engine.label,
            bg=C["bg"],
            fg=C["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="e", pady=(8, 0))

        # Scrollable job list
        list_wrap = tk.Frame(shell, bg=C["bg"])
        list_wrap.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(list_wrap, bg=C["bg"], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(list_wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.cards_host = tk.Frame(self.canvas, bg=C["bg"])
        self._cards_window = self.canvas.create_window(
            (0, 0), window=self.cards_host, anchor="nw"
        )

        self.cards_host.bind("<Configure>", self._on_host_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_host_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._cards_window, width=event.width)

    def _on_mousewheel(self, event) -> None:
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def add_card(self) -> None:
        card = JobCard(self, self.cards_host, self.engine)
        self.cards.append(card)
        self.root.after(10, self._on_host_configure)

    def on_card_removed(self, card: JobCard) -> None:
        if card in self.cards:
            self.cards.remove(card)
        if not self.cards:
            self.add_card()
        self.root.after(10, self._on_host_configure)


def main() -> None:
    root = tk.Tk()
    try:
        root.lift()
        root.attributes("-topmost", True)
        root.after(200, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
