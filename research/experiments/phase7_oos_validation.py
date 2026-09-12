"""Phase 7 — Adversarial Out-of-Sample Validation (optimized).

Pre-extracts events + precomputes all metrics once. Analyses are O(1) lookups.
Usage: cd /root/that && .venv/bin/python -u scripts/phase7_oos_validation.py
"""
from __future__ import annotations

import json, pickle, sys, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats as sp_stats

warnings.filterwarnings("ignore")
from nestquant.research.shared.zscore.zscore import compute_zscore_causal

Z_ENTRY=2.2; LOOKBACK=20; COMMISSION=3.50; SLIPPAGE_PIPS=0.3
ATR_PERIOD=14; ATR_SL_MULT=3.0; MAX_HOLD=64
SESSIONS={"london":(7,16),"new_york":(12,21)}; SKIP_FRI=20; SKIP_MON=3
PAIRS=["EUR/USD","GBP/USD","USD/JPY","USD/CHF","AUD/USD","NZD/USD",
       "EUR/GBP","EUR/CHF","EUR/JPY","AUD/JPY","EUR/AUD","AUD/CAD",
       "GBP/JPY","GBP/CAD","GBP/AUD","CAD/JPY","NZD/JPY","NZD/CHF","AUD/CHF","CAD/CHF"]
SPREAD={"EUR/USD":0.8,"GBP/USD":1.0,"USD/JPY":1.0,"USD/CHF":1.2,"AUD/USD":0.9,
        "NZD/USD":1.2,"EUR/GBP":1.2,"EUR/CHF":1.5,"EUR/JPY":2.0,"GBP/JPY":3.0,
        "AUD/JPY":2.0,"CAD/JPY":2.5,"NZD/JPY":3.0,"EUR/AUD":2.0,"EUR/CAD":2.5,
        "GBP/AUD":3.5,"GBP/CAD":3.5,"AUD/CAD":2.0,"AUD/CHF":2.5,"NZD/CHF":3.0,"CAD/CHF":3.0}
DEFAULT_USD={"USD":1.0,"EUR":1.08,"GBP":1.26,"JPY":0.0067,"CHF":0.88,"AUD":0.65,"CAD":0.74,"NZD":0.60}
OUT=Path("research/output/phase7"); OUT.mkdir(parents=True,exist_ok=True)

DISCOVERED_REGIONS=[
    {"key":"Z3-3.5-Vextreme_vol","zlo":3.0,"zhi":3.5,"vr":"extreme_vol"},
    {"key":"Z2.5-3-Vextreme_vol","zlo":2.5,"zhi":3.0,"vr":"extreme_vol"},
    {"key":"Z3.5-4-Vextreme_vol","zlo":3.5,"zhi":4.0,"vr":"extreme_vol"},
    {"key":"Z4-5-Vhigh_vol","zlo":4.0,"zhi":5.0,"vr":"high_vol"},
    {"key":"Z5+-Vmid_vol","zlo":5.0,"zhi":100.0,"vr":"mid_vol"},
    {"key":"Z3.5-4-Vlow_vol","zlo":3.5,"zhi":4.0,"vr":"low_vol"},
]

HELDOUT_GROUPS=[
    ["CAD/JPY","NZD/JPY","NZD/CHF","AUD/CHF","CAD/CHF"],
    ["EUR/AUD","AUD/CAD","GBP/JPY","GBP/CAD","GBP/AUD"],
    ["NZD/USD","EUR/GBP","EUR/CHF","EUR/JPY","AUD/JPY"],
    ["EUR/USD","GBP/USD","USD/JPY","USD/CHF","AUD/USD"],
    ["CAD/JPY","NZD/JPY","NZD/CHF","AUD/CHF","CAD/CHF"],
]


def in_session(ts):
    h,d=ts.hour,ts.dayofweek
    if d==4 and h>=SKIP_FRI: return False
    if d==0 and h<SKIP_MON: return False
    if d>=5: return False
    return any(s<=h<e for s,e in SESSIONS.values())

