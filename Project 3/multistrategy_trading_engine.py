"""
Multi-strategy Optibook engine v4.

Diagnosed problems with v3 from live logs:
  (a) PnL volatility was mostly mark-to-market noise on large pinned
      positions (OB5X complex 100/95 lots), NOT realised drawdown.
  (b) OB5X calendar arb generated phantom "edges" 0.3-0.7 repeatedly
      at the same prices -> the relationship F2 = F1*exp(r*dt) doesn't
      hold for OB5X futures here (they're driven by the index, not each
      other). Net effect: inventory accumulation, no real edge.
  (c) ASML futures/stock all pinned at +-95. Basis arb keeps oscillating
      against the cap, paying spread on every flip, no net edge.
  (d) PHEDGE firing on every status print as option deltas swing.

Fixes in v4:
  1. ENABLE_OB5X_CAL = False (we keep ETF basis, which has a verified model).
  2. Position hysteresis: when |pos| > 80 on an instrument, the strategies
     only execute trades that REDUCE that position. Prevents pin-and-churn.
  3. PnL marked with theoretical valuations (BS for options, basis-adjusted
     for futures, ETF mid for index futures) -> log PnL no longer whips.
  4. PHEDGE has a small dead-band around max_delta and only fires once
     per N seconds to avoid spread-bleed.
  5. Reduced FBASIS lot cap from 12 -> 8 (12 was being used as 1-3 anyway
     because liquidity binds; smaller cap reduces over-shooting in chop).
"""

import datetime as dt
import math
import time
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional

from optibook.synchronous_client import Exchange
from optibook.common_types import InstrumentType


# ============================================================================
# CONFIG
# ============================================================================

LOOP_SLEEP_SEC = 0.20
MAX_WRITES_PER_SEC = 22
STATUS_INTERVAL_SEC = 5.0

ENABLE_BOX = True
ENABLE_VERTICAL = True
ENABLE_PCP = True
ENABLE_CALENDAR_ASML = True
ENABLE_CALENDAR_OB5X = False             # OFF - model doesn't fit, was bleeding
ENABLE_STOCK_FUTURE_BASIS = True
ENABLE_ETF_BASIS = True
ENABLE_DUAL_ARB = True
ENABLE_OPTION_MM = True
FLATTEN_OB5X_ON_STARTUP = True
FLATTEN_ASML_FUTURES_ON_STARTUP = True    # reset pinned futures too

MAX_PORTFOLIO_DELTA = 50
HEDGE_DEAD_BAND = 15                      # don't hedge inside [-50-15, 50+15]
HEDGE_COOLDOWN_SEC = 2.0
PER_INSTRUMENT_HARD_CAP = 95
HYSTERESIS_BAND = 80                      # if |pos|>this, only reduce


# ============================================================================
# BLACK-SCHOLES
# ============================================================================

SQRT_2PI = math.sqrt(2.0 * math.pi)
def _ncdf(x): return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
def _npdf(x): return math.exp(-0.5*x*x) / SQRT_2PI
def _d12(S,K,tau,r,sig):
    if S<=0 or K<=0 or tau<=0 or sig<=0: return None,None
    d1=(math.log(S/K)+(r+0.5*sig*sig)*tau)/(sig*math.sqrt(tau))
    return d1, d1-sig*math.sqrt(tau)
def bs_call(S,K,tau,r,sig):
    if tau<=0: return max(S-K,0.0)
    d1,d2=_d12(S,K,tau,r,sig)
    if d1 is None: return max(S-K*math.exp(-r*tau),0.0)
    return S*_ncdf(d1)-K*math.exp(-r*tau)*_ncdf(d2)
def bs_put(S,K,tau,r,sig):
    if tau<=0: return max(K-S,0.0)
    d1,d2=_d12(S,K,tau,r,sig)
    if d1 is None: return max(K*math.exp(-r*tau)-S,0.0)
    return K*math.exp(-r*tau)*_ncdf(-d2)-S*_ncdf(-d1)
def bs_delta(kind,S,K,tau,r,sig):
    if tau<=0: return (1.0 if S>K else 0.0) if kind=="C" else (-1.0 if S<K else 0.0)
    d1,_=_d12(S,K,tau,r,sig)
    if d1 is None: return 0.0
    return _ncdf(d1) if kind=="C" else _ncdf(d1)-1.0
def bs_vega(S,K,tau,r,sig):
    if tau<=0 or sig<=0: return 0.0
    d1,_=_d12(S,K,tau,r,sig)
    if d1 is None: return 0.0
    return S*_npdf(d1)*math.sqrt(tau)
def implied_vol(kind, price, S, K, tau, r, lo=1e-4, hi=5.0, tol=1e-4, max_iter=50):
    if tau<=0 or price<=0 or S<=0: return None
    intrinsic=max(S-K,0.0) if kind=="C" else max(K-S,0.0)
    if price<intrinsic-1e-6: return None
    f = bs_call if kind=="C" else bs_put
    p_lo,p_hi=f(S,K,tau,r,lo), f(S,K,tau,r,hi)
    if (price-p_lo)*(price-p_hi)>0: return None
    for _ in range(max_iter):
        mid=0.5*(lo+hi); p_mid=f(S,K,tau,r,mid)
        if abs(p_mid-price)<tol: return mid
        if (p_mid-price)*(p_lo-price)<0: hi,p_hi=mid,p_mid
        else: lo,p_lo=mid,p_mid
    return 0.5*(lo+hi)

def years_to(expiry):
    now=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return max((expiry-now).total_seconds()/(365.0*24*3600), 0.0)


# ============================================================================
# HELPERS
# ============================================================================

