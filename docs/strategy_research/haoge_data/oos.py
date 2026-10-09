import sys; import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from haoge_data import MP,EM,D
from haoge_data_oos import MP2,EM2
def vote(vals,rules): return sum(2 if r(v) else -2 for v,r in zip(vals,rules))
V1_MP=[lambda v:v>=30, lambda v:v>=10, lambda v:v<=100, lambda v:v>=0.42, lambda v:v<=2.5]   # frozen from 6/24-7/17
V1_EM=[lambda v:v>0.60, lambda v:v<=0.30, lambda v:v>=0.62, lambda v:v>=0.80, lambda v:v<=0.30, lambda v:v<=0.50]
V2_MP=[lambda v:v>=30, lambda v:v>=11, lambda v:v<=100, lambda v:v>=0.42, lambda v:v<=2.0]   # refined
V2_EM=[lambda v:v>0.60, lambda v:v<=0.30, lambda v:v>=0.62, lambda v:v>0.80, lambda v:v<=0.30, lambda v:v<=0.50]
def run(name,mpr,emr,mp,em,show=False):
    a=b=c=0; fails=[]
    for d in mp:
        x=vote(mp[d][:5],mpr); y=vote(em[d][:6],emr)
        rep_mp=mp[d][5]; rep_em=em[d][6] if len(em[d])==8 else em[d][6]; rep_cy=em[d][7]
        a+=x==rep_mp; b+=y==rep_em; c+=(rep_mp+rep_em==rep_cy)
        if x!=rep_mp: fails.append(f"{d} 势能 {x}≠{rep_mp}")
        if y!=rep_em: fails.append(f"{d} 动能 {y}≠{rep_em}")
    n=len(mp); print(f"{name}: 势能 {a}/{n}  动能 {b}/{n}  周期=势+动 {c}/{n}  fails={fails}")
# in-sample dicts have different tuple layout -> adapt
MPi={d:MP[d][:6] for d in D}; EMi={d:EM[d][:8] for d in D}
run("V1 in-sample 6/24-7/17 ",V1_MP,V1_EM,MPi,EMi)
run("V1 OUT-OF-SAMPLE 7/31-9/29",V1_MP,V1_EM,MP2,EM2)
run("V2 in-sample 6/24-7/17 ",V2_MP,V2_EM,MPi,EMi)
run("V2 7/31-9/29 (refit)   ",V2_MP,V2_EM,MP2,EM2)
