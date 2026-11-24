# Catalogo Manager v3.0 - Team Edition

Sistema di gestione catalogo prodotti con generazione box e impaginazione InDesign.

## Funzionalità

- **Gestione Prodotti**: Import CSV, gestione varianti, posizioni catalogo
- **Generazione Box**: Template Corporate e Full HD (300 DPI)
- **Sistema Task**: Assegnazione task per lavorare in team
- **Script InDesign**: Impaginazione automatica con JSX

## Struttura

```
catalogo-manager/
├── app.py                  # Applicazione Flask principale
├── requirements.txt        # Dipendenze Python
├── templates/
│   └── index.html          # Frontend interfaccia web
└── scripts/
    ├── impagina_catalogo.jsx   # Impaginazione box in InDesign
    ├── box_nativi.jsx          # Box come oggetti InDesign nativi
    ├── prova_box_nativi.jsx    # Test box nativi
    └── pagine_finali.jsx       # Pagine finali del catalogo
```

## Installazione

```bash
pip install -r requirements.txt
python app.py
```

Apri http://localhost:5000

## Cartelle create automaticamente

- `foto_prodotti/` - Immagini prodotti
- `loghi_brand/` - Loghi marchi
- `icone/` - Icone caratteristiche
- `output_box/` - Box generati
- `export_catalogo/` - Export per impaginazione

## Requisiti

- Python 3.8+
- Flask, Pandas, Pillow, openpyxl
