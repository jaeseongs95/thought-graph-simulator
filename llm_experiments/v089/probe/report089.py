from rows089 import main_rows
from tables089 import aggregate,render

def summarize(plan,records,responses,state):
    rows,status,usage=main_rows(plan,records,responses)
    return aggregate(plan,rows,status,usage,state)
