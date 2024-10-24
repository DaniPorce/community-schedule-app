from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import pandas as pd
import calendar
from datetime import datetime
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from fpdf import FPDF
import os

app = Flask(__name__)
app.secret_key = 'your_secure_secret_key'  # Cambia questa chiave con una sicura

# Configurazione della cartella di upload
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    """Verifica se il file ha un'estensione consentita."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Rotta principale
@app.route('/')
def index():
    """Rende la pagina principale con due opzioni: Genera Calendario Gruppi e Creazione Form Preparazione."""
    return render_template('index.html', datetime=datetime, calendar=calendar)

# Funzione per addestrare il modello di machine learning (KMeans Clustering)
def addestra_modello(users, num_gruppi=3):
    """Addestra un modello KMeans per raggruppare gli utenti."""
    X = users[['Disponibilità', 'Esperienza', 'Preferenze']]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(n_clusters=num_gruppi, random_state=42)
    kmeans.fit(X_scaled)

    users['Gruppo'] = kmeans.labels_
    return users, kmeans, scaler

# Funzione per generare il calendario
def genera_calendario(mese, anno, users, giorno_personalizzato):
    """Genera un calendario con le assegnazioni dei gruppi."""
    calendario = {}

    # Aggiungiamo il giorno personalizzato e il sabato
    for week in calendar.monthcalendar(anno, mese):
        if week[giorno_personalizzato] != 0:
            giorno = datetime(anno, mese, week[giorno_personalizzato])
            calendario[giorno] = "Preparazione"
        if week[calendar.SATURDAY] != 0:
            giorno = datetime(anno, mese, week[calendar.SATURDAY])
            calendario[giorno] = "Eucaristia"

    num_gruppi = users['Gruppo'].nunique()
    gruppi = users.groupby('Gruppo')
    date_preparazione = list(calendario.keys())

    assegnazioni = {}
    for i, date in enumerate(date_preparazione):
        gruppo_id = i % num_gruppi
        gruppo = gruppi.get_group(gruppo_id)
        assegnazioni[date] = (gruppo, calendario[date])

    return assegnazioni

# Rotta per gestire la Creazione del Calendario Gruppi
@app.route('/create_groups', methods=['GET', 'POST'])
def create_groups():
    """Gestisce il form per la generazione del calendario gruppi."""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash("Nessun file caricato.", "error")
            return redirect(url_for('create_groups'))

        file = request.files['file']
        mese = request.form.get('mese')
        anno = request.form.get('anno')
        giorno_personalizzato = request.form.get('giorno_personalizzato')
        avvisi_raw = request.form.get('avvisi', '').strip()

        # Validazioni
        if not file or file.filename == '':
            flash("Nessun file selezionato.", "error")
            return redirect(url_for('create_groups'))

        if not allowed_file(file.filename):
            flash("Formato file non supportato. Carica un file .xlsx.", "error")
            return redirect(url_for('create_groups'))

        try:
            mese = int(mese)
            anno = int(anno)
            giorno_personalizzato = int(giorno_personalizzato)
            if giorno_personalizzato < 0 or giorno_personalizzato > 6:
                flash("Giorno personalizzato non valido. Deve essere tra 0 (Monday) e 6 (Sunday).", "error")
                return redirect(url_for('create_groups'))
        except ValueError:
            flash("Mese, anno e giorno personalizzato devono essere numeri validi.", "error")
            return redirect(url_for('create_groups'))

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        try:
            data = pd.read_excel(filepath)
        except Exception as e:
            flash(f"Errore nella lettura del file Excel: {e}", "error")
            return redirect(url_for('create_groups'))

        required_columns = {'Nome', 'Cognome', 'Disponibilità', 'Esperienza', 'Preferenze'}
        if not required_columns.issubset(data.columns):
            flash("Errore: il file deve contenere le colonne 'Nome', 'Cognome', 'Disponibilità', 'Esperienza', 'Preferenze'.", "error")
            return redirect(url_for('create_groups'))

        users = data[['Nome', 'Cognome', 'Disponibilità', 'Esperienza', 'Preferenze']].copy()

        try:
            users, model, scaler = addestra_modello(users)
            assegnazioni = genera_calendario(mese, anno, users, giorno_personalizzato)
        except Exception as e:
            flash(f"Errore durante l'elaborazione dei dati: {e}", "error")
            return redirect(url_for('create_groups'))

        # Processiamo gli avvisi: ogni riga diventa un avviso
        avvisi = [avviso.strip() for avviso in avvisi_raw.split('\n') if avviso.strip()]

        submit_button = request.form.get('submit_button')

        if submit_button == 'PDF':
            try:
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", 'B', 16)
                pdf.cell(200, 10, txt=f"Calendario per il mese {calendar.month_name[mese]} {anno}", ln=True, align='C')
                pdf.ln(10)

                # Aggiungiamo gli avvisi all'inizio del PDF
                if avvisi:
                    pdf.set_font("Arial", 'B', 14)
                    pdf.cell(200, 10, txt="Avvisi:", ln=True)
                    pdf.set_font("Arial", size=12)
                    for avviso in avvisi:
                        pdf.multi_cell(0, 10, txt=f"- {avviso}")
                    pdf.ln(10)

                pdf.set_font("Arial", size=12)
                for data_evento, (gruppo, evento) in assegnazioni.items():
                    pdf.set_font("Arial", 'B', 12)
                    pdf.cell(200, 10, txt=f"{data_evento.strftime('%A %d %B %Y')} - {evento}", ln=True)
                    pdf.ln(5)

                    pdf.set_font("Arial", size=10)
                    nomi_gruppo = ', '.join([f"{persona['Nome']} {persona['Cognome']}" for _, persona in gruppo.iterrows()])
                    pdf.multi_cell(0, 10, txt=f"Partecipanti: {nomi_gruppo}")
                    pdf.ln(5)

                    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                    pdf.ln(10)

                pdf_output = os.path.join(app.config['UPLOAD_FOLDER'], 'calendario_gruppi.pdf')
                pdf.output(pdf_output)
                flash("Calendario generato con successo!", "success")
                return send_file(pdf_output, as_attachment=True)
            except Exception as e:
                flash(f"Errore nella generazione del PDF: {e}", "error")
                return redirect(url_for('create_groups'))

        elif submit_button == 'HTML':
            return render_template('result.html', assegnazioni=assegnazioni, mese=mese, anno=anno, calendar=calendar, avvisi=avvisi)

        else:
            flash("Bottone di submit non riconosciuto.", "error")
            return redirect(url_for('create_groups'))
    else:
        # Metodo GET: renderizza il form
        return render_template('create_groups.html', calendar=calendar)

# Rotta per gestire la Creazione del Form Preparazione
@app.route('/create_preparation', methods=['GET', 'POST'])
def create_preparation():
    """Gestisce il form per la creazione del Form Preparazione."""
    if request.method == 'POST':
        # Estrai i dati delle letture, anche se non obbligatori
        prima_riferimento = request.form.get('prima_riferimento', '')
        prima_ammonizzazione = request.form.get('prima_ammonizzazione', '')
        prima_lettura = request.form.get('prima_lettura', '')

        seconda_riferimento = request.form.get('seconda_riferimento', '')
        seconda_ammonizzazione = request.form.get('seconda_ammonizzazione', '')
        seconda_lettura = request.form.get('seconda_lettura', '')

        terza_riferimento = request.form.get('terza_riferimento', '')
        terza_ammonizzazione = request.form.get('terza_ammonizzazione', '')
        terza_lettura = request.form.get('terza_lettura', '')

        vangelo_riferimento = request.form.get('vangelo_riferimento', '')
        vangelo_lettura = request.form.get('vangelo_lettura', '')
        ambientale = request.form.get('ambientale', '')

        # Debug: stampa i valori ricevuti dal form
        print("Valori ricevuti dal form:")
        print(f"Prima Lettura: {prima_riferimento}, {prima_ammonizzazione}, {prima_lettura}")
        print(f"Seconda Lettura: {seconda_riferimento}, {seconda_ammonizzazione}, {seconda_lettura}")
        print(f"Terza Lettura: {terza_riferimento}, {terza_ammonizzazione}, {terza_lettura}")
        print(f"Vangelo: {vangelo_riferimento}, {vangelo_lettura}")
        print(f"Ambientale: {ambientale}")

        # Generazione del PDF solo se almeno un campo è compilato
        if any([prima_riferimento, prima_ammonizzazione, prima_lettura,
                seconda_riferimento, seconda_ammonizzazione, seconda_lettura,
                terza_riferimento, terza_ammonizzazione, terza_lettura,
                vangelo_riferimento, vangelo_lettura, ambientale]):

            try:
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", 'B', 16)
                pdf.cell(200, 10, txt="Form Preparazione", ln=True, align='C')
                pdf.ln(10)

                # Prima Lettura
                if prima_riferimento or prima_ammonizzazione or prima_lettura:
                    pdf.set_font("Arial", 'B', 14)
                    pdf.cell(200, 10, txt="Prima Lettura", ln=True)
                    pdf.set_font("Arial", size=12)
                    pdf.multi_cell(0, 10, txt=f"Riferimenti: {prima_riferimento}")
                    pdf.multi_cell(0, 10, txt=f"Ammonizzazione: {prima_ammonizzazione}")
                    pdf.multi_cell(0, 10, txt=f"Lettura: {prima_lettura}")
                    pdf.ln(5)

                # Seconda Lettura
                if seconda_riferimento or seconda_ammonizzazione or seconda_lettura:
                    pdf.set_font("Arial", 'B', 14)
                    pdf.cell(200, 10, txt="Seconda Lettura", ln=True)
                    pdf.set_font("Arial", size=12)
                    pdf.multi_cell(0, 10, txt=f"Riferimenti: {seconda_riferimento}")
                    pdf.multi_cell(0, 10, txt=f"Ammonizzazione: {seconda_ammonizzazione}")
                    pdf.multi_cell(0, 10, txt=f"Lettura: {seconda_lettura}")
                    pdf.ln(5)

                # Terza Lettura
                if terza_riferimento or terza_ammonizzazione or terza_lettura:
                    pdf.set_font("Arial", 'B', 14)
                    pdf.cell(200, 10, txt="Terza Lettura", ln=True)
                    pdf.set_font("Arial", size=12)
                    pdf.multi_cell(0, 10, txt=f"Riferimenti: {terza_riferimento}")
                    pdf.multi_cell(0, 10, txt=f"Ammonizzazione: {terza_ammonizzazione}")
                    pdf.multi_cell(0, 10, txt=f"Lettura: {terza_lettura}")
                    pdf.ln(5)

                # Vangelo
                if vangelo_riferimento or vangelo_lettura:
                    pdf.set_font("Arial", 'B', 14)
                    pdf.cell(200, 10, txt="Vangelo", ln=True)
                    pdf.set_font("Arial", size=12)
                    pdf.multi_cell(0, 10, txt=f"Riferimenti: {vangelo_riferimento}")
                    pdf.multi_cell(0, 10, txt=f"Lettura: {vangelo_lettura}")
                    pdf.ln(5)

                # Ambientale
                if ambientale:
                    pdf.set_font("Arial", 'B', 14)
                    pdf.cell(200, 10, txt="Ambientale", ln=True)
                    pdf.set_font("Arial", size=12)
                    pdf.multi_cell(0, 10, txt=f"Nome: {ambientale}")
                    pdf.ln(5)

                # Salva il PDF
                pdf_output = os.path.join(app.config['UPLOAD_FOLDER'], 'form_preparazione.pdf')
                pdf.output(pdf_output)
                flash("Documento di preparazione generato con successo!", "success")
                return send_file(pdf_output, as_attachment=True)

            except Exception as e:
                flash(f"Errore nella generazione del PDF: {e}", "error")
                return redirect(url_for('create_preparation'))

        else:
            flash("Almeno un campo deve essere compilato.", "error")
            return redirect(url_for('create_preparation'))

    return render_template('create_preparation.html')


# Rotta per gestire la Creazione del Form Eucaristia
@app.route('/create_eucaristia', methods=['GET', 'POST'])
def create_eucaristia():
    """Gestisce il form per la creazione del Form Eucaristia."""
    if request.method == 'POST':
        # Estrai i dati delle letture e delle preghiere
        prima_riferimento = request.form.get('prima_riferimento')
        prima_lettura = request.form.get('prima_lettura')

        seconda_riferimento = request.form.get('seconda_riferimento')
        seconda_lettura = request.form.get('seconda_lettura')

        vangelo_riferimento = request.form.get('vangelo_riferimento')
        vangelo_lettura = request.form.get('vangelo_lettura')

        preghiere = request.form.get('preghiere')

        # Validazioni di base
        if not all([prima_riferimento, prima_lettura, seconda_riferimento, seconda_lettura, vangelo_riferimento, vangelo_lettura, preghiere]):
            flash("Tutti i campi sono obbligatori.", "error")
            return redirect(url_for('create_eucaristia'))

        # Creazione del PDF riepilogativo
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(200, 10, txt="Form Eucaristia", ln=True, align='C')
            pdf.ln(10)

            # Prima Lettura
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(200, 10, txt="Prima Lettura", ln=True)
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 10, txt=f"Riferimenti: {prima_riferimento}")
            pdf.multi_cell(0, 10, txt=f"Lettura: {prima_lettura}")
            pdf.ln(5)

            # Seconda Lettura
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(200, 10, txt="Seconda Lettura", ln=True)
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 10, txt=f"Riferimenti: {seconda_riferimento}")
            pdf.multi_cell(0, 10, txt=f"Lettura: {seconda_lettura}")
            pdf.ln(5)

            # Vangelo
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(200, 10, txt="Vangelo", ln=True)
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 10, txt=f"Riferimenti: {vangelo_riferimento}")
            pdf.multi_cell(0, 10, txt=f"Lettura: {vangelo_lettura}")
            pdf.ln(5)

            # Preghiere
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(200, 10, txt="Preghiere dei Fedeli", ln=True)
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 10, txt=f"Preghiere fatte da: {preghiere}")
            pdf.ln(5)

            pdf_output = os.path.join(app.config['UPLOAD_FOLDER'], 'form_eucaristia.pdf')
            pdf.output(pdf_output)
            flash("Documento di eucaristia generato con successo!", "success")
            return send_file(pdf_output, as_attachment=True)
        except Exception as e:
            flash(f"Errore nella generazione del documento: {e}", "error")
            return redirect(url_for('create_eucaristia'))

    return render_template('create_eucaristia.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
