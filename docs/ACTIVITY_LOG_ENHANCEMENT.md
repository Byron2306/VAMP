# Activity Log Enhancement for Offline App

## Quick Answer: Where to Check [OCR] Messages

**Currently:** OCR messages print to the terminal/console where you ran `python frontend/offline_app/offline_app.py`

**Problem:** You have to watch the console while scanning - inconvenient!

**Solution:** Add real-time activity log panel to the offline app UI (like the extension has)

---

## Implementation Guide

### What to Add

Add these enhancements to `frontend/offline_app/offline_app.py`:

### 1. Import logging at top of file (after line 8):

```python
import logging
import sys
from io import StringIO
```

### 2. Add custom log handler class (after imports, before OfflineApp class):

```python
class TextWidgetHandler(logging.Handler):
    """Logging handler that writes to a tkinter Text widget."""
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        
    def emit(self, record):
        msg = self.format(record)
        # Thread-safe GUI update
        self.text_widget.after(0, self._append_message, msg)
    
    def _append_message(self, msg):
        self.text_widget.config(state=tk.NORMAL)
        
        # Color coding based on log level
        if "[OCR]" in msg or "Extracting" in msg:
            self.text_widget.insert(tk.END, msg + "\n", "ocr")
        elif "ERROR" in msg or "Failed" in msg:
            self.text_widget.insert(tk.END, msg + "\n", "error")
        elif "SUCCESS" in msg or "✓" in msg:
            self.text_widget.insert(tk.END, msg + "\n", "success")
        elif "WARNING" in msg or "⚠" in msg:
            self.text_widget.insert(tk.END, msg + "\n", "warning")
        else:
            self.text_widget.insert(tk.END, msg + "\n")
        
        # Auto-scroll to bottom
        self.text_widget.see(tk.END)
        self.text_widget.config(state=tk.DISABLED)
```

### 3. In `__init__` method, after creating `self.log_text` widget, add:

```python
# Configure log text colors (add after line ~150 where log_text is created)
self.log_text.tag_config("ocr", foreground="#00d4ff")  # Cyan for OCR
self.log_text.tag_config("error", foreground="#ff4444")  # Red for errors
self.log_text.tag_config("success", foreground="#00ff88")  # Green for success  
self.log_text.tag_config("warning", foreground="#ffaa00")  # Orange for warnings

# Set up logging to write to the text widget
text_handler = TextWidgetHandler(self.log_text)
text_handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', datefmt='%H:%M:%S'))

# Get root logger and add our handler
root_logger = logging.getLogger()
root_logger.addHandler(text_handler)
root_logger.setLevel(logging.INFO)

# Also capture print() statements from backend
self.log("Activity log initialized")
self.log("Ready to scan...")
```

### 4. Modify `_run_scan_thread` to capture backend output:

Find the `_run_scan_thread` method and add stdout/stderr capture:

```python
def _run_scan_thread(self):
    """Background thread for scanning."""
    try:
        # Capture stdout to show OCR messages in GUI
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        
        # Create string buffer to capture prints
        sys.stdout = StdoutRedirector(self.log_text)
        sys.stderr = StdoutRedirector(self.log_text)
        
        self.log("Starting scan...")
        self.log(f"Scanning: {self.folder_path}")
        
        # ... existing scan_and_score code ...
        
    except Exception as e:
        self.log(f"❌ ERROR: {e}", level="error")
    finally:
        # Restore stdout/stderr
        sys.stdout = old_stdout
        sys.stderr = old_stderr
```

### 5. Add stdout redirector class:

```python
class StdoutRedirector:
    """Redirects stdout/stderr to tkinter Text widget."""
    def __init__(self, text_widget):
        self.text_widget = text_widget
        
    def write(self, message):
        if message.strip():  # Ignore empty lines
            self.text_widget.after(0, self._write_message, message)
    
    def _write_message(self, msg):
        self.text_widget.config(state=tk.NORMAL)
        
        # Detect OCR messages
        if "[OCR]" in msg:
            self.text_widget.insert(tk.END, msg, "ocr")
        elif "ERROR" in msg or "Failed" in msg:
            self.text_widget.insert(tk.END, msg, "error")
        elif "Extracted" in msg or "✓" in msg:
            self.text_widget.insert(tk.END, msg, "success")
        else:
            self.text_widget.insert(tk.END, msg)
        
        self.text_widget.see(tk.END)
        self.text_widget.config(state=tk.DISABLED)
    
    def flush(self):
        pass  # Required for file-like object
```

---

## What You'll See

After these changes, when you run a scan, the activity log will show:

```
[18:45:12] Starting scan...
[18:45:12] Scanning: C:\Users\User\Documents\Evidence
[18:45:13] Processing file 1/5: document.pdf
[18:45:13] [OCR] Extracting text from scanned PDF: document.pdf
[18:45:18] [OCR] Extracted 2847 characters from 3 pages
[18:45:18] ✓ Scored: KPA1=0.85, KPA2=0.0
[18:45:19] Processing file 2/5: report.pdf
...
[18:45:45] ✓ Scan complete! Generated audit.csv
```

**Color-coded:**
- 🔵 Cyan: OCR operations
- 🟢 Green: Success messages
- 🟠 Orange: Warnings
- 🔴 Red: Errors

---

## Simpler Alternative: Just Watch the Console

If you don't want to modify the UI code, **just watch the terminal where you ran the offline app**:

1. Open PowerShell/CMD
2. Run: `python frontend/offline_app/offline_app.py`
3. Click "Scan Folder" in the UI
4. **Watch the terminal** - you'll see:
   ```
   [OCR] Extracting text from scanned PDF: document.pdf
   [OCR] Extracted 2847 characters from 3 pages
   ```

If you DON'T see `[OCR]` messages, OCR isn't running (check installation).

---

## Benefits of UI Activity Log

✅ No need to watch two windows (UI + terminal)  
✅ Color-coded messages for quick scanning  
✅ Auto-scrolling to latest message  
✅ Persistent log (doesn't disappear when terminal closes)  
✅ Can copy/paste log for debugging  
✅ Matches extension UI experience

---

## File to Modify

`frontend/offline_app/offline_app.py` (~400 lines)

**Total additions:** ~100 lines of code

**Difficulty:** Medium (requires understanding of Tkinter threading)

Let me know if you want me to implement this directly or if you'd prefer to do it yourself!
