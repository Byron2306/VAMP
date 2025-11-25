# Connector reliability and background efficiency

This guide summarizes the recommended approach to keep live-session connectors stable, low-impact on the user’s machine, and compliant. It focuses on reusing valid sessions where possible and only invoking heavyweight tooling when necessary.

## Principle stack
- **Prefer official APIs first.** Use OAuth/OIDC or service accounts when available; keep scopes minimal and tokens short-lived.
- **Playwright with reusable storage state.** Persist per-account storage state files and refresh them just before expiry. Validate state age/validity via a cheap probe before launching a full browser.
- **Policy-driven issuance.** Issue short-lived, scoped tokens (or decrypt stored credentials) per action and wipe them immediately after use. Avoid long-lived "skeleton keys."
- **Guardrails instead of evasive tactics.** Respect ToS and robots.txt; avoid brittle "blockage jumping" tricks that trigger anti-automation.

## Recommended hardening steps
1. **Health probes:** Add a preflight check that loads the storage state into a new context and fetches a lightweight endpoint (e.g., inbox metadata) to confirm the session is still valid.
2. **Context lifecycle:** Use a fresh incognito context per job with the persisted storage state injected. Close contexts promptly to free memory/CPU.
3. **Rate limits and backoff:** Cap concurrent browser jobs; prefer small worker pools and exponential backoff on 429/5xx responses to stay unobtrusive.
4. **Credential vault:** Store refresh tokens or passwords in a vault and fetch only when needed; never persist in plaintext on disk.
5. **Observability:** Emit structured logs for session refresh attempts, token issuance, revocations, and Playwright crashes. Add alerts for repeated login prompts.
6. **Graceful fallback:** If storage state is invalid, trigger a guided/manual login capture flow rather than looping retries.

## Optional extraction helpers (install as needed)
These packages extend file-type coverage without bloating the default footprint. Install selectively based on connectors you enable:

```bash
pip install "pytesseract>=0.3" "pillow>=10" "opencv-python-headless>=4.10" \ 
            "python-magic>=0.4" "pdfplumber>=0.11" "python-docx>=1.1" \ 
            "openpyxl>=3.1" "py7zr>=0.21" "rarfile>=4.2"
```

- **OCR:** `pytesseract`, `pillow`, `opencv-python-headless` (requires system `tesseract` binary; keep disabled unless needed).
- **File-type detection:** `python-magic` for MIME sniffing.
- **Documents:** `pdfplumber`, `python-docx`, `openpyxl` for PDFs/Word/Excel.
- **Archives:** `py7zr`, `rarfile` to peek into compressed attachments.

Install only the pieces relevant to your target platforms to avoid heavy dependencies. Keep OCR optional to preserve background performance.

## Background efficiency
- **Lightweight scheduling:** Use small async/worker pools and batch low-priority tasks during idle periods.
- **Resource caps:** Limit Playwright concurrency and enforce per-job CPU/memory budgets. Prefer `chromium --headless=new` with reduced viewport.
- **Cache smartly:** Cache connector metadata and capability discovery responses; avoid re-fetching unchanged schemas.

## Model/AI routing
- Use a fixed, vetted roster of models and route by policy (data sensitivity, task type). Avoid probing multiple providers with the same payload.
- Apply server-side PII stripping and guard prompts, but rely on token-based access control for real enforcement.

## Maintenance checklist
- Rotate storage states on a schedule before expiry.
- Periodically validate Playwright browser versions (`playwright install --with-deps` on updates).
- Keep a small suite of smoke tests that launch a context with stored state and hit a harmless endpoint to catch breakage early.
