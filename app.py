import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import streamlit as st
import base64
from typing import List, Dict

# ==============================================================================
# 1. KONFIGURATION & FINA-PUNKTE
# ==============================================================================
st.set_page_config(page_title="ÖM Nachwuchs Tracker", page_icon="🏊", layout="centered")

HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'de-AT,de;q=0.9,en;q=0.7',
}

BASE_TIMES = {
    "SCM": {
        "m": {
            "50m Freistil": 19.90, "100m Freistil": 44.84, "200m Freistil": 98.61, "400m Freistil": 212.25,
            "800m Freistil": 440.46, "1500m Freistil": 846.88,
            "50m Rücken": 22.11, "100m Rücken": 48.33, "200m Rücken": 105.63,
            "50m Brust": 24.95, "100m Brust": 55.28, "200m Brust": 120.16,
            "50m Schmetterling": 21.32, "100m Schmetterling": 47.71, "200m Schmetterling": 106.85,
            "100m Lagen": 49.28, "200m Lagen": 108.88, "400m Lagen": 234.81,
        },
        "w": {
            "50m Freistil": 22.83, "100m Freistil": 50.25, "200m Freistil": 110.31, "400m Freistil": 230.25,
            "800m Freistil": 477.42, "1500m Freistil": 908.24,
            "50m Rücken": 25.23, "100m Rücken": 54.02, "200m Rücken": 118.04,
            "50m Brust": 28.37, "100m Brust": 62.36, "200m Brust": 132.50,
            "50m Schmetterling": 23.94, "100m Schmetterling": 52.71, "200m Schmetterling": 119.32,
            "100m Lagen": 55.11, "200m Lagen": 121.63, "400m Lagen": 255.48,
        }
    },
    "LCM": {
        "m": {
            "50m Freistil": 20.91, "100m Freistil": 46.40, "200m Freistil": 102.00, "400m Freistil": 219.96,
            "800m Freistil": 452.12, "1500m Freistil": 871.02,
            "50m Rücken": 23.55, "100m Rücken": 51.60, "200m Rücken": 111.92,
            "50m Brust": 25.95, "100m Brust": 56.88, "200m Brust": 125.48,
            "50m Schmetterling": 22.27, "100m Schmetterling": 49.45, "200m Schmetterling": 110.34,
            "200m Lagen": 112.69, "400m Lagen": 242.50,
        },
        "w": {
            "50m Freistil": 23.61, "100m Freistil": 51.71, "200m Freistil": 112.23, "400m Freistil": 234.18,
            "800m Freistil": 484.79, "1500m Freistil": 920.48,
            "50m Rücken": 26.86, "100m Rücken": 57.13, "200m Rücken": 123.14,
            "50m Brust": 29.16, "100m Brust": 64.13, "200m Brust": 137.55,
            "50m Schmetterling": 24.43, "100m Schmetterling": 54.60, "200m Schmetterling": 125.70,
            "200m Lagen": 125.70, "400m Lagen": 263.65,
        }
    }
}

def time_to_seconds(time_str: str) -> float:
    try:
        time_str = time_str.replace(",", ".").strip()
        if ":" in time_str:
            parts = time_str.split(":")
            return (float(parts[0]) * 60) + float(parts[1])
        return float(time_str)
    except Exception:
        return 0.0

def calculate_points(time_str: str, discipline: str, gender: str, pool_length: str = "LCM") -> int:
    t = time_to_seconds(time_str)
    if t <= 0: return 0
    
    course_data = BASE_TIMES.get(pool_length, BASE_TIMES["LCM"]).get(gender, {})
    base_time = None
    for key in sorted(course_data.keys(), key=len, reverse=True):
        if key.lower() in discipline.lower():
            base_time = course_data[key]
            break
            
    if not base_time: return 0
    return max(0, int(1000 * ((base_time / t) ** 3)))

