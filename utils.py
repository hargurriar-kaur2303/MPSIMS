"""
utils.py — MPSIMS Finance Dashboard
Real column mapping from actual Excel inspection.

EXACT COLUMNS (identical across all 4 files):
  Sr. No | Plan Type | Scheme Code | Scheme Title
  2023-24 Outlay | 2023-24 Actual Expenditure
  2024-25 Outlay | 2024-25 Anticipated Expenditure
  2025-26 Proposed Outlay | 2025-26 Outlay for Budgeting
  BDS Release By FD (Till last day) | BDS Expenditure (Till last day)
  SDG Status | Scheme Status

MONEY: Indian comma format '3,83,96.67' → remove commas → 38396.67 Lakhs
SECTOR: from filename (no sector column in files)
DEPARTMENT: from Plan Type (General/SCCS/TCS/OTCS)
"""
import os, re, warnings
from io import BytesIO
from datetime import datetime
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

# ── Constants ─────────────────────────────────────────────────────────────────
SECTORS = {
    "Agriculture":    "MPSIMSAgriculturePlanYear25-26.xlsx",
    "Education":      "MPSIMSScheelEducationPlanYear25-26.xlsx",
    "Skills":         "MPSIMSSkillPlanYear25-26.xlsx",
    "Social Justice": "MPSIMSSociaslJusticePlanYear25-26.xlsx",
}
PLAN_TYPE_MAP = {
    "General": "General Schemes",
    "SCCS":    "Scheduled Caste Component Scheme",
    "TCS":     "Tribal Component Scheme",
    "OTCS":    "Other Than Component Scheme",
}
SECTOR_COLORS = {
    "Agriculture":    "#10b981",
    "Education":      "#3b82f6",
    "Skills":         "#f59e0b",
    "Social Justice": "#8b5cf6",
}
PLAN_TYPE_COLORS = {
    "General": "#3b82f6", "SCCS": "#8b5cf6",
    "TCS":     "#10b981", "OTCS": "#f59e0b",
}
STATUS_WEIGHTS = {"A":1.0,"S":0.9,"P":0.7,"R":0.3}
SDG_WEIGHTS    = {"A":1.5,"P":1.0,"NA":0.8}
SCORE_THRESHOLDS = {"SCALE UP":85,"CONTINUE":70,"MONITOR":50}

# Exact column names from files
C_SRNO   = "Sr. No"
C_PTYPE  = "Plan Type"
C_CODE   = "Scheme Code"
C_NAME   = "Scheme Title"
C_O2324  = "2023 - 24 Outlay"
C_E2324  = "2023 - 24 Actual Expenditure"
C_O2425  = "2024 - 25 Outlay"
C_A2425  = "2024 - 25 Anticipated Expenditure"
C_PROP   = "2025 - 26 Proposed Outlay"
C_BUDGET = "2025 - 26 Outlay for Budgeting"
C_REL    = "BDS Release By FD (Till last day)"
C_EXP    = "BDS Expenditure (Till last day)"
C_SDG    = "SDG Status"
C_STATUS = "Scheme Status"

