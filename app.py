#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CATALOGO MANAGER v4.1
- Due template box (Tabella / Scheda Hyundai)
- Sistema Task per lavorare in team
- Import CSV basato su posizione colonne
- v4: Stato prodotti (attivo/obsoleto/da_verificare)
- v4: Flag verificato_catalogo + campo catalogo
- v4: API verifica discrepanze PDF ↔ DB
- v4: Alert codici variante duplicati
- v4.1: Log modifiche con storico
- v4.1: Backup automatico DB (JSON export)
- v4.1: API bulk update prodotti
"""

import os
import time
import sqlite3
import pandas as pd
import json
import re
import hashlib
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont
import io
import base64

# Configurazione
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "catalogo.db"
UPLOAD_FOLDER = BASE_DIR / "uploads"
FOTO_FOLDER = BASE_DIR / "foto_prodotti"
LOGO_FOLDER = BASE_DIR / "loghi_brand"
ICONE_FOLDER = BASE_DIR / "icone"
OUTPUT_FOLDER = BASE_DIR / "output_box"
EXPORT_FOLDER = BASE_DIR / "export_catalogo"
BACKUP_FOLDER = BASE_DIR / "backups"
BOX_CACHE_FOLDER = BASE_DIR / "box_cache"

for folder in [UPLOAD_FOLDER, FOTO_FOLDER, LOGO_FOLDER, ICONE_FOLDER, OUTPUT_FOLDER, EXPORT_FOLDER, BACKUP_FOLDER, BOX_CACHE_FOLDER]:
    folder.mkdir(exist_ok=True)

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
app.config['TEMPLATES_AUTO_RELOAD'] = True  # Forza ricaricamento template

# Token segreto per deploy automatico (Claude)
DEPLOY_TOKEN = "cat_deploy_2024_pugliese"

# ============================================
# DEPLOY AUTOMATICO (per Claude)
# ============================================

@app.route('/api/deploy', methods=['POST'])
def api_deploy():
    """Endpoint per deploy automatico - esegue git pull"""
    import subprocess

    token = request.headers.get('X-Deploy-Token') or request.json.get('token') if request.is_json else None
    if token != DEPLOY_TOKEN:
        return jsonify({'error': 'Token non valido'}), 403

    try:
        result = subprocess.run(
            ['git', 'pull', 'origin', 'main'],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=30
        )
        return jsonify({
            'success': True,
            'output': result.stdout,
            'error': result.stderr if result.returncode != 0 else None
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/reload', methods=['POST'])
def api_reload():
    """Forza reload del server WSGI (PythonAnywhere)"""
    token = request.headers.get('X-Deploy-Token') or request.json.get('token') if request.is_json else None
    if token != DEPLOY_TOKEN:
        return jsonify({'error': 'Token non valido'}), 403

    try:
        # Path WSGI su PythonAnywhere
        wsgi_path = '/var/www/appuntamenti-briconatura_pythonanywhere_com_wsgi.py'
        if os.path.exists(wsgi_path):
            os.utime(wsgi_path, None)  # Touch del file
            return jsonify({'success': True, 'reloaded': True, 'wsgi': wsgi_path})
        else:
            return jsonify({'success': False, 'error': 'File WSGI non trovato', 'wsgi': wsgi_path})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/cache/clear', methods=['POST'])
def api_clear_cache():
    """Pulisce la cache dei box"""
    token = request.headers.get('X-Deploy-Token') or request.json.get('token') if request.is_json else None
    if token != DEPLOY_TOKEN:
        return jsonify({'error': 'Token non valido'}), 403

    try:
        count = 0
        for f in BOX_CACHE_FOLDER.glob('*.png'):
            f.unlink()
            count += 1
        return jsonify({'success': True, 'deleted': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/cache/status')
def api_cache_status():
    """Mostra stato della cache"""
    try:
        files = list(BOX_CACHE_FOLDER.glob('*.png'))
        total_size = sum(f.stat().st_size for f in files)
        return jsonify({
            'folder': str(BOX_CACHE_FOLDER),
            'exists': BOX_CACHE_FOLDER.exists(),
            'files': len(files),
            'total_size_mb': round(total_size / 1024 / 1024, 2)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def invalidate_product_cache(prodotto_id):
    """Invalida la cache per un prodotto specifico (rimuove tutti i box che lo contengono)"""
    # Non possiamo sapere quali file di cache contengono questo prodotto
    # perché l'hash è basato sui dati, non sull'ID
    # Quindi quando un prodotto viene modificato, la prossima generazione
    # avrà un hash diverso e creerà un nuovo file cache
    # La vecchia cache rimarrà ma non verrà più usata
    pass


# ============================================
# DATABASE
# ============================================

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS prodotti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codice_principale TEXT UNIQUE NOT NULL,
            titolo TEXT NOT NULL,
            descrizione TEXT,
            immagine TEXT,
            logo TEXT,
            icona1 TEXT,
            icona2 TEXT,
            icona3 TEXT,
            icona4 TEXT,
            controllato INTEGER DEFAULT 0,
            fonte_file TEXT,
            template TEXT DEFAULT 'corporate',
            data_creazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_modifica TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS varianti (
            codice TEXT PRIMARY KEY,
            prodotto_id INTEGER NOT NULL,
            modello TEXT,
            um TEXT,
            mv TEXT,
            cf TEXT,
            listino TEXT,
            ordine INTEGER DEFAULT 0,
            escludi_stampa INTEGER DEFAULT 0,
            FOREIGN KEY (prodotto_id) REFERENCES prodotti(id) ON DELETE CASCADE
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS posizioni (
            codice TEXT PRIMARY KEY,
            posizione INTEGER NOT NULL,
            categoria TEXT
        )
    ''')
    
    # Tabella TASK per lavorare in team
    c.execute('''
        CREATE TABLE IF NOT EXISTS task (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prodotto_id INTEGER NOT NULL,
            campo TEXT NOT NULL,
            nota TEXT,
            completato INTEGER DEFAULT 0,
            assegnato_da TEXT,
            completato_da TEXT,
            data_creazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_completamento TIMESTAMP,
            FOREIGN KEY (prodotto_id) REFERENCES prodotti(id) ON DELETE CASCADE
        )
    ''')
    
    # Tabella BRAND/MARCHI
    c.execute('''
        CREATE TABLE IF NOT EXISTS brand (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            logo_file TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS import_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            data_import TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            prodotti_importati INTEGER,
            varianti_importate INTEGER,
            duplicati_saltati INTEGER,
            errori TEXT
        )
    ''')

    # === v4.1: Tabella LOG MODIFICHE ===
    c.execute('''
        CREATE TABLE IF NOT EXISTS modifiche_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prodotto_id INTEGER,
            codice_principale TEXT,
            campo TEXT NOT NULL,
            valore_precedente TEXT,
            valore_nuovo TEXT,
            utente TEXT,
            data_modifica TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (prodotto_id) REFERENCES prodotti(id) ON DELETE SET NULL
        )
    ''')
    
    # Migrazione: aggiungi colonne icone se non esistono
    try:
        c.execute('ALTER TABLE prodotti ADD COLUMN icona1 TEXT')
    except:
        pass
    try:
        c.execute('ALTER TABLE prodotti ADD COLUMN icona2 TEXT')
    except:
        pass
    try:
        c.execute('ALTER TABLE prodotti ADD COLUMN icona3 TEXT')
    except:
        pass
    try:
        c.execute('ALTER TABLE prodotti ADD COLUMN icona4 TEXT')
    except:
        pass
    try:
        c.execute('ALTER TABLE prodotti ADD COLUMN controllato INTEGER DEFAULT 0')
    except:
        pass
    try:
        c.execute('ALTER TABLE varianti ADD COLUMN escludi_stampa INTEGER DEFAULT 0')
    except:
        pass

    # === NUOVI CAMPI v4 ===
    # Campo stato prodotto: attivo, obsoleto, da_verificare
    try:
        c.execute("ALTER TABLE prodotti ADD COLUMN stato TEXT DEFAULT 'attivo'")
    except:
        pass

    # Flag verificato su catalogo PDF
    try:
        c.execute('ALTER TABLE prodotti ADD COLUMN verificato_catalogo INTEGER DEFAULT 0')
    except:
        pass

    # Catalogo di appartenenza (BRICO, IDRAULICA, etc.)
    try:
        c.execute('ALTER TABLE prodotti ADD COLUMN catalogo TEXT')
    except:
        pass

    # Campo doppia_colonna per box che occupano 2 colonne
    try:
        c.execute('ALTER TABLE prodotti ADD COLUMN doppia_colonna INTEGER DEFAULT 0')
    except:
        pass

    # Campo immagine_custom per immagini sostitutive
    try:
        c.execute('ALTER TABLE prodotti ADD COLUMN immagine_custom TEXT')
    except:
        pass

    # Campo scala_immagine per proporzioni (50-150%)
    try:
        c.execute('ALTER TABLE prodotti ADD COLUMN scala_immagine INTEGER DEFAULT 100')
    except:
        pass

    # Campi offset immagine per posizionamento
    try:
        c.execute('ALTER TABLE prodotti ADD COLUMN offset_x INTEGER DEFAULT 0')
    except:
        pass
    try:
        c.execute('ALTER TABLE prodotti ADD COLUMN offset_y INTEGER DEFAULT 0')
    except:
        pass

    # Indici per velocizzare le query
    try:
        c.execute('CREATE INDEX IF NOT EXISTS idx_varianti_codice ON varianti(codice)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_varianti_prodotto ON varianti(prodotto_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_prodotti_codice ON prodotti(codice_principale)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_posizioni_codice ON posizioni(codice)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_task_prodotto ON task(prodotto_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_modifiche_prodotto ON modifiche_log(prodotto_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_modifiche_data ON modifiche_log(data_modifica)')
    except:
        pass
    
    conn.commit()
    conn.close()


# ============================================
# IMPORT CSV - BASATO SU POSIZIONE COLONNE
# ============================================

def parse_csv(filepath):
    try:
        df = pd.read_csv(filepath, sep=';', encoding='latin-1', dtype=str)
    except:
        df = pd.read_csv(filepath, sep=';', encoding='utf-8', dtype=str)
    df.columns = [col.strip() for col in df.columns]
    df = df.fillna('')
    return df


def find_column_by_pattern(columns, patterns):
    """Trova colonna per pattern"""
    for pattern in patterns:
        for col in columns:
            if pattern.upper() in col.upper():
                return col
    return None


def get_variante_columns(columns):
    """
    Rileva le colonne varianti in base alla POSIZIONE, non al nome.
    Cerca gruppi di colonne: CODICE, MODELLO, U.M, MV, CF, LISTINO
    """
    varianti_info = []
    
    # Trova tutte le colonne CODICE con il loro indice
    codice_indices = []
    for i, col in enumerate(columns):
        if 'CODICE' in col.upper():
            codice_indices.append(i)
    
    # Per ogni CODICE, prendi le 5 colonne successive come MODELLO, UM, MV, CF, LISTINO
    for codice_idx in codice_indices:
        var_info = {
            'codice': columns[codice_idx],
            'modello': columns[codice_idx + 1] if codice_idx + 1 < len(columns) else None,
            'um': columns[codice_idx + 2] if codice_idx + 2 < len(columns) else None,
            'mv': columns[codice_idx + 3] if codice_idx + 3 < len(columns) else None,
            'cf': columns[codice_idx + 4] if codice_idx + 4 < len(columns) else None,
            'listino': columns[codice_idx + 5] if codice_idx + 5 < len(columns) else None,
        }
        
        # Verifica che la colonna successiva non sia un altro CODICE
        if var_info['modello'] and 'CODICE' in var_info['modello'].upper():
            var_info['modello'] = None
        if var_info['um'] and 'CODICE' in var_info['um'].upper():
            var_info['um'] = None
            
        varianti_info.append(var_info)
    
    return varianti_info


def clean_value(val):
    """Pulisce e converte caratteri speciali"""
    if not val or pd.isna(val):
        return ''
    val = str(val).strip()
    # Converti caratteri speciali
    val = val.replace('€', '€').replace('Ã¨', 'è').replace('Ã©', 'é')
    val = val.replace('Ã ', 'à').replace('Ã¹', 'ù').replace('Ã²', 'ò')
    return val


def import_csv_to_db(filepath, filename):
    df = parse_csv(filepath)
    columns = df.columns.tolist()
    
    # Trova colonne principali
    titolo_col = find_column_by_pattern(columns, ['TITOLO'])
    desc_col = find_column_by_pattern(columns, ['DESCRIZIONE'])
    img_col = find_column_by_pattern(columns, ['@IMAGINE', 'IMAGINE'])
    logo_col = find_column_by_pattern(columns, ['@IMAGINELOGO', 'IMAGINELOGO'])
    
    # Ottieni info varianti basate su POSIZIONE
    varianti_cols = get_variante_columns(columns)
    
    conn = get_db()
    c = conn.cursor()
    
    prodotti_importati = 0
    varianti_importate = 0
    duplicati_saltati = 0
    errori = []
    
    for idx, row in df.iterrows():
        try:
            titolo = clean_value(row.get(titolo_col, '')) if titolo_col else ''
            if not titolo or titolo == '#N/D':
                continue
            
            # Prima variante = codice principale
            if not varianti_cols:
                continue
            
            codice_principale = clean_value(row.get(varianti_cols[0]['codice'], ''))
            if not codice_principale or codice_principale == '#N/D':
                continue
            
            c.execute('SELECT id FROM prodotti WHERE codice_principale = ?', (codice_principale,))
            if c.fetchone():
                duplicati_saltati += 1
                continue
            
            descrizione = clean_value(row.get(desc_col, '')) if desc_col else ''
            immagine = clean_value(row.get(img_col, '')) if img_col else ''
            logo = clean_value(row.get(logo_col, '')) if logo_col else ''
            
            c.execute('''
                INSERT INTO prodotti (codice_principale, titolo, descrizione, immagine, logo, fonte_file)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (codice_principale, titolo, descrizione, immagine, logo, filename))
            
            prodotto_id = c.lastrowid
            prodotti_importati += 1
            
            # Importa varianti
            for i, var_cols in enumerate(varianti_cols):
                codice = clean_value(row.get(var_cols['codice'], ''))
                if not codice or codice == '#N/D':
                    continue
                
                c.execute('SELECT codice FROM varianti WHERE codice = ?', (codice,))
                if c.fetchone():
                    continue
                
                modello = clean_value(row.get(var_cols['modello'], '')) if var_cols['modello'] else ''
                um = clean_value(row.get(var_cols['um'], '')) if var_cols['um'] else ''
                mv = clean_value(row.get(var_cols['mv'], '')) if var_cols['mv'] else ''
                cf = clean_value(row.get(var_cols['cf'], '')) if var_cols['cf'] else ''
                listino = clean_value(row.get(var_cols['listino'], '')) if var_cols['listino'] else ''
                
                c.execute('''
                    INSERT INTO varianti (codice, prodotto_id, modello, um, mv, cf, listino, ordine)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (codice, prodotto_id, modello, um, mv, cf, listino, i + 1))
                
                varianti_importate += 1
                
        except Exception as e:
            errori.append(f"Riga {idx}: {str(e)}")
    
    c.execute('''
        INSERT INTO import_log (filename, prodotti_importati, varianti_importate, duplicati_saltati, errori)
        VALUES (?, ?, ?, ?, ?)
    ''', (filename, prodotti_importati, varianti_importate, duplicati_saltati, json.dumps(errori)))
    
    conn.commit()
    conn.close()
    
    return {
        'prodotti_importati': prodotti_importati,
        'varianti_importate': varianti_importate,
        'duplicati_saltati': duplicati_saltati,
        'errori': errori
    }


def import_posizioni(filepath, categoria):
    """Importa file Excel/CSV con posizioni (CODICE, NUMERO)"""
    
    # Prova a leggere come Excel o CSV
    try:
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath, sep=';', encoding='latin-1', dtype=str)
        else:
            df = pd.read_excel(filepath, dtype=str)
    except:
        df = pd.read_excel(filepath, dtype=str)
    
    # Trova colonne CODICE e NUMERO/POSIZIONE
    codice_col = None
    pos_col = None
    
    for col in df.columns:
        col_upper = str(col).upper().strip()
        if 'CODICE' in col_upper:
            codice_col = col
        elif 'NUMERO' in col_upper or 'POSIZIONE' in col_upper or 'POS' in col_upper:
            pos_col = col
    
    if not codice_col or not pos_col:
        raise ValueError("Colonne CODICE e NUMERO/POSIZIONE non trovate")
    
    conn = get_db()
    c = conn.cursor()
    
    # Pulisci posizioni precedenti per questa categoria
    c.execute('DELETE FROM posizioni WHERE categoria = ?', (categoria,))
    
    importati = 0
    for idx, row in df.iterrows():
        codice = str(row[codice_col]).strip()
        posizione = row[pos_col]
        
        if not codice or pd.isna(posizione):
            continue
        
        try:
            posizione = int(float(posizione))
            c.execute('''
                INSERT OR REPLACE INTO posizioni (codice, posizione, categoria)
                VALUES (?, ?, ?)
            ''', (codice, posizione, categoria))
            importati += 1
        except:
            pass
    
    conn.commit()
    conn.close()
    
    return importati


# ============================================
# GENERATORE BOX - DUE TEMPLATE MIGLIORATI
# ============================================

class BoxGenerator:
    """Generatore box con grafica professionale"""
    
    def __init__(self):
        self.setup_fonts()
        
    def setup_fonts(self):
        """Setup font cross-platform (Windows + Linux + Mac)"""
        import platform
        import os
        
        # Rileva sistema operativo
        system = platform.system()
        
        if system == 'Windows':
            # Font Windows
            self.font_paths = {
                'bold': "C:/Windows/Fonts/arialbd.ttf",
                'regular': "C:/Windows/Fonts/arial.ttf",
                'italic': "C:/Windows/Fonts/ariali.ttf",
            }
            if not os.path.exists(self.font_paths['bold']):
                self.font_paths = {
                    'bold': "C:/Windows/Fonts/segoeui.ttf",
                    'regular': "C:/Windows/Fonts/segoeui.ttf",
                    'italic': "C:/Windows/Fonts/segoeuii.ttf",
                }
        elif system == 'Darwin':  # macOS
            # Font Mac - prova varie posizioni
            mac_font_dirs = [
                "/Library/Fonts",
                "/System/Library/Fonts/Supplemental",
                "/System/Library/Fonts",
                os.path.expanduser("~/Library/Fonts")
            ]
            
            # Cerca Arial
            arial_bold = None
            arial_reg = None
            arial_italic = None
            
            for font_dir in mac_font_dirs:
                if not arial_bold and os.path.exists(f"{font_dir}/Arial Bold.ttf"):
                    arial_bold = f"{font_dir}/Arial Bold.ttf"
                if not arial_reg and os.path.exists(f"{font_dir}/Arial.ttf"):
                    arial_reg = f"{font_dir}/Arial.ttf"
                if not arial_italic and os.path.exists(f"{font_dir}/Arial Italic.ttf"):
                    arial_italic = f"{font_dir}/Arial Italic.ttf"
            
            # Fallback a Helvetica se Arial non trovato
            if not arial_bold:
                for font_dir in mac_font_dirs:
                    if os.path.exists(f"{font_dir}/Helvetica.ttc"):
                        arial_bold = f"{font_dir}/Helvetica.ttc"
                        arial_reg = f"{font_dir}/Helvetica.ttc"
                        arial_italic = f"{font_dir}/Helvetica.ttc"
                        break
            
            # Ultimo fallback
            if not arial_bold:
                arial_bold = "/System/Library/Fonts/Helvetica.ttc"
                arial_reg = "/System/Library/Fonts/Helvetica.ttc"
                arial_italic = "/System/Library/Fonts/Helvetica.ttc"
            
            self.font_paths = {
                'bold': arial_bold,
                'regular': arial_reg or arial_bold,
                'italic': arial_italic or arial_reg or arial_bold,
            }
        else:
            # Font Linux
            self.font_paths = {
                'bold': "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                'regular': "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                'italic': "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
            }
        
        self.fonts = {}
        try:
            # Font per template TABELLA
            self.fonts['tab_title'] = ImageFont.truetype(self.font_paths['bold'], 22)
            self.fonts['tab_desc'] = ImageFont.truetype(self.font_paths['regular'], 13)
            self.fonts['tab_th'] = ImageFont.truetype(self.font_paths['bold'], 13)
            self.fonts['tab_td'] = ImageFont.truetype(self.font_paths['regular'], 13)
            
            # Font per template SCHEDA (1080x1080 Corporate)
            self.fonts['corp_title'] = ImageFont.truetype(self.font_paths['bold'], 36)
            self.fonts['corp_desc'] = ImageFont.truetype(self.font_paths['italic'], 22)
            self.fonts['corp_th'] = ImageFont.truetype(self.font_paths['bold'], 18)
            self.fonts['corp_td'] = ImageFont.truetype(self.font_paths['regular'], 20)
            
            # Font per template FULLHD (1920x1080)
            self.fonts['fhd_title'] = ImageFont.truetype(self.font_paths['bold'], 48)
            self.fonts['fhd_desc'] = ImageFont.truetype(self.font_paths['italic'], 24)
            self.fonts['fhd_th'] = ImageFont.truetype(self.font_paths['bold'], 20)
            self.fonts['fhd_td'] = ImageFont.truetype(self.font_paths['regular'], 22)
            
            # Fallback generici
            self.fonts['title'] = self.fonts['tab_title']
            self.fonts['title_small'] = ImageFont.truetype(self.font_paths['bold'], 18)
            self.fonts['desc'] = self.fonts['tab_desc']
            self.fonts['label'] = ImageFont.truetype(self.font_paths['bold'], 24)
            self.fonts['value'] = ImageFont.truetype(self.font_paths['regular'], 26)
            self.fonts['table_header'] = self.fonts['tab_th']
            self.fonts['table_cell'] = self.fonts['tab_td']
            
            print(f"✅ Font caricati ({system}): {self.font_paths['bold']}")
        except Exception as e:
            print(f"⚠️ Font fallback attivato: {e}")
            default = ImageFont.load_default()
            for k in ['tab_title', 'tab_desc', 'tab_th', 'tab_td', 'corp_title', 'corp_desc',
                      'corp_th', 'corp_td', 'fhd_title', 'fhd_desc', 'fhd_th', 'fhd_td',
                      'title', 'title_small', 'desc', 'label', 'value', 
                      'table_header', 'table_cell']:
                self.fonts[k] = default
    
    def load_image(self, filename, codice=None):
        """Carica immagine da cartelle foto/logo - cerca anche per codice"""
        if not filename and not codice:
            return None

        # Prima cerca il nome esatto
        if filename:
            for folder in [FOTO_FOLDER, LOGO_FOLDER]:
                path = folder / filename
                if path.exists():
                    try:
                        img = Image.open(path)
                        return img.convert('RGBA')
                    except:
                        pass

            # Se non trova, prova VARIAZIONI DI CASE comuni (veloce, senza iterare cartella)
            name, ext = os.path.splitext(filename)
            case_variants = [
                filename.lower(),                    # tutto minuscolo
                filename.upper(),                    # tutto maiuscolo
                name + ext.lower(),                  # estensione minuscola
                name + ext.upper(),                  # estensione maiuscola
                name.upper() + ext.lower(),          # nome maiuscolo, ext minuscola
            ]
            for variant in case_variants:
                if variant == filename:
                    continue  # già provato
                for folder in [FOTO_FOLDER, LOGO_FOLDER]:
                    path = folder / variant
                    if path.exists():
                        try:
                            img = Image.open(path)
                            return img.convert('RGBA')
                        except:
                            pass

        # Se non trova e abbiamo il codice, cerca file che iniziano con il codice
        if codice:
            for folder in [FOTO_FOLDER, LOGO_FOLDER]:
                if folder.exists():
                    for ext in ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG', '.jfif']:
                        # Cerca codice.ext o codice_*.ext
                        for pattern in [f"{codice}{ext}", f"{codice}_*{ext}", f"P{codice}*{ext}"]:
                            matches = list(folder.glob(pattern))
                            if matches:
                                try:
                                    img = Image.open(matches[0])
                                    return img.convert('RGBA')
                                except:
                                    pass
        return None
    
    def load_icona(self, filename):
        """Carica icona dalla cartella icone"""
        if not filename:
            return None
        path = ICONE_FOLDER / filename
        if path.exists():
            try:
                img = Image.open(path)
                return img.convert('RGBA')
            except:
                pass
        return None
    
    def _contain(self, im, max_w, max_h, scala=100):
        """Resize mantenendo proporzioni con LANCZOS. scala è una percentuale (50-150)"""
        if im is None:
            return None

        w, h = im.size
        if w <= 0 or h <= 0:
            return im

        # Prima ridimensiona per entrare nel box
        scale = min(max_w / w, max_h / h)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))

        # Poi applica la scala utente (50-150%)
        if scala and scala != 100:
            scala_factor = scala / 100.0
            nw = max(1, int(nw * scala_factor))
            nh = max(1, int(nh * scala_factor))

        if (nw, nh) != (w, h):
            im = im.resize((nw, nh), Image.LANCZOS)
        return im
    
    def _wrap_text(self, draw, text, font, max_width):
        """Word-wrap per Pillow"""
        if not text:
            return []
        text = re.sub(r"\s+", " ", str(text)).strip()
        if not text:
            return []
        words = text.split(" ")
        lines = []
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if draw.textlength(test, font=font) <= max_width:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines
    
    def format_price(self, price):
        """Formatta prezzo con € - pulisce caratteri problematici"""
        if price is None:
            return ""
        s = str(price).strip()
        s = re.sub(r"[^\d,\.]", "", s)
        if not s:
            return ""
        return f"{s} €"
    
    def _fit_font(self, draw, text, max_width, max_height, font_path, start_size=44, min_size=20):
        """Trova il font size ottimale per far entrare il testo"""
        for size in range(start_size, min_size - 1, -2):
            try:
                font = ImageFont.truetype(font_path, size)
                bbox = draw.textbbox((0, 0), text, font=font)
                if bbox[2] - bbox[0] <= max_width and bbox[3] - bbox[1] <= max_height:
                    return font
            except:
                pass
        # Fallback
        try:
            return ImageFont.truetype(font_path, min_size)
        except:
            return self.fonts.get('title', ImageFont.load_default())
    
    def generate_tabella(self, prodotto, varianti):
        """
        Template TABELLA - Stile professionale (come 97.jpg)
        - Titolo in alto a sinistra
        - Logo in alto a destra
        - Immagine prodotto centrata
        - Descrizione (max 2 righe)
        - Tabella varianti con header verde
        """
        W = 850
        PAD_X = 40
        PAD_TOP = 28
        BG = (255, 255, 255)
        
        # Colori
        GREEN = (106, 176, 76)
        GRID = (220, 220, 220)
        GRID_LIGHT = (235, 235, 235)
        TEXT = (35, 35, 35)
        SUBTEXT = (95, 95, 95)
        
        # Font
        f_title = self.fonts.get('tab_title', self.fonts['title'])
        f_desc = self.fonts.get('tab_desc', self.fonts['desc'])
        f_th = self.fonts.get('tab_th', self.fonts['table_header'])
        f_td = self.fonts.get('tab_td', self.fonts['table_cell'])
        
        # Metriche layout
        title_h = 34
        top_gap = 22
        img_area_h = 285
        desc_gap = 18
        table_top_gap = 22
        header_h = 46
        row_h = 38
        
        # Pre-calcolo descrizione
        dummy = Image.new("RGB", (10, 10), BG)
        d = ImageDraw.Draw(dummy)
        desc_max_w = W - 2 * PAD_X
        desc_lines = []
        if prodotto.get("descrizione"):
            desc_lines = self._wrap_text(d, prodotto["descrizione"], f_desc, desc_max_w)[:2]
        desc_h = 0
        if desc_lines:
            line_h = int(getattr(f_desc, "size", 13) * 1.35)
            desc_h = line_h * len(desc_lines)
        
        # Altezza tabella
        n = len(varianti or [])
        table_h = header_h + n * row_h
        
        # Altezza totale dinamica
        H = PAD_TOP + title_h + top_gap + img_area_h + desc_gap + desc_h + table_top_gap + table_h + 38
        
        img = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(img)
        
        # --- Titolo ---
        title = (prodotto.get("titolo") or "").upper().strip()
        draw.text((PAD_X, PAD_TOP), title, fill=TEXT, font=f_title)
        
        # --- Logo ---
        logo = self.load_image(prodotto.get("logo"))
        if logo:
            logo = self._contain(logo, 120, 55)
            lx = W - PAD_X - logo.size[0]
            ly = PAD_TOP - 6
            img.paste(logo, (lx, ly), logo)
        
        y = PAD_TOP + title_h + top_gap

        # --- Immagine prodotto centrata ---
        scala = prodotto.get("scala_immagine", 100) or 100
        prod = self.load_image(prodotto.get("immagine"), prodotto.get("codice_principale"))
        if prod:
            prod = self._contain(prod, W - 2 * PAD_X - 80, img_area_h, scala)
            px = (W - prod.size[0]) // 2
            py = y + (img_area_h - prod.size[1]) // 2
            img.paste(prod, (px, py), prod)
        y += img_area_h
        
        # --- Descrizione ---
        y += desc_gap
        if desc_lines:
            line_h = int(getattr(f_desc, "size", 13) * 1.35)
            for i, line in enumerate(desc_lines):
                draw.text((PAD_X, y + i * line_h), line, fill=SUBTEXT, font=f_desc)
            y += desc_h
        
        y += table_top_gap
        
        # --- Tabella ---
        table_x = PAD_X
        table_w = W - 2 * PAD_X
        
        headers = ["CODICE", "MODELLO", "U.M.", "MV", "CF", "NETTO"]
        ratios = [0.15, 0.30, 0.10, 0.08, 0.10, 0.27]
        col_w = [int(table_w * r) for r in ratios]
        col_w[-1] = table_w - sum(col_w[:-1])
        
        # Header verde
        x = table_x
        for htxt, cw in zip(headers, col_w):
            draw.rectangle([x, y, x + cw, y + header_h], fill=GREEN)
            draw.text((x + cw / 2, y + header_h / 2), htxt, fill=BG, font=f_th, anchor="mm")
            x += cw
        
        # Bordo esterno
        draw.rectangle([table_x, y, table_x + table_w, y + table_h], outline=GRID, width=1)
        y += header_h
        
        # Righe
        for r, var in enumerate(varianti or []):
            fill_row = (255, 255, 255) if r % 2 == 0 else (250, 250, 250)
            draw.rectangle([table_x, y, table_x + table_w, y + row_h], fill=fill_row)
            
            values = [
                str(var.get("codice", "")),
                str(var.get("modello", "")),
                str(var.get("um", "") or "PZ"),
                str(var.get("mv", "") or "1"),
                str(var.get("cf", "") or ""),
                self.format_price(var.get("listino", "")),
            ]
            
            x = table_x
            for val, cw in zip(values, col_w):
                draw.line([x, y, x, y + row_h], fill=GRID_LIGHT, width=1)
                draw.text((x + cw / 2, y + row_h / 2), (val or "")[:40], fill=TEXT, font=f_td, anchor="mm")
                x += cw
            
            draw.line([table_x + table_w, y, table_x + table_w, y + row_h], fill=GRID_LIGHT, width=1)
            draw.line([table_x, y + row_h, table_x + table_w, y + row_h], fill=GRID_LIGHT, width=1)
            y += row_h
        
        return img
    
    def generate_scheda(self, prodotto, varianti):
        """
        Template SCHEDA - Stile Hyundai orizzontale
        - Titolo grande centrato
        - Immagine prodotto a sinistra grande
        - Griglia dati con label verdi
        - Logo a destra
        """
        W, H = 1600, 500
        BG = (255, 255, 255)
        
        # Colori
        GREEN = (106, 176, 76)
        TEXT = (30, 30, 30)
        GRAY = (80, 80, 80)
        
        # Font
        f_title = self.fonts.get('corp_title', self.fonts['title'])
        f_desc = self.fonts.get('corp_desc', self.fonts['desc'])
        f_label = self.fonts.get('corp_th', self.fonts['table_header'])
        f_val = self.fonts.get('corp_td', self.fonts['table_cell'])
        f_val_big = self.fonts.get('corp_title', self.fonts['title'])
        
        img = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(img)

        # Immagine prodotto (sinistra)
        scala = prodotto.get("scala_immagine", 100) or 100
        prod = self.load_image(prodotto.get("immagine"), prodotto.get("codice_principale"))
        if prod:
            prod = self._contain(prod, 450, 420, scala)
            px = 50
            py = 40 + (420 - prod.size[1]) // 2
            img.paste(prod, (px, py), prod)
        
        # Contenuto destra
        content_x = 550
        
        # Titolo
        title = (prodotto.get("titolo") or "").upper().strip()
        draw.text((content_x, 40), title, fill=TEXT, font=f_title)
        
        # Descrizione
        desc = (prodotto.get("descrizione") or "").strip()
        if desc:
            lines = self._wrap_text(draw, desc, f_desc, 600)[:3]
            y_desc = 90
            for line in lines:
                draw.text((content_x, y_desc), line, font=f_desc, fill=GRAY)
                y_desc += 28
        
        # Logo (alto destra)
        logo = self.load_image(prodotto.get("logo"))
        if logo:
            logo = self._contain(logo, 180, 80)
            img.paste(logo, (W - logo.size[0] - 50, 30), logo)
        
        # Griglia dati (prima variante)
        var = (varianti or [{}])[0]
        
        grid_x = content_x
        grid_y = 200
        box_w, box_h = 140, 55
        val_w = 180
        row_gap = 8
        col_gap = 40
        
        def label_box(x, y, label):
            draw.rectangle([x, y, x + box_w, y + box_h], fill=GREEN)
            draw.text((x + box_w / 2, y + box_h / 2), label, fill=BG, font=f_label, anchor="mm")
        
        def value_box(x, y, text, font):
            draw.rectangle([x, y, x + val_w, y + box_h], outline=GREEN, width=2)
            draw.text((x + val_w / 2, y + box_h / 2), text, fill=TEXT, font=font, anchor="mm")
        
        # Colonna 1
        col1_x = grid_x
        label_box(col1_x, grid_y, "CODICE")
        value_box(col1_x + box_w, grid_y, str(var.get("codice", "")), f_val_big)
        
        label_box(col1_x, grid_y + box_h + row_gap, "MODELLO")
        value_box(col1_x + box_w, grid_y + box_h + row_gap, str(var.get("modello", ""))[:20], f_val)
        
        label_box(col1_x, grid_y + 2*(box_h + row_gap), "U.M.")
        value_box(col1_x + box_w, grid_y + 2*(box_h + row_gap), str(var.get("um", "") or "PZ"), f_val)
        
        # Colonna 2
        col2_x = col1_x + box_w + val_w + col_gap
        label_box(col2_x, grid_y, "MV")
        value_box(col2_x + box_w, grid_y, str(var.get("mv", "") or "1"), f_val)
        
        label_box(col2_x, grid_y + box_h + row_gap, "CF")
        value_box(col2_x + box_w, grid_y + box_h + row_gap, str(var.get("cf", "") or "1"), f_val)
        
        label_box(col2_x, grid_y + 2*(box_h + row_gap), "NETTO")
        value_box(col2_x + box_w, grid_y + 2*(box_h + row_gap), self.format_price(var.get("listino")), f_val_big)
        
        return img
    
    def generate_corporate(self, prodotto, varianti):
        """
        Template CORPORATE - Ottimizzato per stampa A4 a due colonne (InDesign)
        - Larghezza: 1080px (~92mm a 300dpi, perfetto per colonna A4)
        - Altezza: DINAMICA in base alle varianti
        - SENZA spazio bianco intorno
        - Codice in GRASSETTO
        - Striscia verde in basso
        """
        W = 1080
        
        # Colori
        GREEN_DARK = (27, 67, 50)
        BG = (255, 255, 255)
        TEXT_MAIN = (20, 20, 20)
        GRID = (180, 180, 180)
        ROW_ALT = (245, 245, 245)
        
        # Dimensioni
        header_h = 50           # Header ridotto
        row_h = 50              # Righe 50px
        border_width = 2
        strip_h = 14            # Striscia verde in basso
        n_varianti = len(varianti) if varianti else 0
        
        # Layout NUOVO: foto centrata + descrizione sotto
        pad = 15
        top_section = 100       # Titolo + logo
        img_h = 320             # Altezza immagine
        desc_h = 120            # Spazio descrizione (aumentato per staccare da tabella)
        img_section = img_h + desc_h  # Totale area centrale
        table_header = header_h
        table_rows = n_varianti * row_h
        
        # Altezza totale con striscia
        H = top_section + img_section + table_header + table_rows + strip_h
        
        img = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(img)
        
        # Font GRANDI
        try:
            f_title = ImageFont.truetype(self.font_paths['bold'], 44)       # Titolo 44pt
            f_desc = ImageFont.truetype(self.font_paths['italic'], 28)      # Descrizione
            f_th = ImageFont.truetype(self.font_paths['bold'], 30)          # Header tabella 30pt
            f_td = ImageFont.truetype(self.font_paths['regular'], 30)       # Celle
            f_td_bold = ImageFont.truetype(self.font_paths['bold'], 36)     # Codice GRASSETTO 36pt
        except:
            f_title = self.fonts.get('corp_title', self.fonts['title'])
            f_desc = self.fonts.get('corp_desc', self.fonts['desc'])
            f_th = self.fonts.get('corp_th', self.fonts['table_header'])
            f_td = self.fonts.get('corp_td', self.fonts['table_cell'])
            f_td_bold = f_th
        
        # ==========================================
        # 1. INTESTAZIONE (Titolo + Logo + Badge Posizione)
        # ==========================================
        y_start = 8
        badge_offset = 0

        # Badge posizione (Top Left Corner)
        posizione = prodotto.get('posizione') or prodotto.get('_posizione')
        if posizione:
            badge_size = 50
            badge_x, badge_y = 5, 5
            # Cerchio verde
            draw.ellipse([badge_x, badge_y, badge_x + badge_size, badge_y + badge_size], fill=GREEN_DARK)
            # Numero
            try:
                f_badge = ImageFont.truetype(self.font_paths['bold'], 24)
            except:
                f_badge = f_title
            pos_text = str(posizione)
            bbox = draw.textbbox((0, 0), pos_text, font=f_badge)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((badge_x + (badge_size - tw) // 2, badge_y + (badge_size - th) // 2 - 2), pos_text, font=f_badge, fill=(255, 255, 255))
            badge_offset = badge_size + 10

        # Logo (Top Right)
        logo_w = 0
        logo = self.load_image(prodotto.get("logo"))
        if logo:
            logo = self._contain(logo, 170, 75)
            img.paste(logo, (W - logo.size[0] - pad, y_start + 5), logo)
            logo_w = logo.size[0] + 20

        # Titolo PIÙ EVIDENTE (dopo badge) - va a capo se troppo lungo
        title_text = (prodotto.get("titolo") or "").upper()
        title_x = pad + badge_offset  # Sposta a destra per fare spazio al badge
        max_title_w = W - logo_w - pad * 2 - badge_offset

        # Usa font fisso 40px e manda a capo se necessario (max 2 righe)
        try:
            f_title = ImageFont.truetype(self.font_paths['bold'], 40)
        except:
            f_title = self.fonts.get('title', ImageFont.load_default())

        title_lines = self._wrap_text(draw, title_text, f_title, max_title_w)[:2]  # Max 2 righe
        title_y = y_start
        for line in title_lines:
            draw.text((title_x, title_y), line, font=f_title, fill=TEXT_MAIN)
            title_y += 45  # Interlinea
        
        # Linea sotto titolo per evidenziarlo (sotto l'ultima riga)
        if title_lines:
            last_line = title_lines[-1]
            last_line_y = y_start + (len(title_lines) - 1) * 45
            last_bbox = draw.textbbox((title_x, last_line_y), last_line, font=f_title)
            draw.line([title_x, last_bbox[3] + 5, last_bbox[2] + 10, last_bbox[3] + 5], fill=GREEN_DARK, width=3)
        
        # ==========================================
        # 2. IMMAGINE CENTRATA + DESCRIZIONE SOTTO
        # ==========================================
        img_y = top_section

        # Immagine prodotto CENTRATA e PIÙ GRANDE
        scala = prodotto.get("scala_immagine", 100) or 100
        offset_x = prodotto.get("offset_x", 0) or 0
        offset_y = prodotto.get("offset_y", 0) or 0
        prod = self.load_image(prodotto.get("immagine"), prodotto.get("codice_principale"))
        if prod:
            prod = self._contain(prod, 500, img_h - 20, scala)  # Più grande
            px = (W - prod.size[0]) // 2 + offset_x * 3  # Centrata + offset
            py = img_y + offset_y * 3
            img.paste(prod, (px, py), prod)
        
        # Descrizione SOTTO la foto (centrata)
        desc = (prodotto.get("descrizione") or "").strip()
        if desc:
            desc_y = img_y + img_h + 3
            lines = self._wrap_text(draw, desc, f_desc, W - pad * 4)[:3]
            for line in lines:
                # Centra ogni riga
                line_bbox = draw.textbbox((0, 0), line, font=f_desc)
                line_w = line_bbox[2] - line_bbox[0]
                draw.text(((W - line_w) // 2, desc_y), line, font=f_desc, fill=TEXT_MAIN)
                desc_y += 32
        
        # ==========================================
        # 3. TABELLA (bordo a bordo)
        # ==========================================
        table_y = top_section + img_section
        table_x = 0
        table_w = W
        
        cols = [
            ("CODICE", 0.16),
            ("MODELLO", 0.34),
            ("U.M.", 0.10),
            ("MV", 0.10),
            ("CF", 0.10),
            ("NETTO", 0.20)
        ]
        
        # Posizioni colonne
        col_positions = []
        x = table_x
        for _, width_pct in cols:
            col_positions.append(x)
            x += int(table_w * width_pct)
        col_positions.append(table_w)
        
        # HEADER verde scuro
        draw.rectangle([0, table_y, W, table_y + header_h], fill=GREEN_DARK)
        
        for i, (title, _) in enumerate(cols):
            col_center = (col_positions[i] + col_positions[i+1]) // 2
            draw.text((col_center, table_y + header_h // 2), title, 
                     font=f_th, fill=BG, anchor="mm")
        
        # Spazi bianchi tra colonne header
        col_gap = 6
        for pos in col_positions[1:-1]:
            draw.rectangle([pos - col_gap//2, table_y, pos + col_gap//2, table_y + header_h], fill=BG)
        
        # RIGHE DATI
        y = table_y + header_h
        
        for i, v in enumerate(varianti or []):
            row_bg = ROW_ALT if i % 2 != 0 else BG
            draw.rectangle([0, y, W, y + row_h], fill=row_bg)
            
            vals = [
                (str(v.get("codice", "")), f_td_bold),      # CODICE in GRASSETTO
                (str(v.get("modello", ""))[:22], f_td),     # Modello troncato
                (str(v.get("um", "") or "PZ"), f_td),
                (str(v.get("mv", "") or "1"), f_td),
                (str(v.get("cf", "") or "1"), f_td),
                (self.format_price(v.get("listino")), f_td)
            ]
            
            for j, (val, font) in enumerate(vals):
                col_center = (col_positions[j] + col_positions[j+1]) // 2
                draw.text((col_center, y + row_h // 2), val, 
                         font=font, fill=TEXT_MAIN, anchor="mm")
            
            # Spazi bianchi tra colonne
            for pos in col_positions[1:-1]:
                draw.rectangle([pos - 3, y, pos + 3, y + row_h], fill=BG)
            
            # Linea orizzontale
            draw.line([0, y + row_h, W, y + row_h], fill=GRID, width=border_width)
            
            y += row_h
        
        # Bordi laterali tabella
        draw.line([0, table_y, 0, y], fill=GRID, width=border_width)
        draw.line([W-1, table_y, W-1, y], fill=GRID, width=border_width)
        
        # ==========================================
        # 4. STRISCIA VERDE IN BASSO (stesso colore header)
        # ==========================================
        draw.rectangle([0, H - strip_h, W, H], fill=GREEN_DARK)
        
        return img
    
    def generate_fullhd(self, prodotto, varianti):
        """
        Template FULL HD - Orizzontale (1920x1080)
        - Immagine grande a sinistra (45%)
        - Dati a destra con griglia moderna
        - Singola variante con layout elegante
        """
        W, H = 1920, 1080
        
        # Colori
        GREEN_DARK = (27, 67, 50)
        BG = (255, 255, 255)
        TEXT_MAIN = (30, 30, 30)
        TEXT_MUTED = (120, 120, 120)
        LINE_LIGHT = (220, 220, 220)
        
        img = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(img)
        
        # Dati della prima variante
        v = (varianti or [{}])[0]
        
        # ==========================================
        # 1. ZONA IMMAGINE (Sinistra - 45%)
        # ==========================================
        scala = prodotto.get("scala_immagine", 100) or 100
        offset_x = prodotto.get("offset_x", 0) or 0
        offset_y = prodotto.get("offset_y", 0) or 0
        prod = self.load_image(prodotto.get("immagine"), prodotto.get("codice_principale"))
        if prod:
            prod = self._contain(prod, 800, 900, scala)
            img_x = (850 - prod.size[0]) // 2 + 50 + offset_x * 5
            img_y = (H - prod.size[1]) // 2 + offset_y * 5
            img.paste(prod, (img_x, img_y), prod)

        # Linea separatrice verticale
        draw.line([900, 100, 900, H-100], fill=LINE_LIGHT, width=2)
        
        # ==========================================
        # 2. ZONA DATI (Destra - 55%)
        # ==========================================
        x_start = 980
        y = 120
        
        # Logo in alto a destra
        logo = self.load_image(prodotto.get("logo"))
        if logo:
            logo = self._contain(logo, 250, 120)
            img.paste(logo, (W - logo.size[0] - 80, 80), logo)
        
        # Titolo Prodotto
        title_text = (prodotto.get("titolo") or "").upper()
        max_title_w = 650
        try:
            f_title = self._fit_font(draw, title_text, max_title_w, 150, self.font_paths['bold'], start_size=60, min_size=36)
        except:
            f_title = self.fonts.get('fhd_title', self.fonts['title'])
        draw.text((x_start, y), title_text, font=f_title, fill=TEXT_MAIN)
        
        y += 100
        
        # Descrizione
        desc = (prodotto.get("descrizione") or "").strip()
        if desc:
            f_desc = self.fonts.get('fhd_desc', self.fonts['desc'])
            lines = self._wrap_text(draw, desc, f_desc, 800)[:6]
            for line in lines:
                draw.text((x_start, y), line, font=f_desc, fill=TEXT_MUTED)
                y += 40
        
        y += 80
        
        # ==========================================
        # 3. GRIGLIA TECNICA (Key-Value)
        # ==========================================
        f_label = self.fonts.get('fhd_th', self.fonts['table_header'])
        f_value = self.fonts.get('fhd_td', self.fonts['table_cell'])
        
        specs = [
            ("CODICE", v.get("codice", "N/D")),
            ("MODELLO", v.get("modello", "-")),
            ("U.M.", v.get("um", "") or "PZ"),
            ("MIN. VENDITA (MV)", v.get("mv", "") or "1"),
            ("CONFEZIONE (CF)", v.get("cf", "") or "1"),
            ("NETTO", self.format_price(v.get("listino")))
        ]
        
        row_h = 110
        current_col = 0
        
        for i, (label, value) in enumerate(specs):
            item_x = x_start + (current_col * 450)
            item_y = y
            
            # Etichetta
            draw.text((item_x, item_y), label, font=f_label, fill=GREEN_DARK)
            
            # Valore
            draw.text((item_x, item_y + 35), str(value), font=f_value, fill=TEXT_MAIN)
            
            # Linea sottile
            draw.line([item_x, item_y + 85, item_x + 350, item_y + 85], fill=LINE_LIGHT, width=1)
            
            # Gestione 2 colonne
            current_col += 1
            if current_col > 1:
                current_col = 0
                y += row_h
        
        # ==========================================
        # 4. ICONE (sotto Confezione e Listino)
        # ==========================================
        icone_y = y + 40  # Sotto l'ultima riga della griglia
        icone_x_start = x_start + 60
        icone_spacing = 180
        
        for i, icona_key in enumerate(['icona1', 'icona2', 'icona3', 'icona4']):
            icona_file = prodotto.get(icona_key)
            if icona_file:
                icona = self.load_icona(icona_file)
                if icona:
                    icona = self._contain(icona, 130, 130)
                    ix = icone_x_start + (i * icone_spacing)
                    iy = icone_y
                    img.paste(icona, (ix, iy), icona)
        
        return img
    
    def _get_cache_key(self, prodotto, varianti, template):
        """Genera hash unico per cache del box"""
        # Funzione helper per accedere ai campi (dict o sqlite3.Row)
        def get_val(obj, key, default=None):
            try:
                val = obj.get(key, default) if hasattr(obj, 'get') else obj[key] if key in obj.keys() else default
                return val
            except:
                return default

        # Dati che influenzano il rendering del box
        cache_data = {
            'template': template,
            'titolo': get_val(prodotto, 'titolo'),
            'descrizione': get_val(prodotto, 'descrizione'),
            'codice_principale': get_val(prodotto, 'codice_principale'),
            'foto': get_val(prodotto, 'foto'),
            'logo': get_val(prodotto, 'logo'),
            'scala_foto': get_val(prodotto, 'scala_foto', 100),
            'offset_x': get_val(prodotto, 'offset_x', 0),
            'offset_y': get_val(prodotto, 'offset_y', 0),
            'icona1': get_val(prodotto, 'icona1'),
            'icona2': get_val(prodotto, 'icona2'),
            'icona3': get_val(prodotto, 'icona3'),
            'icona4': get_val(prodotto, 'icona4'),
            'varianti': [(get_val(v, 'codice'), get_val(v, 'descrizione'), get_val(v, 'confezione'),
                         get_val(v, 'listino'), get_val(v, 'ordine')) for v in varianti]
        }
        cache_str = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(cache_str.encode()).hexdigest()

    def generate(self, prodotto, varianti, template='corporate', use_cache=True):
        """Genera box con template specificato, usando cache se disponibile"""
        if use_cache:
            cache_key = self._get_cache_key(prodotto, varianti, template)
            cache_path = BOX_CACHE_FOLDER / f"{cache_key}.png"

            # Se esiste in cache, carica
            if cache_path.exists():
                try:
                    return Image.open(cache_path).convert('RGBA')
                except:
                    pass  # Se fallisce, rigenera

        # Genera il box
        if template == 'fullhd':
            box_img = self.generate_fullhd(prodotto, varianti)
        else:
            box_img = self.generate_corporate(prodotto, varianti)

        # Salva in cache
        if use_cache and box_img:
            try:
                cache_key = self._get_cache_key(prodotto, varianti, template)
                cache_path = BOX_CACHE_FOLDER / f"{cache_key}.png"
                box_img.save(cache_path, 'PNG')
                print(f"[CACHE] Salvato: {cache_path}")
            except Exception as e:
                print(f"[CACHE] Errore salvataggio: {e}")

        return box_img
    
    def to_base64(self, img):
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode()
    
    def save_as_jpg(self, img, filepath, quality=95):
        if img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background
        img.save(filepath, 'JPEG', quality=quality, optimize=True)


box_generator = BoxGenerator()


# ============================================
# API ROUTES
# ============================================

@app.route('/')
def index():
    # Use v4 interface by default
    return render_template('index_v4.html')

@app.route('/v3')
def index_v3():
    # Legacy v3 interface
    return render_template('index.html')


@app.route('/api/stats')
def api_stats():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM prodotti')
    num_prodotti = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM varianti')
    num_varianti = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM posizioni')
    num_posizioni = c.fetchone()[0]
    
    c.execute('SELECT DISTINCT categoria FROM posizioni')
    categorie = [row[0] for row in c.fetchall() if row[0]]
    
    c.execute('SELECT COUNT(*) FROM task WHERE completato = 0')
    task_aperti = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM task WHERE completato = 1')
    task_completati = c.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'prodotti': num_prodotti,
        'varianti': num_varianti,
        'posizioni': num_posizioni,
        'categorie': categorie,
        'task_aperti': task_aperti,
        'task_completati': task_completati
    })


@app.route('/api/prodotti')
def api_prodotti():
    search = request.args.get('search', '').strip()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    solo_task = request.args.get('solo_task', '') == '1'
    categoria = request.args.get('categoria', '').strip()

    conn = get_db()
    c = conn.cursor()

    offset = (page - 1) * per_page

    # Se categoria specificata, filtra per categoria
    if categoria and categoria != 'Tutto':
        if categoria == 'SENZA_CATEGORIA':
            # Prodotti senza categoria (non hanno posizione assegnata, o posizione senza categoria)
            c.execute('''
                SELECT p.*, COUNT(v.codice) as num_varianti, pos.posizione,
                       (SELECT COUNT(*) FROM task t WHERE t.prodotto_id = p.id AND t.completato = 0) as task_aperti,
                       pos.categoria
                FROM prodotti p
                LEFT JOIN varianti v ON p.id = v.prodotto_id
                LEFT JOIN posizioni pos ON p.codice_principale = pos.codice
                WHERE pos.categoria IS NULL OR pos.categoria = ''
                GROUP BY p.id
                ORDER BY p.codice_principale ASC
                LIMIT ? OFFSET ?
            ''', (per_page, offset))
            prodotti = [dict(row) for row in c.fetchall()]

            c.execute('''
                SELECT COUNT(DISTINCT p.id) FROM prodotti p
                LEFT JOIN posizioni pos ON p.codice_principale = pos.codice
                WHERE pos.categoria IS NULL OR pos.categoria = ''
            ''')
            total = c.fetchone()[0]
        else:
            c.execute('''
                SELECT p.*, COUNT(v.codice) as num_varianti, pos.posizione,
                       (SELECT COUNT(*) FROM task t WHERE t.prodotto_id = p.id AND t.completato = 0) as task_aperti,
                       pos.categoria
                FROM prodotti p
                LEFT JOIN varianti v ON p.id = v.prodotto_id
                INNER JOIN posizioni pos ON p.codice_principale = pos.codice
                WHERE pos.categoria = ?
                GROUP BY p.id
                ORDER BY pos.posizione ASC NULLS LAST, p.titolo
                LIMIT ? OFFSET ?
            ''', (categoria, per_page, offset))
            prodotti = [dict(row) for row in c.fetchall()]

            c.execute('SELECT COUNT(*) FROM posizioni WHERE categoria = ?', (categoria,))
            total = c.fetchone()[0]

        conn.close()
        return jsonify({
            'prodotti': prodotti,
            'page': page,
            'pages': (total + per_page - 1) // per_page,
            'total': total,
            'categoria': categoria
        })

    if solo_task:
        # Solo prodotti con task aperti - ordinati per posizione
        query = '''
            SELECT DISTINCT p.*, COUNT(v.codice) as num_varianti, pos.posizione,
                   (SELECT COUNT(*) FROM task t WHERE t.prodotto_id = p.id AND t.completato = 0) as task_aperti
            FROM prodotti p
            LEFT JOIN varianti v ON p.id = v.prodotto_id
            LEFT JOIN posizioni pos ON p.codice_principale = pos.codice
            INNER JOIN task t ON p.id = t.prodotto_id AND t.completato = 0
        '''
        if search:
            query += " WHERE p.titolo LIKE ? OR p.codice_principale LIKE ?"
            query += " GROUP BY p.id ORDER BY pos.posizione ASC NULLS LAST, p.titolo LIMIT ? OFFSET ?"
            c.execute(query, (f'%{search}%', f'%{search}%', per_page, offset))
        else:
            query += " GROUP BY p.id ORDER BY pos.posizione ASC NULLS LAST, p.titolo LIMIT ? OFFSET ?"
            c.execute(query, (per_page, offset))
    else:
        # Query ottimizzata: LEFT JOIN invece di subquery correlata
        if search:
            c.execute('''
                SELECT p.*, COUNT(DISTINCT v.codice) as num_varianti, pos.posizione,
                       COALESCE(t_count.task_aperti, 0) as task_aperti
                FROM prodotti p
                LEFT JOIN varianti v ON p.id = v.prodotto_id
                LEFT JOIN posizioni pos ON p.codice_principale = pos.codice
                LEFT JOIN (
                    SELECT prodotto_id, COUNT(*) as task_aperti
                    FROM task WHERE completato = 0
                    GROUP BY prodotto_id
                ) t_count ON p.id = t_count.prodotto_id
                WHERE p.titolo LIKE ? OR p.codice_principale LIKE ?
                GROUP BY p.id
                ORDER BY pos.posizione ASC NULLS LAST, p.titolo
                LIMIT ? OFFSET ?
            ''', (f'%{search}%', f'%{search}%', per_page, offset))
        else:
            c.execute('''
                SELECT p.*, COUNT(DISTINCT v.codice) as num_varianti, pos.posizione,
                       COALESCE(t_count.task_aperti, 0) as task_aperti
                FROM prodotti p
                LEFT JOIN varianti v ON p.id = v.prodotto_id
                LEFT JOIN posizioni pos ON p.codice_principale = pos.codice
                LEFT JOIN (
                    SELECT prodotto_id, COUNT(*) as task_aperti
                    FROM task WHERE completato = 0
                    GROUP BY prodotto_id
                ) t_count ON p.id = t_count.prodotto_id
                GROUP BY p.id
                ORDER BY pos.posizione ASC NULLS LAST, p.titolo
                LIMIT ? OFFSET ?
            ''', (per_page, offset))
    
    prodotti = [dict(row) for row in c.fetchall()]
    
    c.execute('SELECT COUNT(*) FROM prodotti')
    total = c.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'prodotti': prodotti,
        'total': total,
        'page': page,
        'pages': (total + per_page - 1) // per_page
    })


@app.route('/api/prodotto/<codice>')
def api_prodotto(codice):
    conn = get_db()
    c = conn.cursor()

    # Cerca per codice_principale o per id numerico
    c.execute('''
        SELECT p.*, pos.posizione AS posizione, pos.categoria AS pos_categoria
        FROM prodotti p
        LEFT JOIN posizioni pos ON p.codice_principale = pos.codice
        WHERE p.codice_principale = ? OR p.id = ?
    ''', (codice, codice))
    row = c.fetchone()

    if not row:
        conn.close()
        return jsonify({'error': 'Non trovato'}), 404

    prodotto = dict(row)
    # Aggiungi categoria dalla tabella posizioni
    prodotto['categoria'] = prodotto.pop('pos_categoria', None)
    prodotto_id = prodotto['id']

    c.execute('SELECT * FROM varianti WHERE prodotto_id = ? ORDER BY ordine', (prodotto_id,))
    prodotto['varianti'] = [dict(row) for row in c.fetchall()]

    c.execute('SELECT * FROM task WHERE prodotto_id = ? ORDER BY completato, data_creazione DESC', (prodotto_id,))
    prodotto['task'] = [dict(row) for row in c.fetchall()]
    
    conn.close()
    
    return jsonify(prodotto)


@app.route('/api/prodotto/<codice>', methods=['PUT'])
def api_update_prodotto(codice):
    data = request.json
    utente = data.get('utente', 'web')

    conn = get_db()
    c = conn.cursor()

    # Ottieni valori precedenti per il log (cerca per codice_principale o id)
    c.execute('SELECT * FROM prodotti WHERE codice_principale = ? OR id = ?', (codice, codice))
    prodotto_old = c.fetchone()
    if not prodotto_old:
        conn.close()
        return jsonify({'error': 'Prodotto non trovato'}), 404

    id = prodotto_old['id']  # Usa l'id numerico per gli update

    prodotto_old = dict(prodotto_old)
    codice_principale = prodotto_old['codice_principale']

    # Campi da aggiornare con log
    campi_log = ['titolo', 'descrizione', 'immagine', 'logo', 'icona1', 'icona2',
                 'icona3', 'icona4', 'template', 'scala_foto', 'stato',
                 'verificato_catalogo', 'catalogo', 'doppia_colonna']

    for campo in campi_log:
        if campo in data and data[campo] is not None:
            valore_nuovo = data[campo]
            valore_old = prodotto_old.get(campo)
            if str(valore_nuovo) != str(valore_old) if valore_old else valore_nuovo:
                log_modifica(conn, id, codice_principale, campo, valore_old, valore_nuovo, utente)

    # Update base fields (inclusi nuovi campi v4: stato, verificato_catalogo, catalogo, doppia_colonna)
    c.execute('''
        UPDATE prodotti
        SET titolo = COALESCE(?, titolo),
            descrizione = COALESCE(?, descrizione),
            immagine = COALESCE(?, immagine),
            logo = COALESCE(?, logo),
            icona1 = COALESCE(?, icona1),
            icona2 = COALESCE(?, icona2),
            icona3 = COALESCE(?, icona3),
            icona4 = COALESCE(?, icona4),
            template = COALESCE(?, template),
            scala_foto = COALESCE(?, scala_foto),
            stato = COALESCE(?, stato),
            verificato_catalogo = COALESCE(?, verificato_catalogo),
            catalogo = COALESCE(?, catalogo),
            doppia_colonna = COALESCE(?, doppia_colonna),
            data_modifica = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (data.get('titolo'), data.get('descrizione'), data.get('immagine'),
          data.get('logo'), data.get('icona1'), data.get('icona2'), data.get('icona3'), data.get('icona4'),
          data.get('template'), data.get('scala_foto'),
          data.get('stato'), data.get('verificato_catalogo'), data.get('catalogo'),
          data.get('doppia_colonna'), id))

    # Gestisci posizione e categoria
    posizione = data.get('posizione')
    categoria = data.get('categoria')

    # Ottieni valori vecchi
    c.execute('SELECT posizione, categoria FROM posizioni WHERE codice = ?', (codice_principale,))
    pos_old = c.fetchone()
    pos_old_val = pos_old[0] if pos_old else None
    cat_old_val = pos_old[1] if pos_old else None

    # Log modifiche
    if posizione is not None and (str(posizione) != str(pos_old_val) if pos_old_val else posizione):
        log_modifica(conn, id, codice_principale, 'posizione', pos_old_val, posizione, utente)
    if categoria is not None and categoria != cat_old_val:
        log_modifica(conn, id, codice_principale, 'categoria', cat_old_val, categoria, utente)

    # Aggiorna/inserisci nella tabella posizioni
    if posizione is not None or categoria is not None:
        # Usa valori esistenti se non passati
        new_posizione = posizione if posizione is not None else pos_old_val
        new_categoria = categoria if categoria is not None else cat_old_val

        if new_posizione and new_categoria:
            # Verifica se la posizione è già occupata nella stessa categoria
            c.execute('''
                SELECT codice FROM posizioni
                WHERE categoria = ? AND posizione = ? AND codice != ?
            ''', (new_categoria, new_posizione, codice_principale))
            conflitto = c.fetchone()

            if conflitto:
                # Sposta tutti i prodotti dalla posizione target in giù di 1
                c.execute('''
                    UPDATE posizioni
                    SET posizione = posizione + 1
                    WHERE categoria = ? AND posizione >= ? AND codice != ?
                    ORDER BY posizione DESC
                ''', (new_categoria, new_posizione, codice_principale))

            # Inserisci o aggiorna
            c.execute('INSERT OR REPLACE INTO posizioni (codice, posizione, categoria) VALUES (?, ?, ?)',
                     (codice_principale, new_posizione, new_categoria))
        elif new_posizione or new_categoria:
            # Solo uno dei due - inserisci comunque
            c.execute('INSERT OR REPLACE INTO posizioni (codice, posizione, categoria) VALUES (?, ?, ?)',
                     (codice_principale, new_posizione, new_categoria))
        else:
            # Rimuovi se entrambi vuoti
            c.execute('DELETE FROM posizioni WHERE codice = ?', (codice_principale,))

    conn.commit()
    conn.close()

    return jsonify({'success': True})


@app.route('/api/prodotto', methods=['POST'])
def api_create_prodotto():
    """Crea un nuovo prodotto da zero"""
    data = request.json
    
    codice_principale = data.get('codice_principale', '').strip()
    if not codice_principale:
        return jsonify({'error': 'Codice principale obbligatorio'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    # Controlla se esiste già
    c.execute('SELECT id FROM prodotti WHERE codice_principale = ?', (codice_principale,))
    if c.fetchone():
        conn.close()
        return jsonify({'error': f'Codice {codice_principale} già esistente'}), 400
    
    titolo = data.get('titolo', '').strip() or codice_principale
    descrizione = data.get('descrizione', '').strip()
    posizione = data.get('posizione')
    
    c.execute('''
        INSERT INTO prodotti (codice_principale, titolo, descrizione, fonte_file)
        VALUES (?, ?, ?, ?)
    ''', (codice_principale, titolo, descrizione, 'MANUALE'))
    
    prodotto_id = c.lastrowid
    
    # Se c'è posizione, salvala
    if posizione:
        c.execute('INSERT OR REPLACE INTO posizioni (codice, posizione) VALUES (?, ?)', 
                  (codice_principale, posizione))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'id': prodotto_id})


@app.route('/api/prodotto/<int:id>', methods=['DELETE'])
def api_delete_prodotto(id):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM varianti WHERE prodotto_id = ?', (id,))
    c.execute('DELETE FROM task WHERE prodotto_id = ?', (id,))
    c.execute('DELETE FROM prodotti WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/variante/<codice>', methods=['PUT'])
def api_update_variante(codice):
    data = request.json
    conn = get_db()
    c = conn.cursor()

    # Supporta aggiornamenti parziali - aggiorna solo i campi forniti
    updates = []
    params = []
    for field in ['modello', 'um', 'mv', 'cf', 'listino']:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])

    if updates:
        params.append(codice)
        c.execute(f"UPDATE varianti SET {', '.join(updates)} WHERE codice = ?", params)
        conn.commit()

    conn.close()
    return jsonify({'success': True})


@app.route('/api/variante/<codice>', methods=['DELETE'])
def api_delete_variante(codice):
    """Elimina una variante. Se è la principale, la seconda diventa principale."""
    conn = get_db()
    c = conn.cursor()

    # Trova il prodotto a cui appartiene questa variante
    c.execute('SELECT prodotto_id FROM varianti WHERE codice = ?', (codice,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Variante non trovata'}), 404

    prodotto_id = row[0]

    # Verifica se questa variante è il codice_principale del prodotto
    c.execute('SELECT codice_principale FROM prodotti WHERE id = ?', (prodotto_id,))
    prod_row = c.fetchone()

    if prod_row and prod_row[0] == codice:
        # Questa è la variante principale, trova la prossima
        c.execute('''
            SELECT codice FROM varianti
            WHERE prodotto_id = ? AND codice != ?
            ORDER BY codice ASC LIMIT 1
        ''', (prodotto_id, codice))
        next_var = c.fetchone()

        if next_var:
            # Aggiorna il codice_principale al prossimo codice
            c.execute('UPDATE prodotti SET codice_principale = ? WHERE id = ?',
                     (next_var[0], prodotto_id))
        else:
            # Non ci sono altre varianti, elimina tutto il prodotto
            c.execute('DELETE FROM varianti WHERE prodotto_id = ?', (prodotto_id,))
            c.execute('DELETE FROM task WHERE prodotto_id = ?', (prodotto_id,))
            c.execute('DELETE FROM prodotti WHERE id = ?', (prodotto_id,))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'product_deleted': True})

    # Elimina la variante
    c.execute('DELETE FROM varianti WHERE codice = ?', (codice,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/prodotto_by_codice/<codice>', methods=['DELETE'])
def api_delete_prodotto_by_codice(codice):
    """Elimina completamente un prodotto e tutte le sue varianti tramite codice_principale"""
    conn = get_db()
    c = conn.cursor()

    # Trova l'id del prodotto
    c.execute('SELECT id FROM prodotti WHERE codice_principale = ?', (codice,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Prodotto non trovato'}), 404

    prodotto_id = row[0]

    # Elimina tutto
    c.execute('DELETE FROM varianti WHERE prodotto_id = ?', (prodotto_id,))
    c.execute('DELETE FROM task WHERE prodotto_id = ?', (prodotto_id,))
    c.execute('DELETE FROM posizioni WHERE codice = ?', (codice,))
    c.execute('DELETE FROM prodotti WHERE id = ?', (prodotto_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True})


@app.route('/api/posizioni/bulk_update', methods=['POST'])
def api_posizioni_bulk_update():
    """Aggiorna posizioni in bulk per una categoria"""
    data = request.json
    token = data.get('token')
    if token != DEPLOY_TOKEN:
        return jsonify({'error': 'Token non valido'}), 403

    categoria = data.get('categoria')
    posizioni = data.get('posizioni', [])  # Lista di {codice, posizione}

    if not categoria or not posizioni:
        return jsonify({'error': 'Categoria e posizioni richieste'}), 400

    conn = get_db()
    c = conn.cursor()

    # Prima elimina le posizioni esistenti per questa categoria (tranne Tutto)
    if categoria != 'Tutto':
        c.execute('DELETE FROM posizioni WHERE categoria = ?', (categoria,))

    # Inserisce le nuove posizioni
    imported = 0
    for pos in posizioni:
        try:
            c.execute('''
                INSERT OR REPLACE INTO posizioni (codice, posizione, categoria)
                VALUES (?, ?, ?)
            ''', (pos['codice'], pos['posizione'], categoria))
            imported += 1
        except Exception as e:
            print(f"Errore inserimento {pos}: {e}")

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'categoria': categoria,
        'imported': imported
    })


@app.route('/api/variante/<codice>/toggle_stampa', methods=['POST'])
def api_toggle_stampa(codice):
    """Toggle flag escludi_stampa per una variante"""
    conn = get_db()
    c = conn.cursor()
    
    # Leggi valore attuale
    c.execute('SELECT escludi_stampa FROM varianti WHERE codice = ?', (codice,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Variante non trovata'}), 404
    
    # Toggle: se è 1 diventa 0, se è 0 o NULL diventa 1
    current = row[0] or 0
    new_value = 0 if current == 1 else 1
    
    c.execute('UPDATE varianti SET escludi_stampa = ? WHERE codice = ?', (new_value, codice))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'escludi_stampa': new_value})


@app.route('/api/variante', methods=['POST'])
def api_add_variante():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    
    codice = data.get('codice', '').strip()
    
    if not codice:
        conn.close()
        return jsonify({'error': 'Codice obbligatorio'}), 400
    
    # Controlla se esiste già
    c.execute('''
        SELECT v.codice, p.titolo, p.codice_principale 
        FROM varianti v 
        JOIN prodotti p ON v.prodotto_id = p.id 
        WHERE v.codice = ?
    ''', (codice,))
    existing = c.fetchone()
    
    if existing:
        conn.close()
        return jsonify({'error': f'Codice {codice} già esistente nel prodotto: {existing["codice_principale"]} - {existing["titolo"]}'}), 400
    
    c.execute('SELECT MAX(ordine) FROM varianti WHERE prodotto_id = ?', (data.get('prodotto_id'),))
    max_ord = c.fetchone()[0] or 0
    
    c.execute('''
        INSERT INTO varianti (codice, prodotto_id, modello, um, mv, cf, listino, ordine)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (codice, data.get('prodotto_id'), data.get('modello'),
          data.get('um'), data.get('mv'), data.get('cf'), data.get('listino'), max_ord + 1))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/varianti/<codice>')
def api_varianti(codice):
    """Ritorna le varianti di un prodotto dato il codice principale"""
    conn = get_db()
    c = conn.cursor()

    # Prima trova l'ID del prodotto
    c.execute('SELECT id FROM prodotti WHERE codice_principale = ?', (codice,))
    row = c.fetchone()

    if not row:
        conn.close()
        return jsonify({'varianti': [], 'error': 'Prodotto non trovato'})

    prodotto_id = row['id']

    # Prendi le varianti
    c.execute('''
        SELECT * FROM varianti
        WHERE prodotto_id = ?
        ORDER BY ordine, codice
    ''', (prodotto_id,))

    varianti = [dict(row) for row in c.fetchall()]
    conn.close()

    return jsonify({'varianti': varianti, 'count': len(varianti)})


@app.route('/api/prodotto/<int:prodotto_id>/ordine_varianti', methods=['POST'])
def api_ordine_varianti(prodotto_id):
    """Aggiorna ordine delle varianti tramite drag & drop"""
    data = request.json
    ordine_list = data.get('ordine', [])
    
    conn = get_db()
    c = conn.cursor()
    
    for item in ordine_list:
        c.execute('UPDATE varianti SET ordine = ? WHERE codice = ?', 
                  (item['ordine'], item['codice']))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})


# ============================================
# TASK API
# ============================================

@app.route('/api/task', methods=['POST'])
def api_add_task():
    """Aggiungi task"""
    data = request.json
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''
        INSERT INTO task (prodotto_id, campo, nota, assegnato_da)
        VALUES (?, ?, ?, ?)
    ''', (data.get('prodotto_id'), data.get('campo'), data.get('nota', ''), data.get('assegnato_da', '')))
    
    task_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'id': task_id})


@app.route('/api/task/<int:id>', methods=['PUT'])
def api_update_task(id):
    """Aggiorna task (completa/modifica)"""
    data = request.json
    conn = get_db()
    c = conn.cursor()
    
    if 'completato' in data:
        c.execute('''
            UPDATE task SET completato = ?, completato_da = ?, 
            data_completamento = CURRENT_TIMESTAMP WHERE id = ?
        ''', (1 if data['completato'] else 0, data.get('completato_da', ''), id))
    
    if 'nota' in data:
        c.execute('UPDATE task SET nota = ? WHERE id = ?', (data['nota'], id))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/task/<int:id>', methods=['DELETE'])
def api_delete_task(id):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM task WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/task_summary')
def api_task_summary():
    """Riepilogo task aperti"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''
        SELECT t.*, p.codice_principale, p.titolo
        FROM task t
        JOIN prodotti p ON t.prodotto_id = p.id
        WHERE t.completato = 0
        ORDER BY t.data_creazione DESC
        LIMIT 100
    ''')
    
    tasks = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return jsonify(tasks)


# ============================================
# BRAND API
# ============================================

@app.route('/api/brands')
def api_brands():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT DISTINCT logo FROM prodotti WHERE logo IS NOT NULL AND logo != ""')
    brands = [row[0] for row in c.fetchall()]
    conn.close()
    return jsonify(brands)


# ============================================
# FILE API
# ============================================

@app.route('/api/import', methods=['POST'])
def api_import():
    if 'file' not in request.files:
        return jsonify({'error': 'Nessun file'}), 400
    
    file = request.files['file']
    filename = secure_filename(file.filename)
    filepath = UPLOAD_FOLDER / filename
    file.save(str(filepath))
    
    try:
        result = import_csv_to_db(filepath, filename)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/import_posizioni', methods=['POST'])
def api_import_posizioni():
    """Importa file Excel/CSV con posizioni"""
    if 'file' not in request.files:
        return jsonify({'error': 'Nessun file'}), 400
    
    file = request.files['file']
    categoria = request.form.get('categoria', 'default')
    
    if file.filename == '':
        return jsonify({'error': 'Nessun file selezionato'}), 400
    
    filename = secure_filename(file.filename)
    filepath = UPLOAD_FOLDER / filename
    file.save(str(filepath))
    
    try:
        importati = import_posizioni(str(filepath), categoria)
        return jsonify({'importati': importati, 'categoria': categoria})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload_foto/<int:prodotto_id>', methods=['POST'])
def api_upload_foto(prodotto_id):
    if 'file' not in request.files:
        return jsonify({'error': 'Nessun file'}), 400
    
    file = request.files['file']
    filename = secure_filename(file.filename)
    filepath = FOTO_FOLDER / filename
    file.save(str(filepath))


    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE prodotti SET immagine = ? WHERE id = ?', (filename, prodotto_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'filename': filename})


# === API per gestione immagini custom e scala ===

@app.route('/api/upload-image', methods=['POST'])
def api_upload_image():
    """Upload immagine personalizzata per un prodotto"""
    if 'image' not in request.files:
        return jsonify({'error': 'Nessun file'}), 400

    codice = request.form.get('codice')
    if not codice:
        return jsonify({'error': 'Codice prodotto mancante'}), 400

    file = request.files['image']
    if not file.filename:
        return jsonify({'error': 'File non valido'}), 400

    # Genera nome file univoco
    ext = Path(file.filename).suffix.lower() or '.jpg'
    filename = f"custom_{codice}_{int(time.time())}{ext}"
    filepath = FOTO_FOLDER / filename

    try:
        # Salva l'immagine
        img = Image.open(file)
        img = img.convert('RGB')
        img.save(str(filepath), 'JPEG', quality=90)

        # Aggiorna database
        conn = get_db()
        c = conn.cursor()
        c.execute('''
            UPDATE prodotti
            SET immagine_custom = ?, immagine = ?
            WHERE codice_principale = ?
        ''', (filename, filename, codice))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/reset-image', methods=['POST'])
def api_reset_image():
    """Ripristina immagine originale del prodotto"""
    data = request.json
    codice = data.get('codice')

    if not codice:
        return jsonify({'error': 'Codice prodotto mancante'}), 400

    conn = get_db()
    c = conn.cursor()

    # Trova l'immagine originale (quella senza custom_)
    c.execute('SELECT immagine, immagine_custom FROM prodotti WHERE codice_principale = ?', (codice,))
    row = c.fetchone()

    if not row:
        conn.close()
        return jsonify({'error': 'Prodotto non trovato'}), 404

    # Cerca l'immagine originale del codice
    immagine_originale = None
    for ext in ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG', '.jfif']:
        for pattern in [f"{codice}{ext}", f"P{codice}*{ext}"]:
            matches = list(FOTO_FOLDER.glob(pattern))
            # Escludi le custom
            matches = [m for m in matches if not m.name.startswith('custom_')]
            if matches:
                immagine_originale = matches[0].name
                break
        if immagine_originale:
            break

    # Reset
    c.execute('''
        UPDATE prodotti
        SET immagine_custom = NULL, immagine = ?, scala_immagine = 100
        WHERE codice_principale = ?
    ''', (immagine_originale, codice))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'immagine_originale': immagine_originale})


@app.route('/api/save-image-settings', methods=['POST'])
def api_save_image_settings():
    """Salva scala e offset dell'immagine"""
    data = request.json
    codice = data.get('codice')
    scala = data.get('scala', 100)
    offset_x = data.get('offset_x', 0)
    offset_y = data.get('offset_y', 0)

    if not codice:
        return jsonify({'error': 'Codice prodotto mancante'}), 400

    # Limita valori
    scala = max(50, min(150, int(scala)))
    offset_x = max(-50, min(50, int(offset_x)))
    offset_y = max(-50, min(50, int(offset_y)))

    conn = get_db()
    c = conn.cursor()
    c.execute('''UPDATE prodotti SET scala_immagine = ?, offset_x = ?, offset_y = ?
                 WHERE codice_principale = ?''', (scala, offset_x, offset_y, codice))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'scala': scala, 'offset_x': offset_x, 'offset_y': offset_y})


@app.route('/api/upload_logo/<int:prodotto_id>', methods=['POST'])
def api_upload_logo(prodotto_id):
    if 'file' not in request.files:
        return jsonify({'error': 'Nessun file'}), 400
    
    file = request.files['file']
    filename = secure_filename(file.filename)
    filepath = LOGO_FOLDER / filename
    file.save(str(filepath))


    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE prodotti SET logo = ? WHERE id = ?', (filename, prodotto_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'filename': filename})


@app.route('/api/prodotto/<int:prodotto_id>/icona/<int:num>', methods=['POST'])
def api_upload_icona(prodotto_id, num):
    """Upload icona 1, 2, 3 o 4"""
    if num not in [1, 2, 3, 4]:
        return jsonify({'error': 'Numero icona non valido'}), 400
    
    if 'file' not in request.files:
        return jsonify({'error': 'Nessun file'}), 400
    
    file = request.files['file']
    filename = secure_filename(file.filename)
    filepath = ICONE_FOLDER / filename
    file.save(str(filepath))
    
    conn = get_db()
    c = conn.cursor()
    c.execute(f'UPDATE prodotti SET icona{num} = ? WHERE id = ?', (filename, prodotto_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'filename': filename})


@app.route('/api/prodotto/<int:prodotto_id>/delete_image/<tipo>', methods=['DELETE'])
def api_delete_image(prodotto_id, tipo):
    """Cancella immagine, logo o icona"""
    valid_types = ['immagine', 'logo', 'icona1', 'icona2', 'icona3', 'icona4']
    if tipo not in valid_types:
        return jsonify({'error': 'Tipo non valido'}), 400
    
    conn = get_db()
    c = conn.cursor()
    c.execute(f'UPDATE prodotti SET {tipo} = NULL WHERE id = ?', (prodotto_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})


@app.route('/api/prodotto/<int:prodotto_id>/toggle_controllato', methods=['POST'])
def api_toggle_controllato(prodotto_id):
    """Toggle stato controllato del prodotto"""
    conn = get_db()
    c = conn.cursor()
    
    # Ottieni stato attuale
    c.execute('SELECT controllato FROM prodotti WHERE id = ?', (prodotto_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Prodotto non trovato'}), 404
    
    # Toggle
    nuovo_stato = 0 if row['controllato'] else 1
    c.execute('UPDATE prodotti SET controllato = ? WHERE id = ?', (nuovo_stato, prodotto_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'controllato': nuovo_stato})


@app.route('/api/foto/<filename>')
def api_foto(filename):
    # Cerca il file esatto
    filepath = FOTO_FOLDER / filename
    if filepath.exists():
        return send_from_directory(str(FOTO_FOLDER), filename)

    # Cerca con case-insensitive
    filename_lower = filename.lower()
    for f in FOTO_FOLDER.iterdir():
        if f.name.lower() == filename_lower:
            return send_from_directory(str(FOTO_FOLDER), f.name)

    # Non trovato
    return '', 404


@app.route('/api/logos')
def api_logos():
    """Lista tutti i loghi disponibili"""
    logos = []
    if LOGO_FOLDER.exists():
        for f in sorted(LOGO_FOLDER.iterdir()):
            if f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                logos.append(f.name)
    return jsonify({'logos': logos})


@app.route('/api/logo/<filename>')
def api_logo(filename):
    return send_from_directory(str(LOGO_FOLDER), filename)


@app.route('/api/icona/<filename>')
def api_icona(filename):
    return send_from_directory(str(ICONE_FOLDER), filename)


# ============================================
# BOX GENERATION
# ============================================

@app.route('/api/box/<int:id>')
def api_box(id):
    template = request.args.get('template', 'corporate')
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT * FROM prodotti WHERE id = ?', (id,))
    prodotto = c.fetchone()
    
    if not prodotto:
        conn.close()
        return jsonify({'error': 'Non trovato'}), 404
    
    prodotto = dict(prodotto)
    
    # Escludi varianti con flag escludi_stampa
    c.execute('SELECT * FROM varianti WHERE prodotto_id = ? AND (escludi_stampa = 0 OR escludi_stampa IS NULL) ORDER BY ordine', (id,))
    varianti = [dict(row) for row in c.fetchall()]
    
    conn.close()
    
    img = box_generator.generate(prodotto, varianti, template)
    img_base64 = box_generator.to_base64(img)
    
    return jsonify({'image': f'data:image/png;base64,{img_base64}'})


@app.route('/api/box/<int:id>/download')
def api_box_download(id):
    """Scarica box - nome file = POSIZIONE_CODICE.jpg, salva in output_box/"""
    template = request.args.get('template', 'corporate')
    
    conn = get_db()
    c = conn.cursor()
    
    # Prendi prodotto CON posizione
    c.execute('''
        SELECT p.*, pos.posizione
        FROM prodotti p
        LEFT JOIN posizioni pos ON p.codice_principale = pos.codice
        WHERE p.id = ?
    ''', (id,))
    prodotto = c.fetchone()
    
    if not prodotto:
        conn.close()
        return jsonify({'error': 'Non trovato'}), 404
    
    prodotto = dict(prodotto)
    
    # Escludi varianti con flag escludi_stampa
    c.execute('SELECT * FROM varianti WHERE prodotto_id = ? AND (escludi_stampa = 0 OR escludi_stampa IS NULL) ORDER BY ordine', (id,))
    varianti = [dict(row) for row in c.fetchall()]
    
    conn.close()
    
    img = box_generator.generate(prodotto, varianti, template)
    
    # Converti in RGB se necessario
    if img.mode == 'RGBA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    
    # Nome file: POSIZIONE_CODICE.jpg (se ha posizione) altrimenti solo CODICE.jpg
    posizione = prodotto.get('posizione')
    codice = prodotto['codice_principale']
    if posizione:
        filename = f"{posizione}_{codice}.jpg"
    else:
        filename = f"{codice}.jpg"
    
    # Salva in cartella output_box/
    filepath = OUTPUT_FOLDER / filename
    img.save(str(filepath), 'JPEG', quality=95, optimize=True)
    
    # Restituisci il file dalla cartella
    return send_file(str(filepath), mimetype='image/jpeg', as_attachment=True, download_name=filename)


@app.route('/api/box/<int:id>/save', methods=['POST'])
def api_box_save(id):
    """Salva box in output_box/ senza scaricarlo (chiamato dopo modifiche)"""
    data = request.json or {}
    template = data.get('template', 'corporate')
    
    conn = get_db()
    c = conn.cursor()
    
    # Prendi prodotto CON posizione
    c.execute('''
        SELECT p.*, pos.posizione
        FROM prodotti p
        LEFT JOIN posizioni pos ON p.codice_principale = pos.codice
        WHERE p.id = ?
    ''', (id,))
    prodotto = c.fetchone()
    
    if not prodotto:
        conn.close()
        return jsonify({'error': 'Non trovato'}), 404
    
    prodotto = dict(prodotto)
    
    # Escludi varianti con flag escludi_stampa
    c.execute('SELECT * FROM varianti WHERE prodotto_id = ? AND (escludi_stampa = 0 OR escludi_stampa IS NULL) ORDER BY ordine', (id,))
    varianti = [dict(row) for row in c.fetchall()]
    
    conn.close()
    
    if not varianti:
        return jsonify({'saved': False, 'reason': 'Nessuna variante'})
    
    img = box_generator.generate(prodotto, varianti, template)
    
    # Converti in RGB
    if img.mode == 'RGBA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    
    # Nome file: POSIZIONE_CODICE.jpg
    posizione = prodotto.get('posizione')
    codice = prodotto['codice_principale']
    filename = f"{posizione}_{codice}.jpg" if posizione else f"{codice}.jpg"
    
    # Salva
    filepath = OUTPUT_FOLDER / filename
    img.save(str(filepath), 'JPEG', quality=95, optimize=True)
    
    return jsonify({'saved': True, 'filename': filename, 'path': str(filepath)})


@app.route('/api/export_catalogo', methods=['POST'])
def api_export_catalogo():
    """Esporta catalogo con naming POSIZIONE_CODICE.jpg"""
    data = request.json or {}
    categoria = data.get('categoria', 'default')
    template = data.get('template', 'corporate')
    
    conn = get_db()
    c = conn.cursor()
    
    # Prendi prodotti con posizione per questa categoria
    c.execute('''
        SELECT p.*, pos.posizione
        FROM prodotti p
        INNER JOIN posizioni pos ON p.codice_principale = pos.codice
        WHERE pos.categoria = ?
        ORDER BY pos.posizione
    ''', (categoria,))
    
    prodotti = [dict(row) for row in c.fetchall()]
    
    if not prodotti:
        conn.close()
        return jsonify({'error': 'Nessun prodotto con posizione trovato per questa categoria'}), 404
    
    # Crea sottocartella per categoria
    export_path = EXPORT_FOLDER / categoria
    export_path.mkdir(exist_ok=True)
    
    exported = 0
    errors = []
    
    gen = BoxGenerator()
    
    for prod in prodotti:
        try:
            # Escludi varianti con flag escludi_stampa
            c.execute('SELECT * FROM varianti WHERE prodotto_id = ? AND (escludi_stampa = 0 OR escludi_stampa IS NULL) ORDER BY ordine', (prod['id'],))
            varianti = [dict(row) for row in c.fetchall()]
            
            if not varianti:
                continue
            
            img = gen.generate(prod, varianti, template)
            
            # Nome file: POSIZIONE_CODICE.jpg
            filename = f"{prod['posizione']}_{prod['codice_principale']}.jpg"
            filepath = export_path / filename
            
            gen.save_as_jpg(img, str(filepath))
            exported += 1
            
        except Exception as e:
            errors.append(f"{prod['codice_principale']}: {str(e)}")
    
    conn.close()
    
    return jsonify({
        'exported': exported,
        'errors': errors,
        'output_folder': str(export_path),
        'categoria': categoria
    })


@app.route('/api/save_all_boxes', methods=['POST'])
def api_save_all_boxes():
    """Salva tutti i box nella cartella output_box"""
    data = request.json or {}
    template = data.get('template', 'corporate')
    
    conn = get_db()
    c = conn.cursor()
    
    # Prendi tutti i prodotti CON posizione
    c.execute('''
        SELECT p.*, pos.posizione
        FROM prodotti p
        LEFT JOIN posizioni pos ON p.codice_principale = pos.codice
        ORDER BY pos.posizione ASC NULLS LAST, p.codice_principale
    ''')
    prodotti = [dict(row) for row in c.fetchall()]
    
    if not prodotti:
        conn.close()
        return jsonify({'error': 'Nessun prodotto trovato'}), 404
    
    saved = 0
    errors = []
    
    gen = BoxGenerator()
    
    for prod in prodotti:
        try:
            # Escludi varianti con flag escludi_stampa
            c.execute('SELECT * FROM varianti WHERE prodotto_id = ? AND (escludi_stampa = 0 OR escludi_stampa IS NULL) ORDER BY ordine', (prod['id'],))
            varianti = [dict(row) for row in c.fetchall()]
            
            if not varianti:
                continue
            
            img = gen.generate(prod, varianti, template)
            
            # Nome file: POSIZIONE_CODICE.jpg (stessa logica del salvataggio singolo)
            posizione = prod.get('posizione')
            codice = prod['codice_principale']
            filename = f"{posizione}_{codice}.jpg" if posizione else f"{codice}.jpg"
            filepath = OUTPUT_FOLDER / filename
            
            gen.save_as_jpg(img, str(filepath))
            saved += 1
            
        except Exception as e:
            errors.append(f"{prod['codice_principale']}: {str(e)}")
    
    conn.close()
    
    return jsonify({
        'saved': saved,
        'errors': errors,
        'output_folder': str(OUTPUT_FOLDER)
    })


@app.route('/api/reset_db', methods=['POST'])
def api_reset_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM varianti')
    c.execute('DELETE FROM prodotti')
    c.execute('DELETE FROM task')
    c.execute('DELETE FROM import_log')
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ============================================
# PREVIEW CATALOGO & PDF GENERATION (v4.0)
# ============================================

def calcola_altezza_box(num_varianti):
    """
    Calcola altezza box in pixel basata sul numero di varianti.
    Layout corporate: header + righe varianti + descrizione + strip
    Valori calibrati per 4-6 prodotti/pagina.
    """
    TOP_SECTION = 150      # Titolo + logo
    IMG_SECTION = 450      # Immagine + descrizione
    HEADER_ROW = 50        # Header tabella
    VAR_ROW = 35           # Riga per variante
    STRIP = 15             # Striscia verde in basso
    PADDING = 40           # Margini interni

    return TOP_SECTION + IMG_SECTION + HEADER_ROW + (num_varianti * VAR_ROW) + STRIP + PADDING


def impagina_dinamico(prodotti, conn, page_height=3400, col_width=1160, margin_top=60, row_gap=15):
    """
    Impagina i prodotti dinamicamente in base all'altezza reale dei box.
    Layout: 2 colonne, ordine di lettura standard (sinistra-destra, poi giù).
    Ritorna lista di pagine, ogni pagina è lista di prodotti con coordinate.
    """
    c = conn.cursor()

    # Pre-calcola altezze per tutti i prodotti CON UNA SOLA QUERY
    prod_ids = [prod['id'] for prod in prodotti]
    if prod_ids:
        placeholders = ','.join('?' * len(prod_ids))
        c.execute(f'''
            SELECT prodotto_id, COUNT(*) FROM varianti
            WHERE prodotto_id IN ({placeholders}) AND (escludi_stampa = 0 OR escludi_stampa IS NULL)
            GROUP BY prodotto_id
        ''', prod_ids)
        var_counts = {row[0]: row[1] for row in c.fetchall()}
    else:
        var_counts = {}

    prod_heights = []
    for prod in prodotti:
        num_var = var_counts.get(prod['id'], 1) or 1
        box_h = calcola_altezza_box(num_var)
        prod_heights.append((prod, box_h, num_var))

    pages = []
    current_page = []
    col1_y = margin_top
    col2_y = margin_top

    i = 0
    while i < len(prod_heights):
        prod, box_h, num_var = prod_heights[i]

        # Scegli la colonna con PIÙ SPAZIO DISPONIBILE (bilanciamento)
        # Se sono uguali, usa la sinistra (ordine lettura)
        fits_col0 = col1_y + box_h <= page_height
        fits_col1 = col2_y + box_h <= page_height

        if fits_col0 and fits_col1:
            # Entrambe hanno spazio - scegli quella con più spazio (y più basso)
            if col1_y <= col2_y:
                chosen_col = 0
            else:
                chosen_col = 1
        elif fits_col0:
            chosen_col = 0
        elif fits_col1:
            chosen_col = 1
        else:
            # Nessuna colonna ha spazio - nuova pagina
            if current_page:
                pages.append(current_page)
            current_page = []
            col1_y = margin_top
            col2_y = margin_top
            continue  # Riprova con la nuova pagina

        # Posiziona il prodotto nella colonna scelta
        if chosen_col == 0:
            prod['_col'] = 0
            prod['_y'] = col1_y
            prod['_h'] = box_h
            prod['_num_var'] = num_var
            current_page.append(prod)
            col1_y += box_h + row_gap
        else:
            prod['_col'] = 1
            prod['_y'] = col2_y
            prod['_h'] = box_h
            prod['_num_var'] = num_var
            current_page.append(prod)
            col2_y += box_h + row_gap

        i += 1

    # Ultima pagina
    if current_page:
        pages.append(current_page)

    # REDISTRIBUISCI SPAZIO: per ogni pagina, distribuisci lo spazio vuoto
    for page in pages:
        if not page:
            continue

        # Separa prodotti per colonna
        col0 = [p for p in page if p.get('_col') == 0]
        col1 = [p for p in page if p.get('_col') == 1]

        # Redistribuisci colonna sinistra
        if col0:
            total_h = sum(p['_h'] for p in col0)
            space_available = page_height - margin_top - total_h
            if len(col0) > 1 and space_available > 0:
                extra_gap = space_available // (len(col0))
                y = margin_top
                for p in col0:
                    p['_y'] = y
                    y += p['_h'] + row_gap + extra_gap

        # Redistribuisci colonna destra
        if col1:
            total_h = sum(p['_h'] for p in col1)
            space_available = page_height - margin_top - total_h
            if len(col1) > 1 and space_available > 0:
                extra_gap = space_available // (len(col1))
                y = margin_top
                for p in col1:
                    p['_y'] = y
                    y += p['_h'] + row_gap + extra_gap

    return pages


@app.route('/api/catalog/pages-dynamic')
def api_catalog_pages_dynamic():
    """
    Restituisce l'elenco delle pagine con impaginazione DINAMICA.
    Il numero di prodotti per pagina varia in base all'altezza dei box.
    """
    categoria = request.args.get('categoria', 'default')

    conn = get_db()
    c = conn.cursor()

    # Prendi prodotti ordinati per posizione
    c.execute('''
        SELECT p.*, pos.posizione, pos.categoria
        FROM prodotti p
        INNER JOIN posizioni pos ON p.codice_principale = pos.codice
        WHERE pos.categoria = ?
        ORDER BY pos.posizione
    ''', (categoria,))

    prodotti = [dict(row) for row in c.fetchall()]

    if not prodotti:
        conn.close()
        return jsonify({'error': 'Nessun prodotto trovato', 'categoria': categoria}), 404

    # Impagina dinamicamente
    pages = impagina_dinamico(prodotti, conn)

    conn.close()

    # Formatta output
    result_pages = []
    for i, page_prods in enumerate(pages):
        result_pages.append({
            'page_number': i + 1,
            'num_products': len(page_prods),
            'products': [{
                'id': p['id'],
                'codice_principale': p['codice_principale'],
                'titolo': p['titolo'],
                'posizione': p.get('posizione'),
                'col': p.get('_col', 0),
                'y': p.get('_y', 0),
                'height': p.get('_h', 500),
                'num_varianti': p.get('_num_var', 1)
            } for p in page_prods]
        })

    return jsonify({
        'total_products': len(prodotti),
        'total_pages': len(pages),
        'layout': 'dynamic',
        'categoria': categoria,
        'pages': result_pages
    })


@app.route('/api/catalog/page-dynamic/<int:page_num>')
def api_catalog_page_dynamic(page_num):
    """
    Genera un'immagine preview con impaginazione DINAMICA.
    I box sono posizionati in base alla loro altezza reale.
    """
    categoria = request.args.get('categoria', 'default')
    template = request.args.get('template', 'corporate')

    conn = get_db()
    c = conn.cursor()

    # Prendi prodotti ordinati per posizione
    c.execute('''
        SELECT p.*, pos.posizione
        FROM prodotti p
        INNER JOIN posizioni pos ON p.codice_principale = pos.codice
        WHERE pos.categoria = ?
        ORDER BY pos.posizione
    ''', (categoria,))

    all_products = [dict(row) for row in c.fetchall()]

    if not all_products:
        conn.close()
        return jsonify({'error': 'Nessun prodotto trovato'}), 404

    # Impagina dinamicamente
    pages = impagina_dinamico(all_products, conn)

    if page_num < 1 or page_num > len(pages):
        conn.close()
        return jsonify({'error': 'Pagina non trovata'}), 404

    page_products = pages[page_num - 1]

    # Dimensioni pagina A4 @300dpi
    PAGE_W = 2480
    PAGE_H = 3508
    MARGIN = 60
    COL_GAP = 40
    col_w = (PAGE_W - 2 * MARGIN - COL_GAP) // 2

    page_img = Image.new('RGB', (PAGE_W, PAGE_H), (255, 255, 255))

    # Pre-carica TUTTE le varianti per i prodotti della pagina in UNA query
    prod_ids = [prod['id'] for prod in page_products]
    if prod_ids:
        placeholders = ','.join('?' * len(prod_ids))
        c.execute(f'''
            SELECT * FROM varianti
            WHERE prodotto_id IN ({placeholders}) AND (escludi_stampa = 0 OR escludi_stampa IS NULL)
            ORDER BY prodotto_id, ordine
        ''', prod_ids)
        all_varianti = [dict(row) for row in c.fetchall()]
        # Raggruppa per prodotto_id
        varianti_map = {}
        for v in all_varianti:
            pid = v['prodotto_id']
            if pid not in varianti_map:
                varianti_map[pid] = []
            varianti_map[pid].append(v)
    else:
        varianti_map = {}

    # Genera e posiziona ogni box
    for prod in page_products:
        varianti = varianti_map.get(prod['id'], [])

        if varianti:
            box_img = box_generator.generate(prod, varianti, template)

            # Ridimensiona per colonna
            box_scaled = box_generator._contain(box_img, col_w, prod.get('_h', 1600))

            # Posiziona
            col = prod.get('_col', 0)
            x = MARGIN + col * (col_w + COL_GAP)
            y = prod.get('_y', MARGIN)

            if box_scaled:
                if box_scaled.mode == 'RGBA':
                    page_img.paste(box_scaled, (x, y), box_scaled)
                else:
                    page_img.paste(box_scaled, (x, y))

    conn.close()

    # Converti in base64
    buffer = io.BytesIO()
    page_img.save(buffer, format='JPEG', quality=85)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()

    return jsonify({
        'page_number': page_num,
        'total_pages': len(pages),
        'products_on_page': len(page_products),
        'layout': 'dynamic',
        'image': f'data:image/jpeg;base64,{img_base64}'
    })


@app.route('/api/catalog/pages')
def api_catalog_pages():
    """
    Restituisce l'elenco delle pagine del catalogo con i prodotti impaginati.
    Layout: 2 colonne per pagina A4
    """
    categoria = request.args.get('categoria', 'default')
    items_per_page = int(request.args.get('items_per_page', 4))  # 2 colonne x 2 righe default

    conn = get_db()
    c = conn.cursor()

    # Prendi prodotti ordinati per posizione
    c.execute('''
        SELECT p.*, pos.posizione, pos.categoria
        FROM prodotti p
        INNER JOIN posizioni pos ON p.codice_principale = pos.codice
        WHERE pos.categoria = ?
        ORDER BY pos.posizione
    ''', (categoria,))

    prodotti = [dict(row) for row in c.fetchall()]
    conn.close()

    # Dividi in pagine
    pages = []
    for i in range(0, len(prodotti), items_per_page):
        page_products = prodotti[i:i + items_per_page]
        pages.append({
            'page_number': len(pages) + 1,
            'products': page_products
        })

    return jsonify({
        'total_products': len(prodotti),
        'total_pages': len(pages),
        'items_per_page': items_per_page,
        'categoria': categoria,
        'pages': pages
    })


@app.route('/api/catalog/page/<int:page_num>')
def api_catalog_page_preview(page_num):
    """
    Genera un'immagine preview di una pagina del catalogo.
    Layout A4 con 2 colonne.
    """
    categoria = request.args.get('categoria', 'default')
    items_per_page = int(request.args.get('items_per_page', 4))
    template = request.args.get('template', 'corporate')

    conn = get_db()
    c = conn.cursor()

    # Prendi prodotti ordinati per posizione
    c.execute('''
        SELECT p.*, pos.posizione
        FROM prodotti p
        INNER JOIN posizioni pos ON p.codice_principale = pos.codice
        WHERE pos.categoria = ?
        ORDER BY pos.posizione
    ''', (categoria,))

    all_products = [dict(row) for row in c.fetchall()]

    # Calcola offset
    start_idx = (page_num - 1) * items_per_page
    end_idx = start_idx + items_per_page
    page_products = all_products[start_idx:end_idx]

    if not page_products:
        conn.close()
        return jsonify({'error': 'Pagina non trovata'}), 404

    # Pre-carica TUTTE le varianti per i prodotti della pagina
    prod_ids = [prod['id'] for prod in page_products]
    if prod_ids:
        placeholders = ','.join('?' * len(prod_ids))
        c.execute(f'''
            SELECT * FROM varianti
            WHERE prodotto_id IN ({placeholders}) AND (escludi_stampa = 0 OR escludi_stampa IS NULL)
            ORDER BY prodotto_id, ordine
        ''', prod_ids)
        all_varianti = [dict(row) for row in c.fetchall()]
        varianti_map = {}
        for v in all_varianti:
            pid = v['prodotto_id']
            if pid not in varianti_map:
                varianti_map[pid] = []
            varianti_map[pid].append(v)
    else:
        varianti_map = {}

    # Genera i box per ogni prodotto
    boxes = []
    for prod in page_products:
        varianti = varianti_map.get(prod['id'], [])
        if varianti:
            box_img = box_generator.generate(prod, varianti, template)
            boxes.append(box_img)

    conn.close()

    if not boxes:
        return jsonify({'error': 'Nessun box generato'}), 404

    # Crea pagina A4 (2480x3508 @ 300dpi)
    PAGE_W = 2480
    PAGE_H = 3508
    MARGIN = 60
    COL_GAP = 40
    ROW_GAP = 30

    # 2 colonne
    col_w = (PAGE_W - 2 * MARGIN - COL_GAP) // 2

    page_img = Image.new('RGB', (PAGE_W, PAGE_H), (255, 255, 255))

    # Posiziona i box
    for idx, box in enumerate(boxes):
        col = idx % 2
        row = idx // 2

        # Ridimensiona box per adattarlo alla colonna
        box_scaled = box_generator._contain(box, col_w, 1600)

        if box_scaled:
            x = MARGIN + col * (col_w + COL_GAP)
            y = MARGIN + row * (box_scaled.size[1] + ROW_GAP)

            if box_scaled.mode == 'RGBA':
                page_img.paste(box_scaled, (x, y), box_scaled)
            else:
                page_img.paste(box_scaled, (x, y))

    # Converti in base64
    buffer = io.BytesIO()
    page_img.save(buffer, format='JPEG', quality=85)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()

    return jsonify({
        'page_number': page_num,
        'total_pages': (len(all_products) + items_per_page - 1) // items_per_page,
        'products_on_page': len(page_products),
        'image': f'data:image/jpeg;base64,{img_base64}'
    })


@app.route('/api/catalog/pdf', methods=['POST'])
def api_generate_catalog_pdf():
    """
    Genera il PDF completo del catalogo con impaginazione DINAMICA.
    """
    data = request.json or {}
    categoria = data.get('categoria', 'default')
    template = data.get('template', 'corporate')

    conn = get_db()
    c = conn.cursor()

    # Prendi prodotti ordinati per posizione
    c.execute('''
        SELECT p.*, pos.posizione
        FROM prodotti p
        INNER JOIN posizioni pos ON p.codice_principale = pos.codice
        WHERE pos.categoria = ?
        ORDER BY pos.posizione
    ''', (categoria,))

    all_products = [dict(row) for row in c.fetchall()]

    if not all_products:
        conn.close()
        return jsonify({'error': 'Nessun prodotto trovato'}), 404

    # Usa impaginazione dinamica
    pages = impagina_dinamico(all_products, conn)

    # Pre-carica TUTTE le varianti per TUTTI i prodotti in UNA SOLA query
    all_prod_ids = [prod['id'] for prod in all_products]
    if all_prod_ids:
        placeholders = ','.join('?' * len(all_prod_ids))
        c.execute(f'''
            SELECT * FROM varianti
            WHERE prodotto_id IN ({placeholders}) AND (escludi_stampa = 0 OR escludi_stampa IS NULL)
            ORDER BY prodotto_id, ordine
        ''', all_prod_ids)
        all_varianti = [dict(row) for row in c.fetchall()]
        varianti_map = {}
        for v in all_varianti:
            pid = v['prodotto_id']
            if pid not in varianti_map:
                varianti_map[pid] = []
            varianti_map[pid].append(v)
    else:
        varianti_map = {}

    # Dimensioni pagina A4 @ 300dpi
    PAGE_W = 2480
    PAGE_H = 3508
    MARGIN = 60
    COL_GAP = 40
    col_w = (PAGE_W - 2 * MARGIN - COL_GAP) // 2

    pages_images = []

    # Genera tutte le pagine
    for page_num, page_products in enumerate(pages):
        # Crea pagina A4
        page_img = Image.new('RGB', (PAGE_W, PAGE_H), (255, 255, 255))

        # Genera e posiziona ogni box
        for prod in page_products:
            varianti = varianti_map.get(prod['id'], [])

            if varianti:
                # Usa fullhd se doppia_colonna attivo
                prod_template = 'fullhd' if prod.get('doppia_colonna') == 1 else template
                box_img = box_generator.generate(prod, varianti, prod_template)

                # Se doppia colonna, usa tutta la larghezza
                if prod.get('doppia_colonna') == 1:
                    box_scaled = box_generator._contain(box_img, col_w * 2 + COL_GAP, prod.get('_h', 1200))
                    x = MARGIN
                else:
                    box_scaled = box_generator._contain(box_img, col_w, prod.get('_h', 1600))
                    col = prod.get('_col', 0)
                    x = MARGIN + col * (col_w + COL_GAP)

                y = prod.get('_y', MARGIN)

                if box_scaled:
                    if box_scaled.mode == 'RGBA':
                        page_img.paste(box_scaled, (x, y), box_scaled)
                    else:
                        page_img.paste(box_scaled, (x, y))

        pages_images.append(page_img)

    conn.close()

    if not pages_images:
        return jsonify({'error': 'Nessuna pagina generata'}), 404

    # Salva come PDF
    pdf_filename = f"catalogo_{categoria}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf_path = EXPORT_FOLDER / pdf_filename

    # Salva prima immagine e aggiungi le altre
    pages_images[0].save(
        str(pdf_path),
        'PDF',
        resolution=300,
        save_all=True,
        append_images=pages_images[1:] if len(pages_images) > 1 else []
    )

    return jsonify({
        'success': True,
        'filename': pdf_filename,
        'pages': len(pages_images),
        'products': len(all_products),
        'download_url': f'/api/catalog/pdf/download/{pdf_filename}'
    })


@app.route('/api/catalog/pdf/download/<filename>')
def api_download_catalog_pdf(filename):
    """Scarica il PDF generato"""
    filepath = EXPORT_FOLDER / filename
    if not filepath.exists():
        return jsonify({'error': 'File non trovato'}), 404
    return send_file(str(filepath), mimetype='application/pdf', as_attachment=True, download_name=filename)


@app.route('/api/catalog/categories')
def api_catalog_categories():
    """Restituisce le categorie disponibili con il conteggio prodotti"""
    conn = get_db()
    c = conn.cursor()

    c.execute('''
        SELECT categoria, COUNT(*) as count, MIN(posizione) as min_pos, MAX(posizione) as max_pos
        FROM posizioni
        GROUP BY categoria
        ORDER BY categoria
    ''')

    categories = [dict(row) for row in c.fetchall()]
    conn.close()

    return jsonify({'categories': categories})


@app.route('/preview')
def preview_page():
    """Pagina HTML per la preview del catalogo"""
    return render_template('preview.html')


@app.route('/viewer')
def catalog_viewer_page():
    """Nuovo Catalog Viewer interattivo con zoom e click sui prodotti"""
    return render_template('catalog_viewer.html')


# ============================================
# API v4 - VERIFICA CATALOGO E STATO PRODOTTI
# ============================================

@app.route('/api/verifica-catalogo', methods=['POST'])
def api_verifica_catalogo():
    """
    Confronta una lista di codici dal catalogo PDF con il database.
    Input JSON: { "catalogo": "BRICO", "codici": ["1001", "1002", ...] }
    Output: codici mancanti, codici presenti, codici come varianti
    """
    data = request.json
    catalogo = data.get('catalogo', '')
    codici_pdf = set(data.get('codici', []))

    if not codici_pdf:
        return jsonify({'error': 'Nessun codice fornito'}), 400

    conn = get_db()
    c = conn.cursor()

    # Ottieni tutti i codici principali
    c.execute('SELECT codice_principale FROM prodotti')
    codici_principali = set(row[0] for row in c.fetchall())

    # Ottieni tutti i codici varianti con il loro prodotto principale
    c.execute('''
        SELECT v.codice, p.codice_principale, p.titolo
        FROM varianti v
        JOIN prodotti p ON v.prodotto_id = p.id
    ''')
    varianti_map = {row[0]: {'principale': row[1], 'titolo': row[2]} for row in c.fetchall()}
    codici_varianti = set(varianti_map.keys())

    # Tutti i codici coperti
    codici_coperti = codici_principali | codici_varianti

    # Analisi
    presenti_come_principali = codici_pdf & codici_principali
    presenti_come_varianti = codici_pdf & codici_varianti
    mancanti = codici_pdf - codici_coperti

    # Dettaglio varianti
    varianti_dettaglio = []
    for cod in presenti_come_varianti:
        varianti_dettaglio.append({
            'codice': cod,
            'principale': varianti_map[cod]['principale'],
            'titolo': varianti_map[cod]['titolo']
        })

    conn.close()

    return jsonify({
        'catalogo': catalogo,
        'totale_codici_pdf': len(codici_pdf),
        'presenti_come_principali': len(presenti_come_principali),
        'presenti_come_varianti': len(presenti_come_varianti),
        'mancanti': len(mancanti),
        'codici_mancanti': sorted(list(mancanti), key=lambda x: int(x) if x.isdigit() else 0),
        'varianti_dettaglio': varianti_dettaglio
    })


@app.route('/api/prodotti/stato', methods=['POST'])
def api_cambia_stato_prodotti():
    """
    Cambia lo stato di più prodotti in blocco.
    Input JSON: { "codici": ["1001", "1002"], "stato": "obsoleto" }
    Stati validi: attivo, obsoleto, da_verificare
    """
    data = request.json
    codici = data.get('codici', [])
    nuovo_stato = data.get('stato', '')

    stati_validi = ['attivo', 'obsoleto', 'da_verificare']
    if nuovo_stato not in stati_validi:
        return jsonify({'error': f'Stato non valido. Usa: {stati_validi}'}), 400

    if not codici:
        return jsonify({'error': 'Nessun codice fornito'}), 400

    conn = get_db()
    c = conn.cursor()

    placeholders = ','.join('?' * len(codici))
    c.execute(f'''
        UPDATE prodotti
        SET stato = ?, data_modifica = CURRENT_TIMESTAMP
        WHERE codice_principale IN ({placeholders})
    ''', [nuovo_stato] + codici)

    aggiornati = c.rowcount
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'aggiornati': aggiornati,
        'stato': nuovo_stato
    })


@app.route('/api/prodotti/verifica-catalogo', methods=['POST'])
def api_segna_verificati():
    """
    Segna prodotti come verificati sul catalogo PDF.
    Input JSON: { "codici": ["1001", "1002"], "catalogo": "BRICO", "verificato": true }
    """
    data = request.json
    codici = data.get('codici', [])
    catalogo = data.get('catalogo', '')
    verificato = 1 if data.get('verificato', True) else 0

    if not codici:
        return jsonify({'error': 'Nessun codice fornito'}), 400

    conn = get_db()
    c = conn.cursor()

    placeholders = ','.join('?' * len(codici))

    # Aggiorna verificato_catalogo e catalogo
    if catalogo:
        c.execute(f'''
            UPDATE prodotti
            SET verificato_catalogo = ?, catalogo = ?, data_modifica = CURRENT_TIMESTAMP
            WHERE codice_principale IN ({placeholders})
        ''', [verificato, catalogo] + codici)
    else:
        c.execute(f'''
            UPDATE prodotti
            SET verificato_catalogo = ?, data_modifica = CURRENT_TIMESTAMP
            WHERE codice_principale IN ({placeholders})
        ''', [verificato] + codici)

    aggiornati = c.rowcount
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'aggiornati': aggiornati,
        'verificato': verificato == 1,
        'catalogo': catalogo
    })


@app.route('/api/verifica-codice-variante/<codice>')
def api_verifica_codice_variante(codice):
    """
    Verifica se un codice è già usato come variante di un altro prodotto.
    Usato per alert durante l'import.
    """
    conn = get_db()
    c = conn.cursor()

    # Cerca come codice principale
    c.execute('SELECT id, titolo FROM prodotti WHERE codice_principale = ?', (codice,))
    principale = c.fetchone()

    # Cerca come variante
    c.execute('''
        SELECT v.codice, p.codice_principale, p.titolo
        FROM varianti v
        JOIN prodotti p ON v.prodotto_id = p.id
        WHERE v.codice = ?
    ''', (codice,))
    variante = c.fetchone()

    conn.close()

    if principale:
        return jsonify({
            'esiste': True,
            'tipo': 'principale',
            'prodotto_id': principale[0],
            'titolo': principale[1],
            'alert': f'⚠️ Codice {codice} già usato come prodotto principale: {principale[1]}'
        })
    elif variante:
        return jsonify({
            'esiste': True,
            'tipo': 'variante',
            'codice_principale': variante[1],
            'titolo': variante[2],
            'alert': f'⚠️ Codice {codice} già usato come variante del prodotto {variante[1]}: {variante[2]}'
        })
    else:
        return jsonify({
            'esiste': False,
            'tipo': None,
            'alert': None
        })


# ============================================
# API v4.1 - LOG MODIFICHE, BACKUP, BULK UPDATE
# ============================================

def log_modifica(conn, prodotto_id, codice_principale, campo, valore_precedente, valore_nuovo, utente='sistema'):
    """Registra una modifica nel log"""
    if valore_precedente == valore_nuovo:
        return  # Nessuna modifica effettiva
    c = conn.cursor()
    c.execute('''
        INSERT INTO modifiche_log (prodotto_id, codice_principale, campo, valore_precedente, valore_nuovo, utente)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (prodotto_id, codice_principale, campo, str(valore_precedente) if valore_precedente else None,
          str(valore_nuovo) if valore_nuovo else None, utente))


