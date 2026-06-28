# termostat_app — Nacrt dizajna

> Radni dokument. Skupljamo sve odluke o izgledu i funkcijama **prije** pisanja koda.

## 1. Svrha i vodeće načelo

Aplikacija za **repliciranje prirodnih uvjeta staništa** u terariju, s krajnjim ciljem
**poticanja parenja** kroz vjerno oponašanje godišnjeg ciklusa.

**Vodeće načelo:** odabir **vrste + lokaliteta** je glavni okidač koji automatski
postavi sve uvjete (kao foto-senzor kod termostata). Korisnik onda svaki parametar
može **fino dotjerati**.

> Jednostavno na površini, fino podesivo u dubini.

## 2. Sučelje — tri sloja

| Sloj | Što korisnik vidi |
|------|-------------------|
| **A. Odabir** | Vrsta + lokalitet + **korisnikova lokacija** (npr. Split). Jedini obavezni korak. |
| **B. Pregled** | App automatski ispiše uvjete iz lokaliteta (fotoperiod, temp, vlaga, kalendar). |
| **C. Fino podešavanje** | Skriveno iza "Napredno". Override svakog parametra. |

Većina korisnika ostane na A/B; napredni otvore C.

## 3. Skupine parametara (što "lokalitet" postavlja)

1. **Fotoperiod** — ovisi o geo. širini. Fino: dodavanje minuta, ramp zore/sumraka.
2. **Temperatura** — u **rasponima**, ne fiksno; s **gradijentom/mikroklimom**:
   topla točka (uz grijač) → ambijent → hladni kraj. Plus dnevni (dan/noć) i godišnji ciklus.
3. **Vlažnost / oborine** — kišna vs sušna sezona, raspored magljenja.
4. **Sezonski motor** — godišnja krivulja koja spaja sve i vodi prema parenju.

## 4. Dvije vremenske skale, dvije krivulje

App prikazuje na grafu **dvije linije**: **PLAN (cilj)** i **STVARNO (senzor)**.

- **Dnevna krivulja (24 h):** jutarnji rast → dnevni vrh (basking) → noćni pad, meki prijelazi.
- **Godišnja krivulja (12 mj):** ljeto ↔ zimsko mirovanje.

## 5. Senzori

Od početka postoji **odabir senzora po teraju i parametru** (svjetlo, vlaga, temperatura).
- **Faza 1:** korisnik ručno podešava grijače/vlagu; stvarna krivulja iz ručnog unosa ili prazna.
- **Faza 2:** senzori automatski pune stvarnu krivulju.
- **Faza 3 (kasnije):** app pali/gasi grijač/svjetlo (relej, npr. Raspberry Pi).

UI za senzore postoji već u Fazi 1 (samo neaktivan).

## 6. Sezonski pomak (poravnanje sezona)

Životinja iz druge hemisfere ima obrnut kalendar. App **NE pomiče sam** — daje **hint**:

> Lokacija: Split (HR). Životinja: Australija.
> AU zima: vrhunac ~srpanj. Tvoja zima: ~siječanj.
> 💡 Prijedlog: pomak **+6 mjeseci**. *(Korisnik primijeni ručno.)*

Zato app treba znati i **klimu korisnikove lokacije** (kad je lokalno najhladnije/najtoplije).
Logika: poravnaj "njihovu zimu" s lokalnom zimom → umjetni i pravi vanjski signali se **pojačavaju**.

## 7. Okidač parenja

- **Automatski**, emergentan iz krivulja, **ponavlja se svake godine** (ciklus je godišnji).
- **Tip okidača** ovisi o klimi lokaliteta:
  - `ekvatorski` → motor prati **vlažnost + fotoperiod** (temp gotovo ravna).
  - `umjereni` → motor prati **hladno razdoblje pa zagrijavanje**.
- App označi očekivani prozor parenja na vremenskoj traci godine.

## 8. Zimsko mirovanje (brumacija)

Reptilska zimska pauza: usporen metabolizam, smanjeno/zaustavljeno hranjenje, često okida parenje.
- App **sugerira hranjenje** (smanji/pauza u mirovanju).
- App zna **ciljnu temperaturu hlađenja** i uspoređuje sa stvarnošću:
  > Cilj zimske noći ~13 °C, kuća pada na ~18 °C → ⚠️ otvori prozor / hladnija prostorija.

## 9. Više terarija

Korisnik upravlja s više terarija; svaki ima svoj profil; lako prebacivanje između njih.

## 10. Baza podataka

Za sada **datoteka**, lako nadogradiva; kasnije SQL. Profili lokaliteta s **realnim podacima**
(prosjek s interneta).

**Polja profila lokaliteta (radna verzija):**
- vrsta, lokalitet, **geo. širina**
- temp topla zona / hladni kraj — dan / noć / godišnji raspon
- godišnja amplituda
- vlažnost (raspon) + kišni mjeseci
- **tip okidača** (`ekvatorski` / `umjereni`)
- napomene

**Skica entiteta (za kasnije):**
`korisnik_lokacija`, `vrsta`, `lokalitet_profil`, `teraj` (instanca: ime, vrsta, lokalitet,
pomak_mjeseci, override-i), `senzor` (tip, parametar, dodjela teraju),
`ocitanje` (vremenski niz: teraj, parametar, vrijeme, vrijednost, izvor).

## 11. Gotovi profili (realni podaci)

### Morelia viridis — "Biak" (ekvatorski)
- Geo. širina **−1.18°**; fotoperiod ~**12.1 h** cijele godine
- Ambijent: dan 29–30 °C, noć 24–25 °C; **godišnja amplituda ~1 °C**
- Gradijent: topla točka ~31–32, ambijent 27–28, hladni kraj 24–25; noć ~23–24
- Vlažnost ~77–100 %; kišni vrhunci ožujak/lipanj, najsuše listopad/studeni
- Okidač: kišna sezona ↑ (NE temperatura)

### Morelia spilota spilota — "Diamond" (umjereni; Sydney, −33.9°)
- Fotoperiod 9 h 54 min (zima) → 14 h 25 min (ljeto)
- Najhladnije srpanj, najtoplije siječanj (južna hemisfera)
- Ljeto: dan ~26–27, noć ~18–19 · Zima: dan ~16–18, noć ~8–9
- Zimsko mirovanje DA; okidač: zagrijavanje nakon hladnog razdoblja

## 12. Otvorena pitanja / sljedeći koraci
- [ ] Potvrditi husbandry brojeve iskustvom (Biak, Diamond)
- [ ] Definirati točan format raspona u unosu (sloj C)
- [ ] Odabrati format datoteke za bazu (JSON / CSV) prije gradnje
- [ ] Skicirati ekran jednog terarija (A→B→C na djelu)
