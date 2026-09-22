import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import copy, json, random
import plotly.graph_objects as go
import plotly.express as px

from data import (
    ROUTES, SLOT_LABELS, DAY_LABELS, DAY_NAMES, CITIES,
    DEFAULT_BUSES, DEFAULT_DRIVERS, DEFAULT_CONDUCTORS,
    TOTAL_TRIPS, N_DAYS, N_SLOTS, BUSES_PER_SLOT,
)
from aco import ACO
from dpso import DPSO

#  Page config
st.set_page_config(
    page_title="SmartBus · PT Restu",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');
:root{--red:#C0392B;--red-dark:#96281B;--red-light:#FDECEA;--ink:#1A1A2E;--ink2:#2D2D44;--mist:#F5F6FA;--border:#E2E4EC;--green:#1E8449;--amber:#D68910;--blue:#1A5276;}
html,body,[class*="css"]{font-family:'Inter',sans-serif;color:var(--ink);}
[data-testid="stSidebar"]{background:var(--ink)!important;}
[data-testid="stSidebar"] *{color:#E8E8F0!important;}
[data-testid="stSidebar"] hr{border-color:#333355!important;}
#MainMenu,footer,header{visibility:hidden;}
.topbar{display:flex;align-items:center;gap:14px;padding:18px 0 6px;border-bottom:2px solid var(--red);margin-bottom:28px;}
.topbar-logo{background:var(--red);color:white;font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:22px;width:46px;height:46px;border-radius:10px;display:flex;align-items:center;justify-content:center;}
.topbar-title h1{font-size:20px;font-weight:700;margin:0;color:var(--ink);font-family:'Space Grotesk',sans-serif;}
.topbar-title p{font-size:12px;color:#888;margin:0;}
.topbar-badge{margin-left:auto;background:var(--red-light);color:var(--red);font-size:11px;font-weight:600;padding:4px 10px;border-radius:20px;border:1px solid #f5bcb8;}
.metric-card{background:white;border:1px solid var(--border);border-radius:12px;padding:16px 20px;border-top:3px solid var(--red);}
.metric-card .val{font-family:'Space Grotesk',sans-serif;font-size:28px;font-weight:700;color:var(--red);line-height:1;}
.metric-card .lbl{font-size:11px;color:#888;margin-top:4px;text-transform:uppercase;letter-spacing:.5px;}
.sec-header{font-family:'Space Grotesk',sans-serif;font-size:15px;font-weight:600;color:var(--ink);margin:24px 0 12px;display:flex;align-items:center;gap:8px;}
.sec-header::after{content:'';flex:1;height:1px;background:var(--border);margin-left:8px;}
.badge{display:inline-block;padding:3px 9px;border-radius:12px;font-size:11px;font-weight:600;}
.badge-green{background:#D5F5E3;color:var(--green);}
.badge-red{background:var(--red-light);color:var(--red);}
.badge-amber{background:#FDEBD0;color:var(--amber);}
.stButton>button{background:var(--red)!important;color:white!important;border:none!important;border-radius:8px!important;font-weight:600!important;font-family:'Space Grotesk',sans-serif!important;padding:10px 24px!important;}
.stButton>button:hover{background:var(--red-dark)!important;}
.stTabs [aria-selected="true"]{color:var(--red)!important;border-bottom-color:var(--red)!important;}
.card{background:white;border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:16px;}
.log-box{background:#0D1117;color:#58D68D;font-family:'Courier New',monospace;font-size:12px;padding:14px 16px;border-radius:10px;max-height:260px;overflow-y:auto;line-height:1.8;}
.phase-pill{display:inline-block;background:var(--ink2);color:white;font-size:11px;font-weight:600;padding:4px 10px;border-radius:20px;font-family:'Space Grotesk',sans-serif;margin-right:6px;}
.assign-box{background:#0D1117;color:#CDD6F4;font-family:'Courier New',monospace;font-size:11.5px;padding:16px;border-radius:10px;max-height:480px;overflow-y:auto;line-height:1.7;white-space:pre;}
.del-btn button{background:#dc3545!important;font-size:11px!important;padding:4px 10px!important;}
</style>
""", unsafe_allow_html=True)

# Session state
def _init_state():
    if "buses"       not in st.session_state: st.session_state.buses       = copy.deepcopy(DEFAULT_BUSES)
    if "drivers"     not in st.session_state: st.session_state.drivers     = copy.deepcopy(DEFAULT_DRIVERS)
    if "conductors"  not in st.session_state: st.session_state.conductors  = copy.deepcopy(DEFAULT_CONDUCTORS)
    if "aco_result"  not in st.session_state: st.session_state.aco_result  = None
    if "dpso_result" not in st.session_state: st.session_state.dpso_result = None
    if "aco_log"     not in st.session_state: st.session_state.aco_log     = []
    if "dpso_log"    not in st.session_state: st.session_state.dpso_log    = []

_init_state()

# Sidebar
with st.sidebar:
    st.markdown("""
    <div style="padding:16px 0 8px;">
      <div style="font-family:'Space Grotesk',sans-serif;font-size:18px;font-weight:700;color:white;">🚌 PT Restu</div>
      <div style="font-size:11px;color:#888;margin-top:2px;">SmartBus Scheduler</div>
    </div><hr/>
    """, unsafe_allow_html=True)
    page = st.radio("Menu",
        ["Dashboard","Armada & Kru","Rute Jaringan","Optimasi Jadwal","Hasil & Laporan"],
        label_visibility="collapsed")
    st.markdown("<hr/>", unsafe_allow_html=True)
    nb = len(st.session_state.buses)
    nd = len(st.session_state.drivers)
    nc = len(st.session_state.conductors)
    st.markdown(f"""
    <div style="font-size:12px;color:#aaa;line-height:2.2;">
      🚌 {nb} Bus &nbsp;·&nbsp; 👤 {nd} Driver<br/>
      🎟️ {nc} Kondektur &nbsp;·&nbsp; 🗺️ {len(ROUTES)} Rute<br/>
      📅 {TOTAL_TRIPS} Trip/Minggu
    </div>""", unsafe_allow_html=True)

# Top bar
st.markdown("""
<div class="topbar">
  <div class="topbar-logo">R</div>
  <div class="topbar-title">
    <h1>PT Restu Ibu Putera</h1>
    <p>Sistem Penjadwalan Armada Bus Antar Kota — Lintas Jawa</p>
  </div>
  <div class="topbar-badge">Hybrid ACO + DPSO</div>
</div>
""", unsafe_allow_html=True)

# DASHBOARD
if page == "Dashboard":
    aco_r  = st.session_state.aco_result
    dpso_r = st.session_state.dpso_result
    cov  = aco_r["stats"]["coverage_pct"]  if aco_r  else 0
    pen  = dpso_r["stats"]["penalty"]      if dpso_r else "-"

    cols = st.columns(5)
    def mk(col, v, l):
        col.markdown(f'<div class="metric-card"><div class="val">{v}</div><div class="lbl">{l}</div></div>', unsafe_allow_html=True)
    mk(cols[0], nb,  "Total Bus")
    mk(cols[1], nd,  "Total Driver")
    mk(cols[2], nc,  "Kondektur")
    mk(cols[3], f"{cov:.0f}%", "Coverage Rute")
    mk(cols[4], ("✓" if pen == 0 else ("✗" if isinstance(pen, int) else "—")), "Zero Conflict")

    st.markdown('<div class="sec-header">Status Optimasi</div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown('<span class="phase-pill">FASE 1</span> Ant Colony Optimization', unsafe_allow_html=True)
        if aco_r:
            s = aco_r["stats"]
            st.markdown('<span class="badge badge-green">✓ Selesai</span>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame({
                "Metrik":["Total Trip","Rute Unik","Coverage","Teleportasi","Jarak Total","Fitness"],
                "Nilai": [s["total_trips"],s["unique_routes"],f"{s['coverage_pct']}%",
                          s["teleports"],f"{s['total_distance']:,} km",f"{aco_r['fitness']:.1f}"],
            }), use_container_width=True, hide_index=True)
        else:
            st.markdown('<span class="badge badge-amber">Belum Dijalankan</span>', unsafe_allow_html=True)
            st.info("Jalankan optimasi di menu **Optimasi Jadwal**.")

    with col_b:
        st.markdown('<span class="phase-pill">FASE 2</span> Discrete PSO', unsafe_allow_html=True)
        if dpso_r:
            ds = dpso_r["stats"]
            hard = ds.get("overlap",0)+ds.get("maintenance",0)+ds.get("leave_drv",0)+ds.get("leave_cnd",0)
            st.markdown('<span class="badge badge-green">✓ Selesai</span>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame({
                "Metrik":["Bus Terpakai","Driver Terpakai","Kondektur Terpakai","Hard Violations","Penalti Total","Fitness"],
                "Nilai": [f"{ds['unique_buses']}/{nb}",f"{ds['unique_drivers']}/{nd}",
                          f"{ds['unique_conductors']}/{nc}",hard,f"{ds['penalty']:,}",f"{dpso_r['fitness']:.1f}"],
            }), use_container_width=True, hide_index=True)
        else:
            st.markdown('<span class="badge badge-amber">Belum Dijalankan</span>', unsafe_allow_html=True)
            st.info("ACO harus selesai terlebih dahulu.")

    st.markdown('<div class="sec-header">Peta Jaringan Rute Jawa</div>', unsafe_allow_html=True)
    city_coords = {
        "Surabaya":(112.75,-7.25),"Malang":(112.62,-7.98),"Kediri":(112.02,-7.82),
        "Blitar":(112.17,-8.10),"Madiun":(111.53,-7.63),"Solo":(110.83,-7.57),
        "Yogyakarta":(110.37,-7.80),"Semarang":(110.42,-7.00),"Purwokerto":(109.24,-7.42),
        "Tegal":(109.13,-6.87),"Cirebon":(108.56,-6.73),"Bandung":(107.60,-6.92),
        "Jakarta":(106.85,-6.21),"Bekasi":(107.00,-6.24),"Serang":(106.15,-6.12),
    }
    active = set(aco_r["chain"]) if aco_r else set()
    fig = go.Figure()
    for r in ROUTES:
        o,d = r["origin"],r["dest"]
        if o in city_coords and d in city_coords:
            ox,oy = city_coords[o]; dx,dy = city_coords[d]
            col = "#C0392B" if r["id"] in active else "#D5D8DC"
            w   = 2.5       if r["id"] in active else 0.8
            fig.add_trace(go.Scatter(x=[ox,dx,None],y=[oy,dy,None],mode="lines",
                line=dict(color=col,width=w),hoverinfo="skip",showlegend=False))
    for city,(cx,cy) in city_coords.items():
        fig.add_trace(go.Scatter(x=[cx],y=[cy],mode="markers+text",
            marker=dict(size=12,color="#1A1A2E",line=dict(color="white",width=2)),
            text=[city],textposition="top center",textfont=dict(size=10,family="Space Grotesk"),
            hovertemplate=f"<b>{city}</b><extra></extra>",showlegend=False))
    fig.update_layout(height=360,margin=dict(l=0,r=0,t=0,b=0),
        xaxis=dict(showgrid=False,zeroline=False,showticklabels=False),
        yaxis=dict(showgrid=False,zeroline=False,showticklabels=False),
        plot_bgcolor="#F5F6FA",paper_bgcolor="#F5F6FA")
    st.plotly_chart(fig, use_container_width=True)

# ARMADA & KRU
elif page == "Armada & Kru":
    tab_bus, tab_drv, tab_cnd = st.tabs(["🚌 Armada Bus","👤 Driver","🎟️ Kondektur"])

    # BUS
    with tab_bus:
        st.markdown('<div class="sec-header">Daftar Armada Bus</div>', unsafe_allow_html=True)
        with st.expander("Tambah Bus Baru"):
            n1   = st.text_input("Nama/Nomor Bus", placeholder="Rajawali 04", key="b_name")
            h1   = st.selectbox("Kota Home Base", CITIES, key="b_home")
            cp1  = st.selectbox("Posisi Saat Ini", CITIES, key="b_cp")
            m1   = st.multiselect("Hari Maintenance", DAY_NAMES, key="b_maint")
            cap1 = st.selectbox("Kapasitas Penumpang", [32,40,44,48], key="b_cap")
            if st.button("Tambah Bus", key="btn_add_bus"):
                new_id = max(b["id"] for b in st.session_state.buses)+1 if st.session_state.buses else 0
                st.session_state.buses.append({
                    "id":new_id,"bus_id":f"BUS{new_id+1:03d}",
                    "name":n1 or f"BUS{new_id+1:03d}","capacity":cap1,
                    "homebase":h1,"current_position":cp1,
                    "maintenance_days":[DAY_NAMES.index(x) for x in m1],
                })
                st.success("Bus ditambahkan."); st.rerun()

        # Render Table menggunakan st.data_editor 
        df_b = pd.DataFrame([{
            "id_internal": b["id"],
            "ID": b["bus_id"],
            "Nama": b["name"],
            "Kapasitas": b["capacity"],
            "Home Base": b["homebase"],
            "Posisi Saat Ini": b["current_position"],
            "Hari Maintenance": ", ".join(DAY_NAMES[x] for x in b.get("maintenance_days",[])) or "—",
        } for b in st.session_state.buses])

        st.markdown("**Daftar Bus** ")
        edited_df_b = st.data_editor(
            df_b, 
            use_container_width=True, 
            hide_index=True,
            num_rows="dynamic",
            column_config={"id_internal": None} 
        )
        
        # Sinkronisasi state jika ada baris yang dihapus via UI tabel
        if len(edited_df_b) != len(df_b):
            keep_ids = edited_df_b["id_internal"].tolist()
            st.session_state.buses = [x for x in st.session_state.buses if x["id"] in keep_ids]
            st.rerun()

        st.markdown("---")
        if st.button("↺ Reset Default Bus", key="reset_bus"):
            st.session_state.buses = copy.deepcopy(DEFAULT_BUSES); st.rerun()

    # DRIVER
    with tab_drv:
        st.markdown('<div class="sec-header">Daftar Driver</div>', unsafe_allow_html=True)
        with st.expander("Tambah Driver Baru"):
            n2  = st.text_input("Nama Driver", placeholder="Budi Santoso", key="d_name")
            h2  = st.selectbox("Kota Asal", CITIES, key="d_home")
            cp2 = st.selectbox("Posisi Saat Ini", CITIES, key="d_cp")
            l2  = st.multiselect("Hari Cuti", DAY_NAMES, key="d_leave")
            if st.button("Tambah Driver", key="btn_add_drv"):
                new_id = max(d["id"] for d in st.session_state.drivers)+1 if st.session_state.drivers else 0
                st.session_state.drivers.append({
                    "id":new_id,"driver_id":f"DRV{new_id+1:03d}",
                    "name":n2 or f"DRV{new_id+1:03d}","homebase":h2,
                    "current_position":cp2,"leave_days":[DAY_NAMES.index(x) for x in l2],
                })
                st.success("Driver ditambahkan."); st.rerun()

        df_d = pd.DataFrame([{
            "id_internal": d["id"],
            "ID": d["driver_id"],
            "Nama": d["name"],
            "Kota Asal": d["homebase"],
            "Posisi Saat Ini": d["current_position"],
            "Cuti": ", ".join(DAY_NAMES[x] for x in d.get("leave_days",[])) or "—",
        } for d in st.session_state.drivers])

        st.markdown("**Daftar Driver**")
        edited_df_d = st.data_editor(
            df_d, 
            use_container_width=True, 
            hide_index=True,
            num_rows="dynamic",
            column_config={"id_internal": None}
        )
        
        if len(edited_df_d) != len(df_d):
            keep_ids = edited_df_d["id_internal"].tolist()
            st.session_state.drivers = [x for x in st.session_state.drivers if x["id"] in keep_ids]
            st.rerun()

        st.markdown("---")
        if st.button("↺ Reset Default Driver", key="reset_drv"):
            st.session_state.drivers = copy.deepcopy(DEFAULT_DRIVERS); st.rerun()

    # KONDEKTUR
    with tab_cnd:
        st.markdown('<div class="sec-header">Daftar Kondektur</div>', unsafe_allow_html=True)
        with st.expander("Tambah Kondektur Baru"):
            n3  = st.text_input("Nama Kondektur", placeholder="Siti Rahayu", key="c_name")
            h3  = st.selectbox("Kota Asal", CITIES, key="c_home")
            cp3 = st.selectbox("Posisi Saat Ini", CITIES, key="c_cp")
            l3  = st.multiselect("Hari Cuti", DAY_NAMES, key="c_leave")
            if st.button("Tambah Kondektur", key="btn_add_cnd"):
                new_id = max(c["id"] for c in st.session_state.conductors)+1 if st.session_state.conductors else 0
                st.session_state.conductors.append({
                    "id":new_id,"conductor_id":f"CON{new_id+1:03d}",
                    "name":n3 or f"CON{new_id+1:03d}","homebase":h3,
                    "current_position":cp3,"leave_days":[DAY_NAMES.index(x) for x in l3],
                })
                st.success("Kondektur ditambahkan."); st.rerun()

        df_c = pd.DataFrame([{
            "id_internal": c["id"],
            "ID": c["conductor_id"],
            "Nama": c["name"],
            "Kota Asal": c["homebase"],
            "Posisi Saat Ini": c["current_position"],
            "Cuti": ", ".join(DAY_NAMES[x] for x in c.get("leave_days",[])) or "—",
        } for c in st.session_state.conductors])

        st.markdown("**Daftar Kondektur**")
        edited_df_c = st.data_editor(
            df_c, 
            use_container_width=True, 
            hide_index=True,
            num_rows="dynamic",
            column_config={"id_internal": None}
        )
        
        if len(edited_df_c) != len(df_c):
            keep_ids = edited_df_c["id_internal"].tolist()
            st.session_state.conductors = [x for x in st.session_state.conductors if x["id"] in keep_ids]
            st.rerun()

        st.markdown("---")
        if st.button("↺ Reset Default Kondektur", key="reset_cnd"):
            st.session_state.conductors = copy.deepcopy(DEFAULT_CONDUCTORS); st.rerun()

# RUTE JARINGAN
elif page == "Rute Jaringan":
    st.markdown('<div class="sec-header">Jaringan Rute Lintas Jawa (36 Rute)</div>', unsafe_allow_html=True)
    df_r = pd.DataFrame([{"ID":r["id"],"Asal":r["origin"],"Tujuan":r["dest"],"Jarak (km)":r["dist"]} for r in ROUTES])
    c1,c2 = st.columns(2)
    opts = ["Semua"]+sorted(set(r["origin"] for r in ROUTES))
    ff = c1.selectbox("Filter Asal",  opts)
    ft = c2.selectbox("Filter Tujuan",opts)
    fdf = df_r
    if ff != "Semua": fdf = fdf[fdf["Asal"]==ff]
    if ft != "Semua": fdf = fdf[fdf["Tujuan"]==ft]
    st.dataframe(fdf, use_container_width=True, hide_index=True)
    fig2 = px.histogram(df_r, x="Jarak (km)", nbins=12, color_discrete_sequence=["#C0392B"])
    fig2.update_layout(height=220,margin=dict(l=0,r=0,t=10,b=0),plot_bgcolor="#F5F6FA",paper_bgcolor="#F5F6FA")
    st.plotly_chart(fig2, use_container_width=True)

# OPTIMASI JADWAL
elif page == "Optimasi Jadwal":
    st.markdown('<div class="sec-header">Konfigurasi Parameter</div>', unsafe_allow_html=True)
    col_p1, col_p2 = st.columns(2)

    with col_p1:
        st.markdown('<span class="phase-pill">FASE 1</span> **Ant Colony Optimization**', unsafe_allow_html=True)
        aco_ants = st.slider("Jumlah Semut",  10, 80, 30)
        aco_iter = st.slider("Iterasi ACO",   20, 200, 80)
        with st.expander("Parameter Lanjutan ACO"):
            aco_alpha = st.number_input("Alpha", 0.5, 3.0, 1.0, 0.1)
            aco_beta  = st.number_input("Beta",  1.0, 6.0, 2.0, 0.1)
            aco_rho   = st.number_input("Rho",   0.05, 0.5, 0.1, 0.05)
            aco_q     = st.number_input("Q",     50.0, 300.0, 100.0, 10.0)
            aco_stag  = st.slider("Stagnation Limit", 5, 30, 12)

    with col_p2:
        st.markdown('<span class="phase-pill">FASE 2</span> **Discrete PSO**', unsafe_allow_html=True)
        dpso_part = st.slider("Jumlah Partikel", 10, 100, 30)
        dpso_iter = st.slider("Iterasi DPSO",    20, 400, 200)
        with st.expander("Parameter Lanjutan DPSO"):
            dpso_ws   = st.number_input("Inertia Awal",   0.5, 1.0, 0.9, 0.05)
            dpso_we   = st.number_input("Inertia Akhir",  0.1, 0.6, 0.3, 0.05)
            dpso_c1   = st.number_input("c1 (Cognitive)", 1.0, 3.0, 2.0, 0.1)
            dpso_c2   = st.number_input("c2 (Social)",    1.0, 3.0, 2.0, 0.1)
            dpso_stag = st.slider("Stagnation Limit DPSO", 10, 60, 25)
            dpso_levy = st.slider("Lévy Prob (%)", 5, 40, 15)

    st.markdown('<div class="sec-header">Jalankan Optimasi</div>', unsafe_allow_html=True)
    col_r1, col_r2, _ = st.columns([1,1,2])

    # ACO
    with col_r1:
        run_aco = st.button("▶ Jalankan ACO", use_container_width=True)

    if run_aco:
        st.session_state.aco_log    = []
        st.session_state.aco_result = None
        st.session_state.dpso_result = None
        log_ph = st.empty(); prog = st.progress(0); stat_ph = st.empty()

        def aco_cb(it, total, fit, chain):
            prog.progress(it/total)
            stat_ph.markdown(f"**Iterasi {it}/{total}** — Fitness: `{fit:.2f}`")
            if it % max(1, total//25) == 0 or it == total:
                st.session_state.aco_log.append(f"Iter {it:>4}/{total}  |  Fitness = {fit:.2f}")
            log_ph.markdown('<div class="log-box">' + "<br>".join(st.session_state.aco_log[-14:]) + '</div>', unsafe_allow_html=True)

        engine = ACO(n_ants=aco_ants, n_iterations=aco_iter, alpha=aco_alpha,
                     beta=aco_beta, rho=aco_rho, q=aco_q, n_trips=TOTAL_TRIPS,
                     stagnation_limit=aco_stag, callback=aco_cb)
        chain, fit, hist = engine.run()
        vstats   = engine.validate_chain(chain)
        route_txt = engine.format_result(chain, fit)

        st.session_state.aco_result = {
            "chain":chain,"fitness":fit,"history":hist,"stats":vstats,"route_txt":route_txt,
        }
        prog.progress(1.0)
        st.success(f"✓ ACO selesai — Coverage: {vstats['coverage_pct']}% | Teleportasi: {vstats['teleports']} | {len(chain)} trips")
        st.code(route_txt, language="")

    if st.session_state.aco_result and not run_aco:
        with st.expander("📋 Lihat Hasil ACO Route Chain"):
            st.code(st.session_state.aco_result["route_txt"], language="")

    # DPSO
    with col_r2:
        disabled = st.session_state.aco_result is None
        run_dpso = st.button("▶ Jalankan DPSO", use_container_width=True, disabled=disabled,
                             help="Jalankan ACO terlebih dahulu." if disabled else "Alokasi resource.")

    if run_dpso and st.session_state.aco_result:
        st.session_state.dpso_log    = []
        st.session_state.dpso_result = None
        chain = st.session_state.aco_result["chain"]
        log_ph2 = st.empty(); prog2 = st.progress(0); stat_ph2 = st.empty()

        def dpso_cb(it, total, fit):
            prog2.progress(it/total)
            stat_ph2.markdown(f"**Iterasi {it}/{total}** — Global Best: `{fit:.2f}`")
            if it % max(1, total//25) == 0 or it == total:
                st.session_state.dpso_log.append(f"Iter {it:>4}/{total}  |  GBest = {fit:.2f}")
            log_ph2.markdown('<div class="log-box">' + "<br>".join(st.session_state.dpso_log[-14:]) + '</div>', unsafe_allow_html=True)

        dpso_eng = DPSO(
            n_particles=dpso_part, n_iterations=dpso_iter,
            w_start=dpso_ws, w_end=dpso_we, c1=dpso_c1, c2=dpso_c2,
            n_trips=len(chain),
            buses=st.session_state.buses,
            drivers=st.session_state.drivers,
            conductors=st.session_state.conductors,
            stagnation_limit=dpso_stag, levy_prob=dpso_levy/100.0,
            callback=dpso_cb,
        )
        trips, fit2, hist2, fstats = dpso_eng.run(chain)
        assign_log = dpso_eng.format_assignments(
            trips, st.session_state.buses, st.session_state.drivers, st.session_state.conductors)

        st.session_state.dpso_result = {
            "trips":trips,"fitness":fit2,"history":hist2,"stats":fstats,"assign_log":assign_log,
        }
        prog2.progress(1.0)
        hard = fstats.get("overlap",0)+fstats.get("maintenance",0)+fstats.get("leave_drv",0)+fstats.get("leave_cnd",0)
        if hard == 0:
            st.success("✓ Zero Hard Constraint Violations!")
        else:
            st.warning(f"⚠ {hard} hard constraint dilanggar — coba tingkatkan iterasi.")

    ar = st.session_state.aco_result
    dr = st.session_state.dpso_result
    if ar or dr:
        st.markdown('<div class="sec-header">Grafik Konvergensi</div>', unsafe_allow_html=True)
        ccols = st.columns(2 if (ar and dr) else 1)
        idx = 0
        if ar:
            with ccols[idx]:
                fa = go.Figure(go.Scatter(y=ar["history"],mode="lines",
                    line=dict(color="#C0392B",width=2),fill="tozeroy",fillcolor="rgba(192,57,43,0.08)"))
                fa.update_layout(title="ACO — Best Fitness",xaxis_title="Iterasi",yaxis_title="Fitness",
                    height=280,margin=dict(l=0,r=0,t=36,b=0),plot_bgcolor="#F5F6FA",paper_bgcolor="white")
                st.plotly_chart(fa, use_container_width=True)
            idx += 1
        if dr:
            with ccols[idx]:
                fd = go.Figure(go.Scatter(y=dr["history"],mode="lines",
                    line=dict(color="#1A5276",width=2),fill="tozeroy",fillcolor="rgba(26,82,118,0.08)"))
                fd.update_layout(title="DPSO — Global Best",xaxis_title="Iterasi",yaxis_title="Fitness",
                    height=280,margin=dict(l=0,r=0,t=36,b=0),plot_bgcolor="#F5F6FA",paper_bgcolor="white")
                st.plotly_chart(fd, use_container_width=True)

# HASIL & LAPORAN
elif page == "Hasil & Laporan":
    if not st.session_state.dpso_result:
        st.info("Jalankan optimasi di menu **Optimasi Jadwal** terlebih dahulu.")
        st.stop()

    dr        = st.session_state.dpso_result
    ar        = st.session_state.aco_result
    trips     = dr["trips"]
    ds        = dr["stats"]
    aco_stats = ar["stats"]
    buses     = st.session_state.buses
    drivers   = st.session_state.drivers
    conductors= st.session_state.conductors
    bus_map   = {b["id"]: b for b in buses}
    drv_map   = {d["id"]: d for d in drivers}
    cnd_map   = {c["id"]: c for c in conductors}

    def _sort_key(t):
        return (t.day_id, t.slot_id, bus_map.get(t.bus_id, {}).get("bus_id", "ZZZ"))

    sorted_trips = sorted(trips, key=_sort_key)

    rows = []
    slot_counter = {}   
    for t in sorted_trips:
        r   = ROUTES[t.route_id]
        b   = bus_map.get(t.bus_id, {})
        d_  = drv_map.get(t.driver_id, {})
        c   = cnd_map.get(t.conductor_id, {})
        key = (t.day_id, t.slot_id)
        slot_counter[key] = slot_counter.get(key, 0) + 1
        bus_num = slot_counter[key]
        rows.append({
            "No":        len(rows)+1,
            "Hari":      DAY_LABELS.get(t.day_id, "?"),
            "Slot":      SLOT_LABELS.get(t.slot_id, "?"),
            "Bus ke-":   bus_num,
            "Asal":      r["origin"],
            "Tujuan":    r["dest"],
            "Jarak":     f"{r['dist']} km",
            "Bus":       b.get("bus_id",       f"BUS{t.bus_id}"),
            "Driver":    d_.get("driver_id",   f"DRV{t.driver_id}"),
            "Kondektur": c.get("conductor_id", f"CON{t.conductor_id}"),
            "_day":      t.day_id,
            "_slot":     t.slot_id,
        })

    tab_sched, tab_assign, tab_gantt, tab_stats, tab_export = st.tabs([
        "📋 Jadwal Lengkap","🔍 Detail Assignment","📊 Gantt Chart","📈 Statistik","⬇️ Export",
    ])

    # Jadwal Lengkap
    with tab_sched:
        st.markdown('<div class="sec-header">Tabel Jadwal 1 Minggu</div>', unsafe_allow_html=True)
        df_s = pd.DataFrame([{k: v for k,v in r.items() if not k.startswith("_")} for r in rows])
        fc1, fc2, fc3 = st.columns(3)
        fd = fc1.selectbox("Filter Hari",  ["Semua"]+list(DAY_LABELS.values()))
        fs = fc2.selectbox("Filter Slot",  ["Semua"]+list(SLOT_LABELS.values()))
        fb = fc3.selectbox("Filter Bus",   ["Semua"]+sorted(set(r["Bus"] for r in rows)))
        fdf = df_s
        if fd != "Semua": fdf = fdf[fdf["Hari"]==fd]
        if fs != "Semua": fdf = fdf[fdf["Slot"]==fs]
        if fb != "Semua": fdf = fdf[fdf["Bus"]==fb]
        st.dataframe(fdf, use_container_width=True, hide_index=True, height=500)
        st.caption(f"Total trip ditampilkan: {len(fdf)} / {TOTAL_TRIPS}")

    # Detail Assignment
    with tab_assign:
        st.markdown('<div class="sec-header">Log Penugasan Resource per Trip</div>', unsafe_allow_html=True)
        st.caption("Posisi sebelum & sesudah setiap trip. ⚠ = pelanggaran constraint.")
        assign_log = dr.get("assign_log","")
        if assign_log:
            n_show = st.slider("Tampilkan trip ke-1 s/d", 1, len(sorted_trips), min(10, len(sorted_trips)))
            dpso_tmp = DPSO(n_trips=len(trips), buses=buses, drivers=drivers, conductors=conductors)
            short_log = dpso_tmp.format_assignments(sorted_trips[:n_show], buses, drivers, conductors)
            st.markdown(f'<div class="assign-box">{short_log}</div>', unsafe_allow_html=True)
        else:
            st.info("Log tidak tersedia.")

    # Gantt Chart
    with tab_gantt:
        slot_h = {0:0, 1:6, 2:12, 3:18}

        st.markdown('<div class="sec-header">Gantt — Per Bus</div>', unsafe_allow_html=True)
        gantt = []
        for t in trips:
            r = ROUTES[t.route_id]; h = slot_h.get(t.slot_id, 6)
            gantt.append({
                "Task":  bus_map.get(t.bus_id,{}).get("bus_id",f"BUS{t.bus_id}"),
                "Start": f"2024-01-{t.day_id+1:02d} {h:02d}:00",
                "Finish":f"2024-01-{t.day_id+1:02d} {(h+max(1,r['dist']//60))%24:02d}:00",
                "Rute":  f"{r['origin']} → {r['dest']}","Slot":SLOT_LABELS[t.slot_id],
                "Driver":drv_map.get(t.driver_id,{}).get("driver_id","?"),
            })
        if gantt:
            fg = px.timeline(pd.DataFrame(gantt),x_start="Start",x_end="Finish",
                y="Task",color="Slot",hover_data=["Rute","Driver"],
                color_discrete_map={"00:00":"#8E44AD","06:00":"#2980B9","12:00":"#27AE60","18:00":"#E67E22"})
            fg.update_yaxes(autorange="reversed")
            fg.update_layout(height=max(300,len(set(d["Task"] for d in gantt))*36+80),
                margin=dict(l=0,r=0,t=10,b=0),plot_bgcolor="#F5F6FA",paper_bgcolor="white")
            st.plotly_chart(fg, use_container_width=True)

        st.markdown('<div class="sec-header">Gantt — Per Driver</div>', unsafe_allow_html=True)
        gantt_d = []
        for t in trips:
            r = ROUTES[t.route_id]; h = slot_h.get(t.slot_id,6)
            gantt_d.append({
                "Task": drv_map.get(t.driver_id,{}).get("driver_id",f"DRV{t.driver_id}"),
                "Start":f"2024-01-{t.day_id+1:02d} {h:02d}:00",
                "Finish":f"2024-01-{t.day_id+1:02d} {(h+max(1,r['dist']//60))%24:02d}:00",
                "Rute":f"{r['origin']} → {r['dest']}","Slot":SLOT_LABELS[t.slot_id],
                "Bus":bus_map.get(t.bus_id,{}).get("bus_id","?"),
            })
        if gantt_d:
            fgd = px.timeline(pd.DataFrame(gantt_d),x_start="Start",x_end="Finish",
                y="Task",color="Slot",hover_data=["Rute","Bus"],
                color_discrete_map={"00:00":"#8E44AD","06:00":"#2980B9","12:00":"#27AE60","18:00":"#E67E22"})
            fgd.update_yaxes(autorange="reversed")
            fgd.update_layout(height=max(300,len(set(d["Task"] for d in gantt_d))*36+80),
                margin=dict(l=0,r=0,t=10,b=0),plot_bgcolor="#F5F6FA",paper_bgcolor="white")
            st.plotly_chart(fgd, use_container_width=True)

    # Statistik
    with tab_stats:
        st.markdown('<div class="sec-header">Ringkasan Kualitas Jadwal</div>', unsafe_allow_html=True)
        hard = ds.get("overlap",0)+ds.get("maintenance",0)+ds.get("leave_drv",0)+ds.get("leave_cnd",0)
        c1,c2,c3 = st.columns(3)
        def sc(col, v, l, color="#C0392B"):
            col.markdown(f'<div class="metric-card" style="border-top-color:{color};"><div class="val" style="color:{color};">{v}</div><div class="lbl">{l}</div></div>', unsafe_allow_html=True)
        sc(c1, f"{aco_stats['coverage_pct']}%","Coverage Rute","#27AE60")
        sc(c2, str(hard),"Hard Violations","#C0392B" if hard>0 else "#27AE60")
        sc(c3, f"{aco_stats['total_distance']:,} km","Jarak Mingguan","#1A5276")
        c4,c5,c6 = st.columns(3)
        sc(c4, f"{ds['unique_buses']}",     f"Bus Terpakai/{nb}","#E67E22")
        sc(c5, f"{ds['unique_drivers']}",   f"Driver Terpakai/{nd}","#E67E22")
        sc(c6, f"{ds['unique_conductors']}",f"Kond. Terpakai/{nc}","#E67E22")

        st.markdown('<div class="sec-header">Detail Pelanggaran</div>', unsafe_allow_html=True)
        viol = pd.DataFrame([
            {"Kategori":"Overlap Jadwal (Hard)",    "Jumlah":ds.get("overlap",0),      "Penalti/kasus":"100,000"},
            {"Kategori":"Bus Maintenance (Hard)",   "Jumlah":ds.get("maintenance",0),  "Penalti/kasus":"100,000"},
            {"Kategori":"Cuti Driver (Hard)",       "Jumlah":ds.get("leave_drv",0),    "Penalti/kasus":"100,000"},
            {"Kategori":"Cuti Kondektur (Hard)",    "Jumlah":ds.get("leave_cnd",0),    "Penalti/kasus":"100,000"},
            {"Kategori":"Teleportasi Bus",          "Jumlah":ds.get("teleport_bus",0), "Penalti/kasus":"100,000"},
            {"Kategori":"Teleportasi Driver",       "Jumlah":ds.get("teleport_drv",0), "Penalti/kasus":"100,000"},
            {"Kategori":"Teleportasi Kond.",        "Jumlah":ds.get("teleport_cnd",0), "Penalti/kasus":"100,000"},
            {"Kategori":"Trip Limit >2/hari",       "Jumlah":ds.get("trip_limit",0),   "Penalti/kasus":"8,000"},
        ])
        st.dataframe(viol, use_container_width=True, hide_index=True)

        st.markdown('<div class="sec-header">Repair Statistics</div>', unsafe_allow_html=True)
        rep = pd.DataFrame([
            {"Tipe":"Swap Success",       "Count":ds.get("repair_swap_success",0)},
            {"Tipe":"Replacement Success","Count":ds.get("repair_replacement_success",0)},
            {"Tipe":"Repair Fail",        "Count":ds.get("repair_fail",0)},
            {"Tipe":"Teleport (before)",  "Count":ds.get("teleport_before_repair",0)},
            {"Tipe":"Teleport (after)",   "Count":ds.get("teleport_after_repair",0)},
        ])
        st.dataframe(rep, use_container_width=True, hide_index=True)

        st.markdown('<div class="sec-header">Workload Balance</div>', unsafe_allow_html=True)
        wb_data = []
        for label, ws_key in [("Bus","workload_bus"),("Driver","workload_drv"),("Kondektur","workload_cnd")]:
            ws = ds.get(ws_key, {})
            wb_data.append({
                "Resource": label,
                "Max":       ws.get("max","-"),
                "Min":       ws.get("min","-"),
                "Avg":       ws.get("avg","-"),
                "Std Dev":   ws.get("std_dev","-"),
                "CV":        ws.get("cv","-"),
            })
        st.dataframe(pd.DataFrame(wb_data), use_container_width=True, hide_index=True)

        st.markdown('<div class="sec-header">Beban Kerja per Bus</div>', unsafe_allow_html=True)
        bl = {}
        for t in trips:
            bn = bus_map.get(t.bus_id,{}).get("bus_id",f"BUS{t.bus_id}")
            bl[bn] = bl.get(bn,0)+1
        fig_l = go.Figure(go.Bar(x=list(bl.keys()),y=list(bl.values()),marker_color="#C0392B"))
        fig_l.update_layout(height=240,margin=dict(l=0,r=0,t=10,b=0),
            xaxis_title="Bus",yaxis_title="Jumlah Trip",
            plot_bgcolor="#F5F6FA",paper_bgcolor="white")
        st.plotly_chart(fig_l, use_container_width=True)

# Export
    with tab_export:
        st.markdown('<div class="sec-header">Export Data</div>', unsafe_allow_html=True)
        rows_e = [{
            "No":r["No"],"Hari":r["Hari"],"Slot":r["Slot"],"Bus_ke":r["Bus ke-"],
            "Asal":r["Asal"],"Tujuan":r["Tujuan"],"Jarak_km":r["Jarak"].replace(" km",""),
            "Bus":r["Bus"],"Driver":r["Driver"],"Kondektur":r["Kondektur"],
        } for r in rows]
        df_e = pd.DataFrame(rows_e)
        hard2 = ds.get("overlap",0)+ds.get("maintenance",0)+ds.get("leave_drv",0)+ds.get("leave_cnd",0)
        st.download_button("⬇️ Download Jadwal (CSV)",
            df_e.to_csv(index=False).encode(),"jadwal_ptrestu.csv","text/csv",use_container_width=True)
        summary = {
            "total_trips":TOTAL_TRIPS,"coverage_pct":aco_stats["coverage_pct"],
            "total_distance_km":aco_stats["total_distance"],"teleports_aco":aco_stats["teleports"],
            "hard_violations":hard2,"buses_used":ds["unique_buses"],
            "drivers_used":ds["unique_drivers"],"conductors_used":ds["unique_conductors"],
            "penalty":ds["penalty"],
        }
        st.download_button("⬇️ Download Ringkasan (JSON)",
            json.dumps({"summary":summary,"schedule":rows_e},indent=2,ensure_ascii=False).encode(),
            "jadwal_ptrestu_summary.json","application/json",use_container_width=True)
        st.markdown("**Preview (20 baris pertama)**")
        st.dataframe(df_e.head(20), use_container_width=True, hide_index=True)