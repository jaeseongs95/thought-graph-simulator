"""변경하지 않은 v086 r2 계약·전송·생산/독립 채점 모듈 경로."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
FROZEN = ROOT / 'frozen086'
if str(FROZEN) not in sys.path: sys.path.append(str(FROZEN))
import bootstrap
