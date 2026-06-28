"""
termostat_app — usporedba klime tvoje lokacije i lokaliteta vrste (vidi DIZAJN.md).
Pokretanje:  streamlit run app.py
"""
import datetime
import json
import urllib.parse
import urllib.request
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_searchbox import st_searchbox

MJESECI = ["Sij", "Velj", "Ozu", "Tra", "Svi", "Lip",
           "Srp", "Kol", "Ruj", "Lis", "Stu", "Pro"]
ZELENA, CRVENA = "#2ca02c", "#d62728"


# ---------------------------------------------------------------- weather API (Open-Meteo)
@st.cache_data(ttl=86400, show_spinner=False)
def geokodiraj(grad):
    """Grad -> lista mogućih lokacija (naziv, država, koordinate)."""
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": grad, "count": 5, "language": "hr", "format": "json"})
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.load(r).get("results", [])


@st.cache_data(ttl=86400, show_spinner=False)
def klima_mjesecno(lat, lon):
    """12 mjesečnih prosjeka temperature (zadnjih 10 punih godina)."""
    do_g = datetime.date.today().year - 1
    od_g = do_g - 9
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "start_date": f"{od_g}-01-01", "end_date": f"{do_g}-12-31",
        "daily": "temperature_2m_mean", "timezone": "auto"})
    with urllib.request.urlopen(url, timeout=40) as r:
        d = json.load(r)["daily"]
    df = pd.DataFrame({"dan": pd.to_datetime(d["time"]),
                       "t": d["temperature_2m_mean"]}).dropna()
    po_mjesecu = df.groupby(df["dan"].dt.month)["t"].mean()
    return [round(float(po_mjesecu.get(m, np.nan)), 1) for m in range(1, 13)]


@st.cache_data(ttl=86400, show_spinner=False)
def klima_dnevno(lat, lon):
    """Prosječni dnevni hod temperature (24 vrijednosti, prosjek zadnje 2 god.)."""
    do_g = datetime.date.today().year - 1
    od_g = do_g - 1
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "start_date": f"{od_g}-01-01", "end_date": f"{do_g}-12-31",
        "hourly": "temperature_2m", "timezone": "auto"})
    with urllib.request.urlopen(url, timeout=60) as r:
        h = json.load(r)["hourly"]
    df = pd.DataFrame({"v": pd.to_datetime(h["time"]),
                       "t": h["temperature_2m"]}).dropna()
    po_satu = df.groupby(df["v"].dt.hour)["t"].mean()
    return [round(float(po_satu.get(s, np.nan)), 1) for s in range(24)]


# ---------------------------------------------------------------- racun
def godisnja_krivulja(vrijednosti, pomak):
    return np.roll(np.array(vrijednosti, dtype=float), pomak)


def dnevni_iz_mjesecnih(mjesecne, raspon=8):
    """Gruba dnevna krivulja iz godišnjeg prosjeka (offline fallback)."""
    m = float(np.nanmean(np.array(mjesecne, dtype=float)))
    sati = np.arange(24)
    return list(m + (raspon / 2) * np.cos(2 * np.pi * (sati - 15) / 24))


def najbolji_pomak(crveno, zeleno):
    """Pomak (0-11 mj) pri kojem se crvena najbolje poklopi sa zelenom (ili None)."""
    c, z = np.array(crveno, dtype=float), np.array(zeleno, dtype=float)
    if c.max() - c.min() < 3:
        return None
    return int(np.argmax([np.corrcoef(z, np.roll(c, p))[0, 1] for p in range(12)]))


def podudaranje(crveno, zeleno, pomak):
    """Koliko se trenutno poklapaju (0-100 %) ili None."""
    c, z = np.array(crveno, dtype=float), np.array(zeleno, dtype=float)
    if c.std() < 0.5 or z.std() < 0.5:
        return None
    return max(0.0, np.corrcoef(z, np.roll(c, pomak))[0, 1]) * 100


# ---------------------------------------------------------------- odabir grada (autocomplete)
def trazi_grad(upit):
    """Live pretraga gradova (za st_searchbox): vraća [(opis, (lat, lon, ime)), ...]."""
    if not upit or not upit.strip():
        return []
    try:
        rez = geokodiraj(upit)
    except Exception:
        return []
    out = []
    for g in rez:
        opis = ", ".join(x for x in (g["name"], g.get("admin1"), g.get("country")) if x)
        out.append((opis, (g["latitude"], g["longitude"], g["name"])))
    return out


