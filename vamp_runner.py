#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vamp_runner.py — Year-end aggregation & report (NWU Brain–aligned)

Reads all monthly `_out/audit.csv` files produced by `vamp_master.py`,
aggregates per-KPA results using the **deterministic CSV v2 fields** emitted
by `nwu_brain.scoring.NWUScorer`, applies rank weightings, enforces the OHS
(KPA2) must-pass check, and writes a concise final report + summary CSV.

What’s different vs legacy runner
---------------------------------
• No fuzzy tier/keyword logic. We **trust** the CSV v2 fields:
    - kpa, tier, tier_rule, values_score, values_hits,
      policy_hits, policy_hit_details, must_pass_risks,
      score (0–5), band, rationale, actions
• KPA aggregation is simple and deterministic:
    - For each KPA bucket, take the **top 5** items by `score`.
    - Compute KPA score = mean(top5) × 20  → percentage out of 100.
• OHS must-pass:
    - If KPA2 has **no evidence** → overall status “BLOCKED (no OHS evidence)”.
    - If any KPA2 item carries `must_pass_risks` → “BLOCKED (OHS risks)”.
• Rank weighting:
    - Weighted composite excludes KPA2 (weight 0.0).
    - Default weights align with typical academic ranks (can be overridden).

Outputs
-------
• <root>/_final/year_report.md
• <root>/_final/year_summary.csv  (per-KPA scores, counts, blocking status)
• <root>/_final/evidence_flat.csv (merged rows across months for auditing)

CLI
---
$ python vamp_runner.py --root ./VAMP --year 2025 --rank "Senior Lecturer"
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ----------------------------
# Rank weighting configuration
# ----------------------------

RANK_WEIGHTS: Dict[str, List[float]] = {
    #              KPA1   KPA2   KPA3   KPA4   KPA5
    "Junior Lecturer":     [0.80, 0.00, 0.10, 0.05, 0.05],
    "Lecturer":            [0.70, 0.00, 0.20, 0.05, 0.05],
    "Senior Lecturer":     [0.50, 0.00, 0.30, 0.10, 0.10],
    "Associate Professor": [0.40, 0.00, 0.40, 0.10, 0.10],
    "Full Professor":      [0.30, 0.00, 0.50, 0.10, 0.10],
    "Director/Dean":       [0.20, 0.00, 0.40, 0.30, 0.10],
}

DEFAULT_WEIGHTS = [0.25, 0.00, 0.25, 0.25, 0.25]  # if rank not found


# ----------------------------
# Paths & helpers
# ----------------------------

def discover_audits(root: Path) -> List[Path]:
    """
    Find all audit.csv files under the root, excluding `_final` snapshots.
    """
    out: List[Path] = []
    for p in root.rglob("audit.csv"):
        if p.parent.name == "_final":
            continue
        out.append(p)
    return sorted(out)

def _safe_json_list(s: str) -> List[Any]:
    """
    Robustly parse a list that might be stored as:
      - JSON string: '["a","b"]'
      - CSV-ish string: 'a,b'
      - Empty: ''
    """
    if s is None:
        return []
    s = str(s).strip()
    if not s:
        return []
    # Try JSON first
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return v
        return [v]
    except Exception:
        pass
    # Fallback: split on commas
    return [x.strip() for x in s.split(",") if x.strip()]

def _safe_kpa_list(s: str) -> List[int]:
    """
    Parse KPA column that may be:
      - JSON list: [1,2]
      - CSV-ish: '1,2'
      - Single: '3'
      - Empty: ''
    """
    out: List[int] = []
    if s is None:
        return out
    s = str(s).strip()
    if not s:
        return out
    # JSON first
    try:
        v = json.loads(s)
        if isinstance(v, list):
            for x in v:
                try:
                    out.append(int(x))
                except Exception:
                    pass
            return out
        else:
            return [int(v)]
    except Exception:
        pass
    # CSV fallback
    for x in s.split(","):
        x = x.strip()
        if not x:
            continue
        try:
            out.append(int(x))
        except Exception:
            pass
    return out

def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


# ----------------------------
# Row model & reading
# ----------------------------

@dataclass
class EvidenceRow:
    kpa_list: List[int]
    score_0_to_5: float          # 0..5 numeric score from NWUScorer
    band: str                    # textual band from institution_profile (for display)
    must_pass_risks: List[Any]   # list (if non-empty, indicates risk)
    title: str                   # optional display
    hash: str                    # for dedup
    source: str                  # platform/source (display)
    relpath: str                 # relative path if local FS scan
    policy_hits: List[Any]       # canonical policy flags (display)
    rationale: str               # textual rationale from scorer
    actions: List[str]           # recommended actions