def pip_size(pair): return 0.01 if "JPY" in pair else 0.0001
def pip_value(pair): return pip_size(pair)*100000*DEFAULT_USD.get(pair.split("/")[1],1.0)

def classify_vol(atr_pct_arr,i):
    if i>=len(atr_pct_arr) or np.isnan(atr_pct_arr[i]): return "unknown"
    v=atr_pct_arr[~np.isnan(atr_pct_arr)]
    if len(v)==0: return "unknown"
    a=atr_pct_arr[i]; p25,p75,p95=np.percentile(v,[25,75,95])
    if a<=p25: return "low_vol"
    if a>=p95: return "extreme_vol"
    if a>=p75: return "high_vol"
    return "mid_vol"


def load_all(start,end):
    pdata={}
    for pair in PAIRS:
        try:
            with open(f"/root/data/{pair.replace('/','_')}.pkl","rb") as f: raw=pickle.load(f)
        except Exception: continue
        df=raw.get(pair)
        if df is None or df.empty: continue
        idx=pd.to_datetime(df.index)
        idx=idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        df.index=idx; df=df[(df.index>=start)&(df.index<=end)]
        if len(df)<500: continue
        df=df[["open","high","low","close"]].resample("30min").agg(
            {"open":"first","high":"max","low":"min","close":"last"}).dropna(subset=["close"])
        if len(df)<500: continue
        c=df["close"].values.astype(np.float64)
        obs=compute_zscore_causal(c,df.index,pair,lookback=LOOKBACK)
        z=np.array([o.z_score for o in obs])
        tr=pd.concat([df["high"]-df["low"],(df["high"]-df["close"].shift(1)).abs(),
                       (df["low"]-df["close"].shift(1)).abs()],axis=1).max(axis=1)
        atr=tr.rolling(ATR_PERIOD).mean().values
        atr_pct=atr/df["close"].values*100
        ema200=df["close"].ewm(span=200,adjust=False).mean().values
        pdata[pair]={"c":c,"h":df["high"].values,"lo":df["low"].values,
                      "ts":df.index,"n":len(df),"z":z,"atr":atr,"atr_pct":atr_pct,
                      "ema200":ema200,
                      "pip":pip_size(pair),"pv":pip_value(pair),
                      "spread":SPREAD.get(pair,2.0)}
    return pdata


def causal_pct(z,bar_idx,lookback):
    start=max(0,bar_idx-lookback);window=np.abs(z[start:bar_idx+1])
    valid=window[~np.isnan(window)]
    if len(valid)<20: return 50.0
    cur=abs(z[bar_idx]) if not np.isnan(z[bar_idx]) else 0.0
    return float(np.mean(valid<=cur))*100


def precompute_metrics(events):
    """Compute fwd4, pnl4, mae4 for each event and cache on the dict."""
    for e in events:
        pp=e["price_path"]; zp=e["z_path"]; hp=e["high_path"]; lp=e["low_path"]
        d=e["direction"]; pip=e["pip"]; pv=e["pv"]; ep=e["entry_price"]
        n=min(4,len(pp)); sl=e["sl_price"]
        # fwd4
        e["fwd4"]=(pp[n-1]-ep)*d/pip if n>=2 else 0.0
        # pnl4 at different costs
        for cost_name,cost in [("c0",0),("c35",3.5),("c15",15),("c5",5)]:
            pnl=0.0; sl_hit=False
            for j in range(1,n):
                if d==1 and lp[j]<=sl: pnl=(sl-ep)/pip*pv*e["lot"]-e["lot"]*cost; sl_hit=True; break
                if d==-1 and hp[j]>=sl: pnl=(ep-sl)/pip*pv*e["lot"]-e["lot"]*cost; sl_hit=True; break
            if not sl_hit: pnl=(pp[n-1]-ep)*d/pip*pv*e["lot"]-e["lot"]*cost
            e[f"pnl4_{cost_name}"]=pnl
        # mae4 / mfe4
        mae=mfe=0.0
        for j in range(1,n):
            cmae=(ep-lp[j])/pip if d==1 else (hp[j]-ep)/pip
            cmfe=(hp[j]-ep)/pip if d==1 else (ep-lp[j])/pip
            if cmae>mae: mae=cmae
            if cmfe>mfe: mfe=cmfe
        e["mae4"]=mae; e["mfe4"]=mfe
        # z at different horizons
        for h in [4,8,16]:
            idx=min(h,len(zp)-1)
            e[f"z{h}"]=zp[idx]
    return events


