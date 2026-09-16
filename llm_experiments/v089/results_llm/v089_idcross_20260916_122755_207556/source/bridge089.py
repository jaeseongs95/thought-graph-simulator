"""v088 실제 실행 소스를 바이트 보존해 v087/v086 전송·채점 계약을 불러온다."""
from pathlib import Path
import sys
FROZEN = Path(__file__).resolve().parent / 'frozen088'
if str(FROZEN) not in sys.path:
    sys.path.append(str(FROZEN))
import bridge088
