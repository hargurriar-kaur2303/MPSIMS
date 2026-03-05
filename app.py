"""
app.py — MPSIMS Maharashtra Finance Dashboard 2025-26
=====================================================
• NO sidebar — full-width layout
• Top header with Maharashtra branding
• Inline filter bar (Sector, Plan Type, SDG, Status)
• 16 tabs with real data (338 schemes, 4 sectors)
• Bottom-right floating chatbot via st.components.v1.html
  — fully self-contained iframe chatbot, communicates back
    to Streamlit via URL query params + st.rerun()
Run: streamlit run app.py
"""
import os, re, warnings
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

warnings.filterwarnings("ignore")

from utils import (
    SECTORS, SECTOR_COLORS, PLAN_TYPE_COLORS, PLAN_TYPE_MAP,
    load_all_sectors, load_excel_file,
    compute_kpis, compute_decision_scores,
    forecast_sector_totals, forecast_scheme_prophet,
    lakhs_to_display, lakhs_to_crore, sname, clean_df_strings,
    export_to_excel, export_to_pdf_simple,
    FinanceAgent,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MPSIMS Maharashtra Finance Dashboard",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

T = "plotly_white"   # plotly template

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Hide sidebar toggle + default padding */
[data-testid="stSidebar"]       { display: none !important; }
[data-testid="collapsedControl"]{ display: none !important; }
.main .block-container { padding: 0.5rem 1.5rem 4rem 1.5rem; }
header[data-testid="stHeader"]  { background: transparent; }

/* ── Top header banner ── */
.mpsims-header {
    background: linear-gradient(135deg,#1e3a5f 0%,#2563eb 50%,#7c3aed 100%);
    border-radius: 14px; padding: 18px 28px; margin-bottom: 14px;
    display: flex; align-items: center; justify-content: space-between;
    box-shadow: 0 4px 20px rgba(37,99,235,0.3);
}
.mpsims-header .title-block h1 {
    margin:0; font-size:1.55rem; color:white; font-weight:800; letter-spacing:-.01em;
}
.mpsims-header .title-block p {
    margin:4px 0 0; color:rgba(255,255,255,0.82); font-size:0.82rem;
}
.mpsims-header .badge-row { display:flex; gap:8px; flex-wrap:wrap; }
.badge {
    background: rgba(255,255,255,0.18); color:white; border-radius:20px;
    padding:3px 11px; font-size:0.72rem; font-weight:600; backdrop-filter:blur(4px);
}

/* ── KPI cards ── */
.kpi-card {
    background: linear-gradient(135deg,#667eea,#764ba2);
    border-radius:12px; padding:14px 18px; color:white;
    text-align:center; box-shadow:0 4px 12px rgba(102,126,234,.3); margin-bottom:8px;
}
.kpi-card .kv { font-size:1.65rem; font-weight:700; }
.kpi-card .kl { font-size:0.72rem; opacity:.88; text-transform:uppercase; letter-spacing:.05em; }
.kpi-card.red   { background:linear-gradient(135deg,#ef4444,#b91c1c); }
.kpi-card.green { background:linear-gradient(135deg,#10b981,#065f46); }
.kpi-card.amber { background:linear-gradient(135deg,#f59e0b,#b45309); }
.kpi-card.blue  { background:linear-gradient(135deg,#3b82f6,#1d4ed8); }
.kpi-card.teal  { background:linear-gradient(135deg,#14b8a6,#0f766e); }
.kpi-card.indigo{ background:linear-gradient(135deg,#6366f1,#4338ca); }

/* ── Filter bar ── */
.filter-bar {
    background:#f8fafc; border:1px solid #e2e8f0;
    border-radius:10px; padding:10px 16px; margin-bottom:12px;
    display:flex; align-items:center; gap:10px; flex-wrap:wrap;
}

/* ── Alert boxes ── */
.alert-red   { background:#fef2f2;border-left:4px solid #ef4444;padding:10px 14px;border-radius:6px;color:#991b1b;margin-bottom:8px; }
.alert-amber { background:#fffbeb;border-left:4px solid #f59e0b;padding:10px 14px;border-radius:6px;color:#92400e;margin-bottom:8px; }

/* ── Tab font ── */
button[data-baseweb="tab"] { font-size:0.8rem !important; padding:6px 10px !important; }
</style>
""", unsafe_allow_html=True)

# ── Session init ──────────────────────────────────────────────────────────────
def init_session():
    defaults = {"df": pd.DataFrame(), "kpis": {}, "agent": None,
                "chat_history": [], "data_loaded": False}
    for k,v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if not st.session_state.data_loaded:
        _autoload_data_folder()

def _autoload_data_folder():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    files = {}

    for fname in os.listdir(data_dir):

        if fname.startswith("~$"):
            continue

        if not fname.lower().endswith((".xlsx",".xls")):
            continue
        f = fname.lower()

        if "agriculture" in f:
            files["Agriculture"] = os.path.join(data_dir, fname)

        elif "education" in f:
            files["School Education"] = os.path.join(data_dir, fname)

        elif "skill" in f:
            files["Skill"] = os.path.join(data_dir, fname)

        elif "social" in f or "justice" in f:
            files["Social Justice"] = os.path.join(data_dir, fname)

    try:
        df = load_all_sectors(files)
        if not df.empty:
            _finalize(df)
    except Exception as e:
        st.session_state["_load_err"] = str(e)

def _finalize(df: pd.DataFrame):
    df = clean_df_strings(df)
    st.session_state.df         = df
    st.session_state.kpis       = compute_kpis(df)
    st.session_state.agent      = FinanceAgent(df)
    st.session_state.data_loaded = True

# ── KPI card HTML ─────────────────────────────────────────────────────────────
def kcard(label, value, color=""):
    c = f"kpi-card {color}".strip()
    return f'<div class="{c}"><div class="kv">{value}</div><div class="kl">{label}</div></div>'

# ── Apply filters ─────────────────────────────────────────────────────────────
def apply_filters(df, sectors, departments, sdg_list, status_list, plan_types=None):
    d = df.copy()
    if sectors:     d = d[d["sector"].isin(sectors)]
    if departments: d = d[d["department"].isin(departments)]
    if sdg_list:    d = d[d["sdg_status"].isin(sdg_list)]
    if status_list: d = d[d["scheme_status"].isin(status_list)]
    if plan_types and "plan_type" in d.columns:
        d = d[d["plan_type"].isin(plan_types)]
    return d

# ── Safe chart wrapper ────────────────────────────────────────────────────────
def safe(fig):
    try: return fig
    except Exception as e:
        f=go.Figure(); f.update_layout(title=f"Chart error: {e}",template=T); return f

# ═══════════════════════════════════════════════════════════════════════════════
# CHART FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════
def ch_funnel(kpis):
    vals=[kpis.get("total_budget_L",0),kpis.get("total_released_L",0),kpis.get("total_expenditure_L",0)]
    fig=go.Figure(go.Funnel(y=["Budget Allocated","Funds Released","Actual Spend"],x=vals,
        textinfo="value+percent previous",
        texttemplate=[f"{lakhs_to_display(v)}<br>%{{percentPrevious}}" for v in vals],
        marker_color=["#667eea","#7c3aed","#10b981"]))
    fig.update_layout(title="Budget Funnel",template=T,margin=dict(t=40,b=10))
    return fig

def ch_sector_bar(df,ycol,title):
    agg=df.groupby("sector")[ycol].sum().reset_index()
    agg["disp"]=agg[ycol].apply(lakhs_to_display)
    fig=px.bar(agg,x="sector",y=ycol,text="disp",color="sector",
               color_discrete_map=SECTOR_COLORS,title=title,template=T)
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False,margin=dict(t=40,b=10))
    return fig

def ch_plan_type_pie(df,title="Budget by Department"):
    agg=df.groupby("department")["budget_alloc"].sum().reset_index()
    agg["disp"]=agg["budget_alloc"].apply(lakhs_to_display)
    fig=px.pie(agg,names="department",values="budget_alloc",
               color="department",color_discrete_map=PLAN_TYPE_COLORS,
               title=title,template=T,hole=0.4)
    fig.update_traces(textinfo="percent+label")
    fig.update_layout(margin=dict(t=40,b=10))
    return fig

def ch_heatmap(df):
    df2=df.copy()
    df2["util_pct"]=df2.apply(lambda r:r["expenditure"]/r["released"]*100 if r["released"]>0 else 0,axis=1)
    pivot=df2.pivot_table(index="department",columns="sector",values="util_pct",aggfunc="mean").fillna(0)
    fig=px.imshow(pivot,color_continuous_scale="RdYlGn",zmin=0,zmax=100,
                  title="Utilization Heatmap: Plan Type × Sector (%)",template=T,text_auto=".0f")
    fig.update_layout(margin=dict(t=50,b=20))
    return fig

def ch_radar(df):
    secs=df["sector"].unique().tolist()
    cats=["Budget %","Released %","Expend %","Utilization %","Schemes %"]
    RCOLS={"Agriculture":"#10b981","Education":"#3b82f6","Skills":"#f59e0b","Social Justice":"#7c3aed"}
    fig=go.Figure()
    for sec in secs:
        sub=df[df["sector"]==sec]
        tb=df["budget_alloc"].sum(); tr=df["released"].sum(); te=df["expenditure"].sum()
        util=min(sub["expenditure"].sum()/sub["released"].sum()*100,100) if sub["released"].sum()>0 else 0
        vals=[round(sub["budget_alloc"].sum()/tb*100,1) if tb>0 else 0,
              round(sub["released"].sum()/tr*100,1) if tr>0 else 0,
              round(sub["expenditure"].sum()/te*100,1) if te>0 else 0,
              round(util,1), round(len(sub)/len(df)*100,1)]
        clr=RCOLS.get(sec,SECTOR_COLORS.get(sec,"#666"))
        fig.add_trace(go.Scatterpolar(
            r=vals+[vals[0]], theta=cats+[cats[0]],
            fill="toself", name=sec,
            line=dict(color=clr,width=2.5), opacity=0.82,
        ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True,range=[0,100],
                           tickfont=dict(size=11,color="#64748b"),
                           gridcolor="#e2e8f0",linecolor="#cbd5e1",
                           tickvals=[20,40,60,80,100],
                           ticktext=["20%","40%","60%","80%","100%"]),
            angularaxis=dict(tickfont=dict(size=13,color="#334155",family="Segoe UI"),
                            linecolor="#cbd5e1"),
            bgcolor="rgba(248,250,252,1)",
        ),
        showlegend=True,
        title=dict(text="Sector Performance Radar (% of Total)",
                   font=dict(size=14,color="#1e293b",family="Segoe UI"),x=0.5,xanchor="center"),
        template=T, height=420,
        margin=dict(t=60,b=90,l=50,r=50),
        legend=dict(orientation="h",yanchor="bottom",y=-0.22,xanchor="center",x=0.5,
                    font=dict(size=12,color="#475569",family="Segoe UI"),
                    bgcolor="rgba(248,250,252,0.9)",bordercolor="#e2e8f0",borderwidth=1),
        paper_bgcolor="white",
    )
    return fig

def ch_waterfall(df):
    agg=df.groupby("sector").agg(budget=("budget_alloc","sum"),
        expenditure=("expenditure","sum")).reset_index()
    agg["unspent"]=agg["budget"]-agg["expenditure"]
    labels=(["Total Budget"]+
            [f"{s}\nSpent" for s in agg["sector"]]+
            [f"{s}\nUnspent" for s in agg["sector"]])
    yvals=([agg["budget"].sum()]+
           [-v for v in agg["expenditure"]]+
           [-v for v in agg["unspent"]])
    text_labels=([f"₹{agg['budget'].sum():,.0f} L"]+
                 [f"₹{v:,.0f} L" for v in agg["expenditure"]]+
                 [f"₹{v:,.0f} L" for v in agg["unspent"]])
    fig=go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute"]+["relative"]*(len(agg)*2),
        x=labels, y=yvals,
        text=text_labels,
        textposition="outside",
        textfont=dict(size=11,color="#334155",family="Segoe UI"),
        connector={"line":{"color":"#94a3b8","width":1}},
        decreasing={"marker":{"color":"#ef4444"}},
        increasing={"marker":{"color":"#10b981"}},
        totals={"marker":{"color":"#3b82f6"}},
    ))
    fig.update_layout(
        title=dict(text="Budget vs Expenditure Waterfall (₹ Lakhs)",
                   font=dict(size=14,color="#1e293b",family="Segoe UI"),x=0.5,xanchor="center"),
        template=T,
        height=440,
        margin=dict(t=60,b=100,l=70,r=20),
        xaxis=dict(tickfont=dict(size=11,color="#475569"),tickangle=-30),
        yaxis=dict(title="₹ Lakhs",tickfont=dict(size=11,color="#475569"),
                   gridcolor="#e2e8f0",zeroline=True,zerolinecolor="#94a3b8"),
        plot_bgcolor="rgba(248,250,252,1)",
        paper_bgcolor="white",
        showlegend=False,
    )
    return fig

def ch_scatter_matrix(df):
    sc=compute_decision_scores(df)
    sc["util_pct"]=sc.apply(lambda r:min(r["expenditure"]/r["released"]*100,150) if r["released"]>0 else 0,axis=1)
    fig=px.scatter(sc,x="util_pct",y="decision_score",color="sector",
        size="budget_alloc",size_max=40,
        hover_name="scheme_name",
        hover_data={"recommendation":True,"department":True,"util_pct":":.1f"},
        color_discrete_map=SECTOR_COLORS,template=T,
        title="Decision Matrix: Utilization % vs Decision Score",
        labels={"util_pct":"Utilization % (capped 150%)","decision_score":"Decision Score"},
        opacity=0.8)
    fig.add_hline(y=70,line_dash="dash",line_color="#f59e0b",line_width=2,
                  annotation_text="Scale-Up threshold (70)",
                  annotation_font=dict(size=12,color="#f59e0b"))
    fig.add_vline(x=50,line_dash="dash",line_color="#ef4444",line_width=2,
                  annotation_text="50% utilization",
                  annotation_font=dict(size=12,color="#ef4444"))
    fig.update_layout(
        title=dict(text="Decision Matrix: Utilization % vs Decision Score",
                   font=dict(size=15,color="#1e293b"),x=0.5,xanchor="center"),
        height=480,margin=dict(t=60,b=60,l=70,r=20),
        xaxis=dict(title="Utilization % (capped 150%)",tickfont=dict(size=12),
                   range=[-5,160],gridcolor="#e2e8f0"),
        yaxis=dict(title="Decision Score",tickfont=dict(size=12),
                   range=[-5,110],gridcolor="#e2e8f0"),
        plot_bgcolor="rgba(248,250,252,1)",paper_bgcolor="white",
        legend=dict(title="Sector",font=dict(size=12),
                    bgcolor="rgba(248,250,252,0.9)",bordercolor="#e2e8f0",borderwidth=1),
    )
    return fig

def ch_sdg(df):
    agg=df.groupby(["sector","sdg_status"]).size().reset_index(name="count")
    fig=px.bar(agg,x="sector",y="count",color="sdg_status",barmode="group",
        color_discrete_map={"A":"#10b981","P":"#f59e0b","NA":"#ef4444"},
        title="SDG Alignment by Sector",template=T,labels={"sdg_status":"SDG Status"})
    fig.update_layout(margin=dict(t=40,b=10))
    return fig

def ch_gap(df):
    df2=df.copy(); df2["scheme_name"]=df2["scheme_name"].fillna("").astype(str)
    df2["gap_L"]=df2["released"]-df2["expenditure"]
    top=df2.nlargest(20,"gap_L")
    labels=sname(top["scheme_name"],22)
    fig=go.Figure()
    fig.add_trace(go.Bar(name="Released",x=labels,y=top["released"].tolist(),marker_color="#3b82f6"))
    fig.add_trace(go.Bar(name="Expenditure",x=labels,y=top["expenditure"].tolist(),marker_color="#10b981"))
    fig.update_layout(barmode="group",title="Top 20 Gap: Release vs Spend (Lakhs)",
                      template=T,margin=dict(t=50,b=80),xaxis_tickangle=-40)
    return fig

def ch_sunburst(df):
    df2=df.copy()
    df2["sector"]=df2["sector"].fillna("Unknown").astype(str)
    df2["scheme_status"]=df2["scheme_status"].fillna("P").astype(str)
    sl={"A":"Approved","S":"Submitted","P":"Pending","R":"Rejected"}
    df2["status_label"]=df2["scheme_status"].map(sl).fillna(df2["scheme_status"])
    agg=df2.groupby(["sector","status_label"]).size().reset_index(name="count")
    if agg.empty: return go.Figure()
    fig=px.sunburst(agg,path=["sector","status_label"],values="count",color="status_label",
        color_discrete_map={"Approved":"#10b981","Submitted":"#3b82f6","Pending":"#f59e0b","Rejected":"#ef4444"},
        title="Status Sunburst: Sector → Status",template=T)
    fig.update_layout(margin=dict(t=50,b=10))
    return fig

def ch_treemap(df):
    clean=df.copy()
    clean["sector"]=clean["sector"].fillna("Unknown").astype(str).str.strip().replace("","Unknown")
    clean["department"]=clean["department"].fillna("General").astype(str).str.strip().replace("","General")
    clean["budget_alloc"]=clean["budget_alloc"].clip(lower=0.01)
    agg=clean.groupby(["sector","department"],as_index=False).agg(
        budget_alloc=("budget_alloc","sum"),schemes=("scheme_name","count"))
    agg["budget_alloc"]=agg["budget_alloc"].clip(lower=0.01)
    if agg.empty: return go.Figure()
    fig=px.treemap(agg,path=["sector","department"],values="budget_alloc",
        color="budget_alloc",color_continuous_scale="Viridis",
        title="Budget Treemap: Sector → Plan Type (Lakhs)",template=T,hover_data={"schemes":True})
    fig.update_layout(margin=dict(t=50,b=10))
    return fig

def ch_forecast(fc_df):
    fig=go.Figure()
    fig.add_trace(go.Bar(name="2023-24 Actual",x=fc_df["sector"],y=fc_df["year_2324_L"],
        marker_color="#94a3b8",
        text=fc_df["year_2324_L"].apply(lambda v: f"₹{v:,.0f} L"),
        textposition="outside",textfont=dict(size=13,color="#334155",family="Segoe UI")))
    fig.add_trace(go.Bar(name="2025-26 Actual",x=fc_df["sector"],y=fc_df["year_2526_L"],
        marker_color="#3b82f6",
        text=fc_df["year_2526_L"].apply(lambda v: f"₹{v:,.0f} L"),
        textposition="outside",textfont=dict(size=13,color="#334155",family="Segoe UI")))
    fig.add_trace(go.Bar(name="2026-27 Forecast",x=fc_df["sector"],y=fc_df["forecast_2627_L"],
        marker_color="#10b981",
        text=fc_df["forecast_2627_L"].apply(lambda v: f"₹{v:,.0f} L"),
        textposition="outside",textfont=dict(size=13,color="#334155",family="Segoe UI")))
    fig.update_layout(
        barmode="group",
        title=dict(text="3-Year Trend & 2026-27 Forecast (₹ Lakhs)",
                   font=dict(size=17,color="#1e293b",family="Segoe UI"),
                   x=0.5,xanchor="center"),
        template=T, height=520,
        margin=dict(t=70,b=120,l=70,r=20),
        xaxis=dict(tickfont=dict(size=13,color="#475569")),
        yaxis=dict(title="₹ Lakhs",tickfont=dict(size=12,color="#475569"),
                   gridcolor="#e2e8f0",zeroline=False),
        legend=dict(orientation="h",yanchor="bottom",y=-0.26,
                    xanchor="center",x=0.5,
                    font=dict(size=13,color="#475569",family="Segoe UI"),
                    bgcolor="rgba(248,250,252,0.95)",
                    bordercolor="#e2e8f0",borderwidth=1),
        plot_bgcolor="rgba(248,250,252,1)",paper_bgcolor="white",
    )
    return fig

def ch_yoy(df):
    agg=df.groupby("sector").agg(exp_2324=("exp_2324","sum"),expenditure=("expenditure","sum")).reset_index()
    agg["growth"]=(agg["expenditure"]-agg["exp_2324"])/agg["exp_2324"]*100
    fig=px.bar(agg,x="sector",y="growth",color="sector",color_discrete_map=SECTOR_COLORS,
        title="YoY Growth: 2023-24 → 2025-26 (%)",template=T,
        text=agg["growth"].apply(lambda x:f"{x:+.1f}%"))
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False,margin=dict(t=40,b=10))
    return fig

# ═══════════════════════════════════════════════════════════════════════════════
# CHATBOT — injected into Streamlit main page DOM via st.markdown
# WHY NOT components.html: that renders in a sandboxed iframe where
#   position:fixed is relative to the iframe box (height=100px, invisible),
#   not the browser window. window.parent.location is also CSP-blocked.
# HOW IT WORKS:
#   st.markdown injects HTML/CSS/JS into the real page DOM → position:fixed
#   anchors to actual viewport bottom-right corner.
#   JS sends question via window.location?_cq=... → Streamlit reruns →
#   agent.respond() → history updated → re-rendered with new JSON → panel
#   reopens automatically via sessionStorage.
# ═══════════════════════════════════════════════════════════════════════════════
def render_chatbot():
    import json, urllib.parse

    agent = st.session_state.get("agent")

    # ── Process question from URL param ───────────────────────────────────
    params  = st.query_params
    chat_q  = params.get("_cq", "")
    chat_ts = params.get("_ct", "")
    if chat_q and chat_ts and chat_ts != st.session_state.get("_last_chat_ts", ""):
        st.session_state["_last_chat_ts"] = chat_ts
        try:    decoded = urllib.parse.unquote(chat_q)
        except: decoded = chat_q
        if agent and decoded:
            resp = agent.respond(decoded)
            st.session_state.chat_history.append({
                "user": decoded, "bot": resp["text"],
                "table": resp.get("table"), "chart": resp.get("chart_data"),
            })
        st.query_params.clear()
        st.rerun()

    # ── Serialize history safely for JS ───────────────────────────────────
    hist_js = []
    for item in st.session_state.chat_history[-50:]:
        u = str(item.get("user","")).replace("\\","\\\\").replace("`","'").replace("\n"," ")
        b = str(item.get("bot", "")).replace("\\","\\\\").replace("`","'").replace("\n","\\n")
        hist_js.append({"u": u, "b": b})
    hist_json = json.dumps(hist_js, ensure_ascii=False)

    ready = ("Hi! Ask me anything about Maharashtra budget — Agriculture, "
             "Education, Skills &amp; Social Justice.") if agent else             "⚠️ Data not loaded. Place 4 Excel files in data/ folder and restart."

    # ── Inject into main page DOM ─────────────────────────────────────────
    st.markdown(f"""
<style>
#_cf{{position:fixed;bottom:26px;right:26px;z-index:2147483647;
  width:62px;height:62px;border-radius:50%;border:none;cursor:pointer;
  background:linear-gradient(135deg,#4f46e5,#7c3aed);
  box-shadow:0 4px 20px rgba(79,70,229,.55);
  display:flex;align-items:center;justify-content:center;
  font-size:1.6rem;color:#fff;
  transition:transform .2s,box-shadow .2s;
  animation:_cfp 2.8s infinite;}}
#_cf:hover{{transform:scale(1.1);box-shadow:0 6px 28px rgba(79,70,229,.75);}}
@keyframes _cfp{{
  0%,100%{{box-shadow:0 4px 20px rgba(79,70,229,.55),0 0 0 0 rgba(79,70,229,.4);}}
  60%{{box-shadow:0 4px 20px rgba(79,70,229,.55),0 0 0 14px rgba(79,70,229,0);}}}}

#_cp{{position:fixed;bottom:100px;right:26px;z-index:2147483646;
  width:375px;background:#fff;border-radius:18px;
  box-shadow:0 20px 60px rgba(0,0,0,.18),0 2px 12px rgba(79,70,229,.1);
  display:flex;flex-direction:column;overflow:hidden;
  font-family:'Segoe UI',Arial,sans-serif;max-height:580px;
  transform:scale(.9) translateY(16px);transform-origin:bottom right;
  opacity:0;pointer-events:none;
  transition:transform .28s cubic-bezier(.34,1.56,.64,1),opacity .2s;}}
#_cp._on{{transform:scale(1) translateY(0);opacity:1;pointer-events:all;}}

#_ch{{background:linear-gradient(135deg,#4f46e5,#7c3aed);
  padding:14px 16px;display:flex;align-items:center;gap:12px;flex-shrink:0;}}
#_chav{{width:42px;height:42px;border-radius:50%;
  background:rgba(255,255,255,.2);border:2px solid rgba(255,255,255,.3);
  display:flex;align-items:center;justify-content:center;font-size:1.2rem;flex-shrink:0;}}
._chin{{flex:1;}}
._chn{{color:#fff;font-weight:700;font-size:.95rem;}}
._chs{{color:rgba(255,255,255,.8);font-size:.68rem;margin-top:2px;display:flex;align-items:center;gap:5px;}}
._cdot{{width:7px;height:7px;border-radius:50%;background:#4ade80;box-shadow:0 0 5px #4ade80;}}
#_cc{{background:rgba(255,255,255,.18);border:none;color:#fff;border-radius:50%;
  width:30px;height:30px;cursor:pointer;font-size:1rem;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:background .15s;}}
#_cc:hover{{background:rgba(255,255,255,.32);}}

#_cm{{flex:1;overflow-y:auto;padding:14px 12px;background:#f8fafc;
  display:flex;flex-direction:column;gap:10px;
  min-height:200px;max-height:310px;scroll-behavior:smooth;}}
#_cm::-webkit-scrollbar{{width:3px;}}
#_cm::-webkit-scrollbar-thumb{{background:#cbd5e1;border-radius:3px;}}

._cb{{display:flex;gap:8px;align-items:flex-start;}}
._cbav{{width:28px;height:28px;border-radius:50%;
  background:linear-gradient(135deg,#4f46e5,#7c3aed);
  display:flex;align-items:center;justify-content:center;
  font-size:.75rem;flex-shrink:0;margin-top:2px;}}
._cbb{{background:#fff;color:#1e293b;border-radius:4px 14px 14px 14px;
  padding:9px 13px;font-size:.81rem;line-height:1.55;
  box-shadow:0 1px 5px rgba(0,0,0,.08);max-width:87%;word-break:break-word;}}
._cu{{display:flex;justify-content:flex-end;}}
._cub{{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;
  border-radius:14px 14px 4px 14px;padding:9px 13px;font-size:.81rem;line-height:1.5;
  max-width:82%;word-break:break-word;box-shadow:0 2px 8px rgba(79,70,229,.28);}}
._cdt{{display:flex;gap:4px;padding:2px 0;align-items:center;}}
._cd{{width:7px;height:7px;border-radius:50%;background:#a78bfa;animation:_cdb 1.3s infinite;}}
._cd:nth-child(2){{animation-delay:.18s;}}._cd:nth-child(3){{animation-delay:.36s;}}
@keyframes _cdb{{0%,60%,100%{{transform:translateY(0);opacity:.5;}}30%{{transform:translateY(-6px);opacity:1;}}}}

#_ck{{padding:8px 10px 6px;background:#fff;border-top:1px solid #f1f5f9;
  display:flex;flex-wrap:wrap;gap:5px;flex-shrink:0;}}
._ck{{background:#f1f5f9;border:1px solid #e2e8f0;border-radius:20px;padding:4px 10px;
  font-size:.69rem;font-weight:500;cursor:pointer;color:#4f46e5;
  font-family:'Segoe UI',sans-serif;transition:background .15s,border-color .15s;white-space:nowrap;}}
._ck:hover{{background:#ede9fe;border-color:#c4b5fd;}}

#_ci{{padding:10px 12px 14px;background:#fff;border-top:1px solid #e2e8f0;
  display:flex;gap:8px;align-items:center;flex-shrink:0;}}
#_cinp{{flex:1;border:1.5px solid #e2e8f0;border-radius:12px;padding:9px 13px;
  font-size:.83rem;outline:none;color:#1e293b;font-family:'Segoe UI',sans-serif;background:#fff;
  transition:border-color .2s,box-shadow .2s;}}
#_cinp:focus{{border-color:#7c3aed;box-shadow:0 0 0 3px rgba(124,58,237,.1);}}
#_cinp::placeholder{{color:#94a3b8;}}
#_csnd{{width:40px;height:40px;border-radius:12px;border:none;
  background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;cursor:pointer;
  font-size:.9rem;flex-shrink:0;display:flex;align-items:center;justify-content:center;
  box-shadow:0 2px 8px rgba(79,70,229,.35);transition:transform .15s,opacity .15s;}}
#_csnd:hover{{transform:scale(1.08);}}
#_csnd:disabled{{opacity:.4;cursor:not-allowed;transform:none;}}
</style>

<button id="_cf" onclick="_cft()" title="Finance AI Assistant">💰</button>
<div id="_cp">
  <div id="_ch">
    <div id="_chav">💰</div>
    <div class="_chin">
      <div class="_chn">Finance AI Assistant</div>
      <div class="_chs"><span class="_cdot"></span>4 MPSIMS sheets &bull; Live answers</div>
    </div>
    <button id="_cc" onclick="_cft()">✕</button>
  </div>
  <div id="_cm">
    <div style="text-align:center;color:#94a3b8;font-size:.65rem;padding:2px 0 6px;">Today</div>
    <div class="_cb"><div class="_cbav">💰</div>
    <div class="_cbb">{ready}<br><br><span style="color:#7c3aed;font-weight:600;">Try a chip or type below ↓</span></div></div>
  </div>
  <div id="_ck">
    <span class="_ck" onclick="_cfa('Show all zero expenditure schemes')">🚨 Zero Spend</span>
    <span class="_ck" onclick="_cfa('Top 5 high priority schemes')">🔥 Top 5</span>
    <span class="_ck" onclick="_cfa('Forecast budget 2026-27')">🔮 Forecast</span>
    <span class="_ck" onclick="_cfa('SDG alignment summary')">🌍 SDG</span>
    <span class="_ck" onclick="_cfa('Compare expenditure across all sectors')">⚖️ Compare</span>
    <span class="_ck" onclick="_cfa('Gap analysis unspent funds')">💰 Gap</span>
    <span class="_ck" onclick="_cfa('Agriculture sector budget summary')">🌾 Agriculture</span>
    <span class="_ck" onclick="_cfa('Education sector utilization')">📚 Education</span>
    <span class="_ck" onclick="_cfa('Skills sector budget summary')">🔧 Skills</span>
    <span class="_ck" onclick="_cfa('Social Justice sector summary')">⚖️ Social Justice</span>
    <span class="_ck" onclick="_cfa('Show all pending status schemes')">⏳ Pending</span>
    <span class="_ck" onclick="_cfa('Show rejected schemes')">❌ Rejected</span>
  </div>
  <div id="_ci">
    <input id="_cinp" placeholder="Ask about budgets, schemes, forecasts…"
           onkeydown="if(event.key==='Enter'){{event.preventDefault();_cfs();}}"/>
    <button id="_csnd" onclick="_cfs()">➤</button>
  </div>
</div>

<script>
(function(){{
  var _on=false;
  var H={hist_json};

  /* render saved history immediately */
  (function(){{
    if(!H.length) return;
    var m=document.getElementById('_cm');
    H.forEach(function(h){{_au(h.u,m);_ab(h.b,m);}});
    m.scrollTop=99999;
  }})();

  window._cft=function(){{
    _on=!_on;
    document.getElementById('_cp').classList.toggle('_on',_on);
    if(_on) setTimeout(function(){{document.getElementById('_cinp').focus();}},240);
    try{{sessionStorage.setItem('_cbo',_on?'1':'0');}}catch(e){{}}
  }};

  window._cfa=function(q){{document.getElementById('_cinp').value=q;_cfs();}};

  function _fmt(s){{
    return String(s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/[*][*](.*?)[*][*]/g,'<strong>$1</strong>')
      .replace(/[*](.*?)[*]/g,'<em>$1</em>')
      .replace(/\\n/g,'<br>')
      .replace(/^[-•] /gm,'• ');
  }}

  function _au(t,c){{
    var m=c||document.getElementById('_cm');
    var d=document.createElement('div');d.className='_cu';
    d.innerHTML='<div class="_cub">'+String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</div>';
    m.appendChild(d);m.scrollTop=99999;
  }}
  function _ab(t,c){{
    var m=c||document.getElementById('_cm');
    var d=document.createElement('div');d.className='_cb';
    d.innerHTML='<div class="_cbav">💰</div><div class="_cbb">'+_fmt(t)+'</div>';
    m.appendChild(d);m.scrollTop=99999;
  }}
  function _showt(){{
    var m=document.getElementById('_cm');
    if(document.getElementById('_cbtd')) return;
    var d=document.createElement('div');d.className='_cb';d.id='_cbtd';
    d.innerHTML='<div class="_cbav">💰</div><div class="_cbb"><div class="_cdt"><div class="_cd"></div><div class="_cd"></div><div class="_cd"></div></div></div>';
    m.appendChild(d);m.scrollTop=99999;
  }}

  window._cfs=function(){{
    var inp=document.getElementById('_cinp');
    var snd=document.getElementById('_csnd');
    var q=inp.value.trim();
    if(!q||snd.disabled) return;
    inp.value='';snd.disabled=true;
    _au(q);_showt();
    try{{sessionStorage.setItem('_cbo','1');}}catch(e){{}}
    var ts=String(Date.now());
    var url=new URL(window.location.href);
    url.searchParams.set('_cq',encodeURIComponent(q));
    url.searchParams.set('_ct',ts);
    window.location.href=url.toString();
  }};

  /* reopen after Streamlit rerun */
  try{{
    if(sessionStorage.getItem('_cbo')==='1')
      setTimeout(function(){{if(!_on)_cft();}},350);
  }}catch(e){{}}
}})();
</script>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB RENDERERS
# ═══════════════════════════════════════════════════════════════════════════════
def tab1_alerts(df,kpis):
    st.subheader("🚨 Critical Alerts")
    c1,c2,c3,c4=st.columns(4)
    c1.markdown(kcard("Zero-Spend Schemes",str(kpis.get("zero_spend_schemes",0)),"red"),unsafe_allow_html=True)
    c2.markdown(kcard("Rejected Schemes",str(kpis.get("rejected_schemes",0)),"red"),unsafe_allow_html=True)
    c3.markdown(kcard("Pending Schemes",str(kpis.get("status_P_count",0)),"amber"),unsafe_allow_html=True)
    c4.markdown(kcard("At-Risk Amount",lakhs_to_display(kpis.get("zero_spend_amount_L",0)),"red"),unsafe_allow_html=True)

    z=df[(df["expenditure"]==0)&(df["released"]>10)].copy()
    st.markdown(f'<div class="alert-red">🚨 <b>{len(z)} schemes</b> received funds but spent ₹0! Total at risk: <b>{lakhs_to_display(z["released"].sum())}</b></div>',unsafe_allow_html=True)
    if not z.empty:
        d=z[["scheme_name","sector","department","released","scheme_status","sdg_status"]].copy()
        d["released"]=d["released"].apply(lakhs_to_display)
        st.dataframe(d,height=300)
        st.plotly_chart(px.bar(z.head(20),x="scheme_name",y="released",color="sector",
            color_discrete_map=SECTOR_COLORS,title="Zero-Spend Schemes (Released Lakhs)",template=T
            ).update_layout(xaxis_tickangle=-40,margin=dict(t=40,b=80)),width='stretch')

    rej=df[df["scheme_status"]=="R"].copy()
    st.markdown(f'<div class="alert-amber">❌ <b>{len(rej)} Rejected Schemes</b> | Budget: <b>{lakhs_to_display(rej["budget_alloc"].sum())}</b></div>',unsafe_allow_html=True)
    if not rej.empty:
        r2=rej[["scheme_name","sector","department","budget_alloc"]].copy()
        r2["budget_alloc"]=r2["budget_alloc"].apply(lakhs_to_display)
        st.dataframe(r2,height=200)

def tab2_summary(df,kpis):
    st.subheader("📊 Executive Summary")
    cols=st.columns(6)
    specs=[("Total Schemes",str(kpis.get("total_schemes",0)),"blue"),
           ("Budget 2025-26",lakhs_to_display(kpis.get("total_budget_L",0)),""),
           ("Released",lakhs_to_display(kpis.get("total_released_L",0)),"teal"),
           ("Expenditure",lakhs_to_display(kpis.get("total_expenditure_L",0)),"green"),
           ("Utilization",f"{kpis.get('overall_utilization_pct',0):.1f}%",""),
           ("YoY Growth",f"{kpis.get('yoy_growth_pct',0):+.1f}%","indigo")]
    for col,(l,v,c) in zip(cols,specs):
        col.markdown(kcard(l,v,c),unsafe_allow_html=True)
    c1,c2=st.columns(2)
    with c1: st.plotly_chart(ch_funnel(kpis),width='stretch')
    with c2: st.plotly_chart(ch_sector_bar(df,"budget_alloc","Budget by Sector (Lakhs)"),width='stretch')
    c3,c4=st.columns(2)
    with c3:
        sc=compute_decision_scores(df)
        top=sc.nlargest(10,"decision_score")[["scheme_name","sector","department","decision_score","recommendation"]].copy()
        top["decision_score"]=top["decision_score"].apply(lambda x:f"{x:.1f}")
        st.subheader("🔥 Top 10 Scale-Up Candidates")
        st.dataframe(top,height=320)
    with c4: st.plotly_chart(ch_plan_type_pie(df),width='stretch')

def tab3_forecasts(df):
    st.subheader("🔮 2026-27 Forecasts")
    fc=forecast_sector_totals(df)
    st.plotly_chart(ch_forecast(fc),width='stretch')
    cols=st.columns(len(fc))
    for col,(_,r) in zip(cols,fc.iterrows()):
        col.markdown(kcard(r["sector"],f"{r['growth_pct']:+.1f}%","green" if r["growth_pct"]>=0 else "red"),unsafe_allow_html=True)
    st.dataframe(fc.rename(columns={"year_2324_L":"2023-24 Exp","year_2526_L":"2025-26 Exp",
                                     "forecast_2627_L":"2026-27 Forecast","growth_pct":"Growth %"}),height=200)
    st.subheader("🔍 Individual Scheme Forecast (Prophet)")
    sel=st.selectbox("Scheme",sorted(df["scheme_name"].dropna().unique()))
    if st.button("Run Prophet"):
        with st.spinner("Forecasting…"):
            f=forecast_scheme_prophet(sel,df,4)
        if f is not None:
            fig=go.Figure()
            fig.add_trace(go.Scatter(x=f["ds"],y=f["yhat"],mode="lines+markers",name="Forecast",
                line=dict(color="#7c3aed",width=2.5)))
            fig.add_trace(go.Scatter(x=pd.concat([f["ds"],f["ds"][::-1]]),
                y=pd.concat([f["yhat_upper"],f["yhat_lower"][::-1]]),
                fill="toself",fillcolor="rgba(124,58,237,.12)",
                line=dict(color="rgba(255,255,255,0)"),name="80% CI"))
            fig.update_layout(title=f"Prophet: {sel[:50]}",template=T)
            st.plotly_chart(fig,width='stretch')
        else: st.info("Insufficient data for Prophet on this scheme.")

def tab4_trends(df):
    st.subheader("📈 Trend Analysis")
    c1,c2=st.columns(2)
    with c1: st.plotly_chart(ch_radar(df),width='stretch')
    with c2: st.plotly_chart(ch_waterfall(df),width='stretch')
    st.plotly_chart(ch_yoy(df),width='stretch')
    df2=df.copy()
    df2["util_pct"]=df2.apply(lambda r:r["expenditure"]/r["released"]*100 if r["released"]>0 else 0,axis=1)
    st.plotly_chart(px.histogram(df2,x="util_pct",color="sector",nbins=20,
        color_discrete_map=SECTOR_COLORS,title="Utilization % Distribution",template=T,
        labels={"util_pct":"Utilization %"}),width='stretch')

def tab5_heatmap(df):
    st.subheader("🌡️ Utilization Heatmap")
    st.plotly_chart(ch_heatmap(df),width='stretch')
    df2=df.copy()
    df2["util_pct"]=df2.apply(lambda r:min(r["expenditure"]/r["released"]*100,150) if r["released"]>0 else 0,axis=1)
    fig=px.scatter(df2,x="budget_alloc",y="util_pct",color="sector",
        size="released",size_max=40,
        hover_name="scheme_name",color_discrete_map=SECTOR_COLORS,
        title="Budget Size vs Utilization %",template=T,opacity=0.75,
        labels={"budget_alloc":"Budget Allocated (₹ Lakhs)","util_pct":"Utilization % (capped 150%)","sector":"Sector"})
    fig.update_layout(
        title=dict(text="Budget Size vs Utilization %",font=dict(size=15,color="#1e293b"),x=0.5,xanchor="center"),
        height=440,margin=dict(t=60,b=60,l=70,r=20),
        xaxis=dict(title="Budget Allocated (₹ Lakhs)",tickfont=dict(size=12),gridcolor="#e2e8f0"),
        yaxis=dict(title="Utilization % (capped 150%)",tickfont=dict(size=12),gridcolor="#e2e8f0",range=[-5,160]),
        plot_bgcolor="rgba(248,250,252,1)",paper_bgcolor="white",
        legend=dict(title="Sector",font=dict(size=12),bgcolor="rgba(248,250,252,0.9)",bordercolor="#e2e8f0",borderwidth=1),
    )
    st.plotly_chart(fig,width='stretch')

def tab6_decision(df):
    st.subheader("🎯 Decision Matrix")
    st.caption("Score = utilization×0.4 + growth×0.3 + forecast×0.3 × status_weight × SDG_weight")
    st.plotly_chart(ch_scatter_matrix(df),width='stretch')
    sc=compute_decision_scores(df)
    rc=sc["recommendation"].value_counts().reset_index(); rc.columns=["rec","count"]
    c1,c2=st.columns(2)
    with c1:
        fig=px.pie(rc,names="rec",values="count",
            color="rec",color_discrete_map={"🔥 SCALE UP":"#10b981","✅ CONTINUE":"#3b82f6",
            "🟡 MONITOR":"#f59e0b","🔴 REVIEW/PAUSE":"#ef4444"},
            title="Recommendation Distribution",template=T)
        st.plotly_chart(fig,width='stretch')
    with c2:
        d=sc[["scheme_name","sector","department","decision_score","recommendation","util_pct"]].copy()
        d["decision_score"]=d["decision_score"].apply(lambda x:f"{x:.1f}")
        d["util_pct"]=d["util_pct"].apply(lambda x:f"{x:.1f}%")
        st.dataframe(d.sort_values("decision_score",ascending=False),height=380)

def tab7_sdg(df):
    st.subheader("🌍 SDG Alignment")
    st.plotly_chart(ch_sdg(df),width='stretch')
    c1,c2,c3=st.columns(3)
    for col,code,label,clr in [(c1,"A","✅ Applicable","green"),(c2,"P","⏳ Pending","amber"),(c3,"NA","❌ Not Applicable","red")]:
        sub=df[df["sdg_status"]==code]
        col.markdown(kcard(f"{label}\n{lakhs_to_display(sub['budget_alloc'].sum())}",str(len(sub)),clr),unsafe_allow_html=True)
    sc=compute_decision_scores(df[df["sdg_status"]=="A"])
    top=sc.nlargest(15,"decision_score")[["scheme_name","sector","department","decision_score","recommendation","budget_alloc"]].copy()
    top["budget_alloc"]=top["budget_alloc"].apply(lakhs_to_display)
    top["decision_score"]=top["decision_score"].apply(lambda x:f"{x:.1f}")
    st.subheader("🌟 SDG-Applicable High-Priority Schemes")
    st.dataframe(top)

def tab8_crosssector(df):
    st.subheader("⚖️ Cross-Sector Comparison")
    agg=df.groupby("sector").agg(schemes=("scheme_name","count"),
        budget_L=("budget_alloc","sum"),released_L=("released","sum"),
        expenditure_L=("expenditure","sum")).reset_index()
    agg["util_pct"]=agg.apply(lambda r:r["expenditure_L"]/r["released_L"]*100 if r["released_L"]>0 else 0,axis=1)
    fig=go.Figure()
    for col,name,clr in [("budget_L","Budget","#667eea"),("released_L","Released","#7c3aed"),("expenditure_L","Expenditure","#10b981")]:
        fig.add_trace(go.Bar(name=name,x=agg["sector"],y=agg[col],marker_color=clr,
            text=agg[col].apply(lakhs_to_display),textposition="outside"))
    fig.update_layout(barmode="group",title="Sector: Budget vs Released vs Expenditure",template=T,margin=dict(t=50,b=10))
    st.plotly_chart(fig,width='stretch')
    c1,c2=st.columns(2)
    with c1:
        st.plotly_chart(px.bar(agg,x="sector",y="util_pct",color="sector",
            color_discrete_map=SECTOR_COLORS,title="Utilization % by Sector",template=T,
            text=agg["util_pct"].apply(lambda x:f"{x:.1f}%")).update_traces(textposition="outside"),width='stretch')
    with c2:
        try: st.plotly_chart(ch_treemap(df),width='stretch')
        except Exception as e: st.warning(f"Treemap: {e}")

def tab9_gap(df):
    st.subheader("💰 Release-Spend Gap Analysis")
    df3=df.copy(); df3["gap_L"]=df3["released"]-df3["expenditure"]
    total=df3["gap_L"].sum()
    st.markdown(f'<div class="alert-amber">💰 Total Unspent: <b>{lakhs_to_display(total)}</b></div>',unsafe_allow_html=True)
    st.plotly_chart(ch_gap(df),width='stretch')
    c1,c2=st.columns(2)
    with c1:
        gs=df3.groupby("sector")["gap_L"].sum().reset_index()
        st.plotly_chart(px.pie(gs,names="sector",values="gap_L",color="sector",
            color_discrete_map=SECTOR_COLORS,title="Unspent by Sector",template=T),width='stretch')
    with c2:
        top=df3.nlargest(15,"gap_L")[["scheme_name","sector","department","released","expenditure","gap_L"]].copy()
        for c in ["released","expenditure","gap_L"]: top[c]=top[c].apply(lakhs_to_display)
        st.subheader("Top 15 Gap Schemes"); st.dataframe(top,height=360)

def tab10_status(df,kpis):
    st.subheader("🔔 Status Risk Analysis")
    try: st.plotly_chart(ch_sunburst(df),width='stretch')
    except Exception as e: st.warning(f"Sunburst: {e}")
    cols=st.columns(4)
    for col,(code,label,clr) in zip(cols,[("A","Approved","green"),("S","Submitted","blue"),("P","Pending","amber"),("R","Rejected","red")]):
        col.markdown(kcard(f"{label}\n{lakhs_to_display(kpis.get(f'status_{code}_budget_L',0))}",
                           str(kpis.get(f"status_{code}_count",0)),clr),unsafe_allow_html=True)
    pend=df[df["scheme_status"]=="P"].copy()
    st.subheader(f"⏳ {len(pend)} Pending Schemes")
    if not pend.empty:
        d=pend[["scheme_name","sector","department","budget_alloc","released","sdg_status"]].copy()
        for c in ["budget_alloc","released"]: d[c]=d[c].apply(lakhs_to_display)
        st.dataframe(d,height=300)

def tab11_plantype(df):
    st.subheader("📋 Department Analysis")
    agg=df.groupby(["sector","department"]).agg(
        schemes=("scheme_name","count"),budget_L=("budget_alloc","sum"),
        released_L=("released","sum"),expenditure_L=("expenditure","sum")).reset_index()
    agg["util_pct"]=agg.apply(lambda r:r["expenditure_L"]/r["released_L"]*100 if r["released_L"]>0 else 0,axis=1)
    fig=px.bar(agg,x="sector",y="budget_L",color="department",barmode="stack",
        color_discrete_map=PLAN_TYPE_COLORS,title="Budget by Sector & Plan Type (Stacked)",template=T)
    st.plotly_chart(fig,width='stretch')
    c1,c2=st.columns(2)
    with c1: st.plotly_chart(ch_plan_type_pie(df,"Budget Share by Department"),width='stretch')
    with c2:
        d=agg.copy()
        for c in ["budget_L","released_L","expenditure_L"]: d[c]=d[c].apply(lakhs_to_display)
        d["util_pct"]=d["util_pct"].apply(lambda x:f"{x:.1f}%")
        st.dataframe(d,height=380)

def tab12_explorer(df):
    st.subheader("💾 Data Explorer")
    c1,c2,c3,c4=st.columns(4)
    sf=c1.multiselect("Sector",df["sector"].unique(),default=list(df["sector"].unique()),key="ex_sec")
    pf=c2.multiselect("Plan Type",df["department"].unique(),default=list(df["department"].unique()),key="ex_pt")
    stf=c3.multiselect("Status",["A","S","P","R"],default=["A","S","P","R"],key="ex_st")
    ur=c4.slider("Utilization %",0,100,(0,100),key="ex_ur")
    filt=df.copy()
    filt["util_pct"]=filt.apply(lambda r:r["expenditure"]/r["released"]*100 if r["released"]>0 else 0,axis=1)
    if sf: filt=filt[filt["sector"].isin(sf)]
    if pf: filt=filt[filt["department"].isin(pf)]
    if stf: filt=filt[filt["scheme_status"].isin(stf)]
    filt=filt[(filt["util_pct"]>=ur[0])&(filt["util_pct"]<=ur[1])]
    st.caption(f"Showing {len(filt)} of {len(df)} schemes")
    d=filt[["scheme_name","sector","department","budget_alloc","released","expenditure","util_pct","scheme_status","sdg_status"]].copy()
    for c in ["budget_alloc","released","expenditure"]: d[c]=d[c].apply(lakhs_to_display)
    d["util_pct"]=d["util_pct"].apply(lambda x:f"{x:.1f}%")
    st.dataframe(d,height=450)

def tab13_export(df,kpis):
    st.subheader("📤 Export Panel")
    c1,c2=st.columns(2)
    with c1:
        st.markdown("### 📊 Excel Export")
        if st.button("Generate Excel",type="primary"):
            with st.spinner("Generating…"):
                b=export_to_excel(df,kpis)
            st.download_button("⬇️ Download Excel",data=b,
                file_name=f"MPSIMS_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with c2:
        st.markdown("### 📄 PDF Report")
        if st.button("Generate PDF",type="primary"):
            with st.spinner("Generating…"):
                b=export_to_pdf_simple(df,kpis)
            if b:
                st.download_button("⬇️ Download PDF",data=b,
                    file_name=f"MPSIMS_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf")
            else: st.warning("PDF failed — try Excel.")
    st.divider()
    sc=compute_decision_scores(df)
    st.download_button("⬇️ Download CSV (All Schemes + Scores)",
        data=sc.to_csv(index=False).encode(),file_name="mpsims_schemes.csv",mime="text/csv")

def tab14_config():
    st.subheader("⚙️ Configuration & Reference")
    st.subheader("Decision Score Formula")
    st.code("Score = (utilization×0.4 + growth×0.3 + forecast×0.3) × status_weight × SDG_weight",language="python")
    c1,c2=st.columns(2)
    with c1:
        st.subheader("Status Weights"); st.table(pd.DataFrame({"Status":["A","S","P","R"],"Weight":[1.0,0.9,0.7,0.3],"Meaning":["Approved","Submitted","Pending","Rejected"]}))
    with c2:
        st.subheader("SDG Weights"); st.table(pd.DataFrame({"SDG":["A","P","NA"],"Weight":[1.5,1.0,0.8],"Meaning":["Applicable","Pending","Not Applicable"]}))
    st.subheader("Plan Type Reference")
    st.table(pd.DataFrame({"Code":list(PLAN_TYPE_MAP.keys()),"Full Name":list(PLAN_TYPE_MAP.values())}))
    st.subheader("Recommendation Thresholds")
    st.table(pd.DataFrame({"Score":["≥85","≥70","≥50","<50"],"Action":["🔥 SCALE UP","✅ CONTINUE","🟡 MONITOR","🔴 REVIEW/PAUSE"]}))

def tab15_recs(df):
    st.subheader("📋 Actionable Recommendations")
    sc=compute_decision_scores(df)
    for rec,icon in [("🔥 SCALE UP","scale"),("✅ CONTINUE","cont"),("🟡 MONITOR","mon"),("🔴 REVIEW/PAUSE","rev")]:
        sub=sc[sc["recommendation"]==rec].sort_values("decision_score",ascending=rec=="🔴 REVIEW/PAUSE")
        st.subheader(f"{rec} — {len(sub)} Schemes")
        if not sub.empty:
            d=sub[["scheme_name","sector","department","decision_score","util_pct","budget_alloc","scheme_status"]].copy()
            d["decision_score"]=d["decision_score"].apply(lambda x:f"{x:.1f}")
            d["util_pct"]=d["util_pct"].apply(lambda x:f"{x:.1f}%")
            d["budget_alloc"]=d["budget_alloc"].apply(lakhs_to_display)
            st.dataframe(d,height=min(len(sub)*38+60,280))

def tab16_chat(df):
    st.subheader("🗣️ Finance AI — Full Chat")
    st.caption("🔒 All answers from 4 MPSIMS Excel sheets only. No hallucination.")
    st.markdown("""
    <style>
    [data-testid="stChatMessage"] p,[data-testid="stChatMessage"] li,[data-testid="stChatMessage"] span
    {font-size:0.82rem !important;color:#475569 !important;line-height:1.6 !important;}
    [data-testid="stChatMessage"] strong{color:#334155 !important;}
    </style>""",unsafe_allow_html=True)
    agent=st.session_state.agent
    if not agent: st.warning("Load data first."); return
    CHAT_COLORS=["#4f46e5","#10b981","#f59e0b","#ef4444","#3b82f6","#7c3aed","#ec4899","#14b8a6"]
    SECTOR_PAL={"Agriculture":"#10b981","Education":"#3b82f6","Skills":"#f59e0b","Social Justice":"#7c3aed"}
    STATUS_PAL={"A":"#10b981","S":"#3b82f6","P":"#f59e0b","R":"#ef4444",
                "Approved":"#10b981","Submitted":"#3b82f6","Pending":"#f59e0b","Rejected":"#ef4444"}
    def _lakh_label(v):
        try:   return f"₹{float(v):,.1f} L"
        except: return str(v)
    def _fmt_lakh_col(s): return s.apply(_lakh_label)
    def _clean_table(t):
        t=t.copy()
        mkw=["budget","alloc","released","expenditure","spend","amount","gap","lakh"]
        for col in t.columns:
            cl=col.lower()
            if t[col].dtype==object:
                smp=t[col].dropna().astype(str)
                if smp.str.contains("Cr",na=False).any():
                    def _c2l(s):
                        try: return f"₹{float(str(s).replace('₹','').replace('Cr','').replace(',','').strip())*100:,.1f} L"
                        except: return s
                    t[col]=t[col].apply(_c2l)
            elif t[col].dtype in [float,"float64",int,"int64"]:
                if any(k in cl for k in mkw): t[col]=_fmt_lakh_col(t[col])
        return t
    def _top5_util():
        d=df.copy()
        d["util_pct"]=d.apply(lambda r:r["expenditure"]/r["released"]*100 if r["released"]>0 else 0,axis=1)
        d2=d[d["released"]>0].copy()
        d2=d2.nlargest(5,"util_pct")
        labels=[str(n)[:24]+"…" if len(str(n))>24 else str(n) for n in d2["scheme_name"]]
        fig=go.Figure()
        fig.add_trace(go.Bar(name="Released (₹ L)",x=labels,y=d2["released"].tolist(),
            marker_color="#3b82f6",text=[_lakh_label(v) for v in d2["released"]],
            textposition="outside",textfont=dict(size=13,color="#1e293b")))
        fig.add_trace(go.Bar(name="Expenditure (₹ L)",x=labels,y=d2["expenditure"].tolist(),
            marker_color="#10b981",text=[_lakh_label(v) for v in d2["expenditure"]],
            textposition="outside",textfont=dict(size=13,color="#1e293b")))
        fig.update_layout(
            title=dict(text="Top 5 by Utilization — Released vs Expenditure (₹ Lakhs)",
                       font=dict(size=15,color="#1e293b"),x=0.5,xanchor="center"),
            barmode="group",template=T,paper_bgcolor="white",plot_bgcolor="rgba(248,250,252,1)",
            margin=dict(t=60,b=120,l=60,r=20),height=420,
            yaxis=dict(title="₹ Lakhs",gridcolor="#e2e8f0",tickfont=dict(size=12),zeroline=False),
            xaxis=dict(tickfont=dict(size=11)),showlegend=True,
            legend=dict(orientation="h",yanchor="bottom",y=-0.38,xanchor="center",x=0.5,
                        font=dict(size=13,color="#475569"),bgcolor="rgba(248,250,252,0.9)",
                        bordercolor="#e2e8f0",borderwidth=1))
        top=d[d["released"]>0].nlargest(5,"util_pct")[
            ["scheme_name","sector","department","budget_alloc","released","expenditure","util_pct"]].copy()
        top["budget_alloc"]=_fmt_lakh_col(top["budget_alloc"])
        top["released"]=_fmt_lakh_col(top["released"])
        top["expenditure"]=_fmt_lakh_col(top["expenditure"])
        top["util_pct"]=top["util_pct"].apply(lambda x:f"{x:.1f}%")
        top.rename(columns={"budget_alloc":"Budget (L)","released":"Released (L)",
                             "expenditure":"Expenditure (L)","util_pct":"Utilization %"},inplace=True)
        return {"text":"**🔥 Top 5 High-Priority Schemes** (by Utilization = Expenditure ÷ Released)","table":top,"fig":fig}
    def _bc(l): return SECTOR_PAL.get(str(l),STATUS_PAL.get(str(l),None))
    LH=dict(orientation="h",yanchor="bottom",y=-0.32,xanchor="center",x=0.5,
            font=dict(size=13,color="#475569"),bgcolor="rgba(248,250,252,0.9)",bordercolor="#e2e8f0",borderwidth=1)
    def _make_chart(ch):
        ctype=ch.get("type","bar"); xs=ch.get("x",[]); ys=ch.get("y",[]); title=ch.get("title","")
        base=dict(title=dict(text=title,font=dict(size=15,color="#1e293b"),x=0.5,xanchor="center"),
                  template=T,paper_bgcolor="white",plot_bgcolor="rgba(248,250,252,1)",
                  margin=dict(t=60,b=110,l=60,r=20),height=420,legend=LH)
        if ctype=="bar":
            fig=go.Figure()
            for i,(l,v) in enumerate(zip(xs,ys)):
                clr=_bc(l) or CHAT_COLORS[i%len(CHAT_COLORS)]
                fig.add_trace(go.Bar(name=str(l),x=[l],y=[v],marker_color=clr,
                    text=[_lakh_label(v)],textposition="outside",textfont=dict(size=13,color="#1e293b")))
            fig.update_layout(**base,barmode="group",showlegend=True,
                yaxis=dict(title="₹ Lakhs",gridcolor="#e2e8f0",zeroline=False,tickfont=dict(size=12)),
                xaxis=dict(tickfont=dict(size=12)))
        elif ctype=="pie":
            clrs=[_bc(l) or CHAT_COLORS[i%len(CHAT_COLORS)] for i,l in enumerate(xs)]
            fig=go.Figure(go.Pie(labels=xs,values=ys,
                marker=dict(colors=clrs,line=dict(color="white",width=2)),
                texttemplate="%{label}<br><b>%{percent}</b><br>%{customdata}",
                customdata=[_lakh_label(v) for v in ys],
                textfont=dict(size=13),hole=0.38,pull=[0.04]*len(xs)))
            fig.update_layout(title=dict(text=title,font=dict(size=15,color="#1e293b"),x=0.5,xanchor="center"),
                template=T,paper_bgcolor="white",margin=dict(t=60,b=20,l=20,r=150),height=420,showlegend=True,
                legend=dict(orientation="v",yanchor="middle",y=0.5,xanchor="left",x=1.02,
                            font=dict(size=13),bgcolor="rgba(248,250,252,0.9)",bordercolor="#e2e8f0",borderwidth=1))
        else:
            fig=go.Figure(go.Scatter(x=xs,y=ys,name=title,mode="lines+markers+text",
                line=dict(color=CHAT_COLORS[0],width=2.5,shape="spline"),
                marker=dict(size=10,color=CHAT_COLORS[0],line=dict(color="white",width=2)),
                text=[_lakh_label(v) for v in ys],textposition="top center",textfont=dict(size=13,color="#334155"),
                fill="tozeroy",fillcolor="rgba(79,70,229,0.08)"))
            fig.update_layout(**base,showlegend=True,
                yaxis=dict(title="₹ Lakhs",gridcolor="#e2e8f0",zeroline=False,tickfont=dict(size=12)),
                xaxis=dict(tickfont=dict(size=12)))
        return fig
    for item in st.session_state.chat_history:
        with st.chat_message("user"): st.write(item["user"])
        with st.chat_message("assistant",avatar="💰"):
            st.markdown(item["bot"])
            if item.get("table") is not None:
                try:
                    t=item["table"]
                    if not t.empty: st.dataframe(_clean_table(t),height=min(len(t)*42+60,280))
                except: pass
            if item.get("fig") is not None:
                try: st.plotly_chart(item["fig"],use_container_width=True)
                except: pass
            elif item.get("chart") is not None:
                try: st.plotly_chart(_make_chart(item["chart"]),use_container_width=True)
                except: pass
    st.divider()
    CHIPS=[("🚨 Zero Spend","Show zero spend schemes"),("🔥 Top 5","__TOP5_UTIL__"),
           ("🔮 Forecast","Forecast 2026-27"),("🌍 SDG","SDG alignment"),
           ("⚖️ Compare","Compare sector expenditure"),("💰 Gap","Gap analysis"),
           ("⏳ Pending","Pending status schemes"),("❌ Rejected","Rejected schemes"),
           ("📉 Underutilized","Top 5 underutilized"),("🌾 Agri","Agriculture budget"),
           ("📚 Education","Education expenditure"),("⚖️ Social","Social Justice summary")]
    chip_cols=st.columns(6)
    for i,(lbl,qry) in enumerate(CHIPS):
        with chip_cols[i%6]:
            if st.button(lbl,key=f"ch16_{i}"):
                if qry=="__TOP5_UTIL__":
                    res=_top5_util()
                    st.session_state.chat_history.append(
                        {"user":"Top 5 High-Priority (by Utilization)","bot":res["text"],
                         "table":res["table"],"chart":None,"fig":res["fig"]})
                else:
                    r=agent.respond(qry); t=r.get("table")
                    st.session_state.chat_history.append(
                        {"user":qry,"bot":r["text"],
                         "table":_clean_table(t) if t is not None and not t.empty else t,
                         "chart":r.get("chart_data"),"fig":None})
                st.rerun()
    q=st.chat_input("Ask about budgets, schemes, forecasts, SDG, plan types…")
    if q:
        if any(k in q.lower() for k in ["top 5","scale up","high priority","utilization","utilisation"]):
            res=_top5_util()
            st.session_state.chat_history.append(
                {"user":q,"bot":res["text"],"table":res["table"],"chart":None,"fig":res["fig"]})
        else:
            r=agent.respond(q); t=r.get("table")
            st.session_state.chat_history.append(
                {"user":q,"bot":r["text"],
                 "table":_clean_table(t) if t is not None and not t.empty else t,
                 "chart":r.get("chart_data"),"fig":None})
        st.rerun()
    if st.session_state.chat_history:
        if st.button("🗑️ Clear Chat"):
            st.session_state.chat_history=[]; st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    init_session()

    # ── Floating chatbot (handles query params too) ────────────────────────
    render_chatbot()

    # ── Header ─────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="mpsims-header">
      <div class="title-block">
        <h1>💰 MPSIMS Maharashtra Finance Dashboard</h1>
        <p>Maharashtra Public Scheme Information & Monitoring System | Annual Plan 2025-26</p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Data guard ──────────────────────────────────────────────────────────
    if not st.session_state.data_loaded:
        st.info("⚙️ Loading data from `data/` folder…")
        if st.session_state.get("_load_err"):
            st.error(f"Load error: {st.session_state['_load_err']}")
        st.markdown("""
        ### Setup Instructions
        Add your 4 Excel files to the `data/` folder next to `app.py` and restart:
        ```
        data/MPSIMSAgriculturePlanYear25-26.xlsx
        data/MPSIMSScheelEducationPlanYear25-26.xlsx
        data/MPSIMSSkillPlanYear25-26.xlsx
        data/MPSIMSSociaslJusticePlanYear25-26.xlsx
        ```
        """)
        if st.button("🔄 Retry Auto-Load"):
            st.session_state.data_loaded = False
            _autoload_data_folder()
            st.rerun()
        return

    df_full = st.session_state.df
    kpis    = st.session_state.kpis

    # ── FILTER BAR ──────────────────────────────────────────────────────────
    with st.container():
        fc1,fc2,fc3,fc4,fc5 = st.columns([2.5,2.0,1.5,1.5,0.8])
        f_dept   = fc1.multiselect("🏢 Department",
            sorted(df_full["department"].dropna().unique()),
            default=sorted(df_full["department"].dropna().unique()), key="f_dept")
        plan_type_opts = sorted(df_full["plan_type"].dropna().unique()) if "plan_type" in df_full.columns else []
        f_plan_type = fc2.multiselect("📋 Plan Type",
            plan_type_opts, default=plan_type_opts, key="f_plan_type")
        f_sdg    = fc3.multiselect("🌍 SDG",["A","P","NA"],
            default=["A","P","NA"], key="f_sdg")
        f_status = fc4.multiselect("📊 Status",["A","S","P","R"],
            default=["A","S","P","R"], key="f_st")
        fc5.markdown("<br>",unsafe_allow_html=True)
        if fc5.button("🔄 Reset",key="f_reset"):
            for k in ["f_dept","f_plan_type","f_sdg","f_st"]:
                if k in st.session_state: del st.session_state[k]
            st.rerun()

    df = apply_filters(df_full, [], f_dept, f_sdg, f_status, f_plan_type if plan_type_opts else [])
    kpis_f = compute_kpis(df)

    if df.empty:
        st.warning("No schemes match the current filters. Reset to see all data.")
        return

    # ── Global KPI banner ───────────────────────────────────────────────────
    k1,k2,k3,k4,k5,k6,k7,k8 = st.columns(8)
    banner=[
        (k1,"Schemes",str(kpis_f.get("total_schemes",0)),"blue"),
        (k2,"Budget",lakhs_to_display(kpis_f.get("total_budget_L",0)),""),
        (k3,"Released",lakhs_to_display(kpis_f.get("total_released_L",0)),"teal"),
        (k4,"Expenditure",lakhs_to_display(kpis_f.get("total_expenditure_L",0)),"green"),
        (k5,"Utilization",f"{kpis_f.get('overall_utilization_pct',0):.1f}%",""),
        (k6,"🚨 Zero Spend",str(kpis_f.get("zero_spend_schemes",0)),"red"),
        (k7,"❌ Rejected",str(kpis_f.get("rejected_schemes",0)),"red"),
        (k8,"🔥 Scale-Up",str(kpis_f.get("scale_up_count",0)),"teal"),
    ]
    for col,label,val,clr in banner:
        col.markdown(kcard(label,val,clr),unsafe_allow_html=True)

    st.divider()

    # ── 16 Tabs ─────────────────────────────────────────────────────────────
    tabs = st.tabs([
        "🚨 Critical Alerts","📊 Executive Summary","🔮 Forecasts","📈 Trends",
        "🌡️ Heatmap","🎯 Decision Matrix","🌍 SDG","⚖️ Cross-Sector",
        "💰 Gap Analysis","🔔 Status Risks","📋 Departments","💾 Data Explorer",
        "📤 Export","⚙️ Config","📊 Recommendations","🗣️ Chatbot",
    ])
    with tabs[0]:  tab1_alerts(df,kpis_f)
    with tabs[1]:  tab2_summary(df,kpis_f)
    with tabs[2]:  tab3_forecasts(df)
    with tabs[3]:  tab4_trends(df)
    with tabs[4]:  tab5_heatmap(df)
    with tabs[5]:  tab6_decision(df)
    with tabs[6]:  tab7_sdg(df)
    with tabs[7]:  tab8_crosssector(df)
    with tabs[8]:  tab9_gap(df)
    with tabs[9]:  tab10_status(df,kpis_f)
    with tabs[10]: tab11_plantype(df)
    with tabs[11]: tab12_explorer(df)
    with tabs[12]: tab13_export(df,kpis_f)
    with tabs[13]: tab14_config()
    with tabs[14]: tab15_recs(df)
    with tabs[15]: tab16_chat(df)

if __name__ == "__main__":
    main()