def stats(arr):
    if not arr: return {"n":0}
    a=np.array(arr,dtype=float)
    return {"n":len(a),"mean":round(float(np.mean(a)),4),"median":round(float(np.median(a)),4),
            "std":round(float(np.std(a,ddof=1)),4) if len(a)>1 else 0}

def metrics(pnls):
    if not pnls: return {"n":0}
    a=np.array(pnls,dtype=float)
    w=int(np.sum(a>0));l_=int(np.sum(a<=0))
    gw=float(np.sum(a[a>0])) if w>0 else 0
    gl=float(np.abs(np.sum(a[a<=0]))) if l_>0 else 0
    return {"n":len(a),"win_rate":round(w/(w+l_)*100,1) if (w+l_)>0 else 0,
            "pf":round(gw/gl,2) if gl>0 else (99 if gw>0 else 0),
            "avg":round(float(np.mean(a)),2),"net":round(float(np.sum(a)),2),
            "median":round(float(np.median(a)),2)}

def bootstrap_ci(arr,nb=500):
    a=np.array(arr,dtype=float);means=[];pfs=[]
    for _ in range(nb):
        s=np.random.choice(a,size=len(a),replace=True)
        means.append(float(np.mean(s)))
        gpos=np.sum(s[s>0]) if np.any(s>0) else 0
        gneg=np.abs(np.sum(s[s<=0])) if np.any(s<=0) else 1
        pfs.append(gpos/gneg if gneg>0 else 99)
    return {"mean":round(float(np.mean(means)),4),
            "ci_lo":round(float(np.percentile(means,2.5)),4),
            "ci_hi":round(float(np.percentile(means,97.5)),4),
            "pf":round(float(np.mean(pfs)),4),
            "pf_ci_lo":round(float(np.percentile(pfs,2.5)),4),
            "pf_ci_hi":round(float(np.percentile(pfs,97.5)),4)}


# ── ANALYSIS FUNCTIONS (use cached metrics) ──

def analyze_walk_forward(events):
    print("\n[1] Walk-Forward Validation...")
    splits=[("2016-2020",2016,2021),("2016-2021",2022,2022),
            ("2016-2022",2023,2023),("2016-2023",2024,2024),
            ("2016-2024",2025,2026)]
    results={}
    for si,(label,ts,te) in enumerate(splits):
        test=[e for e in events if ts<=e["year"]<=te]
        r={"n":len(test),"regions":{}}
        for reg in DISCOVERED_REGIONS:
            sub=[e for e in test if reg["zlo"]<=e["abs_z"]<reg["zhi"] and e["vol_regime"]==reg["vr"]]
            if len(sub)<5: r["regions"][reg["key"]]={"n":len(sub)}; continue
            f4=[e["fwd4"] for e in sub]; p4=[e["pnl4_c35"] for e in sub]
            fast=[e for e in sub if e["outcome"]=="fast_mr"]
            slow=[e for e in sub if e["outcome"]=="slow_mr"]
            r["regions"][reg["key"]]={
                "n":len(sub),"fwd4":stats(f4),"pnl4":metrics(p4),
                "pnl4_nocost":metrics([e["pnl4_c0"] for e in sub]),
                "pnl4_high":metrics([e["pnl4_c15"] for e in sub]),
                "mae":stats([e["mae4"] for e in sub]),"mfe":stats([e["mfe4"] for e in sub]),
                "boot":bootstrap_ci(p4),
                "fast_n":len(fast),"fast_f4":stats([e["fwd4"] for e in fast]) if fast else {"n":0},
                "slow_n":len(slow),"slow_f4":stats([e["fwd4"] for e in slow]) if slow else {"n":0}}
        for thr in [3.0,4.0,5.0]:
            sub=[e for e in test if e["abs_z"]>=thr]
            if len(sub)<5: continue
            r["regions"][f"Z{thr}+_abs"]={"n":len(sub),"fwd4":stats([e["fwd4"] for e in sub]),
                                           "pnl4":metrics([e["pnl4_c35"] for e in sub]),
                                           "boot":bootstrap_ci([e["pnl4_c35"] for e in sub])}
        print(f"    Split {si+1}/5: {label} → {te}: n={len(test)}")
        results[label]=r
    return results