@app.route('/api/modifiche/<int:prodotto_id>')
def api_modifiche_prodotto(prodotto_id):
    """
    Storico modifiche di un prodotto.
    Restituisce le ultime 100 modifiche.
    """
    conn = get_db()
    c = conn.cursor()

    c.execute('''
        SELECT * FROM modifiche_log
        WHERE prodotto_id = ?
        ORDER BY data_modifica DESC
        LIMIT 100
    ''', (prodotto_id,))

    modifiche = [dict(row) for row in c.fetchall()]
    conn.close()

    return jsonify({
        'prodotto_id': prodotto_id,
        'totale': len(modifiche),
        'modifiche': modifiche
    })


@app.route('/api/modifiche')
def api_modifiche_recenti():
    """
    Ultime modifiche globali.
    Query params: limit (default 50), utente (filtro opzionale)
    """
    limit = int(request.args.get('limit', 50))
    utente = request.args.get('utente', '')

    conn = get_db()
    c = conn.cursor()

    if utente:
        c.execute('''
            SELECT m.*, p.titolo
            FROM modifiche_log m
            LEFT JOIN prodotti p ON m.prodotto_id = p.id
            WHERE m.utente = ?
            ORDER BY m.data_modifica DESC
            LIMIT ?
        ''', (utente, limit))
    else:
        c.execute('''
            SELECT m.*, p.titolo
            FROM modifiche_log m
            LEFT JOIN prodotti p ON m.prodotto_id = p.id
            ORDER BY m.data_modifica DESC
            LIMIT ?
        ''', (limit,))

    modifiche = [dict(row) for row in c.fetchall()]
    conn.close()

    return jsonify({
        'totale': len(modifiche),
        'modifiche': modifiche
    })


