"""v090 실제 소스 전체를 보존하며 기존 전송·primitive 검증 구현을 불러온다."""
from pathlib import Path
import sys
FROZEN = Path(__file__).resolve().parent / 'frozen090'
if str(FROZEN) not in sys.path:
    sys.path.append(str(FROZEN))
import bridge090
