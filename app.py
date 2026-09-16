"""Workspace entry point for the Streamlit application."""

import runpy
import sys
from pathlib import Path


project_dir = Path(__file__).resolve().parent / ".venv"
sys.path.insert(0, str(project_dir))
runpy.run_path(str(project_dir / "app.py"), run_name="__main__")