@app.route('/api/backup', methods=['GET', 'POST'])
def api_backup():
    """
    Genera un backup completo del database in formato JSON.
    GET: genera e scarica il backup
    POST: genera e salva nella cartella backups/
    """
    conn = get_db()
    c = conn.cursor()

    # Esporta tutte le tabelle
    backup_data = {
        'versione': '4.1',
        'data_backup': datetime.now().isoformat(),
        'prodotti': [],
        'varianti': [],
        'posizioni': [],
        'task': [],
        'brand': [],
        'modifiche_log': []
    }

    # Prodotti
    c.execute('SELECT * FROM prodotti')
    backup_data['prodotti'] = [dict(row) for row in c.fetchall()]

    # Varianti
    c.execute('SELECT * FROM varianti')
    backup_data['varianti'] = [dict(row) for row in c.fetchall()]

    # Posizioni
    c.execute('SELECT * FROM posizioni')
    backup_data['posizioni'] = [dict(row) for row in c.fetchall()]

    # Task
    c.execute('SELECT * FROM task')
    backup_data['task'] = [dict(row) for row in c.fetchall()]

    # Brand
    c.execute('SELECT * FROM brand')
    backup_data['brand'] = [dict(row) for row in c.fetchall()]

    # Log modifiche (ultime 1000)
    c.execute('SELECT * FROM modifiche_log ORDER BY data_modifica DESC LIMIT 1000')
    backup_data['modifiche_log'] = [dict(row) for row in c.fetchall()]

    conn.close()

    # Statistiche
    backup_data['stats'] = {
        'prodotti': len(backup_data['prodotti']),
        'varianti': len(backup_data['varianti']),
        'posizioni': len(backup_data['posizioni']),
        'task': len(backup_data['task']),
        'modifiche': len(backup_data['modifiche_log'])
    }

    # Nome file
    filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    if request.method == 'POST':
        # Salva nella cartella backups/
        filepath = BACKUP_FOLDER / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)

        return jsonify({
            'success': True,
            'filename': filename,
            'path': str(filepath),
            'stats': backup_data['stats']
        })
    else:
        # Restituisci come download
        json_data = json.dumps(backup_data, ensure_ascii=False, indent=2)
        buffer = io.BytesIO(json_data.encode('utf-8'))
        buffer.seek(0)
        return send_file(buffer, mimetype='application/json', as_attachment=True, download_name=filename)


