"""동결된 v080 유틸리티를 명시적으로 로드한다."""
from pathlib import Path
import sys
LEGACY = Path(__file__).resolve().parent / "legacy"
if str(LEGACY) not in sys.path:
    sys.path.append(str(LEGACY))
