"""
Video to Script - offline desktop app.

Pick a video (or audio) file, click Transcribe, and get a text script.
Runs entirely offline. The speech model is embedded in the packaged app.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Block any accidental Hugging Face / hub network use.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

MODEL_SIZE = "base"
REQUIRED_FILES = ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")
IS_FROZEN = getattr(sys, "frozen", False)

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


def app_dir() -> str:
    if IS_FROZEN:
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(*parts: str) -> str | None:
    """Find a bundled asset (embedded) or one next to the app."""
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
    """Prefer the embedded model; allow an override folder next to the .exe."""
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


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.path = tk.StringVar()
        self.status = tk.StringVar(
            value="Choose a video or audio file to begin."
            if model_ready(MODEL_DIR)
            else "Speech model missing from this build."
        )
        self.file_label = tk.StringVar(value="No file selected")
        self.busy = False
        self.msgs: queue.Queue = queue.Queue()
        self.model = None
        self._icon_img = None

        root.title("Video to Script")
        root.geometry("860x640")
        root.minsize(640, 480)
        root.configure(bg=C["bg"])
        self._apply_icon()
        self._style()
        self._build()
        root.after(100, self.poll)

    # ── chrome ──────────────────────────────────────────────────────────

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
        style.configure("Card.TFrame", background=C["surface"])
        style.configure("Surface.TFrame", background=C["surface2"])

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
            "Section.TLabel",
            background=C["bg"],
            foreground=C["muted"],
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "Body.TLabel",
            background=C["surface"],
            foreground=C["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Muted.TLabel",
            background=C["surface"],
            foreground=C["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Status.TLabel",
            background=C["bg"],
            foreground=C["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Badge.TLabel",
            background=C["surface2"],
            foreground=C["accent"],
            font=("Segoe UI Semibold", 8),
            padding=(8, 3),
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
            font=("Segoe UI Semibold", 10),
            padding=(14, 8),
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
            thickness=4,
        )

    def _build(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame", padding=(28, 22, 28, 18))
        shell.pack(fill="both", expand=True)

        # Header
        header = ttk.Frame(shell, style="App.TFrame")
        header.pack(fill="x", pady=(0, 18))

        left = ttk.Frame(header, style="App.TFrame")
        left.pack(side="left", fill="x", expand=True)

        title_row = ttk.Frame(left, style="App.TFrame")
        title_row.pack(anchor="w")
        ttk.Label(title_row, text="Video to Script", style="Title.TLabel").pack(
            side="left"
        )
        badge = tk.Label(
            title_row,
            text="OFFLINE",
            bg=C["surface2"],
            fg=C["accent"],
            font=("Segoe UI Semibold", 8),
            padx=8,
            pady=3,
        )
        badge.pack(side="left", padx=(12, 0), pady=(4, 0))

        ttk.Label(
            left,
            text="Convert speech from any video or audio file into a clean script.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        # Source card
        ttk.Label(shell, text="SOURCE", style="Section.TLabel").pack(anchor="w")
        source = tk.Frame(shell, bg=C["surface"], highlightthickness=1, highlightbackground=C["border"])
        source.pack(fill="x", pady=(6, 14))

        inner = tk.Frame(source, bg=C["surface"], padx=16, pady=14)
        inner.pack(fill="x")

        top_row = tk.Frame(inner, bg=C["surface"])
        top_row.pack(fill="x")
        tk.Label(
            top_row,
            textvariable=self.file_label,
            bg=C["surface"],
            fg=C["text"],
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(top_row, text="Browse…", style="Browse.TButton", command=self.browse).pack(
            side="right"
        )

        tk.Label(
            inner,
            text="mp4 · mkv · mov · webm · mp3 · wav · m4a · and more",
            bg=C["surface"],
            fg=C["faint"],
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(fill="x", pady=(8, 0))

        # Actions
        actions = ttk.Frame(shell, style="App.TFrame")
        actions.pack(fill="x", pady=(0, 10))
        self.go = ttk.Button(
            actions, text="Transcribe", style="Accent.TButton", command=self.start
        )
        self.go.pack(side="left")
        self.save_btn = ttk.Button(
            actions,
            text="Save script…",
            style="Ghost.TButton",
            command=self.save,
            state="disabled",
        )
        self.save_btn.pack(side="left", padx=(10, 0))

        self.progress = ttk.Progressbar(
            shell, style="App.Horizontal.TProgressbar", mode="indeterminate"
        )
        self.progress.pack(fill="x", pady=(2, 8))

        ttk.Label(shell, textvariable=self.status, style="Status.TLabel").pack(
            anchor="w", pady=(0, 12)
        )

        # Script output
        ttk.Label(shell, text="SCRIPT", style="Section.TLabel").pack(anchor="w")
        out = tk.Frame(shell, bg=C["surface"], highlightthickness=1, highlightbackground=C["border"])
        out.pack(fill="both", expand=True, pady=(6, 0))

        text_wrap = tk.Frame(out, bg=C["surface"])
        text_wrap.pack(fill="both", expand=True, padx=2, pady=2)

        self.text = tk.Text(
            text_wrap,
            wrap="word",
            font=("Segoe UI", 11),
            bg=C["surface"],
            fg=C["text"],
            insertbackground=C["accent"],
            selectbackground=C["accent_dim"],
            selectforeground=C["text"],
            relief="flat",
            borderwidth=0,
            padx=14,
            pady=12,
            highlightthickness=0,
            spacing1=2,
            spacing3=4,
        )
        sb = ttk.Scrollbar(text_wrap, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.insert("1.0", "Your transcript will appear here.")
        self.text.configure(fg=C["faint"])
        self._placeholder = True

    # ── actions ─────────────────────────────────────────────────────────

    def browse(self) -> None:
        p = filedialog.askopenfilename(
            title="Select a video or audio file",
            filetypes=[
                (
                    "Media files",
                    "*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.wav *.m4a *.aac *.flac",
                ),
                ("All files", "*.*"),
            ],
        )
        if p:
            self.path.set(p)
            name = os.path.basename(p)
            self.file_label.set(name)
            self.status.set(p)

    def _clear_placeholder(self) -> None:
        if self._placeholder:
            self.text.delete("1.0", "end")
            self.text.configure(fg=C["text"])
            self._placeholder = False

    def start(self) -> None:
        if self.busy:
            return
        if not model_ready(MODEL_DIR):
            messagebox.showerror("Model missing", missing_model_message())
            return
        p = self.path.get().strip()
        if not os.path.isfile(p):
            messagebox.showwarning("No file", "Please choose a valid video or audio file.")
            return

        self._clear_placeholder()
        self.text.delete("1.0", "end")
        self.save_btn.config(state="disabled")
        self.go.config(state="disabled")
        self.busy = True
        self.progress.start(12)
        self.status.set("Working…")
        threading.Thread(target=self.work, args=(p,), daemon=True).start()

    def work(self, path: str) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            self.msgs.put(
                (
                    "error",
                    "Speech engine failed to load."
                    if IS_FROZEN
                    else "Please run:  pip install -r requirements.txt",
                )
            )
            return
        try:
            if self.model is None:
                self.msgs.put(("status", "Loading speech model…"))
                self.model = WhisperModel(
                    MODEL_DIR,
                    device="cpu",
                    compute_type="int8",
                    local_files_only=True,
                )
            self.msgs.put(("status", "Transcribing…"))
            segments, _ = self.model.transcribe(path, vad_filter=True)
            for seg in segments:
                self.msgs.put(("text", seg.text.strip() + " "))
            self.msgs.put(("done", None))
        except Exception as exc:  # noqa: BLE001
            self.msgs.put(("error", str(exc)))

    def save(self) -> None:
        content = self.text.get("1.0", "end").strip()
        if not content or self._placeholder:
            return
        name = os.path.splitext(os.path.basename(self.path.get()))[0] or "script"
        p = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=name,
            filetypes=[("Text file", "*.txt")],
        )
        if p:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(content)
            self.status.set(f"Saved · {p}")

    def poll(self) -> None:
        try:
            while True:
                kind, data = self.msgs.get_nowait()
                if kind == "text":
                    self._clear_placeholder()
                    self.text.insert("end", data)
                    self.text.see("end")
                elif kind == "status":
                    self.status.set(data)
                elif kind == "done":
                    self.finish("Transcription complete.")
                elif kind == "error":
                    self.finish("Something went wrong.")
                    messagebox.showerror("Error", data)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def finish(self, msg: str) -> None:
        self.progress.stop()
        self.busy = False
        self.go.config(state="normal")
        self.status.set(msg)
        if self.text.get("1.0", "end").strip() and not self._placeholder:
            self.save_btn.config(state="normal")


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
