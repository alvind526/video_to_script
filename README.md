# Video to Script — Offline Desktop App

Windows desktop app that turns speech in a **video or audio file** into a
**text script**. Fully offline after build. No Python needed on the target PC.

## Use it

### Build (once)

```powershell
cd video_to_script
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Outputs:

| Path | What it is |
|------|------------|
| `dist\VideoToScript\VideoToScript.exe` | Double-click to launch |
| `dist\VideoToScript-Portable.zip` | Same app, zipped for easy transfer |

Everything is **embedded** (speech model, runtime, icon). Copy the folder or
the zip — nothing else to install.

### Run

1. Open `VideoToScript.exe`
2. **Browse…** → pick a media file
3. **Transcribe**
4. **Save script…**

## Develop from source

```powershell
pip install -r requirements.txt
python download_model.py
python app.py
```

## Notes

- Default model: `base` (~140 MB), embedded at build time
- First launch may take a few seconds while the engine loads
- Longer files take longer; progress runs while it works
