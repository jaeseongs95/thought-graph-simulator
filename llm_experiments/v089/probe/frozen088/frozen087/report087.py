"""생산 원응답 판정을 집계한다. 실행과 분리된 읽기 전용 보고."""
from rows087 import main_rows
from tables087 import aggregate,render

def summarize(plan,records,responses,state):
    rows,statuses,usage=main_rows(plan,records,responses)
    return aggregate(plan,rows,statuses,usage,state)
