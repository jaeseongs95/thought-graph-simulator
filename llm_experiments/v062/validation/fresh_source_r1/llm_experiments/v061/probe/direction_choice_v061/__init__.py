"""Exploratory shallow/deep directive diagnostic; Python standard library."""
from pathlib import Path
import sys

DEPENDENCY_ROOT = Path(__file__).resolve().parents[3] / 'v058' / 'probe'
if not (DEPENDENCY_ROOT / 'order_replay_v058').is_dir():
    raise ImportError('llm_experiments/v058/probe dependency required')
if str(DEPENDENCY_ROOT) not in sys.path:
    sys.path.insert(0, str(DEPENDENCY_ROOT))
import order_replay_v058  # Registers the unchanged v057 dependency.
__version__ = '0.61.0'
