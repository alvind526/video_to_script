# Video to Script — Offline Desktop App

Windows desktop app that turns speech in a **video or audio file** into a
**text script**. Fully offline after setup. Runs on **CPU only** (no CUDA).

---

## Option A — Packaged app (no Python)

Best for quick QA of the shipping build.

1. Unzip `VideoToScript-Portable.zip` (or use `dist\VideoToScript\`)
2. Keep the **whole folder** together (`VideoToScript.exe` + `_internal\`)
3. Double-click `VideoToScript.exe`

No `pip`, no Python, no internet after the zip is on the machine.

---

## Option B — Run from source with `.venv` (developers / QA)

### 1. Prerequisites

- Windows
- **Python 3.10+** on PATH (`python --version`)
- Internet **once** (packages + speech model)

### 2. One-time setup (creates `.venv`)

```powershell
cd video_to_script
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

This will:

1. Create `.venv\`
2. `pip install -r requirements.txt` **into the venv**
3. Download `models/base/` (~140 MB)

### 3. Run

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Or manually:

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

If PowerShell blocks Activate:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

If you see **“Missing Python packages”**, you used system Python instead of the venv — run `setup.ps1` / `run.ps1`.

---

## How to use the UI

1. **Add Thread** for each video (optional; one job is enough)
2. **Browse…** → video/audio file
3. **Browse…** → output folder (defaults to the video’s folder)
4. **Start** → watch progress; script auto-saves as `{filename}.txt`
5. **Cancel** stops early (saves partial text if any)
6. **Open Output Folder** opens the destination

Only one job runs at a time; others wait and continue automatically.

---

## Build a new portable package (maintainers)

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

`build.ps1` uses `.venv` when present.

| Output | Purpose |
|--------|---------|
| `dist\VideoToScript\VideoToScript.exe` | Local packaged app |
| `dist\VideoToScript-Portable.zip` | Give this to QA / clients |

---

## Notes

- `.venv\` is local — not committed to git
- Offline after setup/build — no network at runtime
- CPU (int8) only — GPU / CUDA not required or used
- First model load in a session can take a few seconds