@app.route('/api/backup/list')
def api_backup_list():
    """Lista dei backup disponibili"""
    backups = []
    for f in sorted(BACKUP_FOLDER.glob('backup_*.json'), reverse=True):
        stat = f.stat()
        backups.append({
            'filename': f.name,
            'size_kb': round(stat.st_size / 1024, 1),
            'data': datetime.fromtimestamp(stat.st_mtime).isoformat()
        })

    return jsonify({'backups': backups, 'totale': len(backups)})


@app.route('/api/backup/<filename>')
def api_backup_download(filename):
    """Scarica un backup specifico"""
    filepath = BACKUP_FOLDER / filename
    if not filepath.exists():
        return jsonify({'error': 'Backup non trovato'}), 404
    return send_file(str(filepath), mimetype='application/json', as_attachment=True, download_name=filename)


@app.route('/api/prodotti/bulk-update', methods=['POST'])
def api_bulk_update_prodotti():
    """
    Aggiorna un campo su più prodotti in blocco.
    Input JSON: {
        "codici": ["1001", "1002", ...],
        "campo": "catalogo",
        "valore": "BRICO",
        "utente": "admin"
    }
    Campi consentiti: catalogo, stato, logo, template, verificato_catalogo
    """
    data = request.json
    codici = data.get('codici', [])
    campo = data.get('campo', '')
    valore = data.get('valore')
    utente = data.get('utente', 'api')

    campi_consentiti = ['catalogo', 'stato', 'logo', 'template', 'verificato_catalogo',
                        'descrizione', 'immagine', 'controllato']

    if campo not in campi_consentiti:
        return jsonify({'error': f'Campo non consentito. Usa: {campi_consentiti}'}), 400

    if not codici:
        return jsonify({'error': 'Nessun codice fornito'}), 400

    conn = get_db()
    c = conn.cursor()

    # Prima ottieni i valori precedenti per il log
    placeholders = ','.join('?' * len(codici))
    c.execute(f'''
        SELECT id, codice_principale, {campo} FROM prodotti
        WHERE codice_principale IN ({placeholders})
    ''', codici)

    prodotti_da_aggiornare = c.fetchall()

    # Log delle modifiche
    for prod in prodotti_da_aggiornare:
        log_modifica(conn, prod[0], prod[1], campo, prod[2], valore, utente)

    # Esegui l'update
    c.execute(f'''
        UPDATE prodotti
        SET {campo} = ?, data_modifica = CURRENT_TIMESTAMP
        WHERE codice_principale IN ({placeholders})
    ''', [valore] + codici)

    aggiornati = c.rowcount
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'aggiornati': aggiornati,
        'campo': campo,
        'valore': valore,
        'utente': utente
    })


