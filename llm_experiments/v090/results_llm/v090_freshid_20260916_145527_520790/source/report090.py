"""생산 보고서 연결. 집계와 판정의 역할을 분리한다."""
from rows090 import main_rows
from tables090 import aggregate,render


def summarize(plan,records,responses,state):
    rows,status,usage=main_rows(plan,records,responses)
    return aggregate(plan,rows,status,usage,state)
