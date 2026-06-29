import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import google.generativeai as genai
import time
from google.cloud import bigquery
import os
import math
import requests

# --- KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="PartnerTune: Music Partner Strategy System",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- KREDENSIAL BIGQUERY (Mendukung Deteksi Otomatis Lokal & Server Cloud) ---
try:
    if "gcp_credentials" in st.secrets:
        # Jika berjalan di server cloud Streamlit, baca dari menu Advanced Settings Secrets
        from google.oauth2 import service_account
        creds_dict = dict(st.secrets["gcp_credentials"])
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        client = bigquery.Client(credentials=credentials, project=creds_dict["project_id"])
    else:
        # Jika berjalan di komputer lokal Anda, tetap baca berkas credentials.json
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials.json"
        client = bigquery.Client()
except Exception as e:
    st.error(f"Gagal menginisialisasi BigQuery Client: {e}")
# --- STYLE KUSTOM (Perbaikan Font & Proteksi Ikon Sidebar) ---
st.markdown("""
    <style>
    /* Mengimpor font Inter dari Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
    
    /* Hanya terapkan font Inter ke elemen teks spesifik agar tidak merusak sistem ikon Streamlit */
    html, body, p, label, h1, h2, h3, h4, h5, h6, .stMarkdown, strong, b {
        font-family: 'Inter', sans-serif !important;
    }
    
    /* Proteksi Khusus: Mengembalikan font-family ikon bawaan agar tombol collapse/buka sidebar tidak bocor menjadi teks */
    [data-testid="stSidebarCollapseButton"] button,
    [data-testid="stSidebarCollapseButton"] span,
    [data-testid="stSidebarCollapseButton"] div {
        font-family: inherit !important;
    }
    
    h1 { font-weight: 900 !important; letter-spacing: -0.05em !important; }
    h2, h3 { font-weight: 800 !important; letter-spacing: -0.03em !important; }
    strong, b { font-weight: 700 !important; color: #0f172a !important; }
    
    .bg-gradient-strategy {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
        padding: 2rem;
        border-radius: 1.5rem;
        color: white;
        margin-bottom: 2rem;
    }
    </style>
""", unsafe_allow_html=True)

# --- KONFIGURASI API GEMINI ---
API_KEY = st.secrets.get("GEMINI_API_KEY", "")
if API_KEY:
    genai.configure(api_key=API_KEY)

# --- LOGIKA ENGINE STRATEGI (4 Pilar Nuon Resmi) ---
TEMPLATE_FIELDS = [
    {'id': 'Market_Share_Score', 'weight': 0.35, 'max': 10, 'label': 'Market Share'},
    {'id': 'New_Content_Score', 'weight': 0.25, 'max': 10, 'label': 'New Content'},
    {'id': 'Fraud_Risk_Score', 'weight': 0.25, 'max': 10, 'label': 'Keamanan Fraud'},
    {'id': 'Marketing_Value_Score', 'weight': 0.15, 'max': 10, 'label': 'Strategic Marketing'},
]

def calculate_score(partner):
    total_score = 0
    for field in TEMPLATE_FIELDS:
        val = partner.get(field['id'], 0)
        normalized = val / field['max']
        total_score += normalized * field['weight']
    return round(total_score * 100)

def get_partner_decision(partner):
    score = calculate_score(partner)
    # Aturan Pengecualian Kasus Partner D (Katalog Kuat & Aman Fraud, Rilis Rendah)
    if (float(partner.get('Marketing_Value_Score', 0)) >= 8.0 and float(partner.get('Fraud_Risk_Score', 0)) >= 8.0) and (float(partner.get('New_Content_Score', 0)) <= 3.0 and float(partner.get('Market_Share_Score', 0)) >= 4.0):
        return {'type': 'Direct Strategic', 'color': 'orange'}
    if score >= 70:
        return {'type': 'Direct Partnership', 'color': 'green'}
    return {'type': 'Aggregator (Langitku)', 'color': 'red'}

# --- INTEGRASI API AGGREGATOR EKSTERNAL (SOUNDCHARTS / CHARTMETRIC FALLBACK) ---
def fetch_external_marketing_data(artist_name):
    """
    Mengambil data agregat lintas platform dari API Pihak Ketiga.
    Jika kredensial belum diisi, mengembalikan simulasi data aman.
    """
    app_id = st.secrets.get("SOUNDCHARTS_APP_ID", "")
    api_key = st.secrets.get("SOUNDCHARTS_API_KEY", "")
    
    if not app_id or not api_key:
        # Simulasi fallback berbasis string hash sederhana agar data bervariasi namun konsisten
        mock_listeners = (abs(hash(artist_name)) % 950000) + 50000
        return {"spotify_listeners": mock_listeners}
        
    headers = {"x-app-id": app_id, "x-api-key": api_key}
    try:
        search_url = f"https://api.soundcharts.com/api/v2.2/artist/search?q={artist_name}"
        search_res = requests.get(search_url, headers=headers, timeout=4).json()
        if search_res.get("items"):
            uuid = search_res["items"][0]["uuid"]
            spotify_url = f"https://api.soundcharts.com/api/v2.2/artist/{uuid}/streaming/spotify/listening"
            spot_res = requests.get(spotify_url, headers=headers, timeout=4).json()
            listeners = spot_res.get("latest", {}).get("plots", [{}])[-1].get("value", 0)
            return {"spotify_listeners": listeners}
    except Exception:
        pass
    return {"spotify_listeners": 150000}

# --- INTEGRASI AI GEMINI ---
def call_gemini_api(prompt, system_instruction):
    if not API_KEY: return "API Key Gemini belum diatur. Analisis AI dinonaktifkan."
    try:
        model = genai.GenerativeModel(model_name="gemini-2.5-flash", system_instruction=system_instruction)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gagal mendapatkan analisis dari AI saat ini: {str(e)}"

