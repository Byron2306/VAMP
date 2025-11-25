"""Refresh Playwright browser session storage for a given service."""

import argparse
import os
from pathlib import Path

from backend.vamp_agent import refresh_storage_state_sync


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Refresh Playwright storage_state for Outlook/OneDrive/Drive")
    parser.add_argument("service", choices=["outlook", "onedrive", "drive", "efundi"], help="Target platform service")
    parser.add_argument("--identity", help="Optional identity/email for multi-account setups")
    parser.add_argument(
        "--state-path",
        help="Optional explicit path to write the refreshed storage_state JSON (defaults to managed runtime path)",
    )
    args = parser.parse_args(argv)

    if not os.getenv("VAMP_HEADLESS"):
        os.environ["VAMP_HEADLESS"] = "0"

    state_path = None
    if args.state_path:
        state_path = Path(args.state_path).expanduser()
        state_path.parent.mkdir(parents=True, exist_ok=True)

    refreshed = refresh_storage_state_sync(args.service, args.identity)

    if state_path and refreshed != state_path:
        state_path.write_text(Path(refreshed).read_text(encoding="utf-8"), encoding="utf-8")
        refreshed = state_path

    print(f"[refresh_state] refreshed storage for {args.service}:{args.identity or 'default'} -> {refreshed}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
