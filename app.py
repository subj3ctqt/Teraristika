"""
termostat_app — prototip
Replikacija prirodnih uvjeta stanista u terariju (vidi DIZAJN.md).

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

# ---------------------------------------------------------------- podaci
@st.cache_data
def ucitaj_bazu():
    putanja = Path(__file__).parent / "data" / "profili.json"
    with open(putanja, encoding="utf-8") as f:
        return json.load(f)


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
    do_godine = datetime.date.today().year - 1
    od_godine = do_godine - 9
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "start_date": f"{od_godine}-01-01", "end_date": f"{do_godine}-12-31",
        "daily": "temperature_2m_mean", "timezone": "auto"})
    with urllib.request.urlopen(url, timeout=40) as r:
        d = json.load(r)["daily"]
    df = pd.DataFrame({"dan": pd.to_datetime(d["time"]),
                       "t": d["temperature_2m_mean"]}).dropna()
    po_mjesecu = df.groupby(df["dan"].dt.month)["t"].mean()
    return [round(float(po_mjesecu.get(m, np.nan)), 1) for m in range(1, 13)]


# ---------------------------------------------------------------- racun
def dnevna_krivulja(temp_dan, temp_noc, peak_sat=15):
    """24 sata: glatka krivulja, vrh popodne, minimum pred zoru."""
    sati = np.arange(24)
    sredina = (temp_dan + temp_noc) / 2
    amplituda = (temp_dan - temp_noc) / 2
    return sredina + amplituda * np.cos(2 * np.pi * (sati - peak_sat) / 24)


def godisnja_krivulja(mjesecne_vrijednosti, pomak_mjeseci):
    """Pomakni godisnju krivulju za zadani broj mjeseci (sezonski pomak)."""
    arr = np.array(mjesecne_vrijednosti, dtype=float)
    return np.roll(arr, pomak_mjeseci)


def najbolji_pomak(profil, lok):
    """Pomak (0-11 mj) pri kojem se životinjina krivulja najbolje poklopi s lokalnom."""
    zivotinja = (np.array(profil["mjesecne_temp_dan"], dtype=float)
                 + np.array(profil["mjesecne_temp_noc"], dtype=float)) / 2
    dom = np.array(lok["mjesecne_temp"], dtype=float)
    amplituda = zivotinja.max() - zivotinja.min()
    if amplituda < 3:
        return None, amplituda  # ravna klima -> pomak nije bitan
    korelacije = [np.corrcoef(dom, np.roll(zivotinja, p))[0, 1] for p in range(12)]
    return int(np.argmax(korelacije)), amplituda


def podudaranje(profil, lok, pomak):
    """Koliko se trenutno poklapaju (0-100 %) — korelacija oblika krivulja."""
    zivotinja = (np.array(profil["mjesecne_temp_dan"], dtype=float)
                 + np.array(profil["mjesecne_temp_noc"], dtype=float)) / 2
    dom = np.array(lok["mjesecne_temp"], dtype=float)
    if zivotinja.std() < 0.5 or dom.std() < 0.5:
        return None
    r = np.corrcoef(dom, np.roll(zivotinja, pomak))[0, 1]
    return max(0.0, r) * 100


def prozor_parenja(profil, pomak):
    """Procjena prozora parenja iz tipa okidaca."""
    if profil["tip_okidaca"] == "umjereni":
        noc = godisnja_krivulja(profil["mjesecne_temp_noc"], pomak)
        najhladniji = int(np.argmin(noc))
        # parenje ~ zagrijavanje 2-3 mjeseca nakon najhladnijeg
        return [(najhladniji + k) % 12 for k in (2, 3, 4)]
    else:
        # ekvatorski -> oko kisnih mjeseci
        return [(m - 1) % 12 for m in profil["kisni_mjeseci"]]


# ---------------------------------------------------------------- UI
st.set_page_config(page_title="Termostat za terarij", page_icon="🦎", layout="wide")
baza = ucitaj_bazu()
profili = baza["profili"]

# --- session: lista terarija
if "teraji" not in st.session_state:
    st.session_state.teraji = [
        {"ime": "Teraj 1 — Biak", "profil": 0, "pomak": 0},
        {"ime": "Teraj 2 — Diamond", "profil": 1, "pomak": 6},
    ]

# ============================ SIDEBAR ============================
with st.sidebar:
    st.header("🦎 Moji teraji")

    st.markdown("**📍 Moja lokacija**")
    grad = st.text_input("Upiši grad", "Split")
    lokacija_ime, lok = None, None
    try:
        rezultati = geokodiraj(grad)
        if rezultati:
            opcije = [", ".join(x for x in (r["name"], r.get("admin1"),
                                            r.get("country")) if x)
                      for r in rezultati]
            i = st.selectbox("Potvrdi lokaciju", range(len(rezultati)),
                             format_func=lambda i: opcije[i])
            r = rezultati[i]
            with st.spinner("Dohvaćam klimu (10 g. prosjek)…"):
                mjesecne = klima_mjesecno(r["latitude"], r["longitude"])
            if np.isnan(np.array(mjesecne, dtype=float)).any():
                raise ValueError("nepotpuni podaci")
            lokacija_ime, lok = r["name"], {"mjesecne_temp": mjesecne}
        else:
            st.warning("Grad nije pronađen.")
    except Exception as e:
        st.warning(f"Weather API nedostupan ({e}); koristim spremljenu lokaciju.")

    if lok is None:  # fallback na spremljene podatke
        lokacija_ime = list(baza["korisnik_lokacije"])[0]
        lok = baza["korisnik_lokacije"][lokacija_ime]

    st.divider()

    imena = [t["ime"] for t in st.session_state.teraji]
    odabran = st.radio("Odaberi teraj", range(len(imena)),
                       format_func=lambda i: imena[i])
    teraj = st.session_state.teraji[odabran]

    with st.expander("➕ Dodaj teraj"):
        novo_ime = st.text_input("Naziv terarija", "Novi teraj")
        novi_profil = st.selectbox(
            "Vrsta / lokalitet", range(len(profili)),
            format_func=lambda i: f'{profili[i]["vrsta"]} — {profili[i]["lokalitet"]}')
        if st.button("Spremi teraj"):
            st.session_state.teraji.append(
                {"ime": novo_ime, "profil": novi_profil, "pomak": 0})
            st.rerun()

profil = profili[teraj["profil"]]

# ============================ GLAVNI DIO ============================
st.title(teraj["ime"])
st.caption(f'**{profil["vrsta"]}** · lokalitet *{profil["lokalitet"]}* · '
           f'geo. širina {profil["geo_sirina"]}° · tip: {profil["tip_okidaca"]}')

# ---- B. PREGLED (auto uvjeti) ----
st.subheader("📋 Pregled uvjeta (iz lokaliteta)")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Fotoperiod",
          f'{profil["fotoperiod_min_h"]}–{profil["fotoperiod_max_h"]} h')
c2.metric("Topla točka (dan)",
          f'{profil["temp_topla_tocka_dan"][0]}–{profil["temp_topla_tocka_dan"][1]} °C')
c3.metric("Hladni kraj / noć",
          f'{profil["temp_noc"][0]}–{profil["temp_noc"][1]} °C')
c4.metric("Vlažnost", f'{profil["vlaznost"][0]}–{profil["vlaznost"][1]} %')

# ---- Sezonski pomak (hint) ----
pomak_hint, amplituda = najbolji_pomak(profil, lok)
if pomak_hint is None:
    st.info(f"🌴 Ravna klima (godišnja amplituda ~{amplituda:.0f} °C) — "
            f"sezonski pomak ovdje nije bitan.")
elif pomak_hint == teraj["pomak"]:
    st.success(f"✅ Sezonski pomak poravnat (+{teraj['pomak']} mj). "
               f"Njihova zima se poklapa s tvojom.")
else:
    st.warning(f"💡 Najbolje poklapanje je na **+{pomak_hint} mjeseci** "
               f'(da „njihova zima” padne na tvoju u {lokacija_ime}). '
               f"Trenutno: +{teraj['pomak']} mj. Klizač je u kartici „Godišnja krivulja”.")

# ---- Grafovi: PLAN vs STVARNO ----
rng = np.random.default_rng(odabran)  # demo "stvarno" = plan + sum

tab_dan, tab_god = st.tabs(["📈 Dnevna krivulja (24 h)", "📅 Godišnja krivulja (12 mj)"])

with tab_dan:
    topla = (profil["temp_topla_tocka_dan"][0] + profil["temp_topla_tocka_dan"][1]) / 2
    noc = (profil["temp_noc"][0] + profil["temp_noc"][1]) / 2
    plan = dnevna_krivulja(topla, noc)
    stvarno = plan + rng.normal(0, 0.6, 24)

    # Vremenska os 00:00 -> 23:59 (zadnja točka zatvara dan, krivulja je ciklična)
    base = pd.Timestamp("2024-01-01")
    vrijeme = [base + pd.Timedelta(hours=h) for h in range(24)] + \
              [base + pd.Timedelta(hours=23, minutes=59)]
    plan_f = np.append(plan, plan[0])
    stvarno_f = np.append(stvarno, stvarno[0])

    df = pd.DataFrame({"Vrijeme": vrijeme,
                       "Plan (cilj)": plan_f,
                       "Stvarno (demo senzor)": stvarno_f})
    df_long = df.melt("Vrijeme", var_name="Linija", value_name="°C")
    chart = (alt.Chart(df_long)
             .mark_line()
             .encode(
                 x=alt.X("Vrijeme:T", title=None,
                         axis=alt.Axis(format="%H:%M", tickCount=12),
                         scale=alt.Scale(domain=[base,
                                                 base + pd.Timedelta(hours=23, minutes=59)])),
                 y=alt.Y("°C", title="Temperatura (°C)"),
                 color=alt.Color("Linija", title=None,
                                 legend=alt.Legend(orient="bottom"))))
    st.altair_chart(chart, use_container_width=True)
    st.caption("Plava = ciljna krivulja iz profila · narančasta = (simulirano) očitanje senzora.")

with tab_god:
    st.markdown("**Pomakni životinjinu krivulju preko krivulje tvoje lokacije "
                "dok se ne poklope (najveće podudaranje).**")

    # Klizač DIREKTNO pomiče krivulju (Streamlit sam osvježi graf u istom prolazu)
    pomak = st.slider("🔀 Sezonski pomak (mjeseci)", 0, 11, teraj["pomak"],
                      key=f"pomak_{odabran}")
    teraj["pomak"] = pomak

    zivotinja_god = godisnja_krivulja(
        (np.array(profil["mjesecne_temp_dan"]) + np.array(profil["mjesecne_temp_noc"])) / 2,
        pomak)
    dom_god = np.array(lok["mjesecne_temp"], dtype=float)

    label_dom = f'🟢 {lokacija_ime} (tvoj dom)'
    label_zivotinja = f'🔴 {profil["lokalitet"]} (pomak +{pomak} mj)'
    df = pd.DataFrame({
        "Mjesec": MJESECI,
        label_dom: dom_god,
        label_zivotinja: zivotinja_god,
    })
    df_long = df.melt("Mjesec", var_name="Linija", value_name="°C")

    linije = (alt.Chart(df_long)
              .mark_line()
              .encode(
                  x=alt.X("Mjesec", sort=MJESECI, title=None),  # Sij -> Pro
                  y=alt.Y("°C", title="Temperatura (°C)"),
                  color=alt.Color(
                      "Linija", title=None,
                      scale=alt.Scale(domain=[label_dom, label_zivotinja],
                                      range=["#2ca02c", "#d62728"]),  # zeleno / crveno
                      legend=alt.Legend(orient="bottom"))))

    # Okomite oznake za prozor parenja
    prozor = prozor_parenja(profil, pomak)
    oznake = (alt.Chart(pd.DataFrame({"Mjesec": [MJESECI[i] for i in prozor]}))
              .mark_rule(color="#e0a000", strokeDash=[6, 4], size=2)
              .encode(x=alt.X("Mjesec", sort=MJESECI)))

    st.altair_chart(oznake + linije, use_container_width=True)
    st.caption("🟢 zeleno = tvoje temperature · 🔴 crveno = lokalitet vrste · "
               "🟡 isprekidano = sezona parenja")

    # Live povratna informacija koliko se poklapaju
    pod = podudaranje(profil, lok, pomak)
    cc1, cc2 = st.columns([1, 2])
    if pod is None:
        cc1.metric("Podudaranje", "—")
        cc2.caption("Ravna klima — poravnanje nije bitno.")
    else:
        cc1.metric("Podudaranje", f"{pod:.0f} %")
        if pomak_hint is not None and pomak == pomak_hint:
            cc2.success("✅ Najbolje poklapanje — zime su poravnate.")
        elif pomak_hint is not None:
            cc2.caption(f"Najveće podudaranje je na **+{pomak_hint} mj**.")

    prozor = prozor_parenja(profil, pomak)
    mj = ", ".join(MJESECI[i] for i in prozor)
    st.caption(f"🥚 Očekivani prozor parenja: **{mj}** "
               f'(tip okidača: {profil["tip_okidaca"]}).')

# ---- Zimsko mirovanje / akcijski hintovi ----
st.subheader("❄️ Zimsko mirovanje i akcije")
if profil["tip_okidaca"] == "umjereni":
    cilj_noc = min(profil["mjesecne_temp_noc"])
    kuca = 18
    col1, col2 = st.columns(2)
    col1.metric("Cilj zimske noći", f"{cilj_noc} °C")
    col2.metric("Kuća (procjena)", f"{kuca} °C")
    if kuca - cilj_noc > 2:
        st.warning(f"⚠️ Kuća je {kuca - cilj_noc:.0f} °C pretopla za zimsko "
                   f"mirovanje → razmisli o otvaranju prozora / hladnijoj prostoriji.")
    st.info("🍽️ Prijedlog hranjenja: **smanji/pauziraj** tijekom zimskog mirovanja, "
            "nastavi normalno na proljetno zagrijavanje.")
else:
    st.info("🌴 Ekvatorska vrsta — bez zimskog mirovanja. "
            "🍽️ Hranjenje: ravnomjerno cijele godine.")

# ---- C. NAPREDNO (fino podešavanje) ----
with st.expander("⚙️ Napredno — fino podešavanje"):
    st.markdown("**Senzori** (za sada neaktivno — Faza 2):")
    s1, s2, s3 = st.columns(3)
    s1.selectbox("Temperatura", ["Ručno", "Senzor A", "Senzor B"], disabled=True)
    s2.selectbox("Vlažnost", ["Ručno", "Senzor A"], disabled=True)
    s3.selectbox("Svjetlo", ["Ručno", "Foto-senzor"], disabled=True)

st.caption("Prototip — vrijednosti i izgled mijenjamo prema tvojim povratnim informacijama.")