def best_bid_ask(book):
    if not book or not book.bids or not book.asks: return None,None,None,None
    return book.bids[0].price, book.asks[0].price, book.bids[0].volume, book.asks[0].volume
def mid_of(book):
    bb,ba,*_=best_bid_ask(book)
    return None if bb is None or ba is None else 0.5*(bb+ba)
def round_to_tick(p,t): return round(p/t)*t
def size_by_edge(edge, thr, max_lots):
    if thr<=0: return max_lots
    return max(1, min(max_lots, int(edge/thr)))


# ============================================================================
# WRITE BUDGET
# ============================================================================

class WriteBudget:
    def __init__(self, lim):
        self.limit=lim; self.stamps=deque()
    def try_spend(self,n=1):
        now=time.time()
        while self.stamps and self.stamps[0]<now-1.0: self.stamps.popleft()
        if len(self.stamps)+n > self.limit: return False
        for _ in range(n): self.stamps.append(now)
        return True
    def available(self):
        now=time.time()
        while self.stamps and self.stamps[0]<now-1.0: self.stamps.popleft()
        return self.limit-len(self.stamps)


# ============================================================================
# TRADER
# ============================================================================

class Trader:
    def __init__(self, e, b): self.e=e; self.b=b
    def positions(self):  return self.e.get_positions()
    def book(self,iid):   return self.e.get_last_price_book(iid)
    def outstanding(self,iid):
        try: return self.e.get_outstanding_orders(iid)
        except Exception: return {}
    def pnl(self, valuations=None):
        try:
            if valuations: return self.e.get_pnl(valuations)
            return self.e.get_pnl()
        except Exception: return float("nan")
    def ioc(self,iid,*,price,volume,side):
        if volume<=0 or not self.b.try_spend(): return False
        try:
            r=self.e.insert_order(iid,price=price,volume=volume,side=side,order_type="ioc")
            return bool(r and r.success)
        except Exception as ex:
            print(f"[ORD] ioc FAIL {iid}: {ex}"); return False
    def limit(self,iid,*,price,volume,side):
        if volume<=0 or not self.b.try_spend(): return None
        try:
            r=self.e.insert_order(iid,price=price,volume=volume,side=side,order_type="limit")
            return r.order_id if r and r.success else None
        except Exception as ex:
            print(f"[ORD] limit FAIL {iid}: {ex}"); return None
    def cancel(self,iid,oid):
        if not self.b.try_spend(): return False
        try: self.e.delete_order(iid,order_id=oid); return True
        except Exception: return False
    def cancel_all(self,iid):
        if not self.b.try_spend(): return False
        try: self.e.delete_orders(iid); return True
        except Exception: return False


# ============================================================================
# MARKET STATE
# ============================================================================

@dataclass
class MarketState:
    instruments: dict
    books: dict = field(default_factory=dict)
    positions: dict = field(default_factory=dict)
    iv_cache: dict = field(default_factory=dict)
    def refresh(self, trader, iids):
        self.positions = trader.positions()
        for iid in iids: self.books[iid] = trader.book(iid)
    def pos(self,iid): return self.positions.get(iid,0)


# ============================================================================
# POSITION HYSTERESIS
# ============================================================================
# Returns "allowed direction" for a given instrument:
#   +1 means only buys allowed (we're heavily short, only reduce)
#   -1 means only sells allowed (we're heavily long, only reduce)
#    0 means both sides allowed
def hyst_dir(state, iid):
    p = state.pos(iid)
    if p > HYSTERESIS_BAND: return -1
    if p < -HYSTERESIS_BAND: return +1
    return 0


# ============================================================================
# BOX SPREAD
# ============================================================================

class BoxArb:
    def __init__(self, underlying, strike_groups, min_edge=0.30, max_lots=3):
        self.und=underlying; self.groups=strike_groups
        self.boxes=self._make_boxes(); self.min_edge=min_edge; self.max_lots=max_lots
    def _make_boxes(self):
        Ks=sorted(self.groups.keys()); out=[]
        for i,K_lo in enumerate(Ks):
            for K_hi in Ks[i+1:]:
                gl, gh = self.groups[K_lo], self.groups[K_hi]
                if "C" in gl and "P" in gl and "C" in gh and "P" in gh:
                    out.append((K_lo, K_hi, gl["C"], gl["P"], gh["C"], gh["P"]))
        return out
    def step(self, state, trader):
        for (K_lo, K_hi, c_lo, p_lo, c_hi, p_hi) in self.boxes:
            t = [best_bid_ask(state.books.get(x)) for x in (c_lo,p_lo,c_hi,p_hi)]
            if any(x[0] is None for x in t): continue
            (clb,cla,clbv,clav)=t[0]; (plb,pla,plbv,plav)=t[1]
            (chb,cha,chbv,chav)=t[2]; (phb,pha,phbv,phav)=t[3]
            inst=state.instruments[c_lo]; tau=years_to(inst.expiry); r=inst.interest_rate
            fair=(K_hi-K_lo)*math.exp(-r*tau)

            # Long box: buy c_lo, sell p_lo, sell c_hi, buy p_hi
            cost_long = cla - plb + pha - chb
            edgeL = fair - cost_long
            if edgeL > self.min_edge:
                # required directions: +c_lo, -p_lo, -c_hi, +p_hi
                if not all(hyst_dir(state, x)*sgn >= 0 for x,sgn in
                           [(c_lo,+1),(p_lo,-1),(c_hi,-1),(p_hi,+1)]): continue
                v=min(size_by_edge(edgeL,self.min_edge,self.max_lots),
                      clav,plbv,phav,chbv,
                      PER_INSTRUMENT_HARD_CAP - state.pos(c_lo),
                      PER_INSTRUMENT_HARD_CAP + state.pos(p_lo),
                      PER_INSTRUMENT_HARD_CAP + state.pos(c_hi),
                      PER_INSTRUMENT_HARD_CAP - state.pos(p_hi))
                if v>0 and trader.b.available()>=4:
                    if (trader.ioc(c_lo,price=cla,volume=v,side="bid") and
                        trader.ioc(p_lo,price=plb,volume=v,side="ask")):
                        trader.ioc(p_hi,price=pha,volume=v,side="bid")
                        trader.ioc(c_hi,price=chb,volume=v,side="ask")
                        print(f"[BOX-L] K={K_lo}/{K_hi} v={v} edge={edgeL:.3f}")

            # Short box
            proceeds_short = clb - pla - cha + phb
            edgeS = proceeds_short - fair
            if edgeS > self.min_edge:
                if not all(hyst_dir(state, x)*sgn >= 0 for x,sgn in
                           [(c_lo,-1),(p_lo,+1),(c_hi,+1),(p_hi,-1)]): continue
                v=min(size_by_edge(edgeS,self.min_edge,self.max_lots),
                      clbv,plav,chav,phbv,
                      PER_INSTRUMENT_HARD_CAP + state.pos(c_lo),
                      PER_INSTRUMENT_HARD_CAP - state.pos(p_lo),
                      PER_INSTRUMENT_HARD_CAP - state.pos(c_hi),
                      PER_INSTRUMENT_HARD_CAP + state.pos(p_hi))
                if v>0 and trader.b.available()>=4:
                    if (trader.ioc(c_lo,price=clb,volume=v,side="ask") and
                        trader.ioc(p_lo,price=pla,volume=v,side="bid")):
                        trader.ioc(c_hi,price=cha,volume=v,side="bid")
                        trader.ioc(p_hi,price=phb,volume=v,side="ask")
                        print(f"[BOX-S] K={K_lo}/{K_hi} v={v} edge={edgeS:.3f}")


