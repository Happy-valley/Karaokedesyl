"""
Karaokedesyl - Version 3.0
A Flask-based Karaoke Song Selection and Playlist Management System.
"""

import dropbox
import os
import sqlite3
import csv
from datetime import datetime
from flask import Flask, flash, session, render_template, request, redirect, url_for, send_from_directory, jsonify, Response, send_file
from werkzeug.utils import secure_filename
import qrcode
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'supersecretkey'
DATABASE = 'allsongs.db'
EXPORT_DIR = 'export'
DROPBOX_DIR = '/Users/sylvie/dropbox/songbook'
ADMIN_PASSWORD = 'Syladm1'
NGROK_URL = "https://b408-77-141-137-73.ngrok-free.app"  # Mets à jour si l'URL change
# Définition de la clé secrète pour la gestion des sessions (y compris les messages flash)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Ensure export directory exists
os.makedirs(EXPORT_DIR, exist_ok=True)

# Database Initialization
def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS Allsongs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT,
                        artist TEXT,
                        language TEXT,
                        genre TEXT,
                        period TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS Playlist (
                        id INTEGER PRIMARY KEY,
                        title TEXT UNIQUE,
                        artist TEXT)''')
    conn.commit()
    conn.close()



@app.route('/')
def home():
    return redirect(url_for('home_page'))

@app.route('/home')
def home_page():
    app_py_path = os.path.abspath(__file__)
    last_modified = datetime.fromtimestamp(os.path.getmtime(app_py_path)).strftime("%Y-%m-%d %H:%M:%S")
    print(f"✅ /home loaded from: {app_py_path}")
    print(f"🕒 Last modified: {last_modified}")
    return render_template('home.html', app_py_path=app_py_path, last_modified=last_modified)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    app_directory = os.path.basename(os.path.dirname(os.path.abspath(__file__)))  # Récupère le nom du dossier

    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))

    return render_template('admin.html', app_directory=app_directory)

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin'))

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Récupérer le nombre total de chansons
    cursor.execute("SELECT COUNT(*) FROM Allsongs")
    song_count = cursor.fetchone()[0]

    # Récupérer toutes les chansons
    cursor.execute("SELECT * FROM Allsongs")
    songs = cursor.fetchall()

    # Récupérer la playlist
    cursor.execute("SELECT * FROM Playlist")
    playlist = cursor.fetchall()

    conn.close()

    # Passer toutes les données au template
    return render_template('admin_dashboard.html', song_count=song_count, songs=songs, playlist=playlist)

@app.route('/admin/import', methods=['POST'])
def upload_songs():
    if 'file' not in request.files:
        return redirect(url_for('admin_dashboard'))
    
    file = request.files['file']
    if file.filename == '':
        return redirect(url_for('admin_dashboard'))
    
    filepath = os.path.join(UPLOAD_FOLDER, secure_filename(file.filename))
    file.save(filepath)

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        # Supprimer toutes les chansons avant l'import
        cursor.execute("DELETE FROM Allsongs")
        conn.commit()
        
        # Réimporter les chansons
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            csv_reader = csv.reader(csvfile)
            next(csv_reader)  # Sauter l'en-tête CSV
            cursor.executemany("INSERT INTO Allsongs (title, artist, language, genre, period) VALUES (?, ?, ?, ?, ?)", csv_reader)
        
        conn.commit()
    
    os.remove(filepath)
    return redirect(url_for('admin_dashboard'))
    
@app.route('/songs', methods=['GET'])
def get_songs():
    language = request.args.get('language', 'all')  # Récupère le critère de tri (par défaut : "all")

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    if language == "all":
        cursor.execute("SELECT * FROM Allsongs")  # Affiche toutes les chansons
    else:
        cursor.execute("SELECT * FROM Allsongs WHERE language = ?", (language,))

    songs = cursor.fetchall()
    conn.close()

    # Convertir les résultats en format JSON
    songs_list = [{"id": s[0], "title": s[1], "artist": s[2], "language": s[3], "genre": s[4], "period": s[5]} for s in songs]
    return jsonify(songs_list)

@app.route('/choose_song')
def choose_song():
    selected_language = request.args.get('language', 'all')
    selected_period = request.args.get('period', 'all')
    selected_genre = request.args.get('genre', 'all')  # Nouveau filtre genre
    sort_by = request.args.get('sort_by', 'artist')  # Par défaut : artist
    sort_order = request.args.get('sort_order', 'asc')  # Par défaut : croissant

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Récupérer toutes les langues, périodes et genres uniques
    cursor.execute("SELECT DISTINCT language FROM Allsongs")
    languages = sorted([row[0] for row in cursor.fetchall()])

    cursor.execute("SELECT DISTINCT period FROM Allsongs")
    periods = sorted([row[0] for row in cursor.fetchall()])

    cursor.execute("SELECT DISTINCT genre FROM Allsongs")  # Nouvelle requête pour les genres
    genres = sorted([row[0] for row in cursor.fetchall()])

    # Construire la requête avec filtres
    query = "SELECT * FROM Allsongs WHERE 1=1"
    params = []

    if selected_language != 'all':
        query += " AND language = ?"
        params.append(selected_language)

    if selected_period != 'all':
        query += " AND period = ?"
        params.append(selected_period)

    if selected_genre != 'all':  # Filtre genre
        query += " AND genre = ?"
        params.append(selected_genre)

    # Sécuriser les colonnes et l’ordre de tri (anti-injection SQL)
    valid_columns = ['title', 'artist', 'language', 'genre', 'period']
    if sort_by not in valid_columns:
        sort_by = 'artist'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'asc'

    query += f" ORDER BY {sort_by} {sort_order.upper()}"

    # Exécution de la requête
    cursor.execute(query, params)
    songs = cursor.fetchall()

    # Récupération de la playlist
    cursor.execute("SELECT * FROM Playlist")
    playlist = cursor.fetchall()

    conn.close()

    return render_template('choose_song.html',
                           songs=songs,
                           playlist=playlist,
                           selected_language=selected_language,
                           selected_period=selected_period,
                           selected_genre=selected_genre,  # Passer le genre sélectionné au template
                           sort_by=sort_by,
                           sort_order=sort_order,
                           languages=languages,
                           periods=periods,
                           genres=genres,  # Passer la liste des genres au template
                           table_title="Available Songs",
                           show_buttons=True)
                           
@app.route('/current_playlist')
def current_playlist():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Playlist")  # Vérifie si la table existe et contient des données
    playlist = cursor.fetchall()
    conn.close()
    return jsonify(playlist)  # Retourne la playlist sous format JSON
        
@app.route('/add_to_playlist/<int:song_id>')
def add_to_playlist(song_id):
    # ✅ Récupération des paramètres depuis l'URL
    sort_by = request.args.get('sort_by', default='title')
    sort_order = request.args.get('sort_order', default='asc')
    language = request.args.get('language', default='all')
    period = request.args.get('period', default='all')
    genre = request.args.get('genre', default='all')

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # ✅ Vérifie le nombre de chansons dans la playlist
    cursor.execute("SELECT COUNT(*) FROM Playlist")
    playlist_count = cursor.fetchone()[0]

    # 🚫 Si la playlist est pleine
    if playlist_count >= 30:
        flash("Playlist is full! You can only add up to 30 songs.", "warning")

        # ✅ Recharge les chansons avec tri et filtres
        query = "SELECT * FROM Allsongs WHERE 1=1"
        params = []

        if language != 'all':
            query += " AND language = ?"
            params.append(language)

        if period != 'all':
            query += " AND period = ?"
            params.append(period)

        query += f" ORDER BY {sort_by} {sort_order}"
        cursor.execute(query, params)
        songs = cursor.fetchall()

        # ✅ Recharge la playlist
        cursor.execute("SELECT * FROM Playlist")
        playlist = cursor.fetchall()
        conn.close()

        return render_template('choose_song.html',
                               songs=songs,
                               playlist=playlist,
                               table_title="Available Songs",
                               show_buttons=True,
                               sort_by=sort_by,
                               sort_order=sort_order,
                               selected_language=language,
                               selected_period=period)

    # ✅ Sinon, ajoute la chanson
    cursor.execute("SELECT title, artist FROM Allsongs WHERE id = ?", (song_id,))
    song = cursor.fetchone()

    if song:
        cursor.execute("INSERT OR IGNORE INTO Playlist (title, artist) VALUES (?, ?)", song)
        conn.commit()

    conn.close()

    # ✅ Redirection avec tous les filtres conservés
    return redirect(url_for('choose_song',
                        sort_by=sort_by,
                        sort_order=sort_order,
                        language=language,
                        period=period,
                        genre=genre))

@app.route('/test_flash')
def test_flash():
    flash("Test message", "warning")
    return redirect(url_for('choose_song'))

@app.route('/admin/export')
def export_playlist():
    # Connexion à la base de données
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT title, artist FROM Playlist")
    playlist = cursor.fetchall()
    conn.close()

    # Création du nom de fichier avec horodatage
    filename = f"Playlist_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.lst"
    local_file_path = os.path.join(EXPORT_DIR, filename)
    dropbox_file_path = f"/songbook/{filename}"

    # Extraire le nom de fichier sans l'extension .lst
    filename_without_extension = filename.replace('.lst', '')

    # S'assurer que le dossier 'export' existe
    os.makedirs(EXPORT_DIR, exist_ok=True)

    # Écriture locale du fichier
    with open(local_file_path, 'w', encoding='utf-8') as f:
        # Ajouter la première ligne avec le nom du fichier sans l'extension
        f.write(f"{filename_without_extension}\n")
        for title, artist in playlist:
            f.write(f"{title} - {artist}\n")

    # Envoi sur Dropbox
    dropbox_token = os.environ.get("DROPBOX_TOKEN")
    if not dropbox_token:
        flash("Erreur : DROPBOX_TOKEN manquant. Vérifiez la configuration.", "danger")
        return redirect(url_for('admin_dashboard'))

    try:
        dbx = dropbox.Dropbox(dropbox_token)
        with open(local_file_path, 'rb') as f:
            dbx.files_upload(f.read(), dropbox_file_path, mode=dropbox.files.WriteMode.overwrite)
        flash("Playlist exportée avec succès ! Vous pouvez la retrouver dans Dropbox.", "success")
    except Exception as e:
        flash(f"Erreur lors de l'export Dropbox : {str(e)}", "danger")

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/export_local_lst')
def export_local_lst():
    # Connexion à la base de données
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT title, artist FROM Playlist")
    playlist = cursor.fetchall()
    conn.close()

    # Création du fichier temporaire
    filename = f"Playlist_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.lst"
    local_file_path = os.path.join(EXPORT_DIR, filename)

    # Écriture du fichier
    with open(local_file_path, 'w', encoding='utf-8') as f:
        f.write(filename.replace('.lst', '') + '\n')  # Titre
        for title, artist in playlist:
            f.write(f"{title} - {artist}\n")

    # Téléchargement direct
    return send_file(local_file_path, as_attachment=True)

@app.route('/admin/reset')
def reset_playlist():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM Playlist")
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/qrcode')
def generate_qr():
    qr = qrcode.make(NGROK_URL)
    img_io = BytesIO()
    qr.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))  # Utilisation du port dynamique sur Render
    app.run(host="0.0.0.0", port=port, debug=True)
