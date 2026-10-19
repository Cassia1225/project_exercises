"""Ensure package imports are independent of pytest's file collection order."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