# ============================================================================
# VERTICAL SPREAD
# ============================================================================

class VerticalArb:
    def __init__(self, underlying, strike_groups, min_edge=0.15, max_lots=3):
        self.und=underlying; self.groups=strike_groups
        self.pairs=[]
        Ks=sorted(strike_groups.keys())
        for i,kl in enumerate(Ks):
            for kh in Ks[i+1:]:
                self.pairs.append((kl,kh))
        self.min_edge=min_edge; self.max_lots=max_lots
    def step(self, state, trader):
        for (K_lo,K_hi) in self.pairs:
            gl,gh=self.groups[K_lo], self.groups[K_hi]
            r=state.instruments[gl["C"]].interest_rate
            tau=years_to(state.instruments[gl["C"]].expiry)
            cap=(K_hi-K_lo)*math.exp(-r*tau)

            # Call spread
            clb,cla,clbv,clav=best_bid_ask(state.books.get(gl["C"]))
            chb,cha,chbv,chav=best_bid_ask(state.books.get(gh["C"]))
            if clb is not None and chb is not None:
                # Long lo, short hi: pay cla - chb; arb if negative spread
                edgeA = -(cla - chb)
                if edgeA > self.min_edge:
                    if hyst_dir(state, gl["C"]) >= 0 and hyst_dir(state, gh["C"]) <= 0:
                        v=min(size_by_edge(edgeA,self.min_edge,self.max_lots),clav,chbv,
                              PER_INSTRUMENT_HARD_CAP - state.pos(gl["C"]),
                              PER_INSTRUMENT_HARD_CAP + state.pos(gh["C"]))
                        if v>0 and trader.b.available()>=2:
                            if trader.ioc(gl["C"],price=cla,volume=v,side="bid"):
                                trader.ioc(gh["C"],price=chb,volume=v,side="ask")
                                print(f"[VERT-CL] K={K_lo}/{K_hi} v={v} edge={edgeA:.3f}")
                edgeB = (clb - cha) - cap
                if edgeB > self.min_edge:
                    if hyst_dir(state, gl["C"]) <= 0 and hyst_dir(state, gh["C"]) >= 0:
                        v=min(size_by_edge(edgeB,self.min_edge,self.max_lots),clbv,chav,
                              PER_INSTRUMENT_HARD_CAP + state.pos(gl["C"]),
                              PER_INSTRUMENT_HARD_CAP - state.pos(gh["C"]))
                        if v>0 and trader.b.available()>=2:
                            if trader.ioc(gl["C"],price=clb,volume=v,side="ask"):
                                trader.ioc(gh["C"],price=cha,volume=v,side="bid")
                                print(f"[VERT-CS] K={K_lo}/{K_hi} v={v} edge={edgeB:.3f}")
            # Put spread
            plb,pla,plbv,plav=best_bid_ask(state.books.get(gl["P"]))
            phb,pha,phbv,phav=best_bid_ask(state.books.get(gh["P"]))
            if plb is not None and phb is not None:
                edgeA = -(pha - plb)
                if edgeA > self.min_edge:
                    if hyst_dir(state, gh["P"]) >= 0 and hyst_dir(state, gl["P"]) <= 0:
                        v=min(size_by_edge(edgeA,self.min_edge,self.max_lots),phav,plbv,
                              PER_INSTRUMENT_HARD_CAP - state.pos(gh["P"]),
                              PER_INSTRUMENT_HARD_CAP + state.pos(gl["P"]))
                        if v>0 and trader.b.available()>=2:
                            if trader.ioc(gh["P"],price=pha,volume=v,side="bid"):
                                trader.ioc(gl["P"],price=plb,volume=v,side="ask")
                                print(f"[VERT-PL] K={K_lo}/{K_hi} v={v} edge={edgeA:.3f}")
                edgeB = (phb - pla) - cap
                if edgeB > self.min_edge:
                    if hyst_dir(state, gh["P"]) <= 0 and hyst_dir(state, gl["P"]) >= 0:
                        v=min(size_by_edge(edgeB,self.min_edge,self.max_lots),phbv,plav,
                              PER_INSTRUMENT_HARD_CAP + state.pos(gh["P"]),
                              PER_INSTRUMENT_HARD_CAP - state.pos(gl["P"]))
                        if v>0 and trader.b.available()>=2:
                            if trader.ioc(gh["P"],price=phb,volume=v,side="ask"):
                                trader.ioc(gl["P"],price=pla,volume=v,side="bid")
                                print(f"[VERT-PS] K={K_lo}/{K_hi} v={v} edge={edgeB:.3f}")