# ==============================================================================
# 2. SCRAPING-LOGIK
# ==============================================================================
@st.cache_data(show_spinner=False, ttl=60)
def get_all_event_urls(meet_id: str) -> List[str]:
    base_url = f"https://myresults.eu/de-AT/Meets/Recent/{meet_id}/Results"
    try:
        response = requests.get(base_url, headers=HTTP_HEADERS, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    event_ids = set()
    
    for option in soup.find_all('option'):
        val = option.get('value')
        text = option.get_text().lower()
        if val and val.isdigit() and ("m" in text or "bewerb" in text or "-" in text):
            event_ids.add(val)
                
    if not event_ids:
        pattern = r'value="(\d{5,})"'
        event_ids = set(re.findall(pattern, response.text))

    return sorted([f"https://myresults.eu/de-AT/Meets/Recent/{meet_id}/Results/{eid}" for eid in event_ids])

@st.cache_data(show_spinner=False, ttl=300)
def get_pool_length(meet_id: str) -> str:
    url = f"https://myresults.eu/de-AT/Meets/Recent/{meet_id}/Overview"
    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        response.raise_for_status()
        text = response.text.lower()
        
        if "50m" in text or "lcm" in text: return "LCM"
        elif "25m" in text or "scm" in text: return "SCM"
    except requests.RequestException:
        pass
    return "LCM"

def scrape_event_for_year(event_url: str, target_year: int, pool_length: str) -> List[Dict]:
    try:
        response = requests.get(event_url, headers=HTTP_HEADERS, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    selected_option = soup.find('option', selected=True)
    discipline_name = selected_option.get_text(strip=True) if selected_option else "Unbekannter Bewerb"
    
    if any(x in discipline_name.lower() for x in ["staffel", "relay", "4x"]):
        return []
        
    is_male = re.search(r'\b(männlich|men|herren|knaben|buben)\b', discipline_name.lower())
    gender = "m" if is_male else "w"
    
    course_data = BASE_TIMES.get(pool_length, BASE_TIMES["LCM"]).get(gender, {})
    base_bewerb = discipline_name
    for key in sorted(course_data.keys(), key=len, reverse=True):
        if key.lower() in discipline_name.lower():
            base_bewerb = key
            break

    results = []
    rows = soup.find_all('div', class_=re.compile(r'myresults_content_divtablerow_(odd|even)'))
    for row in rows:
        text_content = row.get_text(separator='|', strip=True)
        parts = [p.strip() for p in text_content.split('|') if p.strip()]
        
        if not any(str(target_year) in part for part in parts):
            continue
            
        name = parts[1] if len(parts) > 1 else "Unbekannt"
        time_str = "00:00.00"
        for part in parts:
            if re.match(r'^(\d{1,2}:)?\d{1,2}[.,]\d{2}$', part):
                time_str = part.replace(",", ".")
                break
        
        points = calculate_points(time_str, discipline_name, gender, pool_length)
        if points > 0:
            results.append({
                "Name": name, 
                "Jahrgang": target_year, 
                "Geschlecht": gender,
                "Bewerb": discipline_name, 
                "Grundbewerb": base_bewerb,
                "Zeit": time_str, 
                "Punkte": points
            })
    return results

# ==============================================================================
# 3. STREAMLIT UI & AUSFÜHRUNG
# ==============================================================================

# Feste Wettkampf-ID für die ÖM Nachwuchs
MEET_ID = "2356"

try:
    with open("logo_sum_blau_gelb.png", "rb") as img_file:
        logo_base64 = base64.b64encode(img_file.read()).decode()
    img_html = f'<img src="data:image/png;base64,{logo_base64}" style="max-width: 120px; width: 100%; height: auto; display: block; margin-left: auto;">'
except Exception:
    img_html = ''

# --- CSS: Top-Menü verstecken & Abstand oben verringern ---
st.markdown(
    f"""
    <style>
        header[data-testid="stHeader"] {{
            display: none !important;
        }}
        #MainMenu {{
            visibility: hidden !important;
        }}
        .block-container {{
            padding-top: 2rem !important;
        }}
    </style>
    
    <div style="display: flex; flex-direction: row; align-items: center; justify-content: space-between; margin-bottom: 15px; gap: 10px;">
        <div style="flex: 1;">
            <h1 style="margin: 0; padding: 0; line-height: 1.1; font-size: 2.0rem; font-weight: 700;">
                🏊 ÖM Nachwuchs<br>2026<br><span style="font-size: 1.2rem; color: #a0a0a0; font-weight: 400;">Live-Tracker</span>
            </h1>
        </div>
        <div style="flex-shrink: 0; width: 120px;">
            {img_html}
        </div>
    </div>
    <p style="margin-top: 0; margin-bottom: 0;">Inoffizielle Live-Rangliste nach AQUA-Punkten für den Wettkampf 2356.</p>
    """,
    unsafe_allow_html=True
)

st.divider()

year_input = st.selectbox("Jahrgang auswählen", [2015, 2014, 2013, 2012], index=1)

if st.button("🚀 Ergebnisse abrufen", type="primary", use_container_width=True):
    pool_length_code = get_pool_length(MEET_ID)
    pool_display = "50m (Langbahn - LCM)" if pool_length_code == "LCM" else "25m (Kurzbahn - SCM)"
    st.success(f"📍 **Erkannte Bahnlänge:** {pool_display}")
    
    urls = get_all_event_urls(MEET_ID)
    
    if not urls:
        st.error(f"❌ Keine Bewerbe gefunden. Bitte prüfen, ob Ergebnisse für Wettkampf {MEET_ID} online sind.")
    else:
        progress_text = st.empty()
        progress_bar = st.progress(0)
        progress_text.text(f"0/{len(urls)} Bewerbe verarbeitet...")
        
        all_results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(scrape_event_for_year, url, year_input, pool_length_code) for url in urls]
            for idx, future in enumerate(futures, 1):
                res = future.result()
                if res: all_results.extend(res)
                progress_bar.progress(idx / len(urls))
                progress_text.text(f"{idx}/{len(urls)} Bewerbe verarbeitet...")
                
        if not all_results:
            st.warning(f"Keine Ergebnisse für Jahrgang {year_input} in diesem Wettkampf gefunden.")
        else:
            df_raw = pd.DataFrame(all_results)
            
            for gender_val, gender_name in [("m", "Herren"), ("w", "Damen")]:
                df_gender = df_raw[df_raw['Geschlecht'] == gender_val]
                if df_gender.empty: continue
                
                # --- VORLAUF / FINALE BEREINIGUNG (Nur für 2012 & 2013) ---
                if int(year_input) in [2012, 2013]:
                    df_gender = df_gender.sort_values('Punkte', ascending=False)
                    df_gender = df_gender.drop_duplicates(subset=['Name', 'Grundbewerb'], keep='first')
                
                total_events = df_gender['Grundbewerb'].nunique()
                
                if int(year_input) in [2014, 2015]:
                    scored_events = 6
                elif int(year_input) in [2012, 2013]:
                    scored_events = 5
                
                def get_live_score(pts_series, starts_count):
                    if starts_count > scored_events:
                        return pts_series.nlargest(scored_events).sum()
                    else:
                        return pts_series.sum()

                df_grouped = df_gender.groupby('Name').agg(
                    Gesamtpunkte=('Punkte', lambda x: get_live_score(x, len(x))),
                    Anzahl_Starts=('Bewerb', 'count')
                ).reset_index()
                
                df_sorted = df_grouped.sort_values(by='Gesamtpunkte', ascending=False).reset_index(drop=True)
                
                st.markdown(f"### 🏆 {gender_name} - Jg. {year_input}")
                st.info(f"📊 ÖM-Regel aktiv: Es werden die besten **{scored_events} Resultate** aus {total_events} möglichen Disziplinen gewertet.")
                
                for idx, row in df_sorted.iterrows():
                    name = row['Name']
                    pts = row['Gesamtpunkte']
                    starts = row['Anzahl_Starts']
                    
                    has_dropped_result = (starts > scored_events)
                    
                    if has_dropped_result:
                        status_icon = f"🏁 Wertung (Best of {scored_events})"
                    else:
                        status_icon = f"⏱️ Zwischenstand ({starts}/{scored_events} gewertet)"
                    
                    with st.expander(f"**{idx+1}. {name}** — {pts} Pkt. | {starts} Starts ({status_icon})"):
                        athlete_events = df_gender[df_gender['Name'] == name].sort_values(by='Punkte', ascending=False)
                        
                        for i, (_, ev_row) in enumerate(athlete_events.iterrows()):
                            if has_dropped_result and i >= scored_events:
                                st.markdown(f"~~{ev_row['Bewerb']} : {ev_row['Zeit']} ({ev_row['Punkte']} Pkt.)~~ 📉 *Streichergebnis*")
                            else:
                                st.markdown(f"**{ev_row['Bewerb']}** : {ev_row['Zeit']} ({ev_row['Punkte']} Pkt.)")
                
                st.divider()

# ==============================================================================
# FOOTER / LEGAL DISCLAIMER
# ==============================================================================
st.caption("⚖️ **Haftungsausschluss:** Die hier angezeigten Ergebnisse werden automatisiert von *myresults.eu* abgerufen und basieren auf den aktuellen AQUA-Punktetabellen. Es wird keine Garantie oder Haftung für die Richtigkeit, Vollständigkeit und Aktualität der dargestellten Daten und Berechnungen übernommen. Technische Fehler oder Verzögerungen bei der Datenübertragung sind vorbehalten.")