def get_vetting_insights(partner_data, final_score, decision_type):
    prompt = f"Analis B2B Musik Nuon. Evaluasi Calon: {partner_data['Nama_Label']}. Skor: {final_score}/100. Rekomendasi: {decision_type}. Data (0-10): MarketShare={partner_data['Market_Share_Score']}, NewContent={partner_data['New_Content_Score']}, KeamananFraud={partner_data['Fraud_Risk_Score']}, StrategicValue={partner_data['Marketing_Value_Score']}."
    return call_gemini_api(prompt, "Berikan analisis ringkas strategis 1 paragraf untuk keputusan Kemitraan Musik B2B.")

def get_audit_summary(partner):
    final_score = calculate_score(partner)
    decision = get_partner_decision(partner)
    prompt = f"Manajer Portofolio B2B Nuon. Tulis audit 1 paragraf untuk label: {partner['Nama_Label']}. Skor: {final_score}/100. Klasifikasi: {decision['type']}. Komponen (1-10): MarketShare={partner['Market_Share_Score']}, NewContent={partner['New_Content_Score']}, KeamananFraud={partner['Fraud_Risk_Score']}, StrategicMarketing={partner['Marketing_Value_Score']}."
    return call_gemini_api(prompt, "Berikan ringkasan audit singkat dan profesional.")

# --- FUNGSI AMBIL DATA DARI BIGQUERY & MAPPING PILAR EVALUASI ---
@st.cache_data(ttl=600)
def load_data_from_bigquery():
    query = """
        WITH KelompokKuartil AS (
            SELECT 
                label_cd Partner_ID,
                label_name Nama_Label,
                count(distinct song_id) as Tracks,
                NTILE(4) OVER (ORDER BY COALESCE(count(distinct song_id), 0) ASC) AS Kuartil
            FROM digital_music.if_song_label
            WHERE date(trx_date) >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH), MONTH)
            group by 1,2
        ),
        score_newcontent as (
            SELECT 
                Partner_ID, Nama_Label, Tracks, Kuartil,
                CASE 
                    WHEN Tracks = 0 OR Tracks IS NULL THEN 0 
                    WHEN Kuartil = 4 THEN 10  
                    WHEN Kuartil = 3 THEN 7   
                    WHEN Kuartil = 2 THEN 4   
                    ELSE 2                    
                END AS New_Content_Score
            FROM KelompokKuartil
        ),
        stream AS (
            SELECT 
                label_cd, label_name,
                sum(stream_cnt) AS stream, sum(service_div_amt) as rev
            FROM `MLB.settlement_music` 
            where datenum BETWEEN FORMAT_DATE('%Y%m', DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)) AND FORMAT_DATE('%Y%m', CURRENT_DATE())
            GROUP BY 1, 2
        )
        SELECT 
            b.label_cd AS Partner_ID, 
            b.company_name AS Nama_Label,
            case when status='approved' then 'EKSISTING' when status like '%waiting%' then 'CALON' else 'NON-AKTIF' end AS Status_Kemitraan, 
            COUNT(DISTINCT a.song_id) AS Tracks, 
            COALESCE(SUM(c.stream), 0) AS Streams,
            COALESCE(SUM(c.rev), 0) AS Rev,
            COALESCE(AVG(d.New_Content_Score), 0) as New_Content_Score
        FROM `melondata.digital_music.md_label` b
        LEFT OUTER JOIN `melondata.digital_music.if_song_label` a ON b.label_cd = a.label_cd 
        LEFT OUTER JOIN stream c ON b.label_cd = c.label_cd
        LEFT OUTER JOIN score_newcontent d ON b.label_cd = d.partner_ID
        GROUP BY 1, 2, b.Status
    """
    try:
        query_job = client.query(query)
        results = query_job.to_dataframe()
    except Exception:
        return []
        
    if results.empty: return []

    # PILAR 1: MARKET SHARE
    results['Market_Share_Score'] = pd.qcut(results['Streams'].rank(method='first'), 10, labels=False) + 1

    # PILAR 2: NEW CONTENT ACTIVITY
    results['New_Content_Score'] = results['New_Content_Score'].round().astype(int)

    # PILAR 3: FRAUD HISTORY (Sistem Deteksi Devisiasi RPM Finansial Nuon)
    results['RPM'] = results.apply(lambda r: (r['Rev'] / r['Streams'] * 1000) if r['Streams'] > 0 else 0, axis=1)
    median_rpm = results[results['RPM'] > 0]['RPM'].median() if len(results[results['RPM'] > 0]) > 0 else 1
    
    def hitung_fraud_score(row):
        if row['Streams'] == 0: return 10
        rasio = row['RPM'] / median_rpm
        if rasio < 0.4: return 3
        if rasio < 0.7: return 6
        return 10
    results['Fraud_Risk_Score'] = results.apply(hitung_fraud_score, axis=1)

    # PILAR 4: STRATEGIC MARKETING VALUE (60% Internal Produktivitas + 40% Popularitas API Eksternal)
    results['Stream_Per_Track'] = results.apply(lambda r: (r['Streams'] / r['Tracks']) if r['Tracks'] > 0 else 0, axis=1)
    results['Internal_Marketing_Score'] = pd.qcut(results['Stream_Per_Track'].rank(method='first'), 10, labels=False) + 1
    
    # Integrasi Menggunakan API Aggregator Lintas Platform
    raw_records = results.to_dict(orient='records')
    for r in raw_records:
        ext_data = fetch_external_marketing_data(r['Nama_Label'])
        listeners = ext_data["spotify_listeners"]
        # Hitung indeks logaritmik eksternal skala 1-10
        calculated_ext_score = min(10, max(1, round(math.log10(listeners) - 2))) if listeners > 0 else 1
        
        # Gabungkan Bobot Evaluasi
        combined_marketing = round((0.6 * r['Internal_Marketing_Score']) + (0.4 * calculated_ext_score))
        r['Marketing_Value_Score'] = max(1, min(10, combined_marketing))
        
    return raw_records