# ============================================================================
# PCP
# ============================================================================

class PCPArb:
    def __init__(self,und,groups,min_edge=0.25,max_lots=4):
        self.und=und; self.groups=groups; self.min_edge=min_edge; self.max_lots=max_lots
    def step(self,state,trader):
        sb,sa,sbv,sav=best_bid_ask(state.books.get(self.und))
        if sb is None: return
        for cid,pid,K in self.groups:
            cb,ca,cbv,cav=best_bid_ask(state.books.get(cid))
            pb,pa,pbv,pav=best_bid_ask(state.books.get(pid))
            if cb is None or pb is None: continue
            inst=state.instruments[cid]
            tau=years_to(inst.expiry); r=inst.interest_rate
            disc_K=K*math.exp(-r*tau)
            edgeA=(sb+pb-ca)-disc_K
            if edgeA > self.min_edge:
                if hyst_dir(state,cid)>=0 and hyst_dir(state,pid)<=0 and hyst_dir(state,self.und)<=0:
                    v=min(size_by_edge(edgeA,self.min_edge,self.max_lots),
                          cav,pbv,sbv,
                          PER_INSTRUMENT_HARD_CAP-state.pos(cid),
                          PER_INSTRUMENT_HARD_CAP+state.pos(pid),
                          PER_INSTRUMENT_HARD_CAP+state.pos(self.und))
                    if v>0 and trader.b.available()>=3:
                        if trader.ioc(cid,price=ca,volume=v,side="bid"):
                            trader.ioc(pid,price=pb,volume=v,side="ask")
                            trader.ioc(self.und,price=sb,volume=v,side="ask")
                            print(f"[PCP-A] K={K} v={v} edge={edgeA:.3f}")
            edgeB=disc_K-(sa+pa-cb)
            if edgeB > self.min_edge:
                if hyst_dir(state,cid)<=0 and hyst_dir(state,pid)>=0 and hyst_dir(state,self.und)>=0:
                    v=min(size_by_edge(edgeB,self.min_edge,self.max_lots),
                          cbv,pav,sav,
                          PER_INSTRUMENT_HARD_CAP+state.pos(cid),
                          PER_INSTRUMENT_HARD_CAP-state.pos(pid),
                          PER_INSTRUMENT_HARD_CAP-state.pos(self.und))
                    if v>0 and trader.b.available()>=3:
                        if trader.ioc(cid,price=cb,volume=v,side="ask"):
                            trader.ioc(pid,price=pa,volume=v,side="bid")
                            trader.ioc(self.und,price=sa,volume=v,side="bid")
                            print(f"[PCP-B] K={K} v={v} edge={edgeB:.3f}")


# ============================================================================
# CALENDAR ARB (ASML only by default)
# ============================================================================

class CalendarArb:
    def __init__(self, futs_sorted, label, min_edge=0.30, max_lots=6):
        self.futs=futs_sorted
        self.pairs=[(futs_sorted[i],futs_sorted[j])
                    for i in range(len(futs_sorted))
                    for j in range(i+1,len(futs_sorted))]
        self.label=label; self.min_edge=min_edge; self.max_lots=max_lots
    def step(self,state,trader):
        for f1,f2 in self.pairs:
            f1b,f1a,f1bv,f1av=best_bid_ask(state.books.get(f1))
            f2b,f2a,f2bv,f2av=best_bid_ask(state.books.get(f2))
            if f1b is None or f2b is None: continue
            i1,i2=state.instruments[f1],state.instruments[f2]
            tau1,tau2=years_to(i1.expiry),years_to(i2.expiry)
            if tau2<=tau1: continue
            r=i1.interest_rate
            mid1=0.5*(f1b+f1a)
            f2_theo=mid1*math.exp(r*(tau2-tau1))

            edgeA=f2b-f2_theo
            if edgeA>self.min_edge:
                if hyst_dir(state,f2)<=0 and hyst_dir(state,f1)>=0:
                    v=min(size_by_edge(edgeA,self.min_edge,self.max_lots),
                          f2bv,f1av,
                          PER_INSTRUMENT_HARD_CAP+state.pos(f2),
                          PER_INSTRUMENT_HARD_CAP-state.pos(f1))
                    if v>0 and trader.b.available()>=2:
                        if trader.ioc(f2,price=f2b,volume=v,side="ask"):
                            trader.ioc(f1,price=f1a,volume=v,side="bid")
                            print(f"[CAL-{self.label}-A] {f1}/{f2} v={v} edge={edgeA:.3f}")
            edgeB=f2_theo-f2a
            if edgeB>self.min_edge:
                if hyst_dir(state,f2)>=0 and hyst_dir(state,f1)<=0:
                    v=min(size_by_edge(edgeB,self.min_edge,self.max_lots),
                          f2av,f1bv,
                          PER_INSTRUMENT_HARD_CAP-state.pos(f2),
                          PER_INSTRUMENT_HARD_CAP+state.pos(f1))
                    if v>0 and trader.b.available()>=2:
                        if trader.ioc(f2,price=f2a,volume=v,side="bid"):
                            trader.ioc(f1,price=f1b,volume=v,side="ask")
                            print(f"[CAL-{self.label}-B] {f1}/{f2} v={v} edge={edgeB:.3f}")


