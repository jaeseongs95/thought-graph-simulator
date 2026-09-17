"""생산 보고서 연결. 집계와 판정의 역할을 분리한다."""
from rows091 import main_rows
from tables091 import aggregate,render


def summarize(plan,records,responses,state):
    rows,status,usage=main_rows(plan,records,responses)
    return aggregate(plan,rows,status,usage,state)