# --- INITIALIZATION DATA ---
if 'partners' not in st.session_state:
    try:
        st.session_state.partners = load_data_from_bigquery()
    except Exception:
        st.session_state.partners = []
        
    if not st.session_state.partners:
        st.session_state.partners = [
            {'Partner_ID': 'EKS-001', 'Nama_Label': 'Partner A (High Performer)', 'Status_Kemitraan': 'EKSISTING', 'Market_Share_Score': 9, 'New_Content_Score': 8, 'Fraud_Risk_Score': 10, 'Marketing_Value_Score': 9, 'gemini_insight': None},
            {'Partner_ID': 'EKS-002', 'Nama_Label': 'Partner B (Low Content)', 'Status_Kemitraan': 'EKSISTING', 'Market_Share_Score': 6, 'New_Content_Score': 2, 'Fraud_Risk_Score': 4, 'Marketing_Value_Score': 5, 'gemini_insight': None},
            {'Partner_ID': 'EKS-003', 'Nama_Label': 'Partner D (Strong Catalog)', 'Status_Kemitraan': 'EKSISTING', 'Market_Share_Score': 5, 'New_Content_Score': 1, 'Fraud_Risk_Score': 9, 'Marketing_Value_Score': 8, 'gemini_insight': None}
        ]

if 'current_audit_id' not in st.session_state:
    st.session_state.current_audit_id = None

# --- SIDEBAR NAVIGASI KIRI KUSTOM ---
menu_options = ["Dashboard Utama", "Panduan Strategi", "Evaluasi Partner", "Audit Portofolio"]

if st.session_state.get("pindah_ke_audit") == True:
    st.session_state.menu_navigasi = "Audit Portofolio"
    st.session_state.pindah_ke_audit = False

# --- PROTEKSI VALUE ERROR (Mencegah List.index x Not in List) ---
# Memeriksa apakah state menu_navigasi ada di st.session_state dan nilainya valid di dalam menu_options
if "menu_navigasi" in st.session_state and st.session_state.menu_navigasi in menu_options:
    default_idx = menu_options.index(st.session_state.menu_navigasi)
else:
    default_idx = 0

with st.sidebar:
    st.markdown("<div style='padding: 10px 0px 20px 10px;'><h1 style='color: #4F46E5; font-size: 28px; font-weight: 900; margin: 0; letter-spacing: -0.04em;'>PartnerTune.</h1></div>", unsafe_allow_html=True)
    from streamlit_option_menu import option_menu
    view = option_menu(
        menu_title=None, options=menu_options,
        icons=["grid-1x2", "easel", "person-plus", "file-earmark-check"], 
        default_index=default_idx, key="menu_navigasi",
        styles={
            "container": {"padding": "0px !important", "background-color": "transparent"},
            "icon": {"color": "#475569", "font-size": "18px", "margin-right": "12px"}, 
            "nav-link": {"font-size": "16px", "text-align": "left", "margin": "8px 0px", "padding": "12px 16px", "border-radius": "12px", "color": "#334155", "font-weight": "500"},
            "nav-link-selected": {"background-color": "#EEF2F6", "color": "#1E3A8A", "font-weight": "600"},
        }
    )
    st.markdown("---")
    st.caption("Platform Engine")
    st.info("💻 Nuon Integrator")

# --- KONTEN UTAMA ---