# ============================================================================
# STOCK-FUTURE BASIS  (with hysteresis)
# ============================================================================

class FutureBasis:
    def __init__(self,und,futs,min_edge=0.20,max_lots=8):
        self.und=und; self.futs=futs; self.min_edge=min_edge; self.max_lots=max_lots
    def step(self,state,trader):
        sb,sa,sbv,sav=best_bid_ask(state.books.get(self.und))
        if sb is None: return
        mid=0.5*(sb+sa)
        for fid in self.futs:
            fb,fa,fbv,fav=best_bid_ask(state.books.get(fid))
            if fb is None: continue
            inst=state.instruments[fid]
            tau=years_to(inst.expiry); r=inst.interest_rate
            F_theo=mid*math.exp(r*tau)

            # A: future rich -> sell F, buy S
            ea=fb-F_theo
            if ea>self.min_edge and hyst_dir(state,fid)<=0 and hyst_dir(state,self.und)>=0:
                v=min(size_by_edge(ea,self.min_edge,self.max_lots),
                      fbv,sav,
                      PER_INSTRUMENT_HARD_CAP+state.pos(fid),
                      PER_INSTRUMENT_HARD_CAP-state.pos(self.und))
                if v>0 and trader.b.available()>=2:
                    if trader.ioc(fid,price=fb,volume=v,side="ask"):
                        trader.ioc(self.und,price=sa,volume=v,side="bid")
                        print(f"[FBASIS-A] {fid} v={v} edge={ea:.3f}")
            # B: future cheap -> buy F, sell S
            eb=F_theo-fa
            if eb>self.min_edge and hyst_dir(state,fid)>=0 and hyst_dir(state,self.und)<=0:
                v=min(size_by_edge(eb,self.min_edge,self.max_lots),
                      fav,sbv,
                      PER_INSTRUMENT_HARD_CAP-state.pos(fid),
                      PER_INSTRUMENT_HARD_CAP+state.pos(self.und))
                if v>0 and trader.b.available()>=2:
                    if trader.ioc(fid,price=fa,volume=v,side="bid"):
                        trader.ioc(self.und,price=sb,volume=v,side="ask")
                        print(f"[FBASIS-B] {fid} v={v} edge={eb:.3f}")


# ============================================================================
# ETF BASIS
# ============================================================================

