# Dependency License Scan (snapshot)

The following table summarizes the licenses of primary Python dependencies declared in
`requirements.txt`. This snapshot is informational only; rerun a license scan whenever
dependencies change.

Recommended commands:

```bash
pip install -r requirements.txt
pip install pip-licenses
pip-licenses --from=mixed --format=markdown > docs/dependency_license_scan.md
```

## Current manual review (2024-08-21)
| Package | Version (pinned) | Reported license* | Notes |
|---------|------------------|-------------------|-------|
| Flask | 3.0.3 | BSD-3-Clause | Web API framework. |
| pandas | 2.2.2 | BSD-3-Clause | Data processing. |
| pillow | 10.4.0 | HPND | Imaging utilities. |
| pytesseract | 0.3.10 | Apache-2.0 | OCR wrapper; requires Tesseract binary. |
| playwright | 1.45.0 | Apache-2.0 | Browser automation. |
| websockets | 12.0 | BSD | Async WebSocket support. |
| websocket-client | 1.8.0 | BSD | WebSocket client. |
| python-dotenv | 1.0.1 | BSD-3-Clause | Environment variable loader. |

\*License values are based on upstream PyPI metadata; verify with `pip-licenses` for the
most accurate, transitive record. Include third-party acknowledgments if redistribution is
planned.
