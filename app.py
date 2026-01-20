import streamlit as st
from groq import Groq
from supabase import create_client, Client
import json
import pandas as pd
from fpdf import FPDF
import datetime
import base64

# --- KONFIGURATION ---
st.set_page_config(page_title="Handwerk-Hero", page_icon="📸")

# --- DATENBANK VERBINDUNG ---
# Wir versuchen, Supabase zu laden. Wenn Keys fehlen, warnen wir nur.
try:
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(supabase_url, supabase_key)
    db_connected = True
except:
    db_connected = False

# --- FUNKTIONEN ---
def encode_image(image_file):
    return base64.b64encode(image_file.getvalue()).decode('utf-8')

def create_pdf(df, total_netto, customer_text, f_name, f_kon):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f_name, ln=True)
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 10, f_kon, ln=True)
    pdf.ln(10)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f"Betreff: {customer_text[:50]}...", ln=True)
    pdf.ln(5)
    
    # Tabelle
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(15, 10, "Menge", 1, 0, "C", 1)
    pdf.cell(80, 10, "Beschreibung", 1, 0, "L", 1)
    pdf.cell(20, 10, "Typ", 1, 0, "C", 1) # Neu
    pdf.cell(25, 10, "Einzel", 1, 0, "R", 1)
    pdf.cell(25, 10, "Gesamt", 1, 1, "R", 1)
    
    pdf.set_font("Arial", "", 10)
    for _, row in df.iterrows():
        desc = str(row.get('beschreibung', ''))[:40]
        typ = str(row.get('typ', 'Mat.'))[:10]
        pdf.cell(15, 10, str(row.get('menge', 1)), 1, 0, "C")
        pdf.cell(80, 10, desc, 1, 0, "L")
        pdf.cell(20, 10, typ, 1, 0, "C")
        pdf.cell(25, 10, f"{float(row.get('einzelpreis', 0)):.2f}", 1, 0, "R")
        pdf.cell(25, 10, f"{float(row.get('gesamtpreis', 0)):.2f}", 1, 1, "R")
        
    pdf.ln(5)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(140, 10, "Netto Summe:", 0, 0, "R")
    pdf.cell(25, 10, f"{total_netto:.2f} EUR", 1, 1, "R")
    
    return pdf.output(dest='S').encode('latin-1')

# --- SIDEBAR & DATENBANK LISTE ---
with st.sidebar:
    st.header("🗄️ Meine Angebote")
    
    # Wenn DB verbunden ist, lade alte Angebote
    if db_connected:
        try:
            response = supabase.table('angebote').select("id, kunde, summe_netto, created_at").order("created_at", desc=True).execute()
            for angebot in response.data:
                datum = angebot['created_at'][:10]
                label = f"{datum}: {angebot['kunde']} ({angebot['summe_netto']}€)"
                if st.button(label, key=angebot['id']):
                    # Lade Angebot aus DB zurück in die App
                    full_data = supabase.table('angebote').select("*").eq("id", angebot['id']).execute()
                    if full_data.data:
                        loaded = full_data.data[0]
                        st.session_state.angebot_daten = pd.DataFrame(loaded['items'])
                        st.toast(f"Angebot für {loaded['kunde']} geladen!")
        except Exception as e:
            st.error(f"DB Fehler: {e}")
    else:
        st.warning("Keine Datenbank verbunden.")

    st.markdown("---")
    st.header("⚙️ Einstellungen")
    firma_name = st.text_input("Firma", value="Meisterbetrieb Müller")
    firma_kontakt = st.text_input("Kontakt", value="info@meister-mueller.de")
    
    # API Key Handling
    if "GROQ_API_KEY" in st.secrets:
        api_key = st.secrets["GROQ_API_KEY"]
    else:
        api_key = st.text_input("Groq API Key:", type="password")

    model_choice = "meta-llama/llama-4-scout-17b-16e-instruct"

# --- HAUPTBEREICH ---
st.title("📸 Handwerk-Hero")

if not db_connected:
    st.info("💡 Tipp: Verbinde Supabase in den Secrets, um Angebote zu speichern.")

if 'angebot_daten' not in st.session_state:
    st.session_state.angebot_daten = None

col1, col2 = st.columns([1, 2])
with col1:
    uploaded_file = st.file_uploader("Foto", type=["jpg", "png", "jpeg"])
    if uploaded_file:
        st.image(uploaded_file, use_container_width=True)
with col2:
    text_input = st.text_area("Notizen:", height=100, placeholder="Was soll gemacht werden?")
    kunde_input = st.text_input("Kundenname / Projekt:", placeholder="z.B. Familie Schmidt, Bad")

if st.button("🚀 Angebot generieren") and api_key:
    client = Groq(api_key=api_key)
    with st.spinner('KI analysiert...'):
        try:
            # Prompt Setup
            user_content = [
                {"type": "text", "text": f"""
                Analysiere: "{text_input}". Erstelle Angebot.
                Regeln: 
                1. Preise schätzen (Netto). 
                2. Unterscheide Material / Lohn.
                JSON Format: [{{ "menge": Zahl, "einheit": "Stk/Std", "beschreibung": "Text", "typ": "Material/Lohn", "einzelpreis": Zahl }}]
                """}
            ]
            if uploaded_file:
                base64_image = encode_image(uploaded_file)
                user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}})
            
            completion = client.chat.completions.create(
                model=model_choice,
                messages=[{"role": "user", "content": user_content}],
                temperature=0
            )
            
            # Parsing
            raw = completion.choices[0].message.content
            s = raw.find('[')
            e = raw.rfind(']')
            if s != -1:
                data = json.loads(raw[s:e+1])
                st.session_state.angebot_daten = pd.DataFrame(data)
                st.rerun()
        except Exception as e:
            st.error(f"Fehler: {e}")

# --- ERGEBNIS & SPEICHERN ---
if st.session_state.angebot_daten is not None:
    st.divider()
    st.subheader("Angebot bearbeiten")
    
    edited_df = st.data_editor(st.session_state.angebot_daten, num_rows="dynamic", use_container_width=True)
    
    # Live-Berechnung
    try:
        edited_df['menge'] = edited_df['menge'].astype(float)
        edited_df['einzelpreis'] = edited_df['einzelpreis'].astype(float)
        edited_df['gesamtpreis'] = edited_df['menge'] * edited_df['einzelpreis']
        total = edited_df['gesamtpreis'].sum()
        
        c1, c2, c3 = st.columns([2,1,1])
        c1.metric("Netto Summe", f"{total:.2f} €")
        
        # PDF Button
        pdf_data = create_pdf(edited_df, total, kunde_input or "Angebot", firma_name, firma_kontakt)
        c2.download_button("📄 PDF", data=pdf_data, file_name="Angebot.pdf", mime="application/pdf")
        
        # SPEICHERN BUTTON (DB)
        if db_connected and c3.button("💾 Speichern"):
            if not kunde_input:
                st.error("Bitte Kundennamen eingeben!")
            else:
                # Daten für DB vorbereiten
                items_json = edited_df.to_dict('records')
                data_to_save = {
                    "kunde": kunde_input,
                    "titel": f"Angebot vom {datetime.date.today()}",
                    "items": items_json,
                    "summe_netto": total
                }
                supabase.table('angebote').insert(data_to_save).execute()
                st.success("Gespeichert! (Siehe Sidebar)")
                st.rerun()
                
    except Exception as e:
        st.error(f"Rechenfehler: {e}")