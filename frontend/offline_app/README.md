# VAMP Offline Desktop Wrapper

This lightweight Tkinter UI mirrors the Chrome extension's local scan workflow without any WebSocket bridge. It calls the backend scanning pipeline (`backend.vamp_master.scan_and_score`) directly and uses the year-end aggregator (`backend.vamp_runner.run`) to keep CSV/Markdown outputs identical to the server-driven flow.

## Features
- Pick any evidence root on disk and run the monthly scan pipeline (text extraction, scoring, CSV v2 export, Markdown report).
- Build a year-end summary from the accumulated `_out/audit.csv` files without hitting the WebSocket bridge or REST API.
- Log pane for progress/errors so the executable can run fully offline.

## Running from source
```bash
python frontend/offline_app/offline_app.py
```

Provide the evidence root folder, year/month, and (optionally) a custom output directory name. The scan writes the audit CSV and Markdown report; the summary button generates `_final/year_summary.csv`, `_final/evidence_flat.csv`, and `_final/year_report.md` for the selected rank.

## Building a standalone EXE
PyInstaller works without extra hooks because the UI imports the backend modules directly:

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole frontend/offline_app/offline_app.py
```

The resulting executable lives under `dist/offline_app`. Distribute it together with the repository data files (e.g., `backend/data/*`) so scoring and manifests remain available.
