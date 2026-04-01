import sys
import os

# Make `backend/` importable so tests can do `from llm.panel_show import ...`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
