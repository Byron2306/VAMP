cd "$PSScriptRoot"

# Create virtual environment
python -m venv venv

# Activate environment
.\venv\Scripts\Activate.ps1

# Install requirements
pip install --upgrade pip
pip install flask websocket-client requests pandas playwright

# Install Playwright browsers
playwright install

# Launch the backend
python vamp_master.py
