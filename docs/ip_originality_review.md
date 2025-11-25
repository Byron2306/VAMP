# IP and Originality Review

This document highlights potential intellectual property (IP) and originality considerations based on the current VAMP codebase. It is not legal advice but a checklist for further review.

## Scope
- Backend automation, scoring logic, and stored knowledge bases.
- Platform-specific connectors for Outlook, OneDrive, Google Drive, NextCloud, and eFundi.
- Data assets in `backend/data/nwu_brain/`.

## Potential IP and Originality Flags

### 1) Third-party platform targeting and automated access
- The README explicitly positions VAMP to scrape Outlook/Office365, OneDrive, Google Drive, NextCloud, and eFundi via Playwright automation and a WebSocket bridge. This may implicate each platform's terms of service, trademark use, and anti-scraping rules. 【F:README.md†L5-L28】
- Connector constants and login selectors hard-code service URLs and automation cues for those platforms, reinforcing the direct targeting. Confirm usage complies with the platforms’ automation and brand policies. 【F:backend/vamp_agent.py†L142-L162】

### 2) Embedded NWU policy corpus (proprietary content)
- The NWU Brain scorer loads a manifest-driven corpus (`policy_registry.json`, `clause_packs.json`, `kpa_router.json`, etc.) to deterministically score evidence. These knowledge files are bundled in the repo, implying redistribution of NWU policy-derived data. Validate ownership and redistribution rights for this corpus. 【F:backend/nwu_brain/scoring.py†L101-L119】
- `policy_playbook.md` contains detailed NWU policy titles, trigger phrases, and guidance; the text appears institution-specific and may be protected or confidential. Ensure permission to store and ship this content. 【F:backend/data/nwu_brain/policy_playbook.md†L3-L104】

### 3) Model prompts include full institutional corpus
- The README notes that the “full NWU brain corpus” is injected into every Ollama prompt, which may leak proprietary policy text to downstream model providers or logs. Confirm data-sharing boundaries and any contractual limits with Ollama/gemma3. 【F:README.md†L70-L75】

### 4) License and distribution clarity
- The project states “Internal use only – NWU Research and Policy Development” but does not include a formal license file. Clarify licensing terms before external distribution or collaboration to avoid implied restrictions or ambiguity. 【F:README.md†L266-L269】

### 5) Third-party dependency licensing
- Backend requirements include Playwright, pandas, pillow/pytesseract (with OCR models), Flask, and WebSocket libraries. Conduct a license audit (MIT/BSD/Apache/Proprietary) and ensure attribution and notice obligations are met before release. 【F:requirements.txt†L1-L13】

## Recommendations
- Confirm that automation against each third-party platform is allowed (terms of service, trademark usage, automated scraping restrictions) and add usage notices if necessary.
- Review the NWU Brain data set for copyrighted or confidential material; document provenance and obtain explicit permission (or replace with synthesized data) for any non-public text.
- Define a project license (or reinforce the internal-only notice) in a dedicated `LICENSE` or `NOTICE` file to prevent ambiguity.
- Perform a dependency license scan and record results; include third-party acknowledgments if redistribution is planned.
- Revisit prompt construction and logging to ensure no proprietary policy text is transmitted to external services without approvals.

## Actions applied
- Added a platform automation notice to the README reminding users to confirm terms of service and trademark usage before running connectors.
- Documented NWU Brain corpus provenance/approvals in `backend/data/nwu_brain/PROVENANCE.md` and instructed replacement/redaction if permissions cannot be obtained.
- Added an internal-use-only `NOTICE` file to clarify licensing and trademark boundaries.
- Captured a dependency license snapshot and command guidance in `docs/dependency_license_scan.md`.
- Added README guidance to keep NWU corpus text out of external prompts/logs and to redact policy text when debugging.