def grad_searchbox(label, kljuc):
    """Prazan combobox za odabir grada. Vraća {ime,lat,lon} ili None."""
    izbor = st_searchbox(trazi_grad, placeholder=label, label=label, key=kljuc)
    if izbor:
        lat, lon, ime = izbor
        return {"ime": ime, "lat": lat, "lon": lon}
    return None


def klima_lokacije(loc):
    """Iz spremljene lokacije {ime,lat,lon} dohvati klimu. None ako lokacija nije postavljena."""
    if not loc:
        return None
    try:
        with st.spinner("Dohvaćam klimu…"):
            mj = klima_mjesecno(loc["lat"], loc["lon"])
            dn = klima_dnevno(loc["lat"], loc["lon"])
        if not np.isnan(np.array(mj, dtype=float)).any():
            return {"ime": loc["ime"], "mjesecne": mj, "dnevne": dn}
    except Exception as e:
        st.warning(f"API nedostupan ({e}).")
    return {"ime": loc["ime"], "mjesecne": FB, "dnevne": dnevni_iz_mjesecnih(FB)}


# ---------------------------------------------------------------- UI
st.set_page_config(page_title="Termostat za terarij", page_icon="🦎", layout="wide")
FB = [8, 8, 11, 14, 18, 22, 25, 25, 21, 16, 12, 9]  # offline fallback (Split)

if "terariji" not in st.session_state:
    st.session_state.terariji = [
        {"ime": "Terarij 1", "vrsta": "Morelia viridis (Biak)",
         "moj": {"ime": "Split", "lat": 43.51, "lon": 16.44},
         "lok": {"ime": "Biak", "lat": -1.18, "lon": 136.08}, "pomak": 0},
        {"ime": "Terarij 2", "vrsta": "Morelia spilota",
         "moj": {"ime": "Split", "lat": 43.51, "lon": 16.44},
         "lok": {"ime": "Sydney", "lat": -33.87, "lon": 151.21}, "pomak": 6},
    ]

# ============================ SIDEBAR ============================
with st.sidebar:
    st.header("🦎 Moji terariji")

    imena = [t["ime"] for t in st.session_state.terariji]
    if imena:
        odabran = st.radio("Odaberi terarij", range(len(imena)),
                           format_func=lambda i: imena[i])
        terarij = st.session_state.terariji[odabran]
    else:
        st.info("Nema terarija — dodaj prvi u „➕ Dodaj terarij”.")
        odabran, terarij = None, None

    with st.expander("➕ Dodaj terarij", expanded=not imena):
        novo_ime = st.text_input("Naziv", "")
        nova_vrsta = st.text_input("Vrsta", "")
        st.caption("📍 Lokacije:")
        novi_moj = grad_searchbox("Moja lokacija", "add_moj")
        novi_lok = grad_searchbox("Grad lokaliteta", "add_lok")
        if st.button("Spremi terarij") and novo_ime.strip():
            if novo_ime.strip() in [t["ime"] for t in st.session_state.terariji]:
                st.error(f"Terarij „{novo_ime.strip()}” već postoji — odaberi drugo ime.")
            else:
                st.session_state.terariji.append(
                    {"ime": novo_ime.strip(), "vrsta": nova_vrsta,
                     "moj": novi_moj, "lok": novi_lok, "pomak": 0})
                st.rerun()

    if terarij is not None:
        with st.expander("⚙️ Postavke ovog terarija"):
            novo = st.text_input("Naziv", terarij["ime"], key=f"ime_{odabran}").strip()
            druga_imena = [t["ime"] for j, t in enumerate(st.session_state.terariji) if j != odabran]
            if novo and novo in druga_imena:
                st.error(f"Već postoji terarij „{novo}” — ime mora biti jedinstveno.")
            elif novo:
                terarij["ime"] = novo
            terarij["vrsta"] = st.text_input("Vrsta", terarij.get("vrsta", ""),
                                             key=f"vrsta_{odabran}")
            st.caption(f'🟢 Moja lokacija: **{terarij["moj"]["ime"] if terarij.get("moj") else "—"}**')
            promjena_moj = grad_searchbox("Promijeni moju lokaciju", f"edit_moj_{odabran}")
            if promjena_moj:
                terarij["moj"] = promjena_moj
            st.caption(f'🔴 Lokalitet: **{terarij["lok"]["ime"] if terarij.get("lok") else "—"}**')
            promjena_lok = grad_searchbox("Promijeni grad lokaliteta", f"edit_lok_{odabran}")
            if promjena_lok:
                terarij["lok"] = promjena_lok
            if st.button("🗑 Obriši terarij"):
                st.session_state.terariji.pop(odabran)
                st.rerun()