class ETFFutureBasis:
    def __init__(self,etf,futs,insts,min_edge=0.40,max_lots=3):
        self.etf=etf; self.futs=futs; self.min_edge=min_edge; self.max_lots=max_lots
        e_inst=insts[etf]
        self.mult=float(getattr(e_inst,"etf_multiplier",None) or getattr(e_inst,"multiplier",1.0) or 1.0)
        self.cash=float(getattr(e_inst,"etf_cash_comp",None) or getattr(e_inst,"cash_comp",0.0) or 0.0)
        print(f"[EBASIS] {etf}: multiplier={self.mult} cash={self.cash}")
    def step(self,state,trader):
        eb,ea,ebv,eav=best_bid_ask(state.books.get(self.etf))
        if eb is None: return
        mid_E=0.5*(eb+ea)
        idx=mid_E*self.mult+self.cash
        per_f=max(1,int(round(self.mult)))
        for fid in self.futs:
            fb,fa,fbv,fav=best_bid_ask(state.books.get(fid))
            if fb is None: continue
            inst=state.instruments[fid]
            tau=years_to(inst.expiry); r=inst.interest_rate
            F_theo=idx*math.exp(r*tau)

            edgeA=fb-F_theo
            if edgeA>self.min_edge and hyst_dir(state,fid)<=0 and hyst_dir(state,self.etf)>=0:
                v=min(size_by_edge(edgeA,self.min_edge,self.max_lots),
                      fbv, eav//per_f,
                      PER_INSTRUMENT_HARD_CAP+state.pos(fid),
                      (PER_INSTRUMENT_HARD_CAP-state.pos(self.etf))//per_f)
                if v>0 and trader.b.available()>=2:
                    if trader.ioc(fid,price=fb,volume=v,side="ask"):
                        trader.ioc(self.etf,price=ea,volume=v*per_f,side="bid")
                        print(f"[EBASIS-A] {fid} v={v} edge={edgeA:.3f}")
            edgeB=F_theo-fa
            if edgeB>self.min_edge and hyst_dir(state,fid)>=0 and hyst_dir(state,self.etf)<=0:
                v=min(size_by_edge(edgeB,self.min_edge,self.max_lots),
                      fav, ebv//per_f,
                      PER_INSTRUMENT_HARD_CAP-state.pos(fid),
                      (PER_INSTRUMENT_HARD_CAP+state.pos(self.etf))//per_f)
                if v>0 and trader.b.available()>=2:
                    if trader.ioc(fid,price=fa,volume=v,side="bid"):
                        trader.ioc(self.etf,price=eb,volume=v*per_f,side="ask")
                        print(f"[EBASIS-B] {fid} v={v} edge={edgeB:.3f}")


# ============================================================================
# DUAL ARB
# ============================================================================

@dataclass
class DualPair:
    leading:str; dual:str; tick:float
    min_edge_ticks:float=2.0; max_lots:int=10

class DualActiveArb:
    def __init__(self,pairs): self.pairs=pairs
    def step(self,state,trader):
        for p in self.pairs:
            lb,la,lbv,lav=best_bid_ask(state.books.get(p.leading))
            db,da,dbv,dav=best_bid_ask(state.books.get(p.dual))
            if None in (lb,la,db,da): continue
            thr=p.min_edge_ticks*p.tick
            ea=lb-da
            if ea>=thr and hyst_dir(state,p.dual)>=0 and hyst_dir(state,p.leading)<=0:
                v=min(size_by_edge(ea,thr,p.max_lots),dav,lbv,
                      PER_INSTRUMENT_HARD_CAP-state.pos(p.dual),
                      PER_INSTRUMENT_HARD_CAP+state.pos(p.leading))
                if v>0 and trader.b.available()>=2:
                    if trader.ioc(p.dual,price=da,volume=v,side="bid"):
                        trader.ioc(p.leading,price=lb,volume=v,side="ask")
                        print(f"[DUAL-A] +{v} {p.dual} -{v} {p.leading} edge={ea:.2f}")
            eb=db-la
            if eb>=thr and hyst_dir(state,p.dual)<=0 and hyst_dir(state,p.leading)>=0:
                v=min(size_by_edge(eb,thr,p.max_lots),dbv,lav,
                      PER_INSTRUMENT_HARD_CAP+state.pos(p.dual),
                      PER_INSTRUMENT_HARD_CAP-state.pos(p.leading))
                if v>0 and trader.b.available()>=2:
                    if trader.ioc(p.dual,price=db,volume=v,side="ask"):
                        trader.ioc(p.leading,price=la,volume=v,side="bid")
                        print(f"[DUAL-B] -{v} {p.dual} +{v} {p.leading} edge={eb:.2f}")


# ============================================================================
# OPTION MM
# ============================================================================

@dataclass
class OptionQuoteState:
    bid_id:Optional[int]=None; bid_price:Optional[float]=None
    ask_id:Optional[int]=None; ask_price:Optional[float]=None

class OptionMM:
    def __init__(self, iids, default_iv=0.30, base_width_ticks=3.0,
                 vega_width_factor=0.05, inv_skew=0.10, lot=3, per_cap=20):
        self.iids=iids; self.default_iv=default_iv
        self.base_width=base_width_ticks; self.vega_factor=vega_width_factor
        self.inv_skew=inv_skew; self.lot=lot; self.per_cap=per_cap
        self.q={iid:OptionQuoteState() for iid in iids}
    def step(self,state,trader):
        for iid in self.iids:
            live=trader.outstanding(iid); qs=self.q[iid]
            if qs.bid_id is not None and qs.bid_id not in live: qs.bid_id=qs.bid_price=None
            if qs.ask_id is not None and qs.ask_id not in live: qs.ask_id=qs.ask_price=None
        for iid in self.iids:
            inst=state.instruments[iid]; base=inst.base_instrument_id
            S=mid_of(state.books.get(base))
            if S is None: continue
            K=inst.strike; tau=years_to(inst.expiry); r=inst.interest_rate
            kind="C" if iid.endswith("C") else "P"; tick=inst.tick_size
            mkt_mid=mid_of(state.books.get(iid))
            sig=state.iv_cache.get(iid,self.default_iv)
            if mkt_mid is not None and mkt_mid>0:
                iv=implied_vol(kind,mkt_mid,S,K,tau,r)
                if iv is not None: sig=iv; state.iv_cache[iid]=iv
            theo = bs_call(S,K,tau,r,sig) if kind=="C" else bs_put(S,K,tau,r,sig)
            vega=bs_vega(S,K,tau,r,sig)
            half_w=(self.base_width+self.vega_factor*vega)*tick
            pos=state.pos(iid); skew=-pos*self.inv_skew*tick
            tb=round_to_tick(theo+skew-half_w,tick); ta=round_to_tick(theo+skew+half_w,tick)
            if ta<=tb: ta=tb+tick
            mb,ma,*_=best_bid_ask(state.books.get(iid))
            if mb is not None and (ta<mb-5*tick or tb>ma+5*tick): continue
            qs=self.q[iid]
            if qs.ask_price is not None and tb>=qs.ask_price and qs.ask_id is not None:
                trader.cancel(iid,qs.ask_id); qs.ask_id=qs.ask_price=None
            if qs.bid_price is not None and ta<=qs.bid_price and qs.bid_id is not None:
                trader.cancel(iid,qs.bid_id); qs.bid_id=qs.bid_price=None
            if pos+self.lot<=self.per_cap:
                if qs.bid_price!=tb and trader.b.available()>=2:
                    if qs.bid_id is not None: trader.cancel(iid,qs.bid_id); qs.bid_id=qs.bid_price=None
                    oid=trader.limit(iid,price=tb,volume=self.lot,side="bid")
                    if oid is not None: qs.bid_id, qs.bid_price=oid,tb
            elif qs.bid_id is not None:
                trader.cancel(iid,qs.bid_id); qs.bid_id=qs.bid_price=None
            if pos-self.lot>=-self.per_cap:
                if qs.ask_price!=ta and trader.b.available()>=2:
                    if qs.ask_id is not None: trader.cancel(iid,qs.ask_id); qs.ask_id=qs.ask_price=None
                    oid=trader.limit(iid,price=ta,volume=self.lot,side="ask")
                    if oid is not None: qs.ask_id, qs.ask_price=oid,ta
            elif qs.ask_id is not None:
                trader.cancel(iid,qs.ask_id); qs.ask_id=qs.ask_price=None


# ============================================================================
# DELTA / SMART HEDGE (with dead-band and cooldown)
# ============================================================================

def _opt_delta(iid,state):
    inst=state.instruments[iid]; base=inst.base_instrument_id
    if base is None: return None
    S=mid_of(state.books.get(base))
    if S is None: return None
    sig=state.iv_cache.get(iid,0.30); kind="C" if iid.endswith("C") else "P"
    return bs_delta(kind,S,inst.strike,years_to(inst.expiry),inst.interest_rate,sig)

def underlying_delta(state,underlying):
    d=0.0
    for iid,p in state.positions.items():
        if p==0: continue
        inst=state.instruments.get(iid)
        if inst is None: continue
        t=inst.instrument_type
        if iid==underlying:
            d+=p
        elif t==InstrumentType.STOCK_FUTURE and inst.base_instrument_id==underlying:
            d+=p
        elif t==InstrumentType.STOCK_OPTION and inst.base_instrument_id==underlying:
            od=_opt_delta(iid,state)
            if od is not None: d+=p*od
    return d

class SmartHedger:
    def __init__(self): self.last_fire = 0.0
    def step(self, state, trader, underlying, front_future, max_delta):
        if time.time() - self.last_fire < HEDGE_COOLDOWN_SEC: return
        d = underlying_delta(state, underlying)
        if abs(d) <= max_delta + HEDGE_DEAD_BAND: return
        excess = d - math.copysign(max_delta, d)
        v = int(round(abs(excess) * 0.5))
        if v <= 0: return
        # pick instrument with room
        if abs(state.pos(underlying)) > 80 and front_future:
            target = front_future
        else:
            target = underlying
        room = (PER_INSTRUMENT_HARD_CAP + state.pos(target)) if d>0 else (PER_INSTRUMENT_HARD_CAP - state.pos(target))
        if room < v and front_future and target != front_future:
            target = front_future
            room = (PER_INSTRUMENT_HARD_CAP + state.pos(target)) if d>0 else (PER_INSTRUMENT_HARD_CAP - state.pos(target))
        v = min(v, room)
        if v <= 0: return
        bb,ba,*_=best_bid_ask(state.books.get(target))
        if bb is None: return
        if d>0:
            trader.ioc(target,price=bb,volume=v,side="ask")
            print(f"[HEDGE] sold {v} {target}@{bb:.2f} (delta {d:.1f})")
        else:
            trader.ioc(target,price=ba,volume=v,side="bid")
            print(f"[HEDGE] bought {v} {target}@{ba:.2f} (delta {d:.1f})")
        self.last_fire = time.time()


# ============================================================================
# PnL with theoretical valuations
# ============================================================================

def build_valuations(state):
    """Return {iid: theo_price} for futures and options so PnL doesn't whip
    on stale last-traded prices."""
    vals = {}
    for iid, inst in state.instruments.items():
        t = inst.instrument_type
        # stock / dual / ETF: use mid if available
        if t in (InstrumentType.STOCK, InstrumentType.INDEX_TRACKING_ETF):
            m = mid_of(state.books.get(iid))
            if m is not None: vals[iid] = m
        elif t == InstrumentType.STOCK_FUTURE:
            base = inst.base_instrument_id
            S = mid_of(state.books.get(base)) if base else None
            if S is not None:
                tau = years_to(inst.expiry); r = inst.interest_rate
                vals[iid] = S * math.exp(r*tau)
            else:
                m = mid_of(state.books.get(iid))
                if m is not None: vals[iid] = m
        elif t == InstrumentType.INDEX_FUTURE:
            m = mid_of(state.books.get(iid))
            if m is not None: vals[iid] = m
        elif t == InstrumentType.STOCK_OPTION:
            base = inst.base_instrument_id
            S = mid_of(state.books.get(base)) if base else None
            if S is not None:
                K=inst.strike; tau=years_to(inst.expiry); r=inst.interest_rate
                kind="C" if iid.endswith("C") else "P"
                sig=state.iv_cache.get(iid, 0.30)
                vals[iid] = bs_call(S,K,tau,r,sig) if kind=="C" else bs_put(S,K,tau,r,sig)
            else:
                m = mid_of(state.books.get(iid))
                if m is not None: vals[iid] = m
    return vals


# ============================================================================
# DISCOVERY / STARTUP
# ============================================================================

def discover(exchange):
    insts=exchange.get_tradable_instruments()
    duals=[]
    for iid,inst in insts.items():
        if iid.endswith("_DUAL"):
            ld=iid[:-5]
            if ld in insts:
                duals.append(DualPair(leading=ld,dual=iid,tick=inst.tick_size))
    asml_groups=defaultdict(dict); asml_opts=[]
    for iid,inst in insts.items():
        if inst.instrument_type==InstrumentType.STOCK_OPTION and inst.base_instrument_id=="ASML":
            asml_opts.append(iid)
            asml_groups[inst.strike]["C" if iid.endswith("C") else "P"]=iid
    pcp_groups=[(kv["C"],kv["P"],K) for K,kv in asml_groups.items() if "C" in kv and "P" in kv]
    asml_opts_atm=[iid for iid in asml_opts if "_075" in iid]
    asml_futs=sorted((iid for iid,inst in insts.items()
                      if inst.instrument_type==InstrumentType.STOCK_FUTURE and inst.base_instrument_id=="ASML"),
                     key=lambda x: insts[x].expiry)
    ob5x_futs=sorted((iid for iid,inst in insts.items()
                      if inst.instrument_type==InstrumentType.INDEX_FUTURE),
                     key=lambda x: insts[x].expiry)
    etf=next((iid for iid,inst in insts.items()
              if inst.instrument_type==InstrumentType.INDEX_TRACKING_ETF), None)
    return {"insts":insts,"duals":duals,"asml_options_all":sorted(asml_opts),
            "asml_options_atm":sorted(asml_opts_atm),"asml_groups_by_K":asml_groups,
            "pcp_groups":pcp_groups,"asml_futures":asml_futs,
            "asml_front_future":asml_futs[0] if asml_futs else None,
            "ob5x_futures":ob5x_futs,"etf_iid":etf}

def flatten_instrument(e,iid,max_attempts=5):
    for _ in range(max_attempts):
        pos=e.get_positions().get(iid,0)
        if pos==0: return True
        book=e.get_last_price_book(iid)
        if not book or not book.bids or not book.asks: return False
        try:
            if pos>0: e.insert_order(iid,price=book.bids[0].price,volume=pos,side="ask",order_type="ioc")
            else: e.insert_order(iid,price=book.asks[0].price,volume=-pos,side="bid",order_type="ioc")
        except Exception as ex:
            print(f"  flatten {iid} fail: {ex}"); return False
        time.sleep(0.1)
    return False

def flatten_targets(exchange, targets, label):
    pos=exchange.get_positions()
    targets=[iid for iid in targets if pos.get(iid,0)!=0]
    if not targets:
        print(f"[STARTUP] {label} already flat."); return
    print(f"[STARTUP] flattening {label}: { {iid: pos[iid] for iid in targets} }")
    for iid in targets:
        ok=flatten_instrument(exchange,iid)
        print(f"  {iid}: {'flat' if ok else 'PARTIAL'}")
    time.sleep(0.5)


# ============================================================================
# MAIN
# ============================================================================

def main():
    logging.getLogger("client").setLevel("ERROR")
    exchange=Exchange(); exchange.connect()
    info=discover(exchange)
    print("Discovered:")
    print(f"  duals          : {[(p.leading,p.dual) for p in info['duals']]}")
    print(f"  asml options   : {info['asml_options_all']}")
    print(f"  asml futures   : {info['asml_futures']}")
    print(f"  ob5x futures   : {info['ob5x_futures']}")
    print(f"  etf            : {info['etf_iid']}")

    if FLATTEN_OB5X_ON_STARTUP:
        ob5x = list(info["ob5x_futures"])
        if info["etf_iid"]: ob5x.append(info["etf_iid"])
        flatten_targets(exchange, ob5x, "OB5X complex")
    if FLATTEN_ASML_FUTURES_ON_STARTUP:
        flatten_targets(exchange, info["asml_futures"], "ASML futures")

    budget=WriteBudget(MAX_WRITES_PER_SEC); trader=Trader(exchange,budget)
    state=MarketState(instruments=info["insts"])
    hedger=SmartHedger()

    strategies=[]
    if ENABLE_BOX and info["asml_groups_by_K"]:
        strategies.append(("BOX",BoxArb("ASML",info["asml_groups_by_K"])))
    if ENABLE_VERTICAL and info["asml_groups_by_K"]:
        strategies.append(("VERT",VerticalArb("ASML",info["asml_groups_by_K"])))
    if ENABLE_PCP and info["pcp_groups"]:
        strategies.append(("PCP",PCPArb("ASML",info["pcp_groups"])))
    if ENABLE_CALENDAR_ASML and len(info["asml_futures"])>=2:
        strategies.append(("CAL-A",CalendarArb(info["asml_futures"],"ASML")))
    if ENABLE_CALENDAR_OB5X and len(info["ob5x_futures"])>=2:
        strategies.append(("CAL-O",CalendarArb(info["ob5x_futures"],"OB5X")))
    if ENABLE_STOCK_FUTURE_BASIS and info["asml_futures"]:
        strategies.append(("FBASIS",FutureBasis("ASML",info["asml_futures"])))
    if ENABLE_ETF_BASIS and info["etf_iid"] and info["ob5x_futures"]:
        strategies.append(("EBASIS",ETFFutureBasis(info["etf_iid"],info["ob5x_futures"],info["insts"])))
    if ENABLE_DUAL_ARB and info["duals"]:
        strategies.append(("DUAL",DualActiveArb(info["duals"])))
    if ENABLE_OPTION_MM and info["asml_options_atm"]:
        strategies.append(("OMM",OptionMM(info["asml_options_atm"])))
    print(f"Strategies: {[n for n,_ in strategies]}")

    relevant={"ASML"}
    for p in info["duals"]: relevant.update([p.leading,p.dual])
    relevant.update(info["asml_options_all"]); relevant.update(info["asml_futures"])
    relevant.update(info["ob5x_futures"])
    if info["etf_iid"]: relevant.add(info["etf_iid"])
    relevant=list(relevant)

    last_status=time.time()
    try:
        while True:
            t0=time.time()
            try:
                state.refresh(trader,relevant)
                for name,strat in strategies:
                    try:
                        strat.step(state,trader)
                        state.positions=trader.positions()
                    except AssertionError: raise
                    except Exception as ex: print(f"[{name}] error: {ex}")
                hedger.step(state, trader, "ASML", info["asml_front_future"], MAX_PORTFOLIO_DELTA)

                if time.time()-last_status > STATUS_INTERVAL_SEC:
                    nz={k:v for k,v in state.positions.items() if v!=0}
                    pnl = trader.pnl(build_valuations(state))
                    d=underlying_delta(state,"ASML")
                    print(f"[STATUS] PnL_theo={pnl:.2f}  asml_delta={d:.1f}  "
                          f"budget={budget.available()}/{budget.limit}  "
                          f"positions={nz}")
                    last_status=time.time()
            except AssertionError as e:
                print(f"[FATAL] disconnected: {e}"); break
            except Exception as e:
                logging.exception("Loop error: %s",e)
            elapsed=time.time()-t0
            time.sleep(max(0,LOOP_SLEEP_SEC-elapsed))
    except KeyboardInterrupt:
        print("\nInterrupted. Cancelling option quotes...")
        for iid in info["asml_options_atm"]: trader.cancel_all(iid)
        print("Done.")

if __name__ == "__main__":
    main()
