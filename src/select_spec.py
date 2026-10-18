"""Train-only specification grid for the muni strategy (python -m src.select_spec)."""
import itertools, pandas as pd, numpy as np
from . import muni
from .metrics import stats
rows=[]
for wr,wf,wc,hl in itertools.product([0,0.3],[0,0.5],[0,0.5],[1,2,3,5]):
    p=muni.run(params=dict(w_risk=wr,w_flow=wf,w_calendar=wc,halflife=hl))
    rows.append(dict(w_risk=wr,w_flow=wf,w_calendar=wc,hl=hl,train=stats(p.loc[:'2017'],252)['sharpe'],test=stats(p.loc['2018':],252)['sharpe']))
d=pd.DataFrame(rows).sort_values('train',ascending=False)
print(d.round(2).head(12).to_string()); print('median test of all 32 specs',round(d.test.median(),2),'min test',round(d.test.min(),2))
print('rank corr train vs test',round(d[['train','test']].corr(method='spearman').iloc[0,1],2))
d.to_csv('results/muni_spec_grid.csv',index=False)