def analyze_pair_holdout(events):
    print("\n[2] Pair Holdout Validation...")
    results={}
    for fi,thp in enumerate(HELDOUT_GROUPS):
        test=[e for e in events if e["pair"] in thp]
        r={"pairs":thp,"n":len(test),"regions":{}}
        for reg in DISCOVERED_REGIONS:
            sub=[e for e in test if reg["zlo"]<=e["abs_z"]<reg["zhi"] and e["vol_regime"]==reg["vr"]]
            if len(sub)<5: r["regions"][reg["key"]]={"n":len(sub)}; continue
            f4=[e["fwd4"] for e in sub]; p4=[e["pnl4_c35"] for e in sub]
            r["regions"][reg["key"]]={
                "n":len(sub),"fwd4":stats(f4),"pnl4":metrics(p4),"boot":bootstrap_ci(p4)}
        print(f"    Fold {fi+1}: test={thp[:2]}... n={len(test)}")
        results[f"fold_{fi+1}"]=r
    agg={}
    for reg in DISCOVERED_REGIONS:
        all_f4=[];ns=[]
        for thp in HELDOUT_GROUPS:
            sub=[e for e in events if e["pair"] in thp and reg["zlo"]<=e["abs_z"]<reg["zhi"] and e["vol_regime"]==reg["vr"]]
            if sub: all_f4.extend([e["fwd4"] for e in sub]);ns.append(len(sub))
        if all_f4: agg[reg["key"]]={"total_n":sum(ns),"fwd4":stats(all_f4),
                                      "pct_pos":round(np.mean(np.array(all_f4)>0)*100,1)}
    results["aggregate"]=agg
    return results


def analyze_regime_stability(events):
    print("\n[3] Regime Stability Across Periods...")
    periods=[("2016-2018",2016,2018),("2019-2021",2019,2021),
             ("2022-2024",2022,2024),("2025-2026",2025,2026)]
    results={}
    for reg in DISCOVERED_REGIONS:
        pr={}
        for label,y1,y2 in periods:
            sub=[e for e in events if y1<=e["year"]<=y2 and reg["zlo"]<=e["abs_z"]<reg["zhi"] and e["vol_regime"]==reg["vr"]]
            if len(sub)<5: pr[label]={"n":len(sub)}; continue
            f4=[e["fwd4"] for e in sub]; p4=[e["pnl4_c35"] for e in sub]
            pr[label]={"n":len(sub),"fwd4":stats(f4),"pnl4":metrics(p4),"boot":bootstrap_ci(p4),
                       "sign":"+" if np.mean(f4)>0 else "-"}
        pos=sum(1 for p in pr.values() if p.get("fwd4",{}).get("mean",0)>0)
        tot=sum(1 for p in pr.values() if p.get("n",0)>5)
        results[reg["key"]]={
            "periods":pr,
            "pct_positive":round(pos/tot*100,1) if tot>0 else 0,
            "n_periods":tot}
        print(f"    {reg['key']}: {pos}/{tot} periods positive")
    return results