@app.route('/api/prodotti/bulk-delete', methods=['POST'])
def api_bulk_delete_prodotti():
    """
    Elimina più prodotti in blocco.
    Input JSON: { "codici": ["1001", "1002", ...], "utente": "admin" }
    """
    data = request.json
    codici = data.get('codici', [])
    utente = data.get('utente', 'api')

    if not codici:
        return jsonify({'error': 'Nessun codice fornito'}), 400

    conn = get_db()
    c = conn.cursor()

    # Prima ottieni gli ID per eliminare varianti e task
    placeholders = ','.join('?' * len(codici))
    c.execute(f'SELECT id, codice_principale, titolo FROM prodotti WHERE codice_principale IN ({placeholders})', codici)
    prodotti_da_eliminare = c.fetchall()

    eliminati = 0
    for prod in prodotti_da_eliminare:
        prod_id, cod, titolo = prod

        # Log eliminazione
        log_modifica(conn, prod_id, cod, 'ELIMINATO', titolo, None, utente)

        # Elimina varianti e task
        c.execute('DELETE FROM varianti WHERE prodotto_id = ?', (prod_id,))
        c.execute('DELETE FROM task WHERE prodotto_id = ?', (prod_id,))
        c.execute('DELETE FROM prodotti WHERE id = ?', (prod_id,))
        eliminati += 1

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'eliminati': eliminati,
        'utente': utente
    })


