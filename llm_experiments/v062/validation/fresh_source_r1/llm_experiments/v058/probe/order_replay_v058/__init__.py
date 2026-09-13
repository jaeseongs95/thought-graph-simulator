"""Counterordered replay of two post-hoc boundary cells."""
from pathlib import Path
import sys
DEPENDENCY_ROOT = Path(__file__).resolve().parents[3] / 'v057' / 'probe'
if not (DEPENDENCY_ROOT / 'selection_probe_v057').is_dir():
    raise ImportError('llm_experiments/v057/probe dependency is required')
if str(DEPENDENCY_ROOT) not in sys.path:
    sys.path.insert(0, str(DEPENDENCY_ROOT))
__version__ = '0.58.0'
