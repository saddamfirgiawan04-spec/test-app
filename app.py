"""
Dashboard Terpadu Bagian Bangunan
Biro Umum · Kementerian Sekretariat Negara · TA 2026
Database: Google Sheets (permanen)
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os
from datetime import datetime, date
import hashlib

# Google Sheets
import gspread
from google.oauth2.service_account import Credentials

# ─────────────────────────────────────────────
# KONFIGURASI HALAMAN
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Dashboard Bangunan Kemensetneg",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────
# CSS KUSTOM
# ─────────────────────────────────────────────
st.markdown("""
<style>
    /* Header utama */
    .main-header {
        background: linear-gradient(135deg, #1a3a5c 0%, #2e6da4 100%);
        color: white;
        padding: 20px 28px;
        border-radius: 10px;
        margin-bottom: 24px;
    }
    .main-header h1 { color: white; margin: 0; font-size: 1.6rem; }
    .main-header p { color: #c8dff0; margin: 4px 0 0 0; font-size: 0.85rem; }

    /* KPI Cards */
    .kpi-card {
        background: white;
        border-radius: 10px;
        padding: 16px 20px;
        border-left: 4px solid #2e6da4;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        margin-bottom: 12px;
    }
    .kpi-card.green { border-left-color: #27ae60; }
    .kpi-card.orange { border-left-color: #e67e22; }
    .kpi-card.red { border-left-color: #e74c3c; }
    .kpi-card .label { font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }
    .kpi-card .value { font-size: 1.5rem; font-weight: 700; color: #1a3a5c; margin-top: 2px; }
    .kpi-card .sub { font-size: 0.78rem; color: #555; margin-top: 2px; }

    /* Badge status */
    .badge-selesai { background: #d4edda; color: #155724; padding: 2px 10px; border-radius: 12px; font-size: 0.78rem; font-weight: 600; }
    .badge-proses { background: #fff3cd; color: #856404; padding: 2px 10px; border-radius: 12px; font-size: 0.78rem; font-weight: 600; }
    .badge-belum { background: #f8d7da; color: #721c24; padding: 2px 10px; border-radius: 12px; font-size: 0.78rem; font-weight: 600; }

    /* Sidebar */
    section[data-testid="stSidebar"] { background: #1a3a5c; }
    section[data-testid="stSidebar"] * { color: white !important; }

    /* Divider */
    .section-divider { border-top: 2px solid #e8eef5; margin: 20px 0; }

    /* Info box */
    .info-box { background: #eaf4fb; border-radius: 8px; padding: 12px 16px; border-left: 3px solid #2e6da4; margin: 12px 0; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# DATA LAYER — GOOGLE SHEETS + JSON FALLBACK
# ─────────────────────────────────────────────
DATA_FILE = "data_dashboard.json"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_gsheet_client():
    """Buat koneksi ke Google Sheets menggunakan Streamlit Secrets."""
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception:
        return None

def get_spreadsheet():
    """Ambil spreadsheet dashboard. Buat sheet baru jika belum ada."""
    client = get_gsheet_client()
    if client is None:
        return None
    try:
        sheet_name = st.secrets.get("sheet_name", "Dashboard Bangunan Kemensetneg")
        try:
            return client.open(sheet_name)
        except gspread.SpreadsheetNotFound:
            # Buat spreadsheet baru otomatis
            sp = client.create(sheet_name)
            return sp
    except Exception:
        return None

@st.cache_data(ttl=30)  # Cache 30 detik agar tidak terlalu sering baca Sheets
def load_sheet_data(sheet_tab):
    """Baca data dari satu tab Google Sheets, return list of dicts."""
    sp = get_spreadsheet()
    if sp is None:
        return None
    try:
        ws = sp.worksheet(sheet_tab)
        records = ws.get_all_records()
        return records
    except gspread.WorksheetNotFound:
        return []
    except Exception:
        return None

def save_sheet_data(sheet_tab, headers, rows_of_dicts):
    """Tulis ulang seluruh tab dengan data baru."""
    sp = get_spreadsheet()
    if sp is None:
        return False
    try:
        try:
            ws = sp.worksheet(sheet_tab)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = sp.add_worksheet(title=sheet_tab, rows=500, cols=30)

        if not rows_of_dicts:
            ws.update([headers])
            return True

        values = [headers]
        for row in rows_of_dicts:
            values.append([str(row.get(h, "")) for h in headers])
        ws.update(values)
        # Cache harus di-invalidate setelah save
        load_sheet_data.clear()
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan ke Google Sheets: {e}")
        return False

# ── Header MAK & PEKERJAAN di Google Sheets ──
MAK_HEADERS = ["no","kro","uraian","pagu","penawaran","kontrak",
               "real_tw1","real_tw2","real_tw3","real_tw4","status","keterangan"]
PEK_HEADERS = ["no","klp","no_sib","nama","kat","pelaksana","nilai","no_adm","tgl_adm",
               "ceklist","upload_draft","ttd_pengawas","ttd_kasubbag","upload_final",
               "status","keterangan","pic"]
META_HEADERS = ["key","value"]
USER_HEADERS = ["username","password","role","nama"]

def parse_int(val):
    try: return int(float(str(val).replace(",","")))
    except: return 0

def sheets_to_mak(records):
    result = []
    for r in records:
        result.append({
            "no": parse_int(r.get("no",0)),
            "kro": str(r.get("kro","")),
            "uraian": str(r.get("uraian","")),
            "pagu": parse_int(r.get("pagu",0)),
            "penawaran": parse_int(r.get("penawaran",0)),
            "kontrak": parse_int(r.get("kontrak",0)),
            "real_tw1": parse_int(r.get("real_tw1",0)),
            "real_tw2": parse_int(r.get("real_tw2",0)),
            "real_tw3": parse_int(r.get("real_tw3",0)),
            "real_tw4": parse_int(r.get("real_tw4",0)),
            "status": str(r.get("status","")),
            "keterangan": str(r.get("keterangan","")),
        })
    return result

def sheets_to_pekerjaan(records):
    result = []
    for r in records:
        result.append({
            "no": parse_int(r.get("no",0)),
            "klp": str(r.get("klp","")),
            "no_sib": str(r.get("no_sib","")),
            "nama": str(r.get("nama","")),
            "kat": str(r.get("kat","")),
            "pelaksana": str(r.get("pelaksana","")),
            "nilai": parse_int(r.get("nilai",0)),
            "no_adm": str(r.get("no_adm","")),
            "tgl_adm": str(r.get("tgl_adm","")),
            "ceklist": parse_int(r.get("ceklist",0)),
            "upload_draft": parse_int(r.get("upload_draft",0)),
            "ttd_pengawas": parse_int(r.get("ttd_pengawas",0)),
            "ttd_kasubbag": parse_int(r.get("ttd_kasubbag",0)),
            "upload_final": parse_int(r.get("upload_final",0)),
            "status": str(r.get("status","")),
            "keterangan": str(r.get("keterangan","")),
            "pic": str(r.get("pic","")),
        })
    return result

def sheets_to_users(records):
    result = {}
    for r in records:
        uname = str(r.get("username",""))
        if uname:
            result[uname] = {
                "password": str(r.get("password","")),
                "role": str(r.get("role","Viewer")),
                "nama": str(r.get("nama",uname)),
            }
    return result if result else None

DEFAULT_USERS = {
    "admin": {"password": hash_password("bangunan2026"), "role": "Admin", "nama": "Administrator"},
    "staf":  {"password": hash_password("staf2026"),     "role": "Staf",  "nama": "Staf Bangunan"},
    "viewer":{"password": hash_password("viewer2026"),   "role": "Viewer","nama": "Pimpinan / Tamu"},
}

# Data anggaran default (dari Excel)
DEFAULT_MAK = [
    {"no":1,"kro":"051","uraian":"Pemeliharaan Gedung Hanggar (Skadron 45 & VVIP) Halim","pagu":1223284000,"penawaran":51542000,"kontrak":47348000,"real_tw1":47084000,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"↗ Proses Bayar","keterangan":""},
    {"no":2,"kro":"051","uraian":"Peralatan ME Hanggar Pesawat Kepresidenan RI Halim","pagu":1519468000,"penawaran":734565000,"kontrak":734565000,"real_tw1":718678003,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"↗ Proses Bayar","keterangan":""},
    {"no":3,"kro":"052","uraian":"Pengadaan/Penggantian Alat-Alat Listrik Rumah Negara","pagu":165375000,"penawaran":0,"kontrak":0,"real_tw1":0,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"○ Belum Kontrak","keterangan":""},
    {"no":4,"kro":"052","uraian":"Pengadaan/Penggantian Gordyn Rumah Negara","pagu":276213000,"penawaran":0,"kontrak":0,"real_tw1":0,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"○ Belum Kontrak","keterangan":""},
    {"no":5,"kro":"052","uraian":"Pengendalian Anti Rayap di Rumah Jabatan Pejabat Negara","pagu":581568000,"penawaran":121475000,"kontrak":121475000,"real_tw1":121208000,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"↗ Proses Bayar","keterangan":""},
    {"no":6,"kro":"052","uraian":"Pemeliharaan Bangunan & Halaman Rumah Negara (99.811 m²)","pagu":7072039000,"penawaran":3534049839,"kontrak":2921446000,"real_tw1":2828343000,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"↗ Proses Bayar","keterangan":""},
    {"no":7,"kro":"052","uraian":"ME Widya Chandra, Kuningan, Kemang, Perdatam, Slipi, Kemayoran","pagu":4848542000,"penawaran":4865306000,"kontrak":4746697000,"real_tw1":4624109879,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"↗ Proses Bayar","keterangan":""},
    {"no":8,"kro":"053","uraian":"Review Desain & Pengawasan Pool Kendaraan VVIP","pagu":897047000,"penawaran":897590400,"kontrak":897047000,"real_tw1":888421800,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"↗ Proses Bayar","keterangan":""},
    {"no":9,"kro":"053","uraian":"Pengadaan/Penggantian AC Split Rumah Negara (31 unit)","pagu":319362000,"penawaran":51048000,"kontrak":51048000,"real_tw1":50500000,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"↗ Proses Bayar","keterangan":""},
    {"no":10,"kro":"053","uraian":"Pengadaan/Penggantian APAR di RJPN Kemensetneg","pagu":298011000,"penawaran":0,"kontrak":298011000,"real_tw1":0,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"[K] Terkontrak","keterangan":"Terkontrak – menunggu pembayaran"},
    {"no":11,"kro":"053","uraian":"Pengadaan Peralatan ME Lengkap di Rumah Negara (60 unit)","pagu":765668000,"penawaran":11710000,"kontrak":10467000,"real_tw1":10233000,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"↗ Proses Bayar","keterangan":"Pompa, Exhaust, Water heater, Filter air"},
    {"no":12,"kro":"053","uraian":"Pengadaan/Penggantian Furniture RJPN dan Kelengkapannya","pagu":906800000,"penawaran":0,"kontrak":0,"real_tw1":0,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"○ Belum Kontrak","keterangan":""},
    {"no":13,"kro":"EBA","uraian":"Pengadaan/Penggantian Alat-Alat Listrik Gedung Kantor","pagu":165375000,"penawaran":0,"kontrak":0,"real_tw1":0,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"○ Belum Kontrak","keterangan":""},
    {"no":14,"kro":"EBA","uraian":"Pemeliharaan Halaman dan Gedung Kantor Kemensetneg (96.960 m²)","pagu":18673111000,"penawaran":4277790462,"kontrak":2832226000,"real_tw1":2492053000,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"↗ Proses Bayar","keterangan":""},
    {"no":15,"kro":"EBA","uraian":"Pemeliharaan Mekanikal dan Elektrikal Gedung dan Bangunan","pagu":10340791000,"penawaran":8410632000,"kontrak":8680393000,"real_tw1":8156980353,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"↗ Proses Bayar","keterangan":""},
    {"no":16,"kro":"EBB","uraian":"Pengadaan Peralatan ME Gedung Kantor Kemensetneg (25 unit)","pagu":256951800,"penawaran":69487000,"kontrak":80310000,"real_tw1":76985000,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"↗ Proses Bayar","keterangan":""},
    {"no":17,"kro":"EBB","uraian":"Pengadaan/Penggantian AC Split (12 unit)","pagu":109080000,"penawaran":0,"kontrak":38270000,"real_tw1":38300000,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"✓ Selesai","keterangan":""},
    {"no":18,"kro":"EBB","uraian":"Pengadaan/Penggantian APAR di Gedung Kantor","pagu":189802800,"penawaran":0,"kontrak":0,"real_tw1":0,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"○ Belum Kontrak","keterangan":""},
    {"no":19,"kro":"EBB","uraian":"Pengadaan/Penggantian Blind Gedung Kantor","pagu":131325000,"penawaran":0,"kontrak":0,"real_tw1":0,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"○ Belum Kontrak","keterangan":""},
    {"no":20,"kro":"EBB","uraian":"Perencanaan Gedung Kantor di Lingkungan Kemensetneg","pagu":200000000,"penawaran":0,"kontrak":0,"real_tw1":0,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"○ Belum Kontrak","keterangan":""},
    {"no":21,"kro":"EBB","uraian":"Pengadaan/Penggantian AC Gedung Kantor","pagu":1472335000,"penawaran":1924234000,"kontrak":1235200000,"real_tw1":1235000000,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"↗ Proses Bayar","keterangan":""},
    {"no":22,"kro":"EBB","uraian":"Pengadaan/Penggantian Furniture Gedung Kantor","pagu":5414370000,"penawaran":872806000,"kontrak":872806000,"real_tw1":920215000,"real_tw2":0,"real_tw3":0,"real_tw4":0,"status":"✓ Selesai","keterangan":""},
]

DEFAULT_PEKERJAAN = [
    {"no":1,"klp":"K1","no_sib":"134/2025","nama":"Perbaikan Panel Kolom dan Lemari Pantry Area Staff Lantai 5","kat":"GK","pelaksana":"PT. Ekatama Barizki","nilai":379550000,"no_adm":"043","tgl_adm":"2026-01-14","ceklist":1,"upload_draft":1,"ttd_pengawas":1,"ttd_kasubbag":1,"upload_final":1,"status":"SELESAI","keterangan":"","pic":"Subbag Pengawasan"},
    {"no":2,"klp":"K1","no_sib":"134A/2025","nama":"Pengadaan Furniture Ruang Zoom Biro KTLN Setneg Lantai 5","kat":"GK","pelaksana":"PT. Bahana Nuansa Indah","nilai":194860000,"no_adm":"047","tgl_adm":"2026-01-12","ceklist":1,"upload_draft":1,"ttd_pengawas":1,"ttd_kasubbag":1,"upload_final":1,"status":"SELESAI","keterangan":"","pic":"Subbag Pengawasan"},
    {"no":3,"klp":"K1","no_sib":"134A/2025","nama":"Pengadaan Meja dan Drawer Area Kerja Analisis Kebijakan Lantai 5","kat":"GK","pelaksana":"PT. Ekatama Barizki","nilai":124912000,"no_adm":"048","tgl_adm":"2026-01-12","ceklist":1,"upload_draft":1,"ttd_pengawas":1,"ttd_kasubbag":1,"upload_final":1,"status":"SELESAI","keterangan":"","pic":"Subbag Pengawasan"},
    {"no":4,"klp":"K1","no_sib":"134B/2025","nama":"Perbaikan Dinding Partisi dan Panel Dinding Biro KTLN Setneg Lantai 1","kat":"GK","pelaksana":"PT. Bahana Nuansa Indah","nilai":198061000,"no_adm":"049","tgl_adm":"2026-01-19","ceklist":1,"upload_draft":1,"ttd_pengawas":1,"ttd_kasubbag":1,"upload_final":1,"status":"SELESAI","keterangan":"","pic":"Subbag Pengawasan"},
    {"no":5,"klp":"K1","no_sib":"134B/2025","nama":"Perbaikan Plafond dan Lemari Built In Area Staf dan Ruang Arsip Lantai 1","kat":"GK","pelaksana":"PT. Rosliana Enam Sembilan","nilai":351105000,"no_adm":"050","tgl_adm":"2026-01-22","ceklist":1,"upload_draft":1,"ttd_pengawas":1,"ttd_kasubbag":1,"upload_final":1,"status":"SELESAI","keterangan":"","pic":"Subbag Pengawasan"},
    {"no":6,"klp":"K1","no_sib":"135/2025","nama":"Penambahan Solar Genset Emergensi Penanganan Gangguan Distribusi PLN","kat":"GK","pelaksana":"PT. Karya Teknik","nilai":78525000,"no_adm":"051","tgl_adm":"2026-01-25","ceklist":1,"upload_draft":1,"ttd_pengawas":1,"ttd_kasubbag":1,"upload_final":0,"status":"BELUM UPLOAD FINAL","keterangan":"","pic":"Subbag Pengawasan"},
    {"no":7,"klp":"K2","no_sib":"201/2025","nama":"Pengecatan Gedung Kantor Kemensetneg","kat":"GK","pelaksana":"PT. Warna Indah","nilai":450000000,"no_adm":"","tgl_adm":"","ceklist":0,"upload_draft":0,"ttd_pengawas":0,"ttd_kasubbag":0,"upload_final":0,"status":"BELUM MULAI","keterangan":"","pic":"Subbag Pengawasan"},
    {"no":8,"klp":"K2","no_sib":"202/2025","nama":"Perbaikan Atap Rumah Negara Widya Chandra","kat":"RN","pelaksana":"PT. Konstruksi Mandiri","nilai":325000000,"no_adm":"","tgl_adm":"","ceklist":0,"upload_draft":0,"ttd_pengawas":0,"ttd_kasubbag":0,"upload_final":0,"status":"BELUM MULAI","keterangan":"","pic":"Subbag Pengawasan"},
    {"no":9,"klp":"K2","no_sib":"203/2025","nama":"Perbaikan Instalasi Air Bersih Gedung Kantor Lantai 3-5","kat":"GK","pelaksana":"PT. Pipa Jaya","nilai":180000000,"no_adm":"055","tgl_adm":"2026-02-10","ceklist":1,"upload_draft":1,"ttd_pengawas":1,"ttd_kasubbag":0,"upload_final":0,"status":"BELUM UPLOAD DRAFT","keterangan":"Menunggu TTD Kasubbag","pic":"Subbag Pengawasan"},
    {"no":10,"klp":"K3","no_sib":"301/2025","nama":"Pengadaan Furniture Ruang Rapat Lantai 8","kat":"GK","pelaksana":"PT. Mebel Nusantara","nilai":520000000,"no_adm":"060","tgl_adm":"2026-03-01","ceklist":1,"upload_draft":1,"ttd_pengawas":0,"ttd_kasubbag":0,"upload_final":0,"status":"BELUM UPLOAD DRAFT","keterangan":"Menunggu TTD Pengawas","pic":"Subbag Pengawasan"},
]

ANGGARAN_KRO = {
    "051": {"nama": "Hanggar Pesawat Kepresidenan", "pagu": 3635323000},
    "052": {"nama": "Rumah Negara (RJPN)", "pagu": 35343497000},
    "053": {"nama": "Pengadaan Peralatan & Fasilitas RJPN", "pagu": 3186888000},
    "EBA": {"nama": "Operasional & Pemeliharaan Gedung Kantor", "pagu": 37960811000},
    "EBB": {"nama": "Pengadaan Sarana & Renovasi Gedung Kantor", "pagu": 7773863000},
}
TOTAL_PAGU = 87900383600

def _use_sheets():
    """True jika konfigurasi Google Sheets tersedia di Streamlit Secrets."""
    return "gcp_service_account" in st.secrets

def load_data():
    """
    Load data dari Google Sheets (jika tersedia) atau fallback ke JSON lokal.
    """
    if _use_sheets():
        mak_records    = load_sheet_data("MAK")
        pek_records    = load_sheet_data("PEKERJAAN")
        meta_records   = load_sheet_data("META")
        user_records   = load_sheet_data("USERS")

        mak        = sheets_to_mak(mak_records)        if mak_records        else DEFAULT_MAK
        pekerjaan  = sheets_to_pekerjaan(pek_records)  if pek_records        else DEFAULT_PEKERJAAN
        users      = sheets_to_users(user_records)     if user_records       else DEFAULT_USERS

        last_update = "–"
        update_by   = "Sistem"
        if meta_records:
            meta_dict = {r["key"]: r["value"] for r in meta_records if "key" in r}
            last_update = meta_dict.get("last_update", "–")
            update_by   = meta_dict.get("update_by",   "Sistem")

        # Jika Sheets masih kosong (baru pertama kali), isi dengan data default
        if not mak:
            mak = DEFAULT_MAK
            _init_sheets_with_defaults()
        if not pekerjaan:
            pekerjaan = DEFAULT_PEKERJAAN

        return {
            "users": users,
            "mak": mak,
            "pekerjaan": pekerjaan,
            "last_update": last_update,
            "update_by": update_by,
            "_source": "sheets",
        }
    else:
        # Fallback: baca dari JSON lokal
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                d["_source"] = "local"
                return d
        return {
            "users": DEFAULT_USERS,
            "mak": DEFAULT_MAK,
            "pekerjaan": DEFAULT_PEKERJAAN,
            "last_update": datetime.now().isoformat(),
            "update_by": "Sistem",
            "_source": "local",
        }

def _init_sheets_with_defaults():
    """Isi Google Sheets dengan data default saat pertama kali dijalankan."""
    save_sheet_data("MAK", MAK_HEADERS, DEFAULT_MAK)
    save_sheet_data("PEKERJAAN", PEK_HEADERS, DEFAULT_PEKERJAAN)
    # Buat sheet USERS dari DEFAULT_USERS
    user_rows = [{"username": k, "password": v["password"],
                  "role": v["role"], "nama": v["nama"]}
                 for k, v in DEFAULT_USERS.items()]
    save_sheet_data("USERS", USER_HEADERS, user_rows)
    save_sheet_data("META", META_HEADERS, [
        {"key": "last_update", "value": datetime.now().isoformat()},
        {"key": "update_by",   "value": "Sistem"},
    ])

def save_data(data):
    """
    Simpan data ke Google Sheets (jika tersedia) atau fallback ke JSON lokal.
    """
    now_str   = datetime.now().isoformat()
    update_by = data.get("update_by", "Sistem")

    if _use_sheets():
        save_sheet_data("MAK",       MAK_HEADERS,  data["mak"])
        save_sheet_data("PEKERJAAN", PEK_HEADERS,  data["pekerjaan"])
        # Update META
        save_sheet_data("META", META_HEADERS, [
            {"key": "last_update", "value": now_str},
            {"key": "update_by",   "value": update_by},
        ])
        # Simpan users jika ada perubahan
        if "users" in data:
            user_rows = [{"username": k, "password": v["password"],
                          "role": v["role"], "nama": v["nama"]}
                         for k, v in data["users"].items()]
            save_sheet_data("USERS", USER_HEADERS, user_rows)
    else:
        # Fallback ke JSON lokal
        data["last_update"] = now_str
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────
def fmt_rp(val):
    if val is None: return "Rp 0"
    return f"Rp {val:,.0f}".replace(",", ".")

def fmt_rp_short(val):
    if val is None: return "0"
    if val >= 1_000_000_000:
        return f"Rp {val/1_000_000_000:.1f} M"
    elif val >= 1_000_000:
        return f"Rp {val/1_000_000:.0f} Jt"
    return f"Rp {val:,.0f}"

def fmt_pct(val):
    return f"{val*100:.1f}%"

def status_badge(status):
    if "SELESAI" in str(status) or "Selesai" in str(status):
        return f'<span class="badge-selesai">✓ {status}</span>'
    elif "Proses" in str(status) or "Terkontrak" in str(status):
        return f'<span class="badge-proses">↗ {status}</span>'
    else:
        return f'<span class="badge-belum">○ {status}</span>'

# ─────────────────────────────────────────────
# AUTENTIKASI
# ─────────────────────────────────────────────
def login_page(data):
    st.markdown("""
    <div class="main-header">
        <h1>🏛️ Dashboard Terpadu Bangunan</h1>
        <p>Bagian Bangunan · Biro Umum · Kementerian Sekretariat Negara · TA 2026</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("### 🔐 Login")
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Masukkan username")
            password = st.text_input("Password", type="password", placeholder="Masukkan password")
            submitted = st.form_submit_button("Masuk", use_container_width=True, type="primary")

            if submitted:
                users = data.get("users", DEFAULT_USERS)
                if username in users:
                    if users[username]["password"] == hash_password(password):
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = username
                        st.session_state["role"] = users[username]["role"]
                        st.session_state["nama"] = users[username]["nama"]
                        st.rerun()
                    else:
                        st.error("Password salah.")
                else:
                    st.error("Username tidak ditemukan.")

        st.markdown("""
        <div class="info-box">
            <b>Akun Demo:</b><br>
            👑 Admin: <code>admin</code> / <code>bangunan2026</code><br>
            ✏️ Staf: <code>staf</code> / <code>staf2026</code><br>
            👁️ Viewer: <code>viewer</code> / <code>viewer2026</code>
        </div>
        """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# HALAMAN: RINGKASAN EKSEKUTIF
# ─────────────────────────────────────────────
def page_ringkasan(data):
    mak = data["mak"]
    pekerjaan = data["pekerjaan"]

    # Hitung KPI Anggaran
    total_pagu = sum(m["pagu"] for m in mak)
    total_real = sum(m["real_tw1"] + m["real_tw2"] + m["real_tw3"] + m["real_tw4"] for m in mak)
    total_kontrak = sum(m["kontrak"] for m in mak if m["kontrak"] > 0)
    pct_real = total_real / total_pagu if total_pagu > 0 else 0

    # Hitung KPI Pekerjaan
    total_pek = len(pekerjaan)
    selesai = sum(1 for p in pekerjaan if p["status"] == "SELESAI")
    proses = sum(1 for p in pekerjaan if "UPLOAD" in p["status"] or "PROSES" in p["status"].upper())
    belum = sum(1 for p in pekerjaan if p["status"] == "BELUM MULAI")

    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🏛️ Dashboard Terpadu Bangunan</h1>
        <p>Bagian Bangunan · Biro Umum · Kementerian Sekretariat Negara · TA 2026</p>
    </div>
    """, unsafe_allow_html=True)

    last_update = data.get("last_update", "")
    try:
        dt = datetime.fromisoformat(last_update)
        update_str = dt.strftime("%d %b %Y, %H:%M")
    except:
        update_str = last_update

    st.caption(f"Update terakhir: {update_str} · Diperbarui oleh: {data.get('update_by', 'Sistem')}")
    st.markdown("---")

    # ── KPI ROW ──
    st.markdown("#### 📊 Ringkasan Anggaran")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="label">Total Pagu Bangunan</div>
            <div class="value">{fmt_rp_short(total_pagu)}</div>
            <div class="sub">TA 2026 · Revisi 3 POK DIPA</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="kpi-card green">
            <div class="label">Realisasi TW I</div>
            <div class="value">{fmt_rp_short(total_real)}</div>
            <div class="sub">{fmt_pct(pct_real)} dari pagu</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="kpi-card orange">
            <div class="label">Total Kontrak</div>
            <div class="value">{fmt_rp_short(total_kontrak)}</div>
            <div class="sub">Nilai terkontrak (MAK)</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        sisa = total_pagu - total_real
        st.markdown(f"""
        <div class="kpi-card red">
            <div class="label">Sisa Anggaran</div>
            <div class="value">{fmt_rp_short(sisa)}</div>
            <div class="sub">{fmt_pct(1-pct_real)} belum direalisasi</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### 🔨 Ringkasan Pekerjaan")
    c5, c6, c7, c8 = st.columns(4)
    with c5:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="label">Total Pekerjaan</div>
            <div class="value">{total_pek}</div>
            <div class="sub">Semua kelompok</div>
        </div>""", unsafe_allow_html=True)
    with c6:
        pct_s = selesai/total_pek*100 if total_pek else 0
        st.markdown(f"""
        <div class="kpi-card green">
            <div class="label">Selesai</div>
            <div class="value">{selesai}</div>
            <div class="sub">{pct_s:.0f}% dari total</div>
        </div>""", unsafe_allow_html=True)
    with c7:
        pct_p = proses/total_pek*100 if total_pek else 0
        st.markdown(f"""
        <div class="kpi-card orange">
            <div class="label">Dalam Proses</div>
            <div class="value">{proses}</div>
            <div class="sub">{pct_p:.0f}% dari total</div>
        </div>""", unsafe_allow_html=True)
    with c8:
        pct_b = belum/total_pek*100 if total_pek else 0
        st.markdown(f"""
        <div class="kpi-card red">
            <div class="label">Belum Mulai</div>
            <div class="value">{belum}</div>
            <div class="sub">{pct_b:.0f}% dari total</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── CHARTS ──
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### 📈 Realisasi Anggaran per KRO")
        kro_data = {}
        for m in mak:
            kro = m["kro"]
            if kro not in kro_data:
                kro_data[kro] = {"pagu": 0, "real": 0}
            kro_data[kro]["real"] += m["real_tw1"] + m["real_tw2"] + m["real_tw3"] + m["real_tw4"]
        # Gunakan ANGGARAN_KRO untuk pagu (konsisten dengan tabel, sudah termasuk Rutin)
        for kro in kro_data:
            kro_data[kro]["pagu"] = ANGGARAN_KRO.get(kro, {}).get("pagu", 0)

        df_kro = pd.DataFrame([
            {"KRO": k, "Pagu (M)": v["pagu"]/1e9, "Realisasi (M)": v["real"]/1e9,
             "% Real": v["real"]/v["pagu"]*100 if v["pagu"] > 0 else 0}
            for k, v in kro_data.items()
        ])
        fig = go.Figure()
        fig.add_trace(go.Bar(name="Pagu", x=df_kro["KRO"], y=df_kro["Pagu (M)"],
                             marker_color="#c8dff0", text=df_kro["Pagu (M)"].apply(lambda x: f"{x:.1f}M"),
                             textposition="outside"))
        fig.add_trace(go.Bar(name="Realisasi", x=df_kro["KRO"], y=df_kro["Realisasi (M)"],
                             marker_color="#2e6da4", text=df_kro["Realisasi (M)"].apply(lambda x: f"{x:.1f}M"),
                             textposition="outside"))
        fig.update_layout(barmode="group", height=320, margin=dict(t=10, b=10),
                          legend=dict(orientation="h", y=1.1),
                          yaxis_title="Miliar Rupiah", plot_bgcolor="white",
                          paper_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.markdown("#### 🟢 Status Pekerjaan")
        status_counts = {}
        for p in pekerjaan:
            s = p["status"]
            status_counts[s] = status_counts.get(s, 0) + 1

        colors = {
            "SELESAI": "#27ae60",
            "BELUM UPLOAD FINAL": "#f39c12",
            "BELUM UPLOAD DRAFT": "#e67e22",
            "BELUM MULAI": "#e74c3c",
        }
        df_status = pd.DataFrame(list(status_counts.items()), columns=["Status", "Jumlah"])
        df_status["Warna"] = df_status["Status"].map(colors)
        fig2 = px.pie(df_status, values="Jumlah", names="Status",
                      color="Status",
                      color_discrete_map=colors,
                      hole=0.45)
        fig2.update_layout(height=320, margin=dict(t=10, b=10),
                           legend=dict(orientation="h", y=-0.1),
                           paper_bgcolor="white")
        fig2.update_traces(textinfo="percent+value")
        st.plotly_chart(fig2, use_container_width=True)

    # ── TABEL RINGKASAN KRO ──
    st.markdown("---")
    st.markdown("#### 📋 Ringkasan per KRO")
    rows_kro = []
    for kro_id, kro_info in ANGGARAN_KRO.items():
        kro_mak = [m for m in mak if m["kro"] == kro_id]
        real_total = sum(m["real_tw1"]+m["real_tw2"]+m["real_tw3"]+m["real_tw4"] for m in kro_mak)
        kontrak_total = sum(m["kontrak"] for m in kro_mak if m["kontrak"] > 0)
        pagu_val = kro_info["pagu"]
        pct = real_total / pagu_val * 100 if pagu_val > 0 else 0
        rows_kro.append({
            "KRO": kro_id,
            "Nama": kro_info["nama"],
            "Pagu": fmt_rp(pagu_val),
            "Terkontrak": fmt_rp(kontrak_total),
            "Realisasi TW I": fmt_rp(real_total),
            "% Real": f"{pct:.1f}%",
        })
    df_kro_tbl = pd.DataFrame(rows_kro)
    st.dataframe(df_kro_tbl, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────
# HALAMAN: DASHBOARD ANGGARAN
# ─────────────────────────────────────────────
def page_anggaran(data):
    mak = data["mak"]

    st.markdown("## 💰 Dashboard Anggaran MAK")
    st.caption("Monitoring realisasi anggaran per item MAK · TA 2026")

    # Filter KRO
    kros = ["Semua"] + sorted(set(m["kro"] for m in mak))
    filter_kro = st.selectbox("Filter KRO:", kros)

    # Filter status
    statuses = ["Semua"] + sorted(set(m["status"] for m in mak))
    filter_status = st.selectbox("Filter Status:", statuses)

    filtered = mak
    if filter_kro != "Semua":
        filtered = [m for m in filtered if m["kro"] == filter_kro]
    if filter_status != "Semua":
        filtered = [m for m in filtered if m["status"] == filter_status]

    # Progress bar realisasi total
    total_pagu_f = sum(m["pagu"] for m in filtered)
    total_real_f = sum(m["real_tw1"]+m["real_tw2"]+m["real_tw3"]+m["real_tw4"] for m in filtered)
    pct_f = total_real_f / total_pagu_f if total_pagu_f > 0 else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Pagu (Filtered)", fmt_rp_short(total_pagu_f))
    col2.metric("Total Realisasi", fmt_rp_short(total_real_f))
    col3.metric("% Realisasi", f"{pct_f*100:.1f}%")

    st.progress(pct_f)
    st.markdown("---")

    # Tabel MAK
    rows = []
    for m in filtered:
        real_total = m["real_tw1"] + m["real_tw2"] + m["real_tw3"] + m["real_tw4"]
        pct = real_total / m["pagu"] * 100 if m["pagu"] > 0 else 0
        rows.append({
            "No": m["no"],
            "KRO": m["kro"],
            "Uraian": m["uraian"],
            "Pagu": fmt_rp(m["pagu"]),
            "Kontrak": fmt_rp(m["kontrak"]),
            "Real TW I": fmt_rp(m["real_tw1"]),
            "Real TW II": fmt_rp(m["real_tw2"]),
            "Real TW III": fmt_rp(m["real_tw3"]),
            "Real TW IV": fmt_rp(m["real_tw4"]),
            "% Real": f"{pct:.1f}%",
            "Status": m["status"],
            "Keterangan": m.get("keterangan", ""),
        })

    df = pd.DataFrame(rows)

    def color_status(val):
        if "Selesai" in str(val) or "✓" in str(val):
            return "background-color: #d4edda"
        elif "Proses" in str(val) or "Terkontrak" in str(val):
            return "background-color: #fff3cd"
        elif "Belum" in str(val) or "○" in str(val):
            return "background-color: #f8d7da"
        return ""

    styled = df.style.map(color_status, subset=["Status"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Chart realisasi per item
    st.markdown("---")
    st.markdown("#### 📊 Perbandingan Pagu vs Realisasi (Top 10)")
    df_chart = pd.DataFrame([{
        "Uraian": m["uraian"][:40] + "..." if len(m["uraian"]) > 40 else m["uraian"],
        "Pagu": m["pagu"] / 1e9,
        "Realisasi": (m["real_tw1"]+m["real_tw2"]+m["real_tw3"]+m["real_tw4"]) / 1e9,
    } for m in sorted(filtered, key=lambda x: x["pagu"], reverse=True)[:10]])

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Pagu", x=df_chart["Uraian"], y=df_chart["Pagu"],
                         marker_color="#c8dff0"))
    fig.add_trace(go.Bar(name="Realisasi", x=df_chart["Uraian"], y=df_chart["Realisasi"],
                         marker_color="#1a3a5c"))
    fig.update_layout(barmode="group", height=380, xaxis_tickangle=-30,
                      yaxis_title="Miliar Rupiah", plot_bgcolor="white", paper_bgcolor="white",
                      margin=dict(t=10, b=80), legend=dict(orientation="h", y=1.05))
    st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────
# HALAMAN: MONITORING PENGAWASAN
# ─────────────────────────────────────────────
def page_pengawasan(data):
    pekerjaan = data["pekerjaan"]

    st.markdown("## 🔨 Monitoring Pengawasan Pekerjaan")
    st.caption("Status administrasi pekerjaan · Subbag Pengawasan Bagian Bangunan · TA 2026")

    col1, col2, col3 = st.columns(3)
    with col1:
        filter_klp = st.selectbox("Kelompok:", ["Semua", "K1", "K2", "K3"])
    with col2:
        filter_kat = st.selectbox("Kategori:", ["Semua", "GK", "RN"])
    with col3:
        filter_status = st.selectbox("Status:", ["Semua", "SELESAI", "BELUM UPLOAD FINAL",
                                                  "BELUM UPLOAD DRAFT", "BELUM MULAI"])

    filtered = pekerjaan
    if filter_klp != "Semua":
        filtered = [p for p in filtered if p["klp"] == filter_klp]
    if filter_kat != "Semua":
        filtered = [p for p in filtered if p["kat"] == filter_kat]
    if filter_status != "Semua":
        filtered = [p for p in filtered if p["status"] == filter_status]

    # Progres checklist
    st.markdown("---")
    st.markdown("#### ✅ Progres Checklist Administrasi")
    cc1, cc2, cc3, cc4, cc5 = st.columns(5)
    total_f = len(filtered) if filtered else 1
    items_check = [
        ("Ceklist Lap.", "ceklist", cc1),
        ("Upload Draft", "upload_draft", cc2),
        ("TTD Pengawas", "ttd_pengawas", cc3),
        ("TTD Kasubbag", "ttd_kasubbag", cc4),
        ("Upload Final", "upload_final", cc5),
    ]
    for label, field, col in items_check:
        done = sum(1 for p in filtered if p.get(field, 0) == 1)
        pct = done / total_f
        with col:
            st.metric(label, f"{done}/{len(filtered)}")
            st.progress(pct)

    st.markdown("---")

    # Tabel pekerjaan
    rows = []
    for p in filtered:
        def ck(val): return "✓" if val == 1 else "✗"
        rows.append({
            "No": p["no"],
            "Klp": p["klp"],
            "No. SIB": p.get("no_sib", ""),
            "Nama Pekerjaan": p["nama"],
            "Kat": p["kat"],
            "Pelaksana": p["pelaksana"],
            "Nilai": fmt_rp_short(p["nilai"]),
            "No. ADM": p.get("no_adm", ""),
            "Ceklist": ck(p.get("ceklist", 0)),
            "Upl Draft": ck(p.get("upload_draft", 0)),
            "TTD Pengawas": ck(p.get("ttd_pengawas", 0)),
            "TTD Kasubbag": ck(p.get("ttd_kasubbag", 0)),
            "Upl Final": ck(p.get("upload_final", 0)),
            "Status": p["status"],
            "Keterangan": p.get("keterangan", ""),
        })

    df = pd.DataFrame(rows)

    def color_row(val):
        if val == "SELESAI":
            return "background-color: #d4edda; color: #155724"
        elif "UPLOAD" in str(val):
            return "background-color: #fff3cd; color: #856404"
        elif val == "BELUM MULAI":
            return "background-color: #f8d7da; color: #721c24"
        return ""

    styled = df.style.map(color_row, subset=["Status"])
    st.dataframe(styled, use_container_width=True, hide_index=True, height=420)

    # Chart status
    st.markdown("---")
    st.markdown("#### 📊 Distribusi Status Pekerjaan")
    status_counts = {}
    for p in filtered:
        s = p["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    if status_counts:
        colors = {"SELESAI": "#27ae60", "BELUM UPLOAD FINAL": "#f39c12",
                  "BELUM UPLOAD DRAFT": "#e67e22", "BELUM MULAI": "#e74c3c"}
        df_s = pd.DataFrame(list(status_counts.items()), columns=["Status", "Jumlah"])
        fig = px.bar(df_s, x="Status", y="Jumlah",
                     color="Status", color_discrete_map=colors, text="Jumlah")
        fig.update_layout(height=300, showlegend=False, plot_bgcolor="white",
                          paper_bgcolor="white", margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────
# HALAMAN: INPUT ANGGARAN
# ─────────────────────────────────────────────
def page_input_anggaran(data):
    st.markdown("## ✏️ Update Realisasi Anggaran")
    st.info("Pilih item MAK dan update nilai realisasi per triwulan. Data tersimpan otomatis.")

    mak = data["mak"]

    # Pilih item
    options = {f"No.{m['no']} | {m['kro']} | {m['uraian'][:50]}...": i for i, m in enumerate(mak)}
    selected_label = st.selectbox("Pilih Item MAK:", list(options.keys()))
    idx = options[selected_label]
    item = mak[idx]

    st.markdown("---")
    st.markdown(f"**{item['uraian']}**")
    st.caption(f"KRO: {item['kro']} | Pagu: {fmt_rp(item['pagu'])}")

    col1, col2 = st.columns(2)
    with col1:
        new_penawaran = st.number_input("Nilai Penawaran (Rp)", value=float(item.get("penawaran", 0)),
                                        min_value=0.0, step=1000000.0, format="%.0f")
        new_kontrak = st.number_input("Nilai Kontrak/RAB (Rp)", value=float(item.get("kontrak", 0)),
                                      min_value=0.0, step=1000000.0, format="%.0f")
    with col2:
        new_real_tw1 = st.number_input("Realisasi TW I (Rp)", value=float(item.get("real_tw1", 0)),
                                        min_value=0.0, step=1000000.0, format="%.0f")
        new_real_tw2 = st.number_input("Realisasi TW II (Rp)", value=float(item.get("real_tw2", 0)),
                                        min_value=0.0, step=1000000.0, format="%.0f")
        new_real_tw3 = st.number_input("Realisasi TW III (Rp)", value=float(item.get("real_tw3", 0)),
                                        min_value=0.0, step=1000000.0, format="%.0f")
        new_real_tw4 = st.number_input("Realisasi TW IV (Rp)", value=float(item.get("real_tw4", 0)),
                                        min_value=0.0, step=1000000.0, format="%.0f")

    status_options = ["○ Belum Kontrak", "[K] Terkontrak", "↗ Proses Bayar", "✓ Selesai"]
    new_status = st.selectbox("Status:", status_options,
                               index=status_options.index(item["status"]) if item["status"] in status_options else 0)
    new_ket = st.text_input("Keterangan:", value=item.get("keterangan", ""))

    total_real = new_real_tw1 + new_real_tw2 + new_real_tw3 + new_real_tw4
    pct = total_real / item["pagu"] * 100 if item["pagu"] > 0 else 0
    st.info(f"Total Realisasi: **{fmt_rp(int(total_real))}** ({pct:.1f}% dari pagu)")

    if st.button("💾 Simpan Perubahan", type="primary", use_container_width=True):
        mak[idx].update({
            "penawaran": int(new_penawaran),
            "kontrak": int(new_kontrak),
            "real_tw1": int(new_real_tw1),
            "real_tw2": int(new_real_tw2),
            "real_tw3": int(new_real_tw3),
            "real_tw4": int(new_real_tw4),
            "status": new_status,
            "keterangan": new_ket,
        })
        data["mak"] = mak
        data["update_by"] = st.session_state.get("nama", "Staf")
        save_data(data)
        st.success("✅ Data berhasil disimpan!")
        st.rerun()


# ─────────────────────────────────────────────
# HALAMAN: INPUT PEKERJAAN
# ─────────────────────────────────────────────
def page_input_pekerjaan(data):
    st.markdown("## ✏️ Update Status Pekerjaan")
    st.info("Update status administrasi pekerjaan. Gunakan tab Tambah untuk menambah pekerjaan baru.")

    pekerjaan = data["pekerjaan"]
    tab1, tab2 = st.tabs(["Update Pekerjaan", "Tambah Pekerjaan Baru"])

    with tab1:
        if not pekerjaan:
            st.warning("Belum ada data pekerjaan.")
            return

        options = {f"No.{p['no']} | {p['klp']} | {p['nama'][:50]}": i for i, p in enumerate(pekerjaan)}
        selected_label = st.selectbox("Pilih Pekerjaan:", list(options.keys()))
        idx = options[selected_label]
        item = pekerjaan[idx]

        st.markdown(f"**{item['nama']}**")
        st.caption(f"Kelompok: {item['klp']} | Kategori: {item['kat']} | Pelaksana: {item['pelaksana']}")
        st.caption(f"Nilai: {fmt_rp(item['nilai'])} | No. ADM: {item.get('no_adm','-')}")

        st.markdown("**Checklist Administrasi:**")
        cc1, cc2, cc3, cc4, cc5 = st.columns(5)
        with cc1: new_ceklist = st.checkbox("Ceklist Lapangan", value=bool(item.get("ceklist", 0)))
        with cc2: new_draft = st.checkbox("Upload Draft", value=bool(item.get("upload_draft", 0)))
        with cc3: new_ttd_p = st.checkbox("TTD Pengawas", value=bool(item.get("ttd_pengawas", 0)))
        with cc4: new_ttd_k = st.checkbox("TTD Kasubbag", value=bool(item.get("ttd_kasubbag", 0)))
        with cc5: new_final = st.checkbox("Upload Final", value=bool(item.get("upload_final", 0)))

        # Auto-status
        score = sum([new_ceklist, new_draft, new_ttd_p, new_ttd_k, new_final])
        if score == 5:
            auto_status = "SELESAI"
        elif score >= 3:
            auto_status = "BELUM UPLOAD FINAL"
        elif score >= 1:
            auto_status = "BELUM UPLOAD DRAFT"
        else:
            auto_status = "BELUM MULAI"

        st.markdown(f"**Status otomatis:** `{auto_status}`")

        new_ket = st.text_input("Keterangan:", value=item.get("keterangan", ""))
        new_pic = st.text_input("PIC:", value=item.get("pic", "Subbag Pengawasan"))

        if st.button("💾 Simpan", type="primary", use_container_width=True):
            pekerjaan[idx].update({
                "ceklist": int(new_ceklist),
                "upload_draft": int(new_draft),
                "ttd_pengawas": int(new_ttd_p),
                "ttd_kasubbag": int(new_ttd_k),
                "upload_final": int(new_final),
                "status": auto_status,
                "keterangan": new_ket,
                "pic": new_pic,
            })
            data["pekerjaan"] = pekerjaan
            data["update_by"] = st.session_state.get("nama", "Staf")
            save_data(data)
            st.success("✅ Status pekerjaan berhasil diperbarui!")
            st.rerun()

    with tab2:
        st.markdown("**Tambah Pekerjaan Baru**")
        with st.form("form_tambah"):
            col1, col2 = st.columns(2)
            with col1:
                t_klp = st.selectbox("Kelompok:", ["K1", "K2", "K3"])
                t_kat = st.selectbox("Kategori:", ["GK", "RN"])
                t_sib = st.text_input("No. SIB:")
                t_nama = st.text_input("Nama Pekerjaan: *", placeholder="Wajib diisi")
            with col2:
                t_pelaksana = st.text_input("Pelaksana / Kontraktor:")
                t_nilai = st.number_input("Nilai Kontrak (Rp):", min_value=0.0, step=1000000.0, format="%.0f")
                t_no_adm = st.text_input("No. ADM (BAPP/BAST):")
                t_tgl_adm = st.date_input("Tgl ADM:", value=date.today())

            t_ket = st.text_input("Keterangan:")
            submitted = st.form_submit_button("➕ Tambah Pekerjaan", use_container_width=True)

            if submitted:
                if not t_nama.strip():
                    st.error("Nama pekerjaan wajib diisi!")
                else:
                    new_no = max(p["no"] for p in pekerjaan) + 1 if pekerjaan else 1
                    new_pek = {
                        "no": new_no, "klp": t_klp, "no_sib": t_sib,
                        "nama": t_nama, "kat": t_kat, "pelaksana": t_pelaksana,
                        "nilai": int(t_nilai), "no_adm": t_no_adm,
                        "tgl_adm": str(t_tgl_adm),
                        "ceklist": 0, "upload_draft": 0, "ttd_pengawas": 0,
                        "ttd_kasubbag": 0, "upload_final": 0,
                        "status": "BELUM MULAI", "keterangan": t_ket,
                        "pic": st.session_state.get("nama", "Staf"),
                    }
                    pekerjaan.append(new_pek)
                    data["pekerjaan"] = pekerjaan
                    data["update_by"] = st.session_state.get("nama", "Staf")
                    save_data(data)
                    st.success(f"✅ Pekerjaan '{t_nama}' berhasil ditambahkan!")
                    st.rerun()


# ─────────────────────────────────────────────
# HALAMAN: MANAJEMEN USER (ADMIN ONLY)
# ─────────────────────────────────────────────
def page_admin(data):
    st.markdown("## ⚙️ Manajemen Pengguna")
    st.warning("Halaman ini hanya untuk Admin.")

    users = data.get("users", DEFAULT_USERS)

    st.markdown("#### Daftar Pengguna")
    df_users = pd.DataFrame([
        {"Username": k, "Nama": v["nama"], "Role": v["role"]}
        for k, v in users.items()
    ])
    st.dataframe(df_users, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### Tambah / Update Pengguna")
    with st.form("form_user"):
        col1, col2 = st.columns(2)
        with col1:
            new_username = st.text_input("Username:")
            new_nama = st.text_input("Nama Lengkap:")
        with col2:
            new_role = st.selectbox("Role:", ["Admin", "Staf", "Viewer"])
            new_pass = st.text_input("Password Baru:", type="password")

        submitted = st.form_submit_button("Simpan Pengguna", use_container_width=True)
        if submitted:
            if not new_username or not new_pass:
                st.error("Username dan password wajib diisi!")
            else:
                users[new_username] = {
                    "password": hash_password(new_pass),
                    "role": new_role,
                    "nama": new_nama or new_username,
                }
                data["users"] = users
                save_data(data)
                st.success(f"✅ User '{new_username}' berhasil disimpan!")
                st.rerun()


# ─────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────
def main():
    data = load_data()

    # Inisialisasi session state
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        login_page(data)
        return

    # Sidebar
    role = st.session_state.get("role", "Viewer")
    nama = st.session_state.get("nama", "User")

    with st.sidebar:
        st.markdown(f"""
        <div style="padding: 12px; margin-bottom: 16px; background: rgba(255,255,255,0.1); border-radius: 8px;">
            <div style="font-size:0.75rem; opacity:0.7;">Masuk sebagai</div>
            <div style="font-size:1rem; font-weight:700;">{nama}</div>
            <div style="font-size:0.75rem; opacity:0.7;">{role}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("### 🗂️ Menu")
        pages = {
            "🏠 Ringkasan Eksekutif": "ringkasan",
            "💰 Dashboard Anggaran": "anggaran",
            "🔨 Monitoring Pengawasan": "pengawasan",
        }
        if role in ["Admin", "Staf"]:
            pages["✏️ Input Anggaran"] = "input_anggaran"
            pages["✏️ Input Pekerjaan"] = "input_pekerjaan"
        if role == "Admin":
            pages["⚙️ Manajemen User"] = "admin"

        if "current_page" not in st.session_state:
            st.session_state["current_page"] = "ringkasan"

        for label, page_id in pages.items():
            if st.button(label, use_container_width=True,
                         type="primary" if st.session_state["current_page"] == page_id else "secondary"):
                st.session_state["current_page"] = page_id
                st.rerun()

        st.markdown("---")
        last_update = data.get("last_update", "")
        try:
            dt = datetime.fromisoformat(last_update)
            upd_str = dt.strftime("%d %b %Y %H:%M")
        except:
            upd_str = "-"
        st.markdown(f"<small>Update terakhir:<br>{upd_str}</small>", unsafe_allow_html=True)
        st.markdown(f"<small>Oleh: {data.get('update_by', '-')}</small>", unsafe_allow_html=True)

        st.markdown("---")
        # Indikator sumber data
        source = data.get("_source", "local")
        if source == "sheets":
            st.markdown("<small>💾 Database: <b>Google Sheets</b> ✅</small>", unsafe_allow_html=True)
        else:
            st.markdown("<small>💾 Database: <b>Lokal</b> ⚠️<br>Tambahkan Secrets untuk Google Sheets</small>",
                        unsafe_allow_html=True)

        st.markdown("---")
        if st.button("🚪 Keluar", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # Routing halaman
    page = st.session_state.get("current_page", "ringkasan")
    data = load_data()  # Reload data tiap halaman agar selalu fresh

    if page == "ringkasan":
        page_ringkasan(data)
    elif page == "anggaran":
        page_anggaran(data)
    elif page == "pengawasan":
        page_pengawasan(data)
    elif page == "input_anggaran" and role in ["Admin", "Staf"]:
        page_input_anggaran(data)
    elif page == "input_pekerjaan" and role in ["Admin", "Staf"]:
        page_input_pekerjaan(data)
    elif page == "admin" and role == "Admin":
        page_admin(data)
    else:
        page_ringkasan(data)


if __name__ == "__main__":
    main()
