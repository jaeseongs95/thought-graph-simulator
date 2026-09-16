"""바이트 보존한 v087 및 그 하위 v086 계약·전송·채점 모듈."""
from pathlib import Path
import sys
FROZEN = Path(__file__).resolve().parent / 'frozen087'
if str(FROZEN) not in sys.path: sys.path.append(str(FROZEN))
import bridge087
