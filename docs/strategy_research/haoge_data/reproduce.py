import sys; import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from haoge_data import *
# fixed thresholds inferred from colors (red=favourable)
MP_RULES=[lambda v:v>=30, lambda v:v>=10, lambda v:v<=100, lambda v:v>=0.42, lambda v:v<=2.5]
EM_RULES=[lambda v:v>0.60, lambda v:v<=0.30, lambda v:v>=0.62, lambda v:v>=0.80, lambda v:v<=0.30, lambda v:v<=0.50]
def vote(vals,rules): return sum(2 if r(v) else -2 for v,r in zip(vals,rules))
cm=ce=cc=0; colmis=[]
print("date   | 势能 rep/calc | 动能 rep/calc | 周期 rep/势+动 | color mismatches")
for d in D:
    mp=MP[d]; em=EM[d]
    a=vote(mp[:5],MP_RULES); b=vote(em[:6],EM_RULES)
    # color-based recount (pure counting of his own colors)
    ac=sum(2 if c=='R' else -2 for c in mp[6]); bc=sum(2 if c=='R' else -2 for c in em[8])
    mis=[]
    for i,(v,r,c) in enumerate(zip(mp[:5],MP_RULES,mp[6])):
        if r(v)!=(c=='R'): mis.append(f"MP{i}:{v}={c}")
    for i,(v,r,c) in enumerate(zip(em[:6],EM_RULES,em[8])):
        if r(v)!=(c=='R'): mis.append(f"EM{i}:{v}={c}")
    cm+=(a==mp[5]); ce+=(b==em[6]); cc+=(mp[5]+em[6]==em[7])
    print(f"{d}  | {mp[5]:>3}/{a:>3} (colors {ac:>3}) | {em[6]:>3}/{b:>3} (colors {bc:>3}) | {em[7]:>3}/{mp[5]+em[6]:>3} | {' '.join(mis)}")
n=len(D); print(f"\n势能 threshold-reproduced {cm}/{n}; 动能 {ce}/{n}; 周期==势能+动能 {cc}/{n}")