@app.route('/api/statistiche-catalogo')
def api_statistiche_catalogo():
    """
    Statistiche sui prodotti per catalogo e stato.
    """
    conn = get_db()
    c = conn.cursor()

    # Per catalogo
    c.execute('''
        SELECT catalogo, COUNT(*) as count
        FROM prodotti
        WHERE catalogo IS NOT NULL AND catalogo != ''
        GROUP BY catalogo
    ''')
    per_catalogo = {row[0]: row[1] for row in c.fetchall()}

    # Per stato
    c.execute('''
        SELECT COALESCE(stato, 'attivo') as stato, COUNT(*) as count
        FROM prodotti
        GROUP BY stato
    ''')
    per_stato = {row[0]: row[1] for row in c.fetchall()}

    # Verificati
    c.execute('SELECT COUNT(*) FROM prodotti WHERE verificato_catalogo = 1')
    verificati = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM prodotti WHERE verificato_catalogo = 0 OR verificato_catalogo IS NULL')
    non_verificati = c.fetchone()[0]

    # Totale
    c.execute('SELECT COUNT(*) FROM prodotti')
    totale = c.fetchone()[0]

    conn.close()

    return jsonify({
        'totale_prodotti': totale,
        'per_catalogo': per_catalogo,
        'per_stato': per_stato,
        'verificati_catalogo': verificati,
        'non_verificati_catalogo': non_verificati
    })


# ============================================
# MAIN
# ============================================

# Inizializza il database (anche quando importato da WSGI)
init_db()

if __name__ == '__main__':
    print("""
╔══════════════════════════════════════════════════════════╗
║         📦 CATALOGO MANAGER v4.1 - LOG & BACKUP          ║
╠══════════════════════════════════════════════════════════╣
║  🌐 Apri: http://localhost:5000                          ║
║  📁 Foto: foto_prodotti/                                 ║
║  🏷️ Loghi: loghi_brand/                                  ║
║  💾 Backups: backups/                                    ║
║  ✅ v4.1: Log modifiche, Backup JSON, Bulk update        ║
╚══════════════════════════════════════════════════════════╝
    """)
    app.run(debug=True, host='0.0.0.0', port=5000)