# Tampilan 1: DASHBOARD UTAMA
if view == "Dashboard Utama":
    st.markdown("""
        <style>
        .metric-card { background-color: #ffffff; border: 1px solid #f1f5f9; border-radius: 1.25rem; padding: 1.5rem; display: flex; align-items: center; gap: 1.25rem; box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05); }
        .metric-icon-blue { background-color: #eff6ff; color: #2563eb; width: 3.5rem; height: 3.5rem; border-radius: 1rem; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; }
        .metric-icon-green { background-color: #f0fdf4; color: #16a34a; width: 3.5rem; height: 3.5rem; border-radius: 1rem; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; }
        .metric-icon-red { background-color: #fef2f2; color: #dc2626; width: 3.5rem; height: 3.5rem; border-radius: 1rem; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; }
        .metric-label { color: #64748b; font-size: 0.875rem; font-weight: 500; margin: 0; }
        .metric-value { color: #0f172a; font-size: 2rem; font-weight: 800; margin: 0; line-height: 1; margin-top: 0.25rem; }
        .filter-board { background-color: #ffffff; border: 1px solid #f1f5f9; border-radius: 1rem; padding: 1rem 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.02); }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<div style='display: flex; align-items: center; gap: 10px; margin-bottom: 1.5rem;'><h1 style='margin: 0; font-size: 2.25rem;'>Dashboard Portfolio</h1><span style='background-color: #e0e7ff; color: #4338ca; font-size: 0.75rem; font-weight: 700; padding: 0.25rem 0.75rem; border-radius: 9999px; margin-top: 0.5rem;'>Berdasarkan Strategi Baru</span></div>", unsafe_allow_html=True)
    
    # METRIK RINGKASAN PRODUKSI (Murni Dari BigQuery)
    bq_existing = [p for p in st.session_state.partners if p['Status_Kemitraan'] == 'EKSISTING' and not str(p.get('Partner_ID', '')).startswith("SIM-")]
    total_existing = len(bq_existing)
    direct_count = len([p for p in bq_existing if "Direct" in get_partner_decision(p)['type']])
    aggregator_count = len([p for p in bq_existing if "Aggregator" in get_partner_decision(p)['type']])
    
    m1, m2, m3 = st.columns(3)
    with m1: st.markdown(f'<div class="metric-card"><div class="metric-icon-blue">📁</div><div><p class="metric-label">Total Eksisting (BQ)</p><p class="metric-value">{total_existing}</p></div></div>', unsafe_allow_html=True)
    with m2: st.markdown(f'<div class="metric-card"><div class="metric-icon-green">✅</div><div><p class="metric-label">Direct Partners</p><p class="metric-value">{direct_count}</p></div></div>', unsafe_allow_html=True)
    with m3: st.markdown(f'<div class="metric-card"><div class="metric-icon-red">📉</div><div><p class="metric-label">Aggregator (Langitku)</p><p class="metric-value">{aggregator_count}</p></div></div>', unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # --- PANEL FILTER MULTI-SUMBER DATA ---
    st.markdown("<div class='filter-board'>", unsafe_allow_html=True)
    f_cols1 = st.columns([1, 2, 2, 2])
    f_cols1[0].markdown("<p style='font-weight: 700; color: #475569; margin-top: 4px;'>🔍 Status:</p>", unsafe_allow_html=True)
    show_eksisting = f_cols1[1].checkbox("EKSISTING", value=True)
    show_calon = f_cols1[2].checkbox("CALON", value=True)
    show_non_aktif = f_cols1[3].checkbox("NON-AKTIF", value=True)
    
    st.markdown("<div style='margin-top: 10px; border-top: 1px dashed #e2e8f0; padding-top: 10px;'></div>", unsafe_allow_html=True)
    f_cols2 = st.columns([1, 2.3, 2.3, 1.4])
    f_cols2[0].markdown("<p style='font-weight: 700; color: #475569; margin-top: 4px;'>📊 Sumber:</p>", unsafe_allow_html=True)
    include_bigquery = f_cols2[1].checkbox("🌐 Data Produksi (BigQuery)", value=True)
    include_simulasi = f_cols2[2].checkbox("✨ Data Simulasi Vetting (Manual)", value=True)
    st.markdown("</div>", unsafe_allow_html=True)
    
    allowed_status = []
    if show_eksisting: allowed_status.append('EKSISTING')
    if show_calon: allowed_status.append('CALON')
    if show_non_aktif: allowed_status.append('NON-AKTIF')
    
    filtered_partners = []
    for p in st.session_state.partners:
        if p.get('Status_Kemitraan') in allowed_status:
            is_simulated = str(p.get('Partner_ID', '')).startswith("SIM-")
            if is_simulated and include_simulasi: filtered_partners.append(p)
            elif not is_simulated and include_bigquery: filtered_partners.append(p)
                
    chart_partners = [p for p in filtered_partners if p['Status_Kemitraan'] == 'EKSISTING']
    
    # --- PORTFOLIO MATRIX ---
    if len(chart_partners) > 0:
        with st.container(border=True):
            c_head1, c_head2 = st.columns([2, 1])
            with c_head1: st.markdown("<h3 style='margin:0; font-size:1.35rem; color:#0f172a;'>Portfolio Matrix</h3>", unsafe_allow_html=True)
            with c_head2: st.markdown("<div style='text-align: right;'><span style='background-color: #f1f5f9; color: #475569; font-size: 0.75rem; font-weight: 600; padding: 0.35rem 0.75rem; border-radius: 0.5rem;'>Ukuran Gelembung = Marketing Value</span></div>", unsafe_allow_html=True)
            
            fig = go.Figure()
            for p in chart_partners:
                score = calculate_score(p)
                decision = get_partner_decision(p)
                is_simulated = str(p.get('Partner_ID', '')).startswith("SIM-")
                
                if is_simulated:
                    marker_color = 'rgba(139, 92, 246, 0.45)' # Ungu transparan premium khusus simulasi
                    line_style = dict(width=2, color='#6d28d9', dash='dot')
                    name_prefix = "✨ [Sim] "
                else:
                    color_map = {'green': 'rgba(56, 189, 248, 0.65)', 'red': 'rgba(244, 63, 94, 0.5)', 'orange': 'rgba(245, 158, 11, 0.5)'}
                    marker_color = color_map.get(decision['color'], 'rgba(56, 189, 248, 0.65)')
                    line_style = dict(width=1.5, color='rgba(255, 255, 255, 0.9)')
                    name_prefix = ""
                
                fig.add_trace(go.Scatter(
                    x=[p['Market_Share_Score'] * 10], y=[score], mode='markers',
                    marker=dict(size=[p['Marketing_Value_Score'] * 4 + 25], color=marker_color, line=line_style),
                    name=f"{name_prefix}{p['Nama_Label']}",
                    text=f"<b>{name_prefix}{p['Nama_Label']}</b><br>Total Skor: {score}/100<br>Market Share Index: {p['Market_Share_Score']}/10",
                    hoverinfo='text'
                ))
                
            fig.update_layout(
                xaxis=dict(title='Market Share Index (Sumbu X)', range=[0, 105], gridcolor='#f1f5f9', zeroline=False),
                yaxis=dict(title='Total Skoring (0-100)', range=[0, 105], gridcolor='#f1f5f9', zeroline=False),
                margin=dict(l=50, r=30, t=20, b=50), height=450, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)
            
    st.markdown("<br>", unsafe_allow_html=True)
    
    # --- STRUKTUR DAFTAR LIST TABEL ---
    for group in ['CALON', 'EKSISTING', 'NON-AKTIF']:
        group_data = [p for p in filtered_partners if p['Status_Kemitraan'] == group]
        
        if len(group_data) > 0:
            # Header Judul Kiri & Badge Jumlah Label Kanan yang Cantik & Presisi
            st.markdown(f"""
                <div style='display: flex; justify-content: space-between; align-items: center; margin-top: 2rem; margin-bottom: 0.75rem; padding: 0 4px;'>
                    <div style='font-size: 1.25rem; font-weight: 800; color: #0f172a; letter-spacing: -0.02em;'>Daftar Partner: {group}</div>
                    <div style='background-color: #e2e8f0; color: #334155; font-size: 0.75rem; font-weight: 700; padding: 0.25rem 0.75rem; border-radius: 9999px;'>
                        {len(group_data)} Label
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            items_per_page = 5
            total_items = len(group_data)
            total_pages = (total_items - 1) // items_per_page + 1
            
            page_key = f"page_{group}"
            if page_key not in st.session_state: st.session_state[page_key] = 1
                
            current_page = st.session_state[page_key]
            start_idx = (current_page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            page_data = group_data[start_idx:end_idx]
            
            table_rows = []
            for p in page_data:
                score = calculate_score(p)
                decision = get_partner_decision(p)
                is_simulated = str(p.get('Partner_ID', '')).startswith("SIM-")
                nama_display = f"✨ [Simulasi] {p['Nama_Label']}" if is_simulated else p['Nama_Label']
                
                table_rows.append({
                    "Nama Label": nama_display, "Model Strategi": decision['type'], "Total Skor": f"{score}/100",
                    "ID": p['Partner_ID'] if pd.notna(p['Partner_ID']) and p['Partner_ID'] != "" else "KOSONG"
                })
            
            df_display = pd.DataFrame(table_rows)
            
            st.markdown("""
                <style>
                /* Hilangkan gap sela baris vertikal bawaan Streamlit block */
                .tight-table div[data-testid="stVerticalBlock"] > div { 
                    gap: 0px !important; 
                }
                
                /* Hubungkan horizontal row Streamlit agar bersambung rata */
                .tight-table div[data-testid="stHorizontalBlock"] { 
                    margin-bottom: 0px !important; 
                    margin-top: 0px !important; 
                    align-items: center !important; /* Memaksa perataan vertikal sempurna di tengah baris */
                }
                
                /* Terapkan border horizontal yang sama dan sejajar langsung pada level kolom */
                .tight-table div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
                    border-bottom: 1px solid #f1f5f9 !important;
                    padding-top: 10px !important;
                    padding-bottom: 10px !important;
                    display: flex !important;
                    align-items: center !important;
                }
                
                /* Hilangkan border bawah pada baris terakhir tabel agar lengkungan kartu tetap utuh */
                .tight-table div[data-testid="stHorizontalBlock"]:last-of-type > div[data-testid="column"] {
                    border-bottom: none !important;
                }
                
                /* Atur perataan tombol aksi detail agar menempel rapi di ujung kanan */
                .tight-table div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child {
                    justify-content: flex-end !important;
                }
                
                /* Container utama kartu tabel */
                .tight-table div.stContainer {
                    background-color: #ffffff !important;
                    border: 1px solid #e2e8f0 !important;
                    border-radius: 1rem !important;
                    padding: 16px 24px 24px 24px !important;
                    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.02), 0 1px 2px 0 rgba(0, 0, 0, 0.03) !important;
                }
                
                /* Header tabel minimalis */
                .custom-table-header { 
                    display: flex; 
                    justify-content: space-between; 
                    align-items: center;
                    width: 100%;
                    padding-bottom: 4px;
                }
                
                /* Layout murni row */
                .custom-table-row { 
                    display: flex; 
                    justify-content: space-between; 
                    align-items: center; 
                    width: 100%;
                    line-height: 1.1; 
                }
                
                /* Kustomisasi eksklusif tombol detail mata (👁️) agar ramping & tidak merusak padding baris */
                .tight-table div[data-testid="stHorizontalBlock"] button {
                    background-color: #f5f3ff !important;
                    color: #6366f1 !important;
                    border: 1px solid #e0e7ff !important;
                    border-radius: 0.5rem !important;
                    padding: 0px !important;
                    width: 32px !important;
                    height: 32px !important;
                    min-height: 32px !important;
                    line-height: 32px !important;
                    font-size: 13px !important;
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    transition: all 0.2s ease !important;
                    box-shadow: none !important;
                }
                
                .tight-table div[data-testid="stHorizontalBlock"] button:hover {
                    background-color: #e0e7ff !important;
                    border-color: #c7d2fe !important;
                    color: #4f46e5 !important;
                }
                
                /* Kontrol pergeseran paginasi bawaan di luar struktur tabel kolom */
                .custom-pagination-block {
                    margin-top: 12px;
                }
                
                .custom-pagination-block button {
                    background-color: #ffffff !important;
                    color: #334155 !important;
                    border: 1px solid #e2e8f0 !important;
                    border-radius: 0.5rem !important;
                    width: auto !important;
                    height: auto !important;
                    min-height: 38px !important;
                    padding: 0.5rem 1rem !important;
                    font-size: 14px !important;
                    font-weight: 600 !important;
                    display: inline-flex !important;
                }
                
                .custom-pagination-block button:hover {
                    background-color: #f8fafc !important;
                    border-color: #cbd5e1 !important;
                    color: #0f172a !important;
                }
                
                .custom-pagination-space { 
                    padding-top: 16px; 
                }
                </style>
            """, unsafe_allow_html=True)

            st.markdown("<div class='tight-table'>", unsafe_allow_html=True)
            with st.container(border=True):
                # Header Tabel diselaraskan horizontal dengan columns data agar lurus presisi
                h_col1, h_col2 = st.columns([8.8, 1.2])
                with h_col1:
                    st.markdown("""
                        <div class='custom-table-header'>
                            <div style='width: 45%; font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.05em;'>NAMA LABEL</div>
                            <div style='width: 35%; font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.05em; text-align: center;'>MODEL STRATEGI</div>
                            <div style='width: 20%; font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.05em; text-align: center;'>TOTAL SKOR</div>
                        </div>
                    """, unsafe_allow_html=True)
                
                # Looping Data Partner Rapat & Aesthetic
                for index, row in df_display.iterrows():
                    badge_style = ""
                    if "Direct Partnership" in row['Model Strategi']: 
                        badge_style = "background-color: #ecfdf5; border: 1px solid #a7f3d0; color: #059669;"
                    elif "Aggregator" in row['Model Strategi']: 
                        badge_style = "background-color: #fff5f5; border: 1px solid #fecaca; color: #e11d48;"
                    else: 
                        badge_style = "background-color: #fffbeb; border: 1px solid #fef3c7; color: #d97706;"

                    r_col1, r_col2 = st.columns([8.8, 1.2])
                    with r_col1:
                        st.markdown(f"""
                            <div class='custom-table-row'>
                                <div style='width: 45%; font-weight: 700; color: #0f172a; font-size: 14px;'>{row['Nama Label']}</div>
                                <div style='width: 35%; text-align: center;'>
                                    <span style='padding: 4px 12px; border-radius: 9999px; font-size: 11px; font-weight: 600; display: inline-block; {badge_style}'>
                                        {row['Model Strategi']}
                                    </span>
                                </div>
                                <div style='width: 20%; font-weight: 800; color: #1e293b; font-size: 14px; text-align: center;'>{row['Total Skor']}</div>
                            </div>
                        """, unsafe_allow_html=True)
                    
                    with r_col2:
                        global_index = index + start_idx
                        if st.button("👁️", key=f"btn_dash_{group}_{row['ID']}_{global_index}", help="Lihat Detail Audit"): 
                            st.session_state.current_audit_id = str(row['ID']).split('.')[0] if pd.notna(row['ID']) and str(row['ID']) != 'nan' else ""
                            st.session_state.pindah_ke_audit = True
                            st.rerun()
                
                # --- NAVIGASI PAGING ---
                st.markdown("<div class='custom-pagination-space'></div>", unsafe_allow_html=True)
                st.markdown("<div class='custom-pagination-block'>", unsafe_allow_html=True)
                p_col1, p_col2, p_col3 = st.columns([1, 2, 1])
                with p_col1:
                    if current_page > 1:
                        if st.button("⬅️ Prev", key=f"prev_{group}"): st.session_state[page_key] -= 1; st.rerun()
                with p_col2: st.markdown(f"<p style='text-align: center; color: #94a3b8; font-size: 0.85rem; padding-top: 10px;'>Halaman <b>{current_page}</b> dari {total_pages}</p>", unsafe_allow_html=True)
                with p_col3:
                    if current_page < total_pages:
                        if st.button("Next ➡️", key=f"next_{group}"): st.session_state[page_key] += 1; st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
                            
            st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("<hr style='border-color: #f1f5f9; margin: 1.5rem 0;'>", unsafe_allow_html=True)

# Tampilan 2: PANDUAN STRATEGI
elif view == "Panduan Strategi":
    st.markdown('<div class="bg-gradient-strategy"><h2 style="margin:0;">MANAGING MUSIC PARTNERS</h2><p style="margin:5px 0 0 0; opacity:0.9;">Data-Driven Scoring Approach & Implementation Framework to manage Fraud Risk, Market Share, and Strategic Value.</p></div>', unsafe_allow_html=True)
    st.markdown("### ⚖️ The 4 Evaluation Criteria")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown("<div class='card-crit'><h3>35%</h3><b>Market Share</b><p style='font-size:12px;'>Kontribusi terhadap total streams & revenue langsung.</p></div>", unsafe_allow_html=True)
    with c2: st.markdown("<div class='card-crit'><h3>25%</h3><b>New Content</b><p style='font-size:12px;'>Aktivitas rilis baru 12 bulan terakhir.</p></div>", unsafe_allow_html=True)
    with c3: st.markdown("<div class='card-crit'><h3>25%</h3><b>Fraud History</b><p style='font-size:12px;'>Keamanan & proteksi integritas pendapatan.</p></div>", unsafe_allow_html=True)
    with c4: st.markdown("<div class='card-crit'><h3>15%</h3><b>Marketing Value</b><p style='font-size:12px;'>Kekuatan katalog historis dan reputasi artis.</p></div>", unsafe_allow_html=True)
    st.markdown("---")
    
    d1, d2 = st.columns(2)
    with d1:
        st.markdown("### Decision Framework")
        st.success("**1. Direct Partnership**\n\nUntuk high performer di seluruh metrik (Skor ≥ 70).")
        st.error("**2. Aggregator Model (Langitku)**\n\nUntuk partner dengan aktivitas rilis rendah, market share kecil, atau risiko fraud tinggi.")
        st.warning("**3. Direct Strategic**\n\nPengecualian khusus untuk label dengan nilai katalog historis tinggi meskipun rilis baru rendah.")
    with d2:
        st.markdown("### Implementation Timeline")
        st.info("📅 **Week 1-2: Data & Model**\n\nPengumpulan data dan analisis migrasi awal.")
        st.info("📅 **Week 3-5: Pilot Scoring (Internal)**\n\nUji coba skoring internal dan pembuatan draft komunikasi.")
        st.info("📅 **Week 6-9: Full Rollout**\n\nImplementasi menyeluruh sistem skoring baru.")
        st.info("📅 **Week 10: Transitions**\n\nMigrasi penuh ke Aggregator (Langitku) & Monitoring berkelanjutan.")

# Tampilan 3: EVALUASI PARTNER BARU
elif view == "Evaluasi Partner":
    st.header("Evaluasi Partner Baru")
    st.markdown("""
        <style>
        div[data-baseweb="slider"] > div > div > div { background: linear-gradient(to right, #6d28d9 0%, #8b5cf6 100%) !important; }
        div[data-testid="stSliderTickBar"] ~ div [role="slider"] { background-color: #6d28d9 !important; box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.4) !important; }
        div[data-testid="stWidgetLabel"] p { color: #0f172a !important; }
        div[data-testid="stForm"] button[data-testid="baseButton-secondaryFormSubmit"] { background-color: #5846f6 !important; color: white !important; border: none !important; padding: 0.6rem 1.5rem !important; border-radius: 1rem !important; font-weight: 700 !important; font-size: 16px !important; box-shadow: 0 4px 12px rgba(88, 70, 246, 0.25) !important; transition: all 0.2s ease !important; }
        div[data-testid="stForm"] button[data-testid="baseButton-secondaryFormSubmit"]:hover { background-color: #4332eb !important; box-shadow: 0 6px 16px rgba(88, 70, 246, 0.4) !important; transform: translateY(-1px); }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown("<div style='background-color: #f5f3ff; border-left: 4px solid #6d28d9; padding: 1rem; border-radius: 0.5rem; margin-bottom: 1.5rem;'><p style='color: #5b21b6; font-size: 14px; margin: 0; font-weight: 500;'>ℹ️ <b>Panduan Input (Skala 0-10):</b> Masukkan nilai 0 hingga 10 untuk setiap kriteria berdasarkan data historis. Sistem otomatis akan menentukan apakah partner layak menjadi <b>Direct Partner</b> atau dialihkan ke <b>Aggregator (Langitku)</b>.</p></div>", unsafe_allow_html=True)
    
    db_labels = [p['Nama_Label'] for p in st.session_state.partners if not str(p.get('Partner_ID', '')).startswith("SIM-")]
    dropdown_options = ["-- Masukkan Label Baru (Manual) --"] + db_labels
    selected_option = st.selectbox("🎯 Cari & Muat Data Otomatis dari BigQuery (Opsional)", options=dropdown_options)
    
    default_nama, default_status, default_market, default_content, default_fraud, default_marketing = "", "CALON", 5, 5, 5, 5
    if selected_option != "-- Masukkan Label Baru (Manual) --":
        matched_partner = next((p for p in st.session_state.partners if p['Nama_Label'] == selected_option), None)
        if matched_partner:
            default_nama = matched_partner.get('Nama_Label', '')
            default_status = str(matched_partner.get('Status_Kemitraan', 'CALON')).upper().strip()
            default_market = int(matched_partner.get('Market_Share_Score', 5))
            default_content = int(matched_partner.get('New_Content_Score', 5))
            default_fraud = int(matched_partner.get('Fraud_Risk_Score', 5))
            default_marketing = int(matched_partner.get('Marketing_Value_Score', 5))

    status_list = ["CALON", "EKSISTING", "NON-AKTOP", "NON-AKTIF"]
    status_display_list = ["CALON (Partner Baru)", "EKSISTING (Mitra Aktif)", "NON-AKTIF (Selesai Kontrak)"]
    status_index = status_list.index(default_status) if default_status in status_list else 0

    with st.form("vetting_form"):
        col_prof1, col_prof2 = st.columns(2)
        with col_prof1:
            with st.container(border=True):
                st.markdown("<p style='font-weight:700; color:#0f172a; margin-bottom:2px;'>Nama Label</p>", unsafe_allow_html=True)
                nama_label = st.text_input("Nama Label", value=default_nama, placeholder="Masukkan Nama Label", label_visibility="collapsed")
        with col_prof2:
            with st.container(border=True):
                st.markdown("<p style='font-weight:700; color:#0f172a; margin-bottom:2px;'>Status Kemitraan</p>", unsafe_allow_html=True)
                status_kemitraan_display = st.selectbox("Status Kemitraan", status_display_list, index=status_index, label_visibility="collapsed")
                status_kemitraan = status_list[status_display_list.index(status_kemitraan_display)]

        st.markdown("<br>", unsafe_allow_html=True)
        col_metrics1, col_metrics2 = st.columns(2)
        with col_metrics1:
            with st.container(border=True):
                st.markdown("<p style='font-weight:700; color:#0f172a; margin-bottom:2px;'>Market Share Score</p>", unsafe_allow_html=True)
                market_share = st.slider("Market Share Score", 0, 10, value=default_market, label_visibility="collapsed")
        with col_metrics2:
            with st.container(border=True):
                st.markdown("<p style='font-weight:700; color:#0f172a; margin-bottom:2px;'>New Content Score</p>", unsafe_allow_html=True)
                new_content = st.slider("New Content Score", 0, 10, value=default_content, label_visibility="collapsed")

        st.markdown("<br>", unsafe_allow_html=True)
        col_metrics3, col_metrics4 = st.columns(2)
        with col_metrics3:
            with st.container(border=True):
                st.markdown("<p style='font-weight:700; color:#0f172a; margin-bottom:2px;'>Fraud Risk Score</p>", unsafe_allow_html=True)
                fraud_risk = st.slider("Fraud Risk Score", 0, 10, value=default_fraud, label_visibility="collapsed")
        with col_metrics4:
            with st.container(border=True):
                st.markdown("<p style='font-weight:700; color:#0f172a; margin-bottom:2px;'>Marketing Value Score</p>", unsafe_allow_html=True)
                marketing_value = st.slider("Marketing Value Score", 0, 10, value=default_marketing, label_visibility="collapsed")

        st.markdown("<br>", unsafe_allow_html=True)
        col_btn1, col_btn2 = st.columns([3, 1])
        with col_btn2: submitted = st.form_submit_button("🔮 Hitung & Analisis Strategi", use_container_width=True)
        
    if submitted:
        if not nama_label: 
            st.error("Nama Label wajib diisi!")
        else:
            eval_partner = {
                'Partner_ID': f"SIM-{int(time.time())}", 
                'Nama_Label': nama_label, 
                'Status_Kemitraan': status_kemitraan,
                'Market_Share_Score': market_share, 
                'New_Content_Score': new_content, 
                'Fraud_Risk_Score': fraud_risk, 
                'Marketing_Value_Score': marketing_value, 
                'gemini_insight': None
            }
            score = calculate_score(eval_partner)
            decision = get_partner_decision(eval_partner)
            
            st.markdown("---")
            st.markdown("### Hasil Keputusan Strategi")
            c_res1, c_res2 = st.columns([2, 1])
            with c_res1: 
                st.subheader(f"🏷️ {eval_partner['Nama_Label']}")
                st.metric("Rekomendasi Sistem", decision['type'])
            with c_res2: 
                st.metric("Total Skor Kelayakan", f"{score}/100")
                
            with st.spinner("✨ Menganalisis pilar metrik melalui AI..."):
                insight = get_vetting_insights(eval_partner, score, decision['type'])
                eval_partner['gemini_insight'] = insight
                
            st.markdown("#### 🪄 AI Strategic Insight")
            st.info(insight)
            
            # ==================================================================
            # --- PROSES SIMPAN PERMANEN KE GOOGLE SHEETS VIA ST.CONNECTION ---
            # ==================================================================
            try:
                from streamlit_gsheets import GSheetsConnection
                
                # Inisialisasi koneksi Google Sheets (menggunakan credentials yang sama dengan BigQuery)
                conn = st.connection("gsheets", type=GSheetsConnection)
                
                # Masukkan URL link Google Sheet Anda di bawah ini
                spreadsheet_url = "https://docs.google.com/spreadsheets/d/MASUKKAN_ID_SPREADSHEET_ANDA/edit"
                
                # 1. Baca data yang sudah ada di sheet saat ini
                existing_df = conn.read(spreadsheet=spreadsheet_url)
                
                # 2. Konversi data simulasi baru menjadi DataFrame
                new_row = pd.DataFrame([{
                    'Partner_ID': eval_partner['Partner_ID'],
                    'Nama_Label': eval_partner['Nama_Label'],
                    'Status_Kemitraan': eval_partner['Status_Kemitraan'],
                    'Market_Share_Score': eval_partner['Market_Share_Score'],
                    'New_Content_Score': eval_partner['New_Content_Score'],
                    'Fraud_Risk_Score': eval_partner['Fraud_Risk_Score'],
                    'Marketing_Value_Score': eval_partner['Marketing_Value_Score']
                }])
                
                # 3. Gabungkan data lama dengan baris baru (append)
                updated_df = pd.concat([existing_df, new_row], ignore_index=True)
                
                # 4. Tulis balik seluruh dataframe yang telah diperbarui ke Google Sheets
                conn.update(spreadsheet=spreadsheet_url, data=updated_df)
                st.success("✅ Data simulasi berhasil disimpan secara permanen ke Google Sheets!")
                
            except Exception as e:
                st.warning(f"Gagal menyimpan ke Google Sheets secara permanen: {e}")
            # ==================================================================
            
            # Tetap simpan ke local session state agar langsung muncul di dashboard saat ini
            existing_idx = next((i for i, p in enumerate(st.session_state.partners) if p['Nama_Label'] == nama_label), None)
            if existing_idx is not None:
                st.session_state.partners[existing_idx].update(eval_partner)
                st.toast("Data simulasi partner berhasil diperbarui di dashboard!")
            else:
                st.session_state.partners.append(eval_partner)
                st.toast("Data simulasi partner berhasil ditambahkan ke dashboard!")

# Tampilan 4: AUDIT PORTOFOLIO PARTNER
elif view == "Audit Portofolio":
    st.header("Audit Portofolio Partner")
    
    if st.session_state.current_audit_id is not None:
        target_id = str(st.session_state.current_audit_id).strip().split('.')[0]
        partner = next((p for p in st.session_state.partners if str(p.get('Partner_ID', '')).strip().split('.')[0] == target_id), None)
        
        if partner:
            if st.button("⬅️ Kembali ke Daftar"): st.session_state.current_audit_id = None; st.rerun()
                
            score = calculate_score(partner)
            decision = get_partner_decision(partner)
            is_simulated = str(partner.get('Partner_ID', '')).startswith("SIM-")
            
            nama_display = f"✨ [Simulasi Vetting] {partner['Nama_Label']}" if is_simulated else partner['Nama_Label']
            st.markdown(f"## {nama_display}")
            st.markdown(f"Status: `{partner['Status_Kemitraan']}` | Klasifikasi: ` {decision['type']} `")
            st.metric("Total Skor Kelayakan", f"{score}/100")
            
            st.markdown("---")
            col_det1, col_det2 = st.columns([2, 3])
            with col_det1:
                st.markdown("### 📊 Metrik 0-10")
                for field in TEMPLATE_FIELDS:
                    val = partner.get(field['id'], 0)
                    contr = (val / field['max']) * field['weight'] * 100
                    st.write(f"**{field['label']}**: {val}/10")
                    st.progress(val / 10)
                    st.caption(f"Kontribusi: +{contr:.1f} Pts")
                    
            with col_det2:
                st.markdown("### 🪄 Rekomendasi AI")
                if st.button("🔄 Perbarui Analisis", key=f"ref_ai_{partner.get('Partner_ID')}"): partner['gemini_insight'] = None; st.rerun()
                    
                if partner.get('gemini_insight'): st.info(partner['gemini_insight'])
                else:
                    with st.spinner("✨ AI sedang merumuskan ringkasan audit..."): partner['gemini_insight'] = get_audit_summary(partner)
                    st.info(partner['gemini_insight'])
        else: st.session_state.current_audit_id = None
            
    else:
        f_cols = st.columns(3)
        show_eksisting = f_cols[0].checkbox("EKSISTING ", value=True)
        show_calon = f_cols[1].checkbox("CALON ", value=True)
        show_non_aktif = f_cols[2].checkbox("NON-AKTIF ", value=True)
        
        allowed_status = [s for s, v in [('EKSISTING', show_eksisting), ('CALON', show_calon), ('NON-AKTIF', show_non_aktif)] if v]
        audit_partners = [p for p in st.session_state.partners if p['Status_Kemitraan'] in allowed_status]
        
        if len(audit_partners) > 0:
            cols_per_row = 3
            for i in range(0, len(audit_partners), cols_per_row):
                row_partners = audit_partners[i:i+cols_per_row]
                cols = st.columns(len(row_partners))
                for idx, p in enumerate(row_partners):
                    with cols[idx]:
                        score = calculate_score(p)
                        decision = get_partner_decision(p)
                        st.markdown(f"### {p['Nama_Label']}")
                        st.caption(f"Status: {p['Status_Kemitraan']}")
                        st.markdown(f"**Skor: {score}**\n`{decision['type']}`")
                        p_id = p['Partner_ID'] if pd.notna(p['Partner_ID']) and p['Partner_ID'] != "" else "KOSONG"
                        if st.button("Detail Skor ➡️", key=f"btn_audit_{p_id}_{i}_{idx}"): st.session_state.current_audit_id = p['Partner_ID']; st.rerun()
        else: st.info("Tidak ada partner yang sesuai dengan filter.")
