"""
termostat_app — prototip
Replikacija prirodnih uvjeta stanista u terariju (vidi DIZAJN.md).

Pokretanje:  streamlit run app.py
"""
import json
from pathlib import Path

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


def predlozi_pomak(profil, lok):
    """Hint: koliko mjeseci pomaknuti da se 'njihova zima' poklopi s lokalnom."""
    noc = np.array(profil["mjesecne_temp_noc"])
    amplituda = noc.max() - noc.min()
    if amplituda < 3:
        return None, amplituda  # ravna klima -> pomak nije bitan
    najhladniji_lokalitet = int(np.argmin(noc)) + 1          # mjesec 1-12
    pomak = (lok["najhladniji_mjesec"] - najhladniji_lokalitet) % 12
    return pomak, amplituda


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
    lokacija_ime = st.selectbox("Moja lokacija", list(baza["korisnik_lokacije"]))
    lok = baza["korisnik_lokacije"][lokacija_ime]

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
pomak_hint, amplituda = predlozi_pomak(profil, lok)
if pomak_hint is None:
    st.info(f"🌴 Ravna klima (godišnja amplituda ~{amplituda:.0f} °C) — "
            f"sezonski pomak ovdje nije bitan.")
elif pomak_hint == teraj["pomak"]:
    st.success(f"✅ Sezonski pomak poravnat (+{teraj['pomak']} mj). "
               f"Njihova zima se poklapa s tvojom.")
else:
    st.warning(f"💡 Prijedlog: postavi pomak na **+{pomak_hint} mjeseci** da se "
               f'„njihova zima” poklopi s tvojom u {lokacija_ime}. '
               f"Trenutno: +{teraj['pomak']} mj. (Promijeni u „Napredno”.)")

# ---- Grafovi: PLAN vs STVARNO ----
rng = np.random.default_rng(odabran)  # demo "stvarno" = plan + sum

tab_dan, tab_god = st.tabs(["📈 Dnevna krivulja (24 h)", "📅 Godišnja krivulja (12 mj)"])

with tab_dan:
    topla = (profil["temp_topla_tocka_dan"][0] + profil["temp_topla_tocka_dan"][1]) / 2
    noc = (profil["temp_noc"][0] + profil["temp_noc"][1]) / 2
    plan = dnevna_krivulja(topla, noc)
    stvarno = plan + rng.normal(0, 0.6, 24)
    df = pd.DataFrame({"Plan (cilj)": plan, "Stvarno (demo senzor)": stvarno},
                      index=[f"{h}:00" for h in range(24)])
    st.line_chart(df)
    st.caption("Plava = ciljna krivulja iz profila · narančasta = (simulirano) očitanje senzora.")

with tab_god:
    pomak = teraj["pomak"]
    dan = godisnja_krivulja(profil["mjesecne_temp_dan"], pomak)
    noc_god = godisnja_krivulja(profil["mjesecne_temp_noc"], pomak)
    stvarno_god = dan + rng.normal(0, 0.8, 12)
    df = pd.DataFrame(
        {"Plan dan": dan, "Plan noć": noc_god, "Stvarno (demo)": stvarno_god},
        index=MJESECI)
    st.line_chart(df)

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
    novi_pomak = st.slider("Sezonski pomak (mjeseci)", 0, 11, teraj["pomak"])
    if novi_pomak != teraj["pomak"]:
        teraj["pomak"] = novi_pomak
        st.rerun()

    st.divider()
    st.markdown("**Senzori** (za sada neaktivno — Faza 2):")
    s1, s2, s3 = st.columns(3)
    s1.selectbox("Temperatura", ["Ručno", "Senzor A", "Senzor B"], disabled=True)
    s2.selectbox("Vlažnost", ["Ručno", "Senzor A"], disabled=True)
    s3.selectbox("Svjetlo", ["Ručno", "Foto-senzor"], disabled=True)

st.caption("Prototip — vrijednosti i izgled mijenjamo prema tvojim povratnim informacijama.")
