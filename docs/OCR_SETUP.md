# OCR Setup Guide for VAMP Offline App

## Problem Statement

If your offline app is generating audit.csv files with **all scores showing 0.0**, it's likely because your PDFs contain scanned images rather than embedded text. The default text extraction (pdfminer/pdfplumber) cannot read scanned images, resulting in empty `full_text` fields and no policy matching.

## Solution

The latest update adds **OCR (Optical Character Recognition) support** to `vamp_master.py`, enabling text extraction from scanned PDFs using Tesseract.

## Installation Steps

### Step 1: Install Tesseract OCR (System Binary)

#### Windows

**Option A: Using Chocolatey (Recommended)**
```bash
choco install tesseract
```

**Option B: Manual Installation**
1. Download the installer from: https://github.com/UB-Mannheim/tesseract/wiki
2. Run the installer (select "Add to PATH" during installation)
3. Verify installation:
   ```bash
   tesseract --version
   ```

**Default installation path:** `C:\Program Files\Tesseract-OCR`

If Tesseract is not in PATH, add it:
1. Open System Properties → Environment Variables
2. Add `C:\Program Files\Tesseract-OCR` to PATH
3. Restart terminal/PowerShell

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install tesseract-ocr
```

#### macOS
```bash
brew install tesseract
```

### Step 2: Install Python OCR Packages

Navigate to your VAMP directory and install required packages:

```bash
cd path/to/VAMP
pip install pytesseract pillow pdf2image
```

**Additional Windows requirement:** pdf2image needs Poppler
```bash
choco install poppler
# Or download from: https://github.com/oschwartz10612/poppler-windows/releases/
```

### Step 3: Pull Latest Changes

```bash
git pull origin main
```

This will fetch the OCR-enhanced `vamp_master.py` with:
- OCR imports (lines 69-78)
- Enhanced `txt_from_pdf()` function with OCR fallback (lines 198-218)

### Step 4: Verify Installation

Run a quick test:

```python
import pytesseract
from PIL import Image
from pdf2image import convert_from_path

print("OCR dependencies installed successfully!")
print(f"Tesseract version: {pytesseract.get_tesseract_version()}")
```

If no errors, you're ready to go!

## Usage

### Run Offline App with OCR

1. Launch the offline app:
   ```bash
   python frontend/offline_app/offline_app.py
   ```

2. Scan a folder containing scanned PDFs

3. Watch the console for OCR diagnostic messages:
   ```
   [OCR] Extracting text from scanned PDF: document.pdf
   [OCR] Extracted 2847 characters from 3 pages
   ```

4. Check `audit.csv` - scores should now be non-zero for files with policy-matching content

### Expected Output

**Before OCR (broken):**
```csv
source,path,full_text,kpa1_score,kpa1_evidence
local,document.pdf,,0.0,No strong matches
```

**After OCR (working):**
```csv
source,path,full_text,kpa1_score,kpa1_evidence  
local,document.pdf,"[Page 1] Password Policy Requirements....",0.85,"Found evidence: password complexity requirements..."
```

## Troubleshooting

### Issue: "WARNING: No text extracted from file.pdf (OCR not available)"

**Cause:** Tesseract or Python OCR packages not installed

**Fix:** 
1. Verify Tesseract is installed: `tesseract --version`
2. Verify Python packages: `pip show pytesseract pillow pdf2image`
3. Restart Python environment after installation

### Issue: "OCR Failed for file.pdf: [Errno 2] No such file or directory: 'tesseract'"

**Cause:** Tesseract not in PATH

**Fix (Windows):**
```python
# Add to vamp_master.py before OCR imports:
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

**Fix (Linux/macOS):**
```bash
export PATH="$PATH:/usr/local/bin"
```

### Issue: "pdf2image.exceptions.PDFInfoNotInstalledError"

**Cause:** Poppler not installed (Windows)

**Fix:**
```bash
choco install poppler
```

Or download manually and add to PATH: https://github.com/oschwartz10612/poppler-windows/releases/

### Issue: OCR is slow

**Cause:** Default 300 DPI setting trades speed for accuracy

**Fix:** Reduce DPI in `vamp_master.py` line 202:
```python
# Change from:
images = convert_from_path(str(path), dpi=300)
# To:
images = convert_from_path(str(path), dpi=150)  # Faster but less accurate
```

### Issue: Still getting 0.0 scores after OCR

**Possible causes:**
1. **PDFs truly contain no policy-related text** - Check OCR output manually
2. **Policy keywords mismatch** - Review `backend/data/nwu_brain/*.json` files
3. **Text quality too poor** - Try higher DPI or clean scanned images

**Debug steps:**
1. Check console logs for `[OCR] Extracted X characters` messages
2. Open `audit.csv` and verify `full_text` column is populated
3. Search audit.csv full_text for expected keywords (e.g., "password", "policy")
4. If text is garbled, source PDF quality may be too low

## Alternative: Test with Text Files

To verify the scoring logic works independently of OCR:

1. Create a test file `test_evidence.txt`:
   ```
   Test Policy Evidence
   Date: 2024-01-15
   
   Password Policy Requirements:
   - Minimum 8 characters
   - Must include uppercase, lowercase, and numbers
   - Multi-factor authentication required
   - Password expiration: 90 days
   ```

2. Scan folder containing only this .txt file
3. Should score correctly without OCR (txt files don't need it)

## Performance Notes

- **OCR speed:** ~2-5 seconds per page at 300 DPI
- **Memory:** ~50-100 MB per PDF during processing
- **Accuracy:** 95%+ for clear scanned documents, lower for handwritten/poor quality
- **Fallback:** If OCR fails, warning is logged but processing continues

## Code Changes Summary

### Added to vamp_master.py:

**Lines 69-78:** OCR imports with availability check
```python
OCR_AVAILABLE = False
_OCR_ERROR = None
try:
    import pytesseract
    from PIL import Image
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError as e:
    _OCR_ERROR = str(e)
```

**Lines 198-218:** OCR fallback in `txt_from_pdf()`
```python
# OCR fallback for scanned PDFs (if text extraction failed)
if (not text or len(text.strip()) < 50) and OCR_AVAILABLE:
    try:
        print(f"[OCR] Extracting text from scanned PDF: {path.name}")
        images = convert_from_path(str(path), dpi=300)
        ocr_text = []
        for i, img in enumerate(images):
            page_text = pytesseract.image_to_string(img, config='--psm 6')
            if page_text.strip():
                ocr_text.append(f"[Page {i+1}]\n{page_text}")
        if ocr_text:
            text = "\n\n".join(ocr_text)
            print(f"[OCR] Extracted {len(text)} characters from {len(images)} pages")
```

## Need Help?

If you're still experiencing issues:
1. Check console logs for specific error messages
2. Verify Tesseract installation: `tesseract --version`
3. Verify Python packages: `pip list | grep -E "pytesseract|pillow|pdf2image"`
4. Test with simple text file first (bypass OCR complexity)
5. Share error logs for further assistance

## Related Files

- **vamp_master.py** - Main text extraction logic with OCR fallback
- **offline_app.py** - Offline UI (unchanged)
- **local_scan_handler.py** - Handles scan requests (unchanged)
- **backend/nwu_brain/scoring.py** - Policy matching scorer (unchanged)
