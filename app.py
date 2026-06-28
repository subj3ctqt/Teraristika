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

MJESECI = ["Sij", "Velj", "Ozu", "Tra", "Svi", "Lip",
           "Srp", "Kol", "Ruj", "Lis", "Stu", "Pro"]
ZELENA, CRVENA, ZUTA = "#2ca02c", "#d62728", "#e0a000"


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


def prozor_parenja(crveno_pomaknuto):
    """Prozor parenja: zagrijavanje nakon najhladnijeg mjeseca (umjerena klima)."""
    arr = np.array(crveno_pomaknuto, dtype=float)
    if arr.max() - arr.min() < 3:
        return []  # ravna/ekvatorska klima
    najhladniji = int(np.argmin(arr))
    return [(najhladniji + k) % 12 for k in (2, 3, 4)]


# ---------------------------------------------------------------- odabir grada (autocomplete)
def odaberi_grad(label, zadani, kljuc, fb_mjesecne):
    """Upiši grad -> klikni točan iz ponude -> klima iz API-ja. Uvijek vrati podatke."""
    grad = st.text_input(label, zadani, key=f"upit_{kljuc}")
    r = None
    if grad.strip():
        try:
            rez = geokodiraj(grad)
            if rez:
                opis = [", ".join(x for x in (g["name"], g.get("admin1"),
                                              g.get("country")) if x) for g in rez]
                if len(rez) == 1:
                    r = rez[0]
                    st.caption(f"📍 {opis[0]}")
                else:
                    i = st.radio("Odaberi grad:", range(len(rez)), key=f"sel_{kljuc}",
                                 format_func=lambda i: opis[i])
                    r = rez[i]
            else:
                st.caption("Nema rezultata.")
        except Exception as e:
            st.warning(f"API nedostupan ({e}).")
    if r is not None:
        try:
            with st.spinner("Dohvaćam klimu…"):
                mj = klima_mjesecno(r["latitude"], r["longitude"])
                dn = klima_dnevno(r["latitude"], r["longitude"])
            if not np.isnan(np.array(mj, dtype=float)).any():
                return {"ime": r["name"], "grad": grad, "mjesecne": mj, "dnevne": dn}
        except Exception as e:
            st.warning(f"API nedostupan ({e}).")
    return {"ime": zadani, "grad": grad, "mjesecne": fb_mjesecne,
            "dnevne": dnevni_iz_mjesecnih(fb_mjesecne)}


# ---------------------------------------------------------------- UI
st.set_page_config(page_title="Termostat za terarij", page_icon="🦎", layout="wide")
FB = [8, 8, 11, 14, 18, 22, 25, 25, 21, 16, 12, 9]  # offline fallback (Split)

if "terariji" not in st.session_state:
    st.session_state.terariji = [
        {"ime": "Terarij 1", "vrsta": "Morelia viridis (Biak)", "grad": "Biak", "pomak": 0},
        {"ime": "Terarij 2", "vrsta": "Morelia spilota", "grad": "Sydney", "pomak": 6},
    ]

# ============================ SIDEBAR ============================
with st.sidebar:
    st.header("🦎 Moji terariji")

    st.markdown("**📍 Moja lokacija (🟢 zeleno)**")
    moja = odaberi_grad("Upiši svoj grad", "Split", "moj", FB)

    st.divider()

    imena = [t["ime"] for t in st.session_state.terariji]
    odabran = st.radio("Odaberi terarij", range(len(imena)),
                       format_func=lambda i: imena[i])
    terarij = st.session_state.terariji[odabran]

    with st.expander("➕ Dodaj terarij"):
        novo_ime = st.text_input("Naziv", "Novi terarij")
        nova_vrsta = st.text_input("Vrsta")
        if st.button("Spremi") and novo_ime.strip():
            st.session_state.terariji.append(
                {"ime": novo_ime, "vrsta": nova_vrsta, "grad": "", "pomak": 0})
            st.rerun()

    st.divider()

    st.markdown("**🔴 Lokalitet vrste (crveno)**")
    lokalitet = odaberi_grad("Upiši grad lokaliteta", terarij.get("grad", ""),
                             f"lok_{odabran}", FB)
    terarij["grad"] = lokalitet["grad"]

# ============================ GLAVNI DIO ============================
st.title(terarij["ime"])
if terarij.get("vrsta"):
    st.caption(terarij["vrsta"])

# ---- Hint za sezonski pomak ----
hint = najbolji_pomak(lokalitet["mjesecne"], moja["mjesecne"])
if hint is not None and hint != terarij["pomak"]:
    st.info(f"💡 Najbolje poklapanje sezona je na **+{hint} mj** "
            f"(klizač u kartici „Godišnja krivulja”).")

# ---- Grafovi (🟢 tvoj grad vs 🔴 lokalitet) ----
tab_dan, tab_god = st.tabs(["📈 Dnevna krivulja (24 h)", "📅 Godišnja krivulja (12 mj)"])

with tab_dan:
    st.markdown("**Prosječni dnevni hod temperature** (vanjski zrak).")
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

    prozor = prozor_parenja(red_god)
    oznake = (alt.Chart(pd.DataFrame({"Mjesec": [MJESECI[i] for i in prozor]}))
              .mark_rule(color=ZUTA, strokeDash=[6, 4], size=2)
              .encode(x=alt.X("Mjesec", sort=MJESECI)))

    st.altair_chart(oznake + linije, use_container_width=True)

    pod = podudaranje(lokalitet["mjesecne"], moja["mjesecne"], pomak)
    c1, c2 = st.columns([1, 2])
    c1.metric("Podudaranje", "—" if pod is None else f"{pod:.0f} %")
    if prozor:
        c2.caption(f"🟡 Procijenjena sezona parenja: **{', '.join(MJESECI[i] for i in prozor)}**")
