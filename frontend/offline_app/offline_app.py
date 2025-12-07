from __future__ import annotations

import datetime
import sys
import threading
from pathlib import Path
from tkinter import BOTH, DISABLED, END, NORMAL, filedialog, messagebox, ttk
import tkinter as tk

# Ensure repository root is importable when packaged
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from backend.vamp_master import scan_and_score
from backend.vamp_runner import run as run_year_end


class OfflineApp(tk.Tk):
    """Lightweight desktop wrapper for VAMP scanning without WebSockets."""

    def __init__(self) -> None:
        super().__init__()
        self.title("VAMP Offline Scanner")
        self.geometry("780x520")

        self.folder_var = tk.StringVar()
        self.year_var = tk.StringVar(value=str(datetime.datetime.now().year))
        self.month_var = tk.StringVar(value=str(datetime.datetime.now().month))
        self.rank_var = tk.StringVar(value="Lecturer")
        self.outdir_var = tk.StringVar(value="_out")

        self._build_inputs()
        self._build_logs()

    def _build_inputs(self) -> None:
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill=tk.X)

        # Folder selection
        ttk.Label(frm, text="Evidence root folder:").grid(row=0, column=0, sticky=tk.W)
        folder_entry = ttk.Entry(frm, textvariable=self.folder_var, width=60)
        folder_entry.grid(row=0, column=1, padx=6, pady=4, sticky=tk.W)
        ttk.Button(frm, text="Browse…", command=self._choose_folder).grid(row=0, column=2, padx=4)

        # Year / Month / Outdir
        ttk.Label(frm, text="Year:").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(frm, textvariable=self.year_var, width=10).grid(row=1, column=1, sticky=tk.W)

        ttk.Label(frm, text="Month (1-12):").grid(row=1, column=2, sticky=tk.W, padx=10)
        ttk.Entry(frm, textvariable=self.month_var, width=10).grid(row=1, column=3, sticky=tk.W)

        ttk.Label(frm, text="Output dir name:").grid(row=1, column=4, sticky=tk.W, padx=10)
        ttk.Entry(frm, textvariable=self.outdir_var, width=14).grid(row=1, column=5, sticky=tk.W)

        # Rank for year-end weighting
        ttk.Label(frm, text="Rank (for year summary):").grid(row=2, column=0, sticky=tk.W)
        ranks = [
            "Junior Lecturer",
            "Lecturer",
            "Senior Lecturer",
            "Associate Professor",
            "Full Professor",
            "Director/Dean",
        ]
        ttk.Combobox(frm, textvariable=self.rank_var, values=ranks, width=24, state="readonly").grid(row=2, column=1, sticky=tk.W, pady=4)

        # Action buttons
        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=3, column=0, columnspan=3, pady=10, sticky=tk.W)
        ttk.Button(btn_frame, text="Run monthly scan", command=self._start_scan).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Build year summary", command=self._start_summary).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Clear log", command=self._clear_log).pack(side=tk.LEFT, padx=4)

    def _build_logs(self) -> None:
        log_frame = ttk.LabelFrame(self, text="Activity", padding=8)
        log_frame.pack(fill=BOTH, expand=True, padx=12, pady=8)
        self.log_widget = tk.Text(log_frame, state=DISABLED, wrap="word", height=18)
        self.log_widget.pack(fill=BOTH, expand=True)

    def _choose_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Select evidence root folder")
        if chosen:
            self.folder_var.set(chosen)

    def _append_log(self, msg: str) -> None:
        self.log_widget.configure(state=NORMAL)
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_widget.insert(END, f"[{timestamp}] {msg}\n")
        self.log_widget.configure(state=DISABLED)
        self.log_widget.see(END)

    def _queue_log(self, msg: str) -> None:
        self.after(0, lambda: self._append_log(msg))

    def _clear_log(self) -> None:
        self.log_widget.configure(state=NORMAL)
        self.log_widget.delete("1.0", END)
        self.log_widget.configure(state=DISABLED)

    def _start_scan(self) -> None:
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showerror("Missing folder", "Please choose an evidence root folder.")
            return

        try:
            year = int(self.year_var.get())
            month = int(self.month_var.get())
        except ValueError:
            messagebox.showerror("Invalid date", "Year and month must be numeric.")
            return

        evidence_root = Path(folder).expanduser().resolve()
        if not evidence_root.exists():
            messagebox.showerror("Not found", f"Folder does not exist: {evidence_root}")
            return

        out_dirname = self.outdir_var.get().strip() or "_out"
        threading.Thread(
            target=self._run_scan,
            args=(evidence_root, year, month, out_dirname),
            daemon=True,
        ).start()

    def _start_summary(self) -> None:
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showerror("Missing folder", "Please choose an evidence root folder.")
            return

        evidence_root = Path(folder).expanduser().resolve()
        if not evidence_root.exists():
            messagebox.showerror("Not found", f"Folder does not exist: {evidence_root}")
            return

        try:
            year = int(self.year_var.get())
        except ValueError:
            messagebox.showerror("Invalid year", "Year must be numeric for the summary.")
            return

        rank = self.rank_var.get().strip() or "Lecturer"
        threading.Thread(
            target=self._run_summary,
            args=(evidence_root, year, rank),
            daemon=True,
        ).start()

    def _run_scan(self, evidence_root: Path, year: int, month: int, out_dirname: str) -> None:
        self._queue_log(f"Starting scan in {evidence_root} (year {year}, month {month})…")

        try:
            csv_path, report_path = scan_and_score(
                evidence_root=evidence_root,
                year=year,
                month=month,
                out_dirname=out_dirname,
            )
            self._queue_log(f"Scan complete. CSV: {csv_path}")
            self._queue_log(f"Report: {report_path}")
            self.after(0, lambda: messagebox.showinfo("Scan complete", f"Scan finished.\nCSV: {csv_path}\nReport: {report_path}"))
        except Exception as exc:  # pragma: no cover - surfaced in dialog/log
            self._queue_log(f"Scan failed: {exc}")
            self.after(0, lambda: messagebox.showerror("Scan failed", str(exc)))

    def _run_summary(self, evidence_root: Path, year: int, rank: str) -> None:
        self._queue_log(f"Building year summary for {evidence_root} (rank {rank})…")
        try:
            summary_csv, flat_csv, report_md = run_year_end(root=evidence_root, year=year, rank=rank)
            self._queue_log(f"Summary CSV: {summary_csv}")
            self._queue_log(f"Evidence flat CSV: {flat_csv}")
            self._queue_log(f"Final report: {report_md}")
            self.after(
                0,
                lambda: messagebox.showinfo(
                    "Summary complete",
                    f"Year-end summary built.\nSummary CSV: {summary_csv}\nFlat CSV: {flat_csv}\nReport: {report_md}",
                ),
            )
        except Exception as exc:  # pragma: no cover - surfaced in dialog/log
            self._queue_log(f"Summary failed: {exc}")
            self.after(0, lambda: messagebox.showerror("Summary failed", str(exc)))


def main() -> None:
    app = OfflineApp()
    app.mainloop()


if __name__ == "__main__":
    main()