def analyze_cost_adversarial(events):
    print("\n[4] Cost Adversarial (break-even commission)...")
    costs=[0,1,2,3.5,5,7,10,15,20]
    results={}
    for reg in DISCOVERED_REGIONS:
        sub=[e for e in events if reg["zlo"]<=e["abs_z"]<reg["zhi"] and e["vol_regime"]==reg["vr"]]
        if len(sub)<10: continue
        gross=np.mean([e["pnl4_c0"] for e in sub])
        avg_lot=np.mean([e["lot"] for e in sub])
        be=gross/avg_lot if avg_lot>0 else 0
        cs={}
        for c in costs:
            pnls=[e["pnl4_c0"]-e["lot"]*c for e in sub]
            cs[f"c{c}"]=metrics(pnls)
        results[reg["key"]]={"n":len(sub),"break_even":round(be,2),"gross":round(gross,2),"costs":cs}
        print(f"    {reg['key']}: break-even ${be:.2f}/lot")
    return results


def analyze_outlier(events):
    print("\n[5] Outlier Robustness (trimmed winsorized)...")
    results={}
    for reg in DISCOVERED_REGIONS:
        sub=[e for e in events if reg["zlo"]<=e["abs_z"]<reg["zhi"] and e["vol_regime"]==reg["vr"]]
        if len(sub)<20: continue
        arr=np.sort(np.array([e["fwd4"] for e in sub]));n=len(arr)
        variants={"full":(0,1),"trim1%":(int(n*0.01),int(n*0.99)),
                  "trim3%":(int(n*0.03),int(n*0.97)),"trim5%":(int(n*0.05),int(n*0.95)),
                  "trim10%":(int(n*0.10),int(n*0.90)),"trim25%":(int(n*0.25),int(n*0.75))}
        rr={}
        for nm,(lo,hi) in variants.items():
            s=arr[lo:hi] if hi>lo else arr;rr[nm]={"n":len(s),"mean":round(float(np.mean(s)),4),
                                                     "median":round(float(np.median(s)),4)}
        full_m=rr["full"]["mean"];trim5_m=rr["trim5%"]["mean"]
        sr=round(trim5_m/full_m,2) if full_m!=0 else 0
        results[reg["key"]]={**rr,"stability_ratio":sr,"outlier_dependent":abs(1-sr)>0.3}
        print(f"    {reg['key']}: stability={sr:.2f} {'DEPENDENT' if abs(1-sr)>0.3 else 'ROBUST'}")
    return results


def analyze_sample_power(events):
    print("\n[6] Sample Power Analysis...")
    results={}
    for reg in DISCOVERED_REGIONS:
        sub=[e for e in events if reg["zlo"]<=e["abs_z"]<reg["zhi"] and e["vol_regime"]==reg["vr"]]
        if len(sub)<5: continue
        fwd=np.array([e["fwd4"] for e in sub]);n=len(fwd)
        m=float(np.mean(fwd));sd=float(np.std(fwd,ddof=1)) if n>1 else 1.0
        se=sd/np.sqrt(n) if n>0 else 1.0
        d=m/sd if sd>0 else 0
        t_s,p_v=(sp_stats.ttest_1samp(fwd,0)) if n>1 and sd>1e-10 else (0,1.0)
        results[reg["key"]]={"n":n,"mean":round(m,4),"std":round(sd,4),"se":round(se,4),
                              "ci95":[round(m-1.96*se,4),round(m+1.96*se,4)],
                              "cohens_d":round(d,4),"t_stat":round(float(t_s),4),
                              "p_value":round(float(p_v),6),"sig_005":p_v<0.05,
                              "adequate":n>=30}
        print(f"    {reg['key']}: n={n} mean={m:.4f} p={p_v:.4f} {'SIG' if p_v<0.05 else ''}")
    return results


