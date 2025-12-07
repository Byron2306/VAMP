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
    """Enhanced VAMP Offline Scanner with Gothic Dark Theme."""
    
    def __init__(self) -> None:
        super().__init__()
        self.title("VAMP — Offline Evidence Scanner")
        self.geometry("800x720")
        self.configure(bg="#000000")
        
        # Variables
        self.folder_var = tk.StringVar()
        self.year_var = tk.StringVar(value=str(datetime.datetime.now().year))
        self.month_var = tk.StringVar(value=str(datetime.datetime.now().month))
        self.rank_var = tk.StringVar(value="Lecturer")
        self.outdir_var = tk.StringVar(value="_out")
        
        # Configure styles
        self._configure_styles()
        
        # Build UI
        self._build_header()
        self._build_identity_section()
        self._build_scan_section()
        self._build_controls_section()
        self._build_log_section()
        
    def _configure_styles(self) -> None:
        """Configure ttk styles to match extension gothic theme."""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Colors from extension
        BG = "#000000"
        PANEL = "#0a0a0a"
        PANEL2 = "#111111"
        TEXT = "#f0f0f0"
        MUTED = "#888888"
        RED = "#ff2a2a"
        RED_DARK = "#cc0000"
        BORDER = "#222222"
        
        # Frame styles
        style.configure("Dark.TFrame", background=BG)
        style.configure("Panel.TFrame", 
                       background=PANEL,
                       borderwidth=1,
                       relief="solid")
        
        # Label styles
        style.configure("Header.TLabel",
                       background=BG,
                       foreground=RED,
                       font=("Arial", 32, "bold"))
        style.configure("Subtitle.TLabel",
                       background=BG,
                       foreground=MUTED,
                       font=("Arial", 10))
        style.configure("Section.TLabel",
                       background=PANEL,
                       foreground=TEXT,
                       font=("Arial", 12, "bold"))
        style.configure("Field.TLabel",
                       background=PANEL,
                       foreground="#e8e8e8",
                       font=("Arial", 10))
        
        # Entry styles
        style.configure("Dark.TEntry",
                       fieldbackground=BG,
                       background=BG,
                       foreground=TEXT,
                       borderwidth=1,
                       relief="solid",
                       insertcolor=TEXT)
        style.map("Dark.TEntry",
                 fieldbackground=[("focus", PANEL2)],
                 bordercolor=[("focus", RED)])
        
        # Combobox styles
        style.configure("Dark.TCombobox",
                       fieldbackground=BG,
                       background=BG,
                       foreground=TEXT,
                       arrowcolor=RED,
                       borderwidth=1)
        style.map("Dark.TCombobox",
                 fieldbackground=[("readonly", BG)],
                 selectbackground=[("readonly", RED_DARK)])
        
        # Button styles
        style.configure("Dark.TButton",
                       background=PANEL2,
                       foreground=TEXT,
                       borderwidth=1,
                       relief="solid",
                       font=("Arial", 10))
        style.map("Dark.TButton",
                 background=[("active", BORDER), ("pressed", BG)],
                 foreground=[("active", RED)])
        
        style.configure("Primary.TButton",
                       background=RED,
                       foreground="#ffffff",
                       borderwidth=1,
                       font=("Arial", 10, "bold"))
        style.map("Primary.TButton",
                 background=[("active", "#ff4444"), ("pressed", RED_DARK)])
        
    def _build_header(self) -> None:
        """Build branded header section."""
        header_frame = ttk.Frame(self, style="Dark.TFrame")
        header_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        # VAMP Title
        title = ttk.Label(header_frame, text="VAMP", style="Header.TLabel")
        title.pack()
        
        # Subtitle
        subtitle = ttk.Label(header_frame, 
                            text="Academic Performance Intelligence Agent — NWU Brain",
                            style="Subtitle.TLabel")
        subtitle.pack()
        
        # Separator
        sep = ttk.Separator(self, orient="horizontal")
        sep.pack(fill=tk.X, padx=20, pady=10)
        
    def _build_identity_section(self) -> None:
        """Build identity/scope section."""
        frame = ttk.Frame(self, style="Panel.TFrame")
        frame.pack(fill=tk.X, padx=20, pady=10, ipady=15, ipadx=15)
        
        # Section title
        ttk.Label(frame, text="Identity & Scope", style="Section.TLabel").grid(
            row=0, column=0, columnspan=4, sticky=tk.W, pady=(0, 10)
        )
        
        # Year / Month in same row
        ttk.Label(frame, text="Year:", style="Field.TLabel").grid(
            row=1, column=0, sticky=tk.W, padx=(0, 10), pady=5
        )
        year_entry = ttk.Entry(frame, textvariable=self.year_var, width=10, style="Dark.TEntry")
        year_entry.grid(row=1, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(frame, text="Month:", style="Field.TLabel").grid(
            row=1, column=2, sticky=tk.W, padx=(20, 10), pady=5
        )
        month_entry = ttk.Entry(frame, textvariable=self.month_var, width=10, style="Dark.TEntry")
        month_entry.grid(row=1, column=3, sticky=tk.W, pady=5)
        
        # Rank for year-end
        ttk.Label(frame, text="Academic Rank:", style="Field.TLabel").grid(
            row=2, column=0, sticky=tk.W, padx=(0, 10), pady=5
        )
        ranks = [
            "Junior Lecturer",
            "Lecturer",
            "Senior Lecturer",
            "Associate Professor",
            "Full Professor",
            "Director/Dean",
        ]
        rank_combo = ttk.Combobox(frame, textvariable=self.rank_var, values=ranks,
                                  width=24, state="readonly", style="Dark.TCombobox")
        rank_combo.grid(row=2, column=1, columnspan=3, sticky=tk.W, pady=5)
        
    def _build_scan_section(self) -> None:
        """Build scan configuration section."""
        frame = ttk.Frame(self, style="Panel.TFrame")
        frame.pack(fill=tk.X, padx=20, pady=10, ipady=15, ipadx=15)
        
        # Section title
        ttk.Label(frame, text="Local Evidence Scan", style="Section.TLabel").grid(
            row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 10)
        )
        
        # Folder selection
        ttk.Label(frame, text="Evidence Folder:", style="Field.TLabel").grid(
            row=1, column=0, sticky=tk.W, padx=(0, 10), pady=5
        )
        folder_entry = ttk.Entry(frame, textvariable=self.folder_var, width=50, style="Dark.TEntry")
        folder_entry.grid(row=1, column=1, sticky=tk.EW, pady=5)
        
        browse_btn = ttk.Button(frame, text="Browse...", command=self._choose_folder, style="Dark.TButton")
        browse_btn.grid(row=1, column=2, padx=(10, 0), pady=5)
        
        # Output directory
        ttk.Label(frame, text="Output Dir:", style="Field.TLabel").grid(
            row=2, column=0, sticky=tk.W, padx=(0, 10), pady=5
        )
        out_entry = ttk.Entry(frame, textvariable=self.outdir_var, width=20, style="Dark.TEntry")
        out_entry.grid(row=2, column=1, sticky=tk.W, pady=5)
        
        frame.columnconfigure(1, weight=1)
        
    def _build_controls_section(self) -> None:
        """Build action buttons section."""
        frame = ttk.Frame(self, style="Panel.TFrame")
        frame.pack(fill=tk.X, padx=20, pady=10, ipady=15, ipadx=15)
        
        # Section title
        ttk.Label(frame, text="Evidence Management", style="Section.TLabel").grid(
            row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 10)
        )
        
        # Button grid
        btn_frame = ttk.Frame(frame, style="Panel.TFrame")
        btn_frame.grid(row=1, column=0, columnspan=3, sticky=tk.EW)
        
        ttk.Button(btn_frame, text="▶ Run Monthly Scan", 
                  command=self._start_scan, style="Primary.TButton").pack(
            side=tk.LEFT, padx=5, fill=tk.X, expand=True
        )
        
        ttk.Button(btn_frame, text="📊 Build Year Summary", 
                  command=self._start_summary, style="Dark.TButton").pack(
            side=tk.LEFT, padx=5, fill=tk.X, expand=True
        )
        
        ttk.Button(btn_frame, text="🗑 Clear Log", 
                  command=self._clear_log, style="Dark.TButton").pack(
            side=tk.LEFT, padx=5, fill=tk.X, expand=True
        )
        
    def _build_log_section(self) -> None:
        """Build activity log section."""
        frame = ttk.Frame(self, style="Panel.TFrame")
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(10, 20), ipady=15, ipadx=15)
        
        # Section title
        ttk.Label(frame, text="Activity Log", style="Section.TLabel").pack(
            anchor=tk.W, pady=(0, 10)
        )
        
        # Log widget with scrollbar
        log_frame = tk.Frame(frame, bg="#000000", highlightthickness=1, highlightbackground="#333333")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(log_frame, bg="#0a0a0a", troughcolor="#000000")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_widget = tk.Text(
            log_frame,
            state=DISABLED,
            wrap="word",
            bg="#000000",
            fg="#f0f0f0",
            font=("Consolas", 9),
            insertbackground="#ff2a2a",
            selectbackground="#ff2a2a",
            selectforeground="#ffffff",
            yscrollcommand=scrollbar.set,
            borderwidth=0,
            highlightthickness=0,
            padx=10,
            pady=10
        )
        self.log_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_widget.yview)
        
        # Configure log tags
        self.log_widget.tag_configure("timestamp", foreground="#888888")
        self.log_widget.tag_configure("success", foreground="#00ff88")
        self.log_widget.tag_configure("error", foreground="#ff4444")
        self.log_widget.tag_configure("info", foreground="#ff2a2a")
        
    def _choose_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Select evidence root folder")
        if chosen:
            self.folder_var.set(chosen)
            self._append_log("📁 Folder selected", "info")
            
    def _append_log(self, msg: str, tag: str = "info") -> None:
        self.log_widget.configure(state=NORMAL)
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_widget.insert(END, f"[{timestamp}] ", "timestamp")
        self.log_widget.insert(END, f"{msg}\n", tag)
        self.log_widget.configure(state=DISABLED)
        self.log_widget.see(END)
        
    def _queue_log(self, msg: str, tag: str = "info") -> None:
        self.after(0, lambda: self._append_log(msg, tag))
        
    def _clear_log(self) -> None:
        self.log_widget.configure(state=NORMAL)
        self.log_widget.delete("1.0", END)
        self.log_widget.configure(state=DISABLED)
        self._append_log("🗑 Log cleared", "info")
        
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
            messagebox.showerror("Missing folder",
                                             messagebox.showerror("Missing folder", "Please choose an evidence root folder.")
            return
            
        try:
            year = int(self.year_var.get())
        except ValueError:
            messagebox.showerror("Invalid year", "Year must be numeric for the summary.")
            return
            
        evidence_root = Path(folder).expanduser().resolve()
        if not evidence_root.exists():
            messagebox.showerror("Not found", f"Folder does not exist: {evidence_root}")
            return
            
        rank = self.rank_var.get().strip() or "Lecturer"
        threading.Thread(
            target=self._run_summary,
            args=(evidence_root, year, rank),
            daemon=True,
        ).start()
        
    def _run_scan(self, evidence_root: Path, year: int, month: int, out_dirname: str) -> None:
        self._queue_log(f"🔍 Starting scan in {evidence_root} (year {year}, month {month})...", "info")
        try:
            csv_path, report_path = scan_and_score(
                evidence_root=evidence_root,
                year=year,
                month=month,
                out_dirname=out_dirname,
            )
            self._queue_log(f"✅ Scan complete. CSV: {csv_path}", "success")
            self._queue_log(f"📄 Report: {report_path}", "success")
            self.after(0, lambda: messagebox.showinfo("Scan complete", f"Scan finished.\nCSV: {csv_path}\nReport: {report_path}"))
        except Exception as exc:
            self._queue_log(f"❌ Scan failed: {exc}", "error")
            self.after(0, lambda: messagebox.showerror("Scan failed", str(exc)))
            
    def _run_summary(self, evidence_root: Path, year: int, rank: str) -> None:
        self._queue_log(f"📊 Building year summary for {evidence_root} (rank {rank})...", "info")
        try:
            summary_csv, flat_csv, report_md = run_year_end(root=evidence_root, year=year, rank=rank)
            self._queue_log(f"✅ Summary CSV: {summary_csv}", "success")
            self._queue_log(f"📋 Evidence flat CSV: {flat_csv}", "success")
            self._queue_log(f"📄 Final report: {report_md}", "success")
            self.after(
                0,
                lambda: messagebox.showinfo(
                    "Summary complete",
                    f"Year-end summary built.\nSummary CSV: {summary_csv}\nFlat CSV: {flat_csv}\nReport: {report_md}",
                ),
            )
        except Exception as exc:
            self._queue_log(f"❌ Summary failed: {exc}", "error")
            self.after(0, lambda: messagebox.showerror("Summary failed", str(exc)))


def main() -> None:
    app = OfflineApp()
    app.mainloop()


if __name__ == "__main__":
    main()
