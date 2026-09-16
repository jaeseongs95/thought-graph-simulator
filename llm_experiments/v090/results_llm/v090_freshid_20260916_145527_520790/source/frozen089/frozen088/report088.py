from rows088 import main_rows
from tables088 import aggregate,render

def summarize(plan,records,responses,state):
    rows,status,usage=main_rows(plan,records,responses)
    return aggregate(plan,rows,status,usage,state)
