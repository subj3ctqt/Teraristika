<!-- knowledge: Python, SQL, HTML & CSS, Git -->

# termostat_app

Streamlit aplikacija za termostat (Python).

## Tehnologije
- **Python** — glavni jezik, Streamlit framework
- **SQL** — baza podataka (npr. SQLite za lokalno, PostgreSQL/Supabase za produkciju)
- **HTML & CSS** — prilagodba izgleda / custom komponente
- **Git** — verzioniranje i deploy

## Napomene za bazu podataka
- Streamlit Cloud nema trajni disk → za produkciju koristi vanjsku bazu (Postgres/Supabase), ne SQLite datoteku.
- Connection stringovi i lozinke idu u `.streamlit/secrets.toml` (Secrets), nikad u kod.
- Preporuka: `st.connection(...)` + `st.cache_data` za keširanje upita.