def analyze_permutation(events, n_perm=500):
    print("\n[7] Permutation Tests...")
    np.random.seed(42);results={}
    for ri,reg in enumerate(DISCOVERED_REGIONS):
        sub=[e for e in events if reg["zlo"]<=e["abs_z"]<reg["zhi"] and e["vol_regime"]==reg["vr"]]
        if len(sub)<20: continue
        actual=np.array([e["fwd4"] for e in sub]);n=len(actual);am=float(np.mean(actual))
        perm_means=np.empty(n_perm)
        for bi in range(n_perm):
            np.random.shuffle(actual);perm_means[bi]=np.mean(actual)
        p_val=float(np.mean(np.abs(perm_means)>=np.abs(am)))
        # Vol-shuffle: shuffle which observations get the vol regime label
        vol_all=np.array([e["vol_regime"] for e in sub]);n_target=int(np.sum(vol_all==reg["vr"]))
        actual_copy=np.array([e["fwd4"] for e in sub])
        vol_perm=np.empty(n_perm)
        for bi in range(n_perm):
            idx=np.random.choice(n,n_target,replace=False)
            vol_perm[bi]=float(np.mean(actual_copy[idx]))
        vp=float(np.mean(vol_perm>=am))
        results[reg["key"]]={"n":n,"actual":round(am,4),"perm_p":round(p_val,4),
                             "vol_p":round(vp,4),"perm_sig":p_val<0.05,"vol_sig":vp<0.05}
        print(f"    {reg['key']}: perm_p={p_val:.4f} vol_p={vp:.4f}")
    return results


def analyze_fast_vs_slow(events):
    print("\n[8] Fast vs Slow MR Stability...")
    periods=[("2016-2018",2016,2018),("2019-2021",2019,2021),
             ("2022-2024",2022,2024),("2025-2026",2025,2026)]
    r={}
    for label,y1,y2 in periods:
        sub=[e for e in events if y1<=e["year"]<=y2]
        fast=[e for e in sub if e["outcome"]=="fast_mr"]
        slow=[e for e in sub if e["outcome"]=="slow_mr"]
        r[label]={"fast_n":len(fast),"slow_n":len(slow),
                   "fast_f4":stats([e["fwd4"] for e in fast]) if fast else {"n":0},
                   "slow_f4":stats([e["fwd4"] for e in slow]) if slow else {"n":0}}
        print(f"    {label}: fast={len(fast)} slow={len(slow)}")
    fast=np.array([e["fwd4"] for e in events if e["outcome"]=="fast_mr"])
    slow=np.array([e["fwd4"] for e in events if e["outcome"]=="slow_mr"])
    mw=sp_stats.mannwhitneyu(fast,slow,alternative="greater") if len(fast)>0 and len(slow)>0 else None
    r["overall"]={"fast_n":len(fast),"slow_n":len(slow),
                   "fast_f4":stats(fast.tolist()),"slow_f4":stats(slow.tolist()),
                   "fast_pnl4":metrics([e["pnl4_c35"] for e in events if e["outcome"]=="fast_mr"]),
                   "slow_pnl4":metrics([e["pnl4_c35"] for e in events if e["outcome"]=="slow_mr"]),
                   "mannwhitney_p":round(float(mw.pvalue),6) if mw else 1.0}
    return r


def classify_hypotheses(R):
    """Classify H1-H7 based on validation results."""
    rules=[]
    for reg in DISCOVERED_REGIONS:
        k=reg["key"]
        wf_ok=0;wf_tot=0;wh_ok=0;wh_tot=0;cs_ok=0
        for label,sr in R.get("walk_forward",{}).items():
            r=sr.get("regions",{}).get(k,{})
            if r.get("n",0)>=10:
                wf_tot+=1
                if r.get("fwd4",{}).get("mean",0)>0: wf_ok+=1
        for fi in range(1,6):
            r=R.get("pair_holdout",{}).get(f"fold_{fi}",{}).get("regions",{}).get(k,{})
            if r.get("n",0)>=10:
                wh_tot+=1
                if r.get("fwd4",{}).get("mean",0)>0: wh_ok+=1
        cs=R.get("cost_adversarial",{}).get(k,{})
        be=cs.get("break_even",0)
        pr=R.get("permutation",{}).get(k,{})
        pp=pr.get("perm_p",1.0)
        ok=wf_ok>=3 and wh_ok>=3 and be>3.5 and pp<0.10
        rules.append({"key":k,"wf_pos":f"{wf_ok}/{wf_tot}","wh_pos":f"{wh_ok}/{wh_tot}",
                       "be":be,"perm_p":pp,"support":"SUPPORTED" if ok else "INCONCLUSIVE"})
    return rules