def read_rows(audit_csv: Path) -> List[EvidenceRow]:
    rows: List[EvidenceRow] = []
    with audit_csv.open("r", encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        for r in reader:
            kpa_list = _safe_kpa_list(r.get("kpa", ""))
            score = _safe_float(r.get("score", 0.0), 0.0)  # 0..5
            band = (r.get("band") or "").strip()
            must_pass = _safe_json_list(r.get("must_pass_risks", ""))
            title = (r.get("name") or r.get("title") or r.get("relpath") or "").strip()
            hsh = (r.get("hash") or "").strip()
            src = (r.get("platform") or r.get("source") or "").strip()
            rel = (r.get("relpath") or "").strip()
            pol = _safe_json_list(r.get("policy_hits", ""))
            rationale = (r.get("rationale") or "").strip()
            actions = _safe_json_list(r.get("actions") or "")
            rows.append(EvidenceRow(
                kpa_list=kpa_list,
                score_0_to_5=score,
                band=band,
                must_pass_risks=must_pass,
                title=title,
                hash=hsh,
                source=src,
                relpath=rel,
                policy_hits=pol,
                rationale=rationale,
                actions=[str(a) for a in actions],
            ))
    return rows


# ----------------------------
# Aggregation
# ----------------------------

@dataclass
class KPASummary:
    kpa: int
    n_items: int
    top_scores: List[float]   # top 5 scores (0..5)
    kpa_score_pct: float      # mean(top5)*20 -> [0..100]
    issues: List[str]

def aggregate_by_kpa(rows: List[EvidenceRow]) -> Dict[int, KPASummary]:
    # Collect per-KPA buckets
    buckets: Dict[int, List[EvidenceRow]] = {k: [] for k in range(1, 6)}
    for r in rows:
        if not r.kpa_list:
            continue
        for k in r.kpa_list:
            if k in buckets:
                buckets[k].append(r)

    result: Dict[int, KPASummary] = {}
    for k in range(1, 5+1):
        items = buckets[k]
        n = len(items)
        # sort by score desc; take top 5
        top5 = sorted((it.score_0_to_5 for it in items), reverse=True)[:5]
        kpa_pct = 0.0
        if top5:
            kpa_pct = sum(top5) / len(top5) * 20.0
        issues: List[str] = []
        # Add simple signals
        if n == 0:
            issues.append("No evidence")
        result[k] = KPASummary(kpa=k, n_items=n, top_scores=top5, kpa_score_pct=round(kpa_pct, 1), issues=issues)

    # OHS / KPA2 must-pass enforcement (flag issues only; final block computed later)
    k2 = result[2]
    if buckets[2]:
        # If any item has must_pass_risks → flag
        if any(it.must_pass_risks for it in buckets[2]):
            k2.issues.append("OHS risks present (must-pass).")
    else:
        k2.issues.append("No OHS evidence (must-pass).")

    return result


def composite_score(kpa_summaries: Dict[int, KPASummary], rank: str) -> Tuple[float, bool, List[str]]:
    """
    Compute weighted composite (KPA2 weight=0). Return (score_pct, blocked, notes).
    """
    weights = RANK_WEIGHTS.get(rank, DEFAULT_WEIGHTS)
    notes: List[str] = []

    # Block if KPA2 has issues that indicate fail conditions
    blocked = False
    k2_issues = kpa_summaries.get(2).issues if 2 in kpa_summaries else ["No OHS evidence (must-pass)."]
    if any(("No OHS evidence" in it) or ("OHS risks" in it) for it in k2_issues):
        blocked = True
        notes.append("Overall blocked by OHS (KPA2) must-pass.")

    overall = 0.0
    for idx, k in enumerate(range(1, 6)):
        w = weights[idx]
        if w <= 0.0:
            continue
        overall += kpa_summaries[k].kpa_score_pct * w

    return round(overall, 1), blocked, notes


# ----------------------------
# Writing outputs
# ----------------------------

def write_year_summary_csv(out_csv: Path, rank: str, kpa_summaries: Dict[int, KPASummary],
                           overall_pct: float, blocked: bool) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(["rank", rank])
        w.writerow([])
        w.writerow(["KPA", "Items", "Top scores (0..5)", "KPA score (%)", "Issues"])
        for k in range(1, 6):
            s = kpa_summaries[k]
            w.writerow([
                f"KPA{k}",
                s.n_items,
                " ".join(f"{x:.2f}" for x in s.top_scores) if s.top_scores else "",
                f"{s.kpa_score_pct:.1f}",
                "; ".join(s.issues) if s.issues else "",
            ])
        w.writerow([])
        w.writerow(["Overall %", f"{overall_pct:.1f}"])
        w.writerow(["OHS block", "YES" if blocked else "NO"])

def write_evidence_flat_csv(out_csv: Path, merged_rows: List[EvidenceRow]) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow([
            "hash", "title", "source", "relpath",
            "kpa_list", "score_0_to_5", "band",
            "policy_hits", "must_pass_risks", "rationale", "actions"
        ])
        for r in merged_rows:
            w.writerow([
                r.hash, r.title, r.source, r.relpath,
                ",".join(str(x) for x in r.kpa_list),
                f"{r.score_0_to_5:.2f}",
                r.band,
                json.dumps(r.policy_hits, ensure_ascii=False),
                json.dumps(r.must_pass_risks, ensure_ascii=False),
                r.rationale,
                json.dumps(r.actions, ensure_ascii=False)
            ])

def write_final_report_md(out_md: Path, year: int, rank: str,
                          kpa_summaries: Dict[int, KPASummary],
                          overall_pct: float, blocked: bool, notes: List[str]) -> None:
    out_md.parent.mkdir(parents=True, exist_ok=True)
    with out_md.open("w", encoding="utf-8") as fp:
        fp.write(f"# VAMP Final Report — {year}\n\n")
        fp.write(f"**Rank:** {rank}\n\n")
        for k in range(1, 6):
            s = kpa_summaries[k]
            fp.write(f"## KPA{k}\n")
            fp.write(f"- Evidence items: **{s.n_items}**\n")
            fp.write(f"- Top scores: {', '.join(f'{x:.2f}' for x in s.top_scores) if s.top_scores else '(none)'}\n")
            fp.write(f"- KPA score: **{s.kpa_score_pct:.1f}%**\n")
            if s.issues:
                fp.write(f"- Issues: {', '.join(s.issues)}\n")
            fp.write("\n")
        fp.write("---\n\n")
        fp.write(f"## Composite\n")
        fp.write(f"- Overall (weighted): **{overall_pct:.1f}%**\n")
        fp.write(f"- OHS must-pass status: **{'BLOCKED' if blocked else 'OK'}**\n")
        if notes:
            fp.write(f"- Notes: {', '.join(notes)}\n")
        fp.write("\nGenerated by vamp_runner.py (NWU Brain–aligned).\n")


# ----------------------------
# Main orchestration
# ----------------------------

def run(root: Path, year: int, rank: str) -> Tuple[Path, Path, Path]:
    audits = discover_audits(root)
    if not audits:
        raise FileNotFoundError(f"No audit.csv files found under: {root}")

    merged: List[EvidenceRow] = []
    for a in audits:
        merged.extend(read_rows(a))

    # Aggregate by KPA
    kpa_summaries = aggregate_by_kpa(merged)
    overall_pct, blocked, notes = composite_score(kpa_summaries, rank)

    final_dir = root / "_final"
    final_dir.mkdir(parents=True, exist_ok=True)

    summary_csv = final_dir / "year_summary.csv"
    flat_csv    = final_dir / "evidence_flat.csv"
    report_md   = final_dir / "year_report.md"

    write_year_summary_csv(summary_csv, rank, kpa_summaries, overall_pct, blocked)
    write_evidence_flat_csv(flat_csv, merged)
    write_final_report_md(report_md, year, rank, kpa_summaries, overall_pct, blocked, notes)

    return summary_csv, flat_csv, report_md


# ----------------------------
# CLI
# ----------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="VAMP Year-end Aggregator (NWU Brain–aligned)")
    p.add_argument("--root", type=str, default=str(Path(__file__).resolve().parent / "VAMP"),
                   help="Evidence root containing monthly _out/audit.csv files")
    p.add_argument("--year", type=int, default=0, help="Assessment year (optional; for report title)")
    p.add_argument("--rank", type=str, default="Lecturer", help="Academic/job rank for weighting")
    return p.parse_args()

def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    year = args.year or 0
    # Title year is cosmetic; we won’t filter by year since audits already reflect month windows.
    try:
        summary_csv, flat_csv, report_md = run(root=root, year=year, rank=args.rank)
        print(f"Wrote: {summary_csv}")
        print(f"Wrote: {flat_csv}")
        print(f"Wrote: {report_md}")
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as e:
        print(f"FATAL: {e}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
