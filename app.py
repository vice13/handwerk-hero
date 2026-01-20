import streamlit as st
from groq import Groq
import json
import pandas as pd
from fpdf import FPDF
import datetime
import base64

# --- KONFIGURATION ---
st.set_page_config(page_title="Handwerk-Hero", page_icon="📸")

# --- FUNKTION: BILD FÜR KI VORBEREITEN ---
def encode_image(image_file):
    return base64.b64encode(image_file.getvalue()).decode('utf-8')

# --- SEITENLEISTE ---
with st.sidebar:
    st.header("⚙️ Einstellungen")
    firma_name = st.text_input("Firma", value="Meisterbetrieb Müller")
    firma_kontakt = st.text_input("Kontakt", value="info@meister-mueller.de")
    
    st.markdown("---")
    # API Key laden
    if "GROQ_API_KEY" in st.secrets:
        api_key = st.secrets["GROQ_API_KEY"]
    else:
        api_key = st.text_input("Groq API Key:", type="password")

    # Auswahl: Welches KI-Modell?
    # Wir nehmen jetzt das VISION Modell für Bilder
    model_choice = "llama-3.2-90b-vision-preview" 

# --- SESSION STATE ---
if 'angebot_daten' not in st.session_state:
    st.session_state.angebot_daten = None

# --- PDF FUNKTION (Minimalisiert für Übersicht) ---
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
    
    # Tabelle Header
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(15, 10, "Menge", 1, 0, "C", 1)
    pdf.cell(90, 10, "Beschreibung", 1, 0, "L", 1)
    pdf.cell(30, 10, "Einzel", 1, 0, "R", 1)
    pdf.cell(30, 10, "Gesamt", 1, 1, "R", 1)
    
    # Tabelle Inhalt
    pdf.set_font("Arial", "", 10)
    for index, row in df.iterrows():
        desc = str(row['beschreibung'])[:45]
        pdf.cell(15, 10, str(row['menge']), 1, 0, "C")
        pdf.cell(90, 10, desc, 1, 0, "L")
        pdf.cell(30, 10, f"{row['einzelpreis']:.2f}", 1, 0, "R")
        pdf.cell(30, 10, f"{row['gesamtpreis']:.2f}", 1, 1, "R")
        
    pdf.ln(5)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(135, 10, "Netto Summe:", 0, 0, "R")
    pdf.cell(30, 10, f"{total_netto:.2f} EUR", 1, 1, "R")
    
    return pdf.output(dest='S').encode('latin-1')

# --- HAUPTBEREICH ---
st.title("📸 Handwerk-Hero: Vision")
st.write("Lade ein Foto von der Baustelle hoch oder beschreibe es.")

col1, col2 = st.columns([1, 2])

with col1:
    # KAMERA / UPLOAD
    uploaded_file = st.file_uploader("Foto aufnehmen/hochladen", type=["jpg", "png", "jpeg"])
    if uploaded_file:
        st.image(uploaded_file, caption="Baustellen-Foto", use_container_width=True)

with col2:
    # TEXT EINGABE (Optional)
    text_input = st.text_area("Zusätzliche Infos (optional):", height=100, placeholder="Z.B.: Bitte hochwertige Fliesen nehmen.")

# START BUTTON
if st.button("Angebot aus Bild & Text erstellen") and api_key:
    client = Groq(api_key=api_key)
    
    with st.spinner('Die KI analysiert das Foto...'):
        try:
            messages = []
            
            # PROMPT VORBEREITEN
            user_content = [
                {"type": "text", "text": f"Erstelle ein Handwerker-Angebot. Infos: {text_input}. \n\nRegeln:\n1. Erkenne Material/Arbeit auf dem Bild (falls vorhanden).\n2. Schätze Preise (Netto).\n3. JSON Format: [{{'menge': Zahl, 'beschreibung': 'Text', 'einzelpreis': Zahl}}]"}
            ]
            
            # Wenn ein Bild da ist, hängen wir es an die Nachricht an
            if uploaded_file:
                base64_image = encode_image(uploaded_file)
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                })
            
            messages.append({"role": "user", "content": user_content})
            
            # KI ANFRAGE (Vision Modell)
            completion = client.chat.completions.create(
                model="llama-3.2-90b-vision-preview", # Das Vision-Modell!
                messages=messages,
                temperature=0,
                max_tokens=1024
            )
            
            # DATEN VERARBEITEN
            raw = completion.choices[0].message.content
            # JSON Extraktor
            s = raw.find('[')
            e = raw.rfind(']')
            if s != -1:
                data = json.loads(raw[s:e+1])
                st.session_state.angebot_daten = pd.DataFrame(data)
                st.rerun()
            else:
                st.error("Konnte keine Daten auslesen.")
                st.write(raw)

        except Exception as e:
            st.error(f"Fehler: {e}")

# --- ERGEBNIS ANZEIGE ---
if st.session_state.angebot_daten is not None:
    st.divider()
    st.subheader("Vorschlag")
    
    edited_df = st.data_editor(
        st.session_state.angebot_daten, 
        num_rows="dynamic", 
        use_container_width=True
    )
    
    # Live-Rechnung
    try:
        edited_df['menge'] = edited_df['menge'].astype(float)
        edited_df['einzelpreis'] = edited_df['einzelpreis'].astype(float)
        edited_df['gesamtpreis'] = edited_df['menge'] * edited_df['einzelpreis']
        total = edited_df['gesamtpreis'].sum()
        
        st.metric("Netto Summe", f"{total:.2f} €")
        
        # PDF Button
        pdf_data = create_pdf(edited_df, total, "Foto-Kalkulation", firma_name, firma_kontakt)
        st.download_button("📄 PDF Export", data=pdf_data, file_name="Angebot.pdf", mime="application/pdf")
        
    except:
        pass