# ============================ GLAVNI DIO ============================
if terarij is None:
    st.title("🦎 Termostat za terarij")
    st.info("ℹ️ Nemaš nijedan terarij. Dodaj prvi u „➕ Dodaj terarij” (lijevo).")
    st.stop()

st.title(terarij["ime"])
if terarij.get("vrsta"):
    st.caption(terarij["vrsta"])

moja = klima_lokacije(terarij.get("moj"))
lokalitet = klima_lokacije(terarij.get("lok"))
if moja is None or lokalitet is None:
    st.info("ℹ️ Postavi **obje lokacije** u „⚙️ Postavke ovog terarija”.")
    st.stop()

# ---- Hint za sezonski pomak ----
hint = najbolji_pomak(lokalitet["mjesecne"], moja["mjesecne"])
if hint is not None and hint != terarij["pomak"]:
    st.info(f"💡 Najbolje poklapanje sezona je na **+{hint} mj** "
            f"(klizač u kartici „Godišnja krivulja”).")

# ---- Grafovi (🟢 tvoj grad vs 🔴 lokalitet) ----
tab_dan, tab_god = st.tabs(["📈 Dnevna krivulja (24 h)", "📅 Godišnja krivulja (12 mj)"])

with tab_dan:
    st.markdown("**Prosječni dnevni hod temperature** (vanjski zrak).")
    st.caption(f"📅 {datetime.date.today().strftime('%d.%m.%Y.')}")
    base = pd.Timestamp("2024-01-01")
    vrijeme = [base + pd.Timedelta(hours=h) for h in range(24)] + \
              [base + pd.Timedelta(hours=23, minutes=59)]
    label_z = f'🟢 {moja["ime"]}'
    label_c = f'🔴 {lokalitet["ime"]}'
    dom = np.array(moja["dnevne"], dtype=float)
    red = np.array(lokalitet["dnevne"], dtype=float)

    df = pd.DataFrame({"Vrijeme": vrijeme,
                       label_z: np.append(dom, dom[0]),
                       label_c: np.append(red, red[0])})
    chart = (alt.Chart(df.melt("Vrijeme", var_name="Linija", value_name="°C"))
             .mark_line()
             .encode(
                 x=alt.X("Vrijeme:T", title=None,
                         axis=alt.Axis(format="%H:%M", tickCount=12),
                         scale=alt.Scale(domain=[base, base + pd.Timedelta(hours=23, minutes=59)])),
                 y=alt.Y("°C", title="Temperatura (°C)"),
                 color=alt.Color("Linija", title=None,
                                 scale=alt.Scale(domain=[label_z, label_c],
                                                 range=[ZELENA, CRVENA]),
                                 legend=alt.Legend(orient="bottom"))))
    st.altair_chart(chart, use_container_width=True)

with tab_god:
    pomak = st.slider("🔀 Sezonski pomak (mjeseci)", 0, 11, terarij["pomak"],
                      key=f"pomak_{odabran}")
    terarij["pomak"] = pomak

    dom_god = np.array(moja["mjesecne"], dtype=float)
    red_god = godisnja_krivulja(lokalitet["mjesecne"], pomak)
    label_z = f'🟢 {moja["ime"]} (tvoj grad)'
    label_c = f'🔴 {lokalitet["ime"]} (pomak +{pomak} mj)'

    df = pd.DataFrame({"Mjesec": MJESECI, label_z: dom_god, label_c: red_god})
    linije = (alt.Chart(df.melt("Mjesec", var_name="Linija", value_name="°C"))
              .mark_line()
              .encode(
                  x=alt.X("Mjesec", sort=MJESECI, title=None),
                  y=alt.Y("°C", title="Temperatura (°C)"),
                  color=alt.Color("Linija", title=None,
                                  scale=alt.Scale(domain=[label_z, label_c],
                                                  range=[ZELENA, CRVENA]),
                                  legend=alt.Legend(orient="bottom"))))

    st.altair_chart(linije, use_container_width=True)

    pod = podudaranje(lokalitet["mjesecne"], moja["mjesecne"], pomak)
    st.metric("Podudaranje", "—" if pod is None else f"{pod:.0f} %")