if __name__=="__main__":
    t0=time.time()
    print("="*80);print("  PHASE 7 — ADVERSARIAL OUT-OF-SAMPLE VALIDATION");print("="*80)
    print("\n[0] Loading data...");pdata=load_all("2016-01-01","2026-07-19")
    print(f"    {len(pdata)} pairs loaded")
    print("\n[*] Pre-extracting ALL events (single pass)...")
    ref_pair=max(pdata.keys(),key=lambda p:pdata[p]["n"])
    ref=pdata[ref_pair];n=ref["n"]
    raw_events=[]
    for i in range(LOOKBACK+ATR_PERIOD+10,n-1):
        ts=ref["ts"][i]
        if not in_session(ts): continue
        for pair in PAIRS:
            pd_=pdata.get(pair)
            if pd_ is None or i>=pd_["n"]: continue
            z_now=pd_["z"][i]
            if np.isnan(z_now) or abs(z_now)<Z_ENTRY: continue
            atr_now=pd_["atr"][i]
            if np.isnan(atr_now) or atr_now<=0: continue
            direction=1 if z_now<0 else -1
            ep=pd_["c"][i]+SLIPPAGE_PIPS*pd_["pip"] if direction==1 else pd_["c"][i]-SLIPPAGE_PIPS*pd_["pip"]
            sl_dist=atr_now*ATR_SL_MULT
            sl_p=pd_["c"][i]-sl_dist if direction==1 else pd_["c"][i]+sl_dist
            sl_pips=sl_dist/pd_["pip"]
            if sl_pips<=0: continue
            lot=max(0.01,min(10.0,round(1.0/sl_pips,2)))
            vr=classify_vol(pd_["atr_pct"],i)
            if vr=="unknown": continue
            z_arr=pd_["z"]
            z4=z_arr[min(4+i,len(z_arr)-1)] if len(z_arr)>4 else z_now
            z16=z_arr[min(16+i,len(z_arr)-1)] if len(z_arr)>16 else z_now
            if direction==1: fast_mr=z4>z_now*0.5; slow_mr=z16>z_now*0.3 and not fast_mr
            else: fast_mr=z4<z_now*0.5; slow_mr=z16<z_now*0.3 and not fast_mr
            outcome="fast_mr" if fast_mr else ("slow_mr" if slow_mr else "other")
            path_n=min(MAX_HOLD,pd_["n"]-i)
            raw_events.append({"pair":pair,"direction":direction,"entry_price":ep,
                               "entry_z":z_now,"abs_z":abs(z_now),"sl_price":sl_p,
                               "lot":lot,"pip":pd_["pip"],"pv":pd_["pv"],
                               "vol_regime":vr,"year":ts.year,
                               "price_path":[float(pd_["c"][i+j]) for j in range(path_n)],
                               "z_path":[float(z_arr[i+j]) if not np.isnan(z_arr[i+j]) else 0.0 for j in range(path_n)],
                               "high_path":[float(pd_["h"][i+j]) for j in range(path_n)],
                               "low_path":[float(pd_["lo"][i+j]) for j in range(path_n)],
                               "outcome":outcome})
    print(f"    {len(raw_events)} events extracted")
    print("\n[*] Precomputing metrics (fwd4, pnl4, mae4)...")
    events=precompute_metrics(raw_events)
    R={}
    R["walk_forward"]=analyze_walk_forward(events)
    R["pair_holdout"]=analyze_pair_holdout(events)
    R["regime_stability"]=analyze_regime_stability(events)
    R["cost_adversarial"]=analyze_cost_adversarial(events)
    R["outlier_robustness"]=analyze_outlier(events)
    R["sample_power"]=analyze_sample_power(events)
    R["permutation"]=analyze_permutation(events)
    R["fast_vs_slow"]=analyze_fast_vs_slow(events)
    R["hypothesis_classification"]=classify_hypotheses(R)
    with open(OUT/"phase7_validation.json","w") as f: json.dump(R,f,indent=2,default=str)
    print(f"\n  Saved {OUT/'phase7_validation.json'}")
    print(f"\n[DONE] {time.time()-t0:.1f}s")
