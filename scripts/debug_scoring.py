#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VAMP Scoring Debugger
Diagnoses why scan results aren't being classified into KPAs or getting proper scores.

Usage:
    python scripts/debug_scoring.py <path_to_audit.csv>
    
Example:
    python scripts/debug_scoring.py ./root_out/audit.csv
"""

import sys
import csv
import json
import re
from pathlib import Path

def load_json_file(filepath):
    """Load and parse JSON file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load {filepath}: {e}")
        return None

def test_clause_matches(text, clause_packs):
    """Test which clauses match the given text."""
    matches = []
    
    for pack_id, pack_data in clause_packs.items():
        if 'mandatory' in pack_data:
            for clause in pack_data['mandatory']:
                clause_id = clause.get('id', 'unknown')
                regex = clause.get('regex', '')
                
                if regex:
                    try:
                        pattern = re.compile(regex, re.IGNORECASE)
                        if pattern.search(text):
                            matches.append({
                                'pack_id': pack_id,
                                'clause_id': clause_id,
                                'regex': regex[:100] + '...' if len(regex) > 100 else regex,
                                'weight': clause.get('weight', 1)
                            })
                    except re.error as e:
                        print(f"[WARN] Invalid regex in {pack_id}/{clause_id}: {e}")
    
    return matches

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/debug_scoring.py <path_to_audit.csv>")
        print("\nExample: python scripts/debug_scoring.py ./root_out/audit.csv")
        sys.exit(1)
    
    audit_csv_path = Path(sys.argv[1])
    
    if not audit_csv_path.exists():
        print(f"[ERROR] File not found: {audit_csv_path}")
        sys.exit(1)
    
    print("="*80)
    print("VAMP Scoring Debugger")
    print("="*80)
    print()
    
    # Load NWU Brain data files
    brain_dir = Path(__file__).parent.parent / 'backend' / 'data' / 'nwu_brain'
    
    print("[STEP 1] Loading NWU Brain configuration...")
    clause_packs = load_json_file(brain_dir / 'clause_packs.json')
    kpa_router = load_json_file(brain_dir / 'kpa_router.json')
    policy_registry = load_json_file(brain_dir / 'policy_registry.json')
    
    if not clause_packs:
        print("[ERROR] Failed to load clause_packs.json")
        sys.exit(1)
    
    print(f"  - Loaded {len(clause_packs)} policy packs")
    if kpa_router:
        print(f"  - Loaded KPA router with {len(kpa_router)} mappings")
    if policy_registry:
        print(f"  - Loaded {len(policy_registry)} policy definitions")
    print()
    
    # Read audit.csv
    print("[STEP 2] Reading audit.csv...")
    try:
        with open(audit_csv_path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        print(f"[ERROR] Failed to read CSV: {e}")
        sys.exit(1)
    
    print(f"  - Found {len(rows)} entries")
    print()
    
    # Analyze each entry
    print("[STEP 3] Analyzing entries...")
    print()
    
    for i, row in enumerate(rows, 1):
        path = row.get('path', 'unknown')
        full_text = row.get('full_text', '')
        kpa1_score = float(row.get('kpa1_score', 0))
        kpa1_evidence = row.get('kpa1_evidence', '')
        
        print(f"Entry {i}: {Path(path).name}")
        print(f"  Full text length: {len(full_text)} characters")
        print(f"  KPA1 Score: {kpa1_score}")
        print(f"  KPA1 Evidence: {kpa1_evidence}")
        
        if len(full_text) == 0:
            print(f"  ⚠️  WARNING: No text extracted! OCR may have failed.")
            print(f"     - Check console for [OCR] messages during scan")
            print(f"     - Verify Tesseract is installed: tesseract --version")
            print(f"     - Try scanning a simple .txt file first")
        elif len(full_text) < 100:
            print(f"  ⚠️  WARNING: Very short text ({len(full_text)} chars). May be extraction issue.")
            print(f"     First 100 chars: {full_text[:100]}")
        else:
            # Test clause matching
            print(f"  ✓ Text extracted successfully")
            print(f"  First 200 chars: {full_text[:200]}...")
            print()
            print(f"  Testing policy clause matches...")
            
            matches = test_clause_matches(full_text, clause_packs)
            
            if matches:
                print(f"  ✓ Found {len(matches)} matching clauses:")
                for match in matches[:5]:  # Show first 5
                    print(f"     - Pack: {match['pack_id']}, Clause: {match['clause_id']}")
                    print(f"       Weight: {match['weight']}")
                    print(f"       Regex: {match['regex']}")
                if len(matches) > 5:
                    print(f"     ... and {len(matches) - 5} more")
            else:
                print(f"  ❌ NO MATCHES FOUND")
                print(f"     This explains why score = 0.0")
                print()
                print(f"  Possible causes:")
                print(f"     1. Document doesn't contain NWU policy-related keywords")
                print(f"     2. Clause regex patterns don't match your document format")
                print(f"     3. OCR text quality too poor (try higher DPI in vamp_master.py)")
                print()
                print(f"  Sample keywords from clause_packs.json:")
                # Show some sample patterns
                sample_patterns = []
                for pack_id, pack_data in list(clause_packs.items())[:3]:
                    if 'mandatory' in pack_data and pack_data['mandatory']:
                        clause = pack_data['mandatory'][0]
                        sample_patterns.append(f"     - {clause.get('id', 'unknown')}: looks for patterns like '{clause.get('regex', '')[:60]}...'")
                
                for pattern in sample_patterns:
                    print(pattern)
        
        print()
        print("-" * 80)
        print()
    
    print("[SUMMARY]")
    print()
    
    # Calculate statistics
    total = len(rows)
    zero_scores = sum(1 for r in rows if float(r.get('kpa1_score', 0)) == 0)
    empty_text = sum(1 for r in rows if len(r.get('full_text', '')) == 0)
    short_text = sum(1 for r in rows if 0 < len(r.get('full_text', '')) < 100)
    
    print(f"Total entries: {total}")
    print(f"Entries with 0.0 score: {zero_scores} ({100*zero_scores/total if total > 0 else 0:.1f}%)")
    print(f"Entries with empty text: {empty_text}")
    print(f"Entries with very short text: {short_text}")
    print()
    
    if empty_text > 0:
        print("⚠️  PRIMARY ISSUE: Text extraction failing")
        print("   Solution: Verify OCR installation")
        print("   1. Run: tesseract --version")
        print("   2. Run: python -c \"import pytesseract; print(pytesseract.get_tesseract_version())\"")
        print("   3. Check vamp_master.py for [OCR] console messages")
    elif zero_scores > total * 0.8:  # > 80% zero scores
        print("⚠️  PRIMARY ISSUE: Policy pattern matching failing")
        print("   Possible solutions:")
        print("   1. Check that PDFs contain NWU policy-related content")
        print("   2. Review clause_packs.json regex patterns")
        print("   3. Check if documents use different terminology")
        print("   4. Increase OCR DPI in vamp_master.py (line 202: dpi=300 -> dpi=400)")
    else:
        print("✓ System appears to be working for some files")
        print("  Mixed results suggest document content variation")
    
    print()
    print("="*80)

if __name__ == '__main__':
    main()