# ── Money parser ──────────────────────────────────────────────────────────────
def parse_indian_money(val) -> float:
    """'3,83,96.67' -> 38396.67 Lakhs. Remove all commas then cast."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",","").replace("₹","").replace(" ","")
    if s in ("","-","nan","None"): return 0.0
    try: return float(s)
    except: return 0.0

def lakhs_to_display(v) -> str:
    if pd.isna(v) or v == 0: return "₹0"
    v = float(v)
    if abs(v) >= 100: return f"₹{v/100:,.2f} Cr"
    return f"₹{v:,.2f} L"

def lakhs_to_crore(v) -> float:
    return float(v)/100 if not pd.isna(v) else 0.0

def sname(series, maxlen=30) -> list:
    return series.fillna("Unknown").astype(str).str[:maxlen].tolist()

def clean_df_strings(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["scheme_name","sector","plan_type","department","scheme_status","sdg_status"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
    df["scheme_name"]   = df["scheme_name"].replace("","Unknown Scheme")
    df["sector"]        = df["sector"].replace("","Unknown Sector")
    df["plan_type"]     = df["plan_type"].replace("","General")
    df["department"]    = df["department"].replace("","General Schemes")
    df["scheme_status"] = df["scheme_status"].replace("","P")
    df["sdg_status"]    = df["sdg_status"].replace("","P")
    return df

# ── Excel loader ──────────────────────────────────────────────────────────────
def load_excel_file(filepath_or_buffer, sector: str) -> pd.DataFrame:
    raw = pd.read_excel(filepath_or_buffer, engine="openpyxl")
    raw.columns = [str(c).strip() for c in raw.columns]
    raw = raw.dropna(how="all").reset_index(drop=True)
    def is_real(v):
        if pd.isna(v): return False
        try: float(str(v).replace(",","")); return True
        except: return False
    data = raw[raw[C_SRNO].apply(is_real)].copy().reset_index(drop=True)
    if data.empty:
        raise ValueError(f"No data rows in {filepath_or_buffer}")
    n = len(data)
    out = pd.DataFrame()
    out["sector"]       = [str(sector)] * n          # explicit list — avoids StringArray NaN bug
    out["scheme_name"]  = data[C_NAME].fillna("").astype(str).str.strip().values
    out["plan_type"]    = data[C_PTYPE].fillna("General").astype(str).str.strip().values
    # Prefer explicit 'department' column in sheets (case-insensitive) if provided;
    # otherwise fall back to mapping from plan_type.
    dept_col = None
    for c in data.columns:
        if str(c).strip().lower() == "department":
            dept_col = c
            break
    if dept_col is not None:
        out["department"] = data[dept_col].fillna(out["plan_type"]).astype(str).str.strip().values
    else:
        out["department"]   = out["plan_type"].map(PLAN_TYPE_MAP).fillna(out["plan_type"]).values
    out["scheme_code"]  = data[C_CODE].apply(lambda x: str(int(x)) if pd.notna(x) and str(x).replace(".0","").isdigit() else str(x))
    out["budget_alloc"] = data[C_BUDGET].apply(parse_indian_money)
    out["released"]     = data[C_REL].apply(parse_indian_money)
    out["expenditure"]  = data[C_EXP].apply(parse_indian_money)
    out["outlay_2324"]  = data[C_O2324].apply(parse_indian_money)
    out["exp_2324"]     = data[C_E2324].apply(parse_indian_money)
    out["outlay_2425"]  = data[C_O2425].apply(parse_indian_money)
    out["ant_2425"]     = data[C_A2425].apply(parse_indian_money)
    out["proposed"]     = data[C_PROP].apply(parse_indian_money)
    def cs(s,d="P"):
        return s.fillna(d).astype(str).str.strip().str.upper().replace({"NAN":d,"":d,"NONE":d})
    out["scheme_status"] = cs(data[C_STATUS])
    out["sdg_status"]    = cs(data[C_SDG])
    out["year"]          = "2025-26"
    out = out[out["scheme_name"].str.len() > 2]
    out = out[~out["scheme_name"].str.lower().str.match(r"^(scheme|title|sr\.?\s*no|nan|none)$")]
    return out.reset_index(drop=True)

def load_all_sectors(uploaded_files: dict) -> pd.DataFrame:
    frames = []
    for sector, f in uploaded_files.items():
        try:
            df = load_excel_file(f, sector)
            frames.append(df)
        except Exception as e:
            print(f"[WARN] {sector}: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

# ── KPIs ──────────────────────────────────────────────────────────────────────
def compute_kpis(df: pd.DataFrame) -> dict:
    if df.empty: return {}
    k = {}
    k["total_schemes"]       = len(df)
    k["total_sectors"]       = df["sector"].nunique()
    k["total_plan_types"]    = df["plan_type"].nunique()
    k["total_budget_L"]      = float(df["budget_alloc"].sum())
    k["total_released_L"]    = float(df["released"].sum())
    k["total_expenditure_L"] = float(df["expenditure"].sum())
    k["total_gap_L"]         = float(k["total_released_L"] - k["total_expenditure_L"])
    k["overall_utilization_pct"] = float(k["total_expenditure_L"]/k["total_released_L"]*100 if k["total_released_L"]>0 else 0)
    k["release_rate_pct"]    = float(k["total_released_L"]/k["total_budget_L"]*100 if k["total_budget_L"]>0 else 0)
    k["total_exp_2324_L"]    = float(df["exp_2324"].sum())
    k["yoy_growth_pct"]      = float((k["total_expenditure_L"]-k["total_exp_2324_L"])/k["total_exp_2324_L"]*100 if k["total_exp_2324_L"]>0 else 0)
    z = df[(df["expenditure"]==0)&(df["released"]>10)]
    k["zero_spend_schemes"]  = len(z)
    k["zero_spend_amount_L"] = float(z["released"].sum())
    for s in ["A","S","P","R"]:
        m = df["scheme_status"]==s
        k[f"status_{s}_count"]    = int(m.sum())
        k[f"status_{s}_budget_L"] = float(df.loc[m,"budget_alloc"].sum())
    for g in ["A","P","NA"]:
        k[f"sdg_{g}_count"] = int((df["sdg_status"]==g).sum())
    df2 = df.copy()
    df2["util_pct"] = df2.apply(lambda r: r["expenditure"]/r["released"]*100 if r["released"]>0 else 0, axis=1)
    u30 = df2[df2["util_pct"]<30]
    k["underutilized_30_count"] = len(u30)
    k["underutilized_30_amt_L"] = float(u30["released"].sum())
    rej = df[df["scheme_status"]=="R"]
    k["rejected_schemes"]  = len(rej)
    k["rejected_budget_L"] = float(rej["budget_alloc"].sum())
    sc = compute_decision_scores(df2)
    k["avg_decision_score"] = float(sc["decision_score"].mean()) if not sc.empty else 0
    k["scale_up_count"]     = int((sc["recommendation"]=="🔥 SCALE UP").sum())
    k["review_pause_count"] = int((sc["recommendation"]=="🔴 REVIEW/PAUSE").sum())
    sk = {}
    for sec in df["sector"].unique():
        sub = df[df["sector"]==sec]; rel = sub["released"].sum()
        sk[sec] = {"schemes":len(sub),"budget_L":float(sub["budget_alloc"].sum()),
                   "released_L":float(rel),"expenditure_L":float(sub["expenditure"].sum()),
                   "util_pct":float(sub["expenditure"].sum()/rel*100) if rel>0 else 0}
    k["sector_kpis"] = sk
    return k

# ── Decision scoring ──────────────────────────────────────────────────────────
def compute_decision_scores(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    r = df.copy()
    r["util_pct"]      = r.apply(lambda x: min(x["expenditure"]/x["released"]*100,100) if x["released"]>0 else 0, axis=1)
    r["growth_score"]  = r.apply(lambda x: min(x["expenditure"]/x["budget_alloc"]*100,100) if x["budget_alloc"]>0 else 0, axis=1)
    r["forecast_score"]= r.apply(lambda x: min(x["released"]/x["budget_alloc"]*100,100) if x["budget_alloc"]>0 else 0, axis=1)
    r["raw_score"]     = r["util_pct"]*0.4 + r["growth_score"]*0.3 + r["forecast_score"]*0.3
    r["status_w"]      = r["scheme_status"].map(STATUS_WEIGHTS).fillna(0.5)
    r["sdg_w"]         = r["sdg_status"].map(SDG_WEIGHTS).fillna(1.0)
    r["decision_score"]= (r["raw_score"]*r["status_w"]*r["sdg_w"]).clip(0,100)
    def rec(s):
        if s>=85: return "🔥 SCALE UP"
        if s>=70: return "✅ CONTINUE"
        if s>=50: return "🟡 MONITOR"
        return "🔴 REVIEW/PAUSE"
    r["recommendation"] = r["decision_score"].apply(rec)
    return r

# ── Forecasting ───────────────────────────────────────────────────────────────
def forecast_sector_totals(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sec in df["sector"].unique():
        sub  = df[df["sector"]==sec]
        curr = sub["expenditure"].sum(); prev = sub["exp_2324"].sum()
        growth = max(min((curr-prev)/prev if prev>0 else 0.10, 0.40), -0.20)
        rows.append({"sector":sec,"year_2324_L":float(prev),"year_2526_L":float(curr),
                     "forecast_2627_L":float(curr*(1+growth)),"growth_pct":float(growth*100)})
    return pd.DataFrame(rows)

def forecast_scheme_prophet(scheme_name, df, periods=4):
    try: from prophet import Prophet
    except: return None
    sub = df[df["scheme_name"].str.contains(scheme_name,case=False,na=False)]
    if sub.empty: return None
    e2324=sub["exp_2324"].iloc[0]; e2425=sub["ant_2425"].iloc[0]; e2526=sub["expenditure"].iloc[0]
    q=[0.20,0.25,0.30,0.25]
    hist=[]
    for yi,(ye,ys) in enumerate([(e2324,"2023"),(e2425,"2024"),(e2526,"2025")]):
        for qi,p in enumerate(q):
            hist.append({"ds":pd.Timestamp(f"{ys}-{qi*3+1:02d}-01"),"y":max(ye*p,0)})
    hdf = pd.DataFrame(hist)
    try:
        m = Prophet(yearly_seasonality=True,weekly_seasonality=False,daily_seasonality=False,
                    interval_width=0.80,changepoint_prior_scale=0.05)
        m.fit(hdf); future=m.make_future_dataframe(periods=periods,freq="QS")
        fc=m.predict(future)
        return fc[fc["ds"]>hdf["ds"].max()][["ds","yhat","yhat_lower","yhat_upper"]].reset_index(drop=True)
    except: return None

# ── Finance Agent ─────────────────────────────────────────────────────────────
class FinanceAgent:
    SCOPE = ["agriculture","education","skill","social","scheme","budget","expenditure",
             "spend","release","sdg","status","forecast","underutil","zero","lakh","crore",
             "plan type","general","sccs","tcs","otcs","growth","trend","recommend","scale",
             "top","compare","gap","sector","2324","2425","2526","prior","previous",
             "pradhan","samagra","shravan","mahajan"]
    OUT = ("💰 I'm trained **only** on 4 MPSIMS Maharashtra budget sheets:\n"
           "🌾 Agriculture • 📚 Education • 🔧 Skills • ⚖️ Social Justice\n\n"
           "Ask about scheme budgets, expenditure, utilization, forecasts, "
           "SDG, Plan Types (General/SCCS/TCS/OTCS), or comparisons.")

    def __init__(self, df):
        self.df=df; self.scored=compute_decision_scores(df) if not df.empty else df
        self.history=[]

    def is_in_scope(self,q): return any(k in q.lower() for k in self.SCOPE)

    def _sf(self,q):
        df=self.scored if not self.scored.empty else self.df
        for s in ["Agriculture","Education","Skills","Social Justice"]:
            if s.lower() in q.lower(): return df[df["sector"]==s]
        return df

    def _lbl(self,q):
        for s in ["Agriculture","Education","Skills","Social Justice"]:
            if s.lower() in q.lower(): return f" ({s})"
        return ""

    def _n(self,q,d=5):
        m=re.search(r"\b(\d+)\b",q); return int(m.group(1)) if m else d

    def respond(self,uq):
        self.history.append({"role":"user","content":uq})
        q=uq.lower(); df=self._sf(q); lbl=self._lbl(q)
        if not self.is_in_scope(q):
            return {"text":self.OUT,"table":None,"chart_data":None}

        # Zero spend
        if any(w in q for w in ["zero","nil spend","0 spend","no spend"]):
            res=df[(df["expenditure"]==0)&(df["released"]>10)].copy()
            t=res[["scheme_name","sector","plan_type","released","scheme_status"]].copy()
            t["released"]=t["released"].apply(lakhs_to_display)
            return {"text":f"🚨 **{len(res)} Zero-Expenditure Schemes{lbl}**\nReleased but unspent: **{lakhs_to_display(res['released'].sum())}**",
                    "table":t,"chart_data":{"type":"bar","x":sname(res["scheme_name"],22)[:12],"y":res["released"].tolist()[:12],"title":"Zero-Spend: Released (Lakhs)"}}

        # Forecast
        if any(w in q for w in ["forecast","predict","2026","next year"]):
            fc=forecast_sector_totals(df)
            rows=[f"- **{r['sector']}**: {lakhs_to_display(r['year_2526_L'])} → {lakhs_to_display(r['forecast_2627_L'])} ({r['growth_pct']:+.1f}%)" for _,r in fc.iterrows()]
            return {"text":f"🔮 **2026-27 Forecast{lbl}**\n\n"+"\n".join(rows),"table":fc,
                    "chart_data":{"type":"bar","x":fc["sector"].tolist(),"y":fc["forecast_2627_L"].tolist(),"title":"2026-27 Forecast (Lakhs)"}}

        # Underutilized
        if any(w in q for w in ["underutil","low util","low spend"]):
            n=self._n(q); df2=df.copy()
            df2["util_pct"]=df2.apply(lambda r: r["expenditure"]/r["released"]*100 if r["released"]>0 else 0,axis=1)
            res=df2.nsmallest(n,"util_pct")[["scheme_name","sector","plan_type","released","expenditure","util_pct"]].copy()
            t=res.copy()
            t["released"]=t["released"].apply(lakhs_to_display)
            t["expenditure"]=t["expenditure"].apply(lakhs_to_display)
            t["util_pct"]=t["util_pct"].apply(lambda x:f"{x:.1f}%")
            return {"text":f"📉 **Top {n} Underutilized{lbl}** | At risk: **{lakhs_to_display(res['released'].sum())}**",
                    "table":t,"chart_data":{"type":"bar","x":sname(res["scheme_name"],22),"y":res["util_pct"].tolist(),"title":f"Top {n} Underutilized %"}}

        # Top/scale
        if any(w in q for w in ["top","scale","best","highest","recommend"]):
            n=self._n(q)
            res=df.nlargest(n,"decision_score")[["scheme_name","sector","plan_type","decision_score","recommendation","budget_alloc","expenditure"]].copy()
            t=res.copy(); t["decision_score"]=t["decision_score"].apply(lambda x:f"{x:.1f}")
            t["budget_alloc"]=t["budget_alloc"].apply(lakhs_to_display); t["expenditure"]=t["expenditure"].apply(lakhs_to_display)
            return {"text":f"🔥 **Top {n} High-Priority{lbl}**","table":t,
                    "chart_data":{"type":"bar","x":sname(res["scheme_name"],22),"y":res["decision_score"].tolist(),"title":f"Top {n} Decision Score"}}

        # Status
        if any(w in q for w in ["pending","rejected","approved","submitted","status"]):
            sm={"pending":"P","rejected":"R","approved":"A","submitted":"S"}
            code=next((sm[w] for w in sm if w in q),None)
            res=df[df["scheme_status"]==code] if code else df
            lbl2={v:k.title() for k,v in sm.items()}.get(code,"All")
            t=res[["scheme_name","sector","plan_type","scheme_status","budget_alloc"]].copy()
            t["budget_alloc"]=t["budget_alloc"].apply(lakhs_to_display)
            return {"text":f"📋 **{len(res)} {lbl2} Schemes{lbl}** | Budget: **{lakhs_to_display(res['budget_alloc'].sum())}**",
                    "table":t,"chart_data":{"type":"pie","x":["Approved","Submitted","Pending","Rejected"],
                    "y":[(df["scheme_status"]==c).sum() for c in "ASPR"],"title":"Status Distribution"}}

        # SDG
        if any(w in q for w in ["sdg","sustainable"]):
            rows=[f"- {'✅ Applicable' if c=='A' else '⏳ Pending' if c=='P' else '❌ NA'}: **{(df['sdg_status']==c).sum()} schemes** — {lakhs_to_display(df.loc[df['sdg_status']==c,'budget_alloc'].sum())}" for c in ["A","P","NA"]]
            return {"text":f"🌍 **SDG Alignment{lbl}**\n\n"+"\n".join(rows),"table":None,
                    "chart_data":{"type":"pie","x":["Applicable","Pending","NA"],"y":[(df["sdg_status"]==c).sum() for c in ["A","P","NA"]],"title":"SDG Alignment"}}

        # Compare
        if any(w in q for w in ["compare","vs","sector","cross"]):
            agg=df.groupby("sector").agg(schemes=("scheme_name","count"),budget_L=("budget_alloc","sum"),
                released_L=("released","sum"),expenditure_L=("expenditure","sum")).reset_index()
            agg["util_pct"]=agg.apply(lambda r:r["expenditure_L"]/r["released_L"]*100 if r["released_L"]>0 else 0,axis=1)
            t=agg.copy()
            for c in ["budget_L","released_L","expenditure_L"]: t[c]=t[c].apply(lakhs_to_display)
            t["util_pct"]=t["util_pct"].apply(lambda x:f"{x:.1f}%")
            return {"text":"⚖️ **Cross-Sector Comparison**","table":t,
                    "chart_data":{"type":"bar","x":agg["sector"].tolist(),"y":agg["expenditure_L"].tolist(),"title":"Expenditure by Sector (Lakhs)"}}

        # Gap
        if any(w in q for w in ["gap","unspent","idle"]):
            df3=df.copy(); df3["gap_L"]=df3["released"]-df3["expenditure"]
            res=df3.nlargest(10,"gap_L")[["scheme_name","sector","released","expenditure","gap_L"]].copy()
            for c in ["released","expenditure","gap_L"]: res[c]=res[c].apply(lakhs_to_display)
            return {"text":f"💰 **Gap Analysis{lbl}** | Unspent: **{lakhs_to_display(df3['gap_L'].sum())}**",
                    "table":res,"chart_data":{"type":"bar","x":sname(df3.nlargest(10,'gap_L')["scheme_name"],22),
                    "y":df3.nlargest(10,"gap_L")["gap_L"].tolist(),"title":"Top 10 Gap (Lakhs)"}}

        # Plan type
        if any(w in q for w in ["plan type","general","sccs","tcs","otcs","component"]):
            agg=df.groupby("plan_type").agg(schemes=("scheme_name","count"),budget_L=("budget_alloc","sum"),
                expenditure_L=("expenditure","sum")).reset_index()
            t=agg.copy()
            for c in ["budget_L","expenditure_L"]: t[c]=t[c].apply(lakhs_to_display)
            return {"text":f"📋 **Plan Type Breakdown{lbl}**","table":t,
                    "chart_data":{"type":"pie","x":agg["plan_type"].tolist(),"y":agg["budget_L"].tolist(),"title":"Budget by Plan Type"}}

        # Generic
        kpis=compute_kpis(df)
        return {"text":(f"📊 **MPSIMS Summary{lbl}**\n"
                f"- Schemes: **{kpis.get('total_schemes',0)}**\n"
                f"- Budget 2025-26: **{lakhs_to_display(kpis.get('total_budget_L',0))}**\n"
                f"- Released: **{lakhs_to_display(kpis.get('total_released_L',0))}**\n"
                f"- Expenditure: **{lakhs_to_display(kpis.get('total_expenditure_L',0))}**\n"
                f"- Utilization: **{kpis.get('overall_utilization_pct',0):.1f}%**\n"
                f"- Zero-Spend: **{kpis.get('zero_spend_schemes',0)}** schemes\n\n"
                "Ask: zero spend | top 5 | forecast | SDG | gap | plan type | compare"),
                "table":None,"chart_data":None}

# ── Exports ───────────────────────────────────────────────────────────────────
def export_to_excel(df, kpis) -> bytes:
    buf=BytesIO()
    with pd.ExcelWriter(buf,engine="openpyxl") as w:
        d=df.copy()
        for c in ["budget_alloc","released","expenditure"]:
            if c in d.columns: d[c+"_disp"]=d[c].apply(lakhs_to_display)
        d.to_excel(w,sheet_name="All Schemes",index=False)
        sc=compute_decision_scores(df)
        sc[["scheme_name","sector","plan_type","decision_score","recommendation","util_pct","scheme_status","sdg_status"]].to_excel(w,sheet_name="Decision Scores",index=False)
        pd.DataFrame([{"KPI":k,"Value":v} for k,v in kpis.items() if k!="sector_kpis" and not isinstance(v,dict)]).to_excel(w,sheet_name="KPIs",index=False)
    buf.seek(0); return buf.read()

def export_to_pdf_simple(df, kpis) -> bytes:
    try:
        from reportlab.lib.pagesizes import A4; from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        buf=BytesIO(); doc=SimpleDocTemplate(buf,pagesize=A4); styles=getSampleStyleSheet(); story=[]
        story.append(Paragraph("MPSIMS Maharashtra Budget Report 2025-26",styles["Title"]))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%d %b %Y %H:%M')}",styles["Normal"]))
        story.append(Spacer(1,12))
        kd=[["KPI","Value"]]+[("Total Schemes",str(kpis.get("total_schemes",0))),("Budget",lakhs_to_display(kpis.get("total_budget_L",0))),
            ("Released",lakhs_to_display(kpis.get("total_released_L",0))),("Expenditure",lakhs_to_display(kpis.get("total_expenditure_L",0))),
            ("Utilization",f"{kpis.get('overall_utilization_pct',0):.1f}%"),("Zero-Spend",str(kpis.get("zero_spend_schemes",0)))]
        t=Table(kd,colWidths=[250,200])
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#4f46e5")),("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTSIZE",(0,0),(-1,-1),10),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f3f4f6")]),
            ("GRID",(0,0),(-1,-1),0.5,colors.grey)]))
        story.append(t); doc.build(story); buf.seek(0); return buf.read()
    except Exception as e: print(f"PDF err:{e}"); return b""
