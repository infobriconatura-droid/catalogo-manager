/*
    BOX NATIVI  —  Catalogo Manager v3
    ------------------------------------------------------------
    Costruisce i box come oggetti InDesign veri (testo modificabile,
    colori CMYK, nero solo K sui testi piccoli).

    NON decide niente da solo: ogni misura arriva gia' calcolata in
    _dati.json, dalle stesse formule dei box a immagine. Cosi' le due
    versioni sono identiche.

    USO
      1. app: Posizioni -> Impaginazione -> "Dati per box nativi"
      2. apri il documento InDesign
      3. Finestra > Utilita > Script -> doppio click
      4. scegli _dati.json

    Tutto sul livello "BOX NATIVI": cancellalo per tornare indietro.
*/

#target indesign

// Riga che compare in fondo a ogni pagina costruita dallo script.
// Per toglierla, metti:  var NOTA_PREZZI = "";
var NOTA_PREZZI = "I prezzi indicati sono indicativi e possono subire variazioni.";

(function () {

    if (app.documents.length === 0) { alert("Apri prima un documento InDesign."); return; }
    var doc = app.activeDocument;

    var oldUnit = app.scriptPreferences.measurementUnit;
    app.scriptPreferences.measurementUnit = MeasurementUnits.POINTS;
    var vp = doc.viewPreferences;
    var oldH = vp.horizontalMeasurementUnits, oldV = vp.verticalMeasurementUnits, oldO = vp.rulerOrigin;
    vp.horizontalMeasurementUnits = MeasurementUnits.POINTS;
    vp.verticalMeasurementUnits = MeasurementUnits.POINTS;
    vp.rulerOrigin = RulerOrigin.PAGE_ORIGIN;
    function ripristina() {
        vp.horizontalMeasurementUnits = oldH; vp.verticalMeasurementUnits = oldV;
        vp.rulerOrigin = oldO; app.scriptPreferences.measurementUnit = oldUnit;
    }

    var f = File.openDialog("Scegli _dati.json", "*.json");
    if (!f) { ripristina(); return; }
    f.encoding = "UTF-8"; f.open("r");
    var txt = f.read(); f.close();
    if (txt.charCodeAt(0) === 65279) txt = txt.substring(1);
    var dati = eval("(" + txt + ")");
    var el = dati.elementi;
    if (!el || !el.length) { alert("Nessun elemento nei dati."); ripristina(); return; }
    var inquadrate = 0, ricostruite = 0;

    // Stesse formule di _filetti_mono nell'app, ma in punti: la larghezza di
    // riferimento del disegno e' 2160, quindi basta la proporzione.
    function inquadraturaDaCapo(D) {
        if (!D || !D.larghezza || !D.altezza) return null;
        var k  = D.larghezza / 2160.0;
        var sp = 3 * k;
        var x0 = 20 * k;
        var pad = D.pad || (24 * k);
        var lw = (D.colonna_x ? D.colonna_x - pad : D.larghezza * 0.40);
        if (lw <= x0 + 10) return null;
        return {
            linea:   { x: x0,           y: 30 * k, w: lw - x0,   h: sp },
            tacca:   { x: x0,           y: 30 * k, w: 110 * k,   h: sp * 2 },
            filetto: { x: lw + 12 * k,  y: 52 * k, w: sp,        h: D.altezza - 104 * k }
        };
    }

    var quanti = prompt("Il file contiene " + el.length + " prodotti.\n\nQuanti ne costruisco?",
                        String(el.length));
    if (quanti === null) { ripristina(); return; }
    quanti = parseInt(quanti, 10);
    if (isNaN(quanti) || quanti < 1) quanti = el.length;
    quanti = Math.min(quanti, el.length);

    // ---------------- colori CMYK ----------------
    function tinta(nome, c, m, y, k) {
        var s;
        try { s = doc.colors.itemByName(nome); s.name; }
        catch (e) { s = doc.colors.add({ name: nome, model: ColorModel.PROCESS,
                                         space: ColorSpace.CMYK, colorValue: [c, m, y, k] }); }
        return s;
    }
    var VERDE     = tinta("CAT Verde", 85, 35, 85, 30);
    var VERDE_MED = tinta("CAT Verde medio", 75, 25, 80, 15);
    var ACCENTO   = tinta("CAT Accento", 60, 5, 90, 0);
    var NERO_K    = tinta("CAT Nero K", 0, 0, 0, 100);
    var GRIGIO    = tinta("CAT Grigio", 0, 0, 0, 62);
    var GRIGIO_SC = tinta("CAT Grigio testo", 0, 0, 0, 72);
    var ZEBRA     = tinta("CAT Zebra", 5, 0, 4, 0);
    var FILETTO   = tinta("CAT Filetto", 0, 0, 0, 14);
    // il filetto dell'inquadratura foto deve vedersi: al 14% spariva in pagina
    var FIL_FOTO  = tinta("CAT Filetto foto", 0, 0, 0, 25);
    var NIENTE    = doc.swatches.itemByName("None");
    var FONT = app.fonts.item("Arial");

    function stile(nome, prop) {
        var s;
        try { s = doc.paragraphStyles.itemByName(nome); s.name; }
        catch (e) { s = doc.paragraphStyles.add({ name: nome }); }
        for (var k in prop) { try { s[k] = prop[k]; } catch (e2) {} }
        return s;
    }
    // Niente sillabazione: un titolo non si spezza mai a meta' parola.
    // Era per quello che si leggeva "FILO PLASTIFICATO PER TENSIO-".
    stile("CAT Titolo", { appliedFont: FONT, fontStyle: "Bold", fillColor: NERO_K,
                          hyphenation: false });
    // Tondo e grigio scuro: in corsivo chiaro a 6,5 pt la descrizione in
    // stampa non si leggeva. Il grigio e' solo K, niente fuori registro.
    stile("CAT Descrizione",  { appliedFont: FONT, fontStyle: "Regular", fillColor: GRIGIO_SC });
    stile("CAT Intestazione", { appliedFont: FONT, fontStyle: "Bold",    fillColor: VERDE_MED });
    stile("CAT Riga",         { appliedFont: FONT, fontStyle: "Regular", fillColor: NERO_K });
    var ST_TIT = doc.paragraphStyles.itemByName("CAT Titolo");
    var ST_DES = doc.paragraphStyles.itemByName("CAT Descrizione");
    var ST_INT = doc.paragraphStyles.itemByName("CAT Intestazione");
    var ST_RIG = doc.paragraphStyles.itemByName("CAT Riga");

    var layer;
    try { layer = doc.layers.itemByName("BOX NATIVI"); layer.name; }
    catch (e) { layer = doc.layers.add({ name: "BOX NATIVI" }); }

    var maxPag = 0;
    for (var i = 0; i < quanti; i++) if (el[i].pagina > maxPag) maxPag = el[i].pagina;
    var partenza = doc.pages.length + 1;
    while (doc.pages.length < partenza + maxPag - 1) doc.pages.add(LocationOptions.AT_END);

    // ---------------- utilita' ----------------
    // Ogni misura passa da qui: se per qualsiasi motivo un valore manca o non
    // e' un numero, si usa il ripiego invece di far fallire tutto lo script.
    function N(v, ripiego) {
        v = Number(v);
        if (isNaN(v) || !isFinite(v)) return Number(ripiego) || 0;
        return v;
    }
    // ---- da che lato cade davvero la pagina ----------------------------
    // L'app calcola la x supponendo che la prima pagina del piano sia una
    // destra. Se il documento ha un numero di pagine diverso da quello
    // previsto, tutto si specchia e la prima colonna finisce SOTTO la banda
    // verde. Qui la x la ricalcola InDesign, che il lato lo sa per certo.
    var G = dati.gabbia || {};
    function ascissa(pag, e) {
        var sinistra = false;
        try { sinistra = (pag.side === PageSideOptions.LEFT_HAND); } catch (err) {}
        var est = N(G.margine_esterno, 25.5118);
        var inte = N(G.margine_interno, 8.5039);
        var cw = N(G.colonna_w, 277.7712);
        var gr = N(G.grondaia, 5.7175);
        // la fascia parte dal filo della banda a sinistra, dalla piega a destra
        if (e.tipo === "fascia") return sinistra ? est : 0;
        var col = N(e.colonna, 1);
        if (col < 1) col = 1;
        return (sinistra ? est : inte) + (col - 1) * (cw + gr);
    }

    // Ogni pezzo creato finisce qui: a fine prodotto diventano un gruppo
    // unico, cosi' il box si sposta trascinandolo una volta sola.
    // Per modificare un testo dentro al gruppo: doppio clic ed entri.
    var pezzi = [];
    function tieni(x) { if (x) pezzi.push(x); return x; }

    function rett(pag, x, y, w, h, colore) {
        x = N(x); y = N(y); w = N(w, 1); h = N(h, 1);
        if (w <= 0 || h <= 0) return null;
        return tieni(pag.rectangles.add(layer, { geometricBounds: [y, x, y + h, x + w],
            strokeWeight: 0, strokeColor: NIENTE, fillColor: colore }));
    }
    function immagine(pag, x, y, w, h, percorso) {
        x = N(x); y = N(y); w = N(w, 1); h = N(h, 1);
        if (w <= 0 || h <= 0 || !percorso) return null;
        var r = pag.rectangles.add(layer, { geometricBounds: [y, x, y + h, x + w],
            strokeWeight: 0, strokeColor: NIENTE, fillColor: NIENTE });
        try { r.place(File(percorso)); r.fit(FitOptions.FILL_PROPORTIONALLY); return tieni(r); }
        catch (err) { r.remove(); return null; }
    }
    function blocco(pag, x, y, w, h, contenuto, st, corpo, interlinea, primaLinea) {
        x = N(x); y = N(y); w = N(w, 10); h = N(h, 10);
        corpo = N(corpo, 8); interlinea = N(interlinea, corpo * 1.2);
        if (w <= 0 || h <= 0) return null;
        var t = tieni(pag.textFrames.add(layer, { geometricBounds: [y, x, y + h, x + w] }));
        // ogni preferenza e' protetta: i nomi delle costanti cambiano fra
        // le versioni di InDesign e una sola non riconosciuta fermerebbe tutto
        try { t.textFramePreferences.insetSpacing = [0, 0, 0, 0]; } catch (e1) {}
        try { t.textFramePreferences.firstBaselineOffset = FirstBaseline.LEADING_OFFSET; }
        catch (e2) {
            try { t.textFramePreferences.firstBaselineOffset = FirstBaseline.CAP_HEIGHT; }
            catch (e3) {}
        }
        try { t.textFramePreferences.autoSizingType = AutoSizingTypeEnum.OFF; } catch (e4) {}
        try { t.textFramePreferences.ignoreWrap = true; } catch (e5) {}
        t.contents = contenuto;
        var s = t.parentStory;
        try { s.appliedParagraphStyle = st; } catch (e6) {}
        try { s.pointSize = corpo; } catch (e7) {}
        try { s.leading = interlinea; } catch (e8) {}
        // posizione esatta della prima linea di base: senza questo il testo
        // non cade dove cade nel box a immagine
        primaLinea = Number(primaLinea);
        if (primaLinea && !isNaN(primaLinea) && isFinite(primaLinea)) {
            try {
                t.textFramePreferences.firstBaselineOffset = FirstBaseline.FIXED_HEIGHT;
                t.textFramePreferences.minimumFirstBaselineOffset = primaLinea;
            } catch (e9) {}
        }
        return t;
    }

    // Rete di sicurezza: l'app calcola il corpo misurando il testo con Arial,
    // ma fra quel calcolo e la composizione vera di InDesign puo' restare
    // mezzo millimetro di scarto. Se il testo trabocca lo stringo finche'
    // entra, invece di lasciarlo tagliato.
    function nonTagliare(t, corpoMinimo) {
        if (!t) return;
        var giri = 0;
        try {
            while (t.overflows && giri < 40) {
                var s = t.parentStory;
                var nuovo = s.pointSize - 0.25;
                if (nuovo < (corpoMinimo || 5)) break;
                s.pointSize = nuovo;
                s.leading = nuovo * 1.1;
                giri++;
            }
        } catch (eN) {}
        if (giri) stretti++;
    }

    // ---------------- costruzione ----------------
    var t0 = new Date().getTime();
    var fatti = 0, senzaFoto = 0, traboccati = 0, specchiate = 0;
    var raggruppati = 0, note = 0, stretti = 0;
    var paginaUsata = {};

    var falliti = [];
    app.doScript(function () {
        for (var i = 0; i < quanti; i++) {
          try {
            var e = el[i], D = e.disegno;
            if (!D) { falliti.push(e.codice + " (dati vecchi: rigenera _dati.json)"); continue; }
            var pag = doc.pages[partenza - 2 + e.pagina];
            var X = ascissa(pag, e), Y = e.y;
            if (Math.abs(X - N(e.x)) > 0.5) specchiate++;
            pezzi = [];
            paginaUsata[e.pagina] = pag;

            // --- logo ---
            if (D.logo && e.logo) immagine(pag, X + D.logo.x, Y + D.logo.y, D.logo.w, D.logo.h, e.logo);

            // --- foto ---
            if (D.foto && e.foto) {
                if (!immagine(pag, X + D.foto.x, Y + D.foto.y, D.foto.w, D.foto.h, e.foto)) senzaFoto++;
            } else senzaFoto++;

            if (e.tipo === "fascia") {
                // ======== FASCIA MONOPRODOTTO ========
                // inquadratura della foto: linea sopra con la tacca verde e
                // filetto verticale che la separa dal testo
                // L'inquadratura (linea grigia in alto, tacca verde sopra,
                // filetto verticale a destra della foto) la costruisco io
                // se nei dati non c'e': cosi' funziona anche con un _dati.json
                // vecchio, senza rigenerare niente.
                if (!D.inquadratura) { D.inquadratura = inquadraturaDaCapo(D); ricostruite++; }
                if (D.inquadratura) {
                    var Q = D.inquadratura;
                    rett(pag, X + Q.linea.x, Y + Q.linea.y, Q.linea.w, Q.linea.h, FIL_FOTO);
                    rett(pag, X + Q.filetto.x, Y + Q.filetto.y, Q.filetto.w, Q.filetto.h, FIL_FOTO);
                    rett(pag, X + Q.tacca.x, Y + Q.tacca.y, Q.tacca.w, Q.tacca.h, ACCENTO);
                    inquadrate++;
                }

                var tf = blocco(pag, X + D.titolo.x, Y + D.titolo.y, D.descrizione.w,
                                D.titolo.corpo * 1.5, e.titolo, ST_TIT,
                                D.titolo.corpo, D.titolo.corpo * 1.1, D.titolo.prima_linea);
                try { tf.parentStory.tracking = D.titolo.tracking; } catch (eE) {}
                nonTagliare(tf, D.titolo.corpo * 0.7);

                rett(pag, X + D.accento.x, Y + D.accento.y, D.accento.w, D.accento.h, ACCENTO);

                if (D.descrizione.righe) {
                    blocco(pag, X + D.descrizione.x, Y + D.descrizione.y, D.descrizione.w,
                           D.descrizione.righe * D.descrizione.interlinea + 4, e.descrizione,
                           ST_DES, D.descrizione.corpo, D.descrizione.interlinea,
                           D.descrizione.prima_linea);
                }

                var B = D.barra, v0 = e.varianti[0] || {};
                rett(pag, X + B.x, Y + B.y, B.w, B.filetto, VERDE);
                rett(pag, X + B.x, Y + B.y + B.h, B.w, B.filetto, VERDE);
                var etich = ["CODICE", "MODELLO", "U.M.", "MV", "CF", "LISTINO"];
                var vals = [v0.codice, v0.modello, v0.um, v0.mv, v0.cf, v0.listino];
                for (var c = 0; c < etich.length; c++) {
                    var cx0 = X + B.x + B.colonne_x[c], cx1 = X + B.x + B.colonne_x[c + 1];
                    if (c) rett(pag, cx0, Y + B.y + B.h * 0.17, 0.4, B.h * 0.66, FILETTO);
                    var lb = blocco(pag, cx0, Y + B.y + B.h * 0.18, cx1 - cx0,
                                    B.corpo_etichetta * 1.4, etich[c], ST_INT,
                                    B.corpo_etichetta, B.corpo_etichetta * 1.2);
                    try { lb.parentStory.justification = Justification.CENTER_ALIGN; } catch (eA) {}
                    var forte = (c === 0 || c === 5);
                    var vb = blocco(pag, cx0, Y + B.y + B.h * 0.48, cx1 - cx0,
                                    B.corpo_forte * 1.4, String(vals[c] || ""), ST_RIG,
                                    forte ? B.corpo_forte : B.corpo_valore,
                                    (forte ? B.corpo_forte : B.corpo_valore) * 1.2);
                    try { vb.parentStory.justification = Justification.CENTER_ALIGN; } catch (eB) {}
                    if (forte) {
                        try { vb.parentStory.fontStyle = "Bold"; } catch (eC) {}
                        if (c === 0) { try { vb.parentStory.fillColor = VERDE; } catch (eD) {} }
                    }
                }

            } else {
                // ======== BOX A COLONNA ========
                var tf2 = blocco(pag, X + D.titolo.x, Y + D.titolo.y, D.titolo.w,
                                 D.titolo.corpo * 1.5, e.titolo, ST_TIT,
                                 D.titolo.corpo, D.titolo.corpo * 1.1, D.titolo.prima_linea);
                try { tf2.parentStory.tracking = D.titolo.tracking; } catch (eF) {}
                nonTagliare(tf2, D.titolo.corpo * 0.7);

                rett(pag, X + D.accento.x, Y + D.accento.y, D.accento.w, D.accento.h, ACCENTO);

                if (D.descrizione.righe) {
                    var db = blocco(pag, X + D.descrizione.x, Y + D.descrizione.y,
                                    D.descrizione.w,
                                    D.descrizione.righe * D.descrizione.interlinea + 4,
                                    e.descrizione, ST_DES,
                                    D.descrizione.corpo, D.descrizione.interlinea,
                                    D.descrizione.prima_linea);
                    try {
                        db.parentStory.justification = D.descrizione.centrata
                            ? Justification.CENTER_ALIGN : Justification.LEFT_ALIGN;
                    } catch (eG) {}
                }

                var T = D.tabella, n = e.varianti.length;
                var tx = X + T.x, ty = Y + T.y;

                // filetti e righe alternate
                rett(pag, tx, ty, T.w, T.filetto_alto, VERDE);
                rett(pag, tx, ty + T.intestazione_h, T.w, 0.3, FILETTO);
                for (var z = 1; z < n; z += 2)
                    rett(pag, tx, ty + T.intestazione_h + z * T.riga_h, T.w, T.riga_h, ZEBRA);
                rett(pag, tx, ty + T.intestazione_h + n * T.riga_h, T.w, T.filetto_basso, VERDE_MED);

                // intestazione
                var etich2 = [];
                for (var c2 = 0; c2 < dati.colonne_tabella.length; c2++)
                    etich2.push(dati.colonne_tabella[c2][0]);
                var ib = blocco(pag, tx, ty, T.w, T.intestazione_h,
                                etich2.join("\t"), ST_INT,
                                T.corpo_intestazione, T.intestazione_h,
                                T.prima_linea_intestazione);
                tabula(ib.paragraphs[0], T.colonne_x, T.w, true);

                // righe
                var righe = [];
                for (var v = 0; v < n; v++) {
                    var va = e.varianti[v];
                    righe.push([va.codice, va.modello, va.um, va.mv, va.cf, va.listino].join("\t"));
                }
                if (n) {
                    var rb = blocco(pag, tx, ty + T.intestazione_h, T.w,
                                    n * T.riga_h + 2, righe.join("\r"), ST_RIG,
                                    T.corpo_riga, T.riga_h, T.prima_linea_riga);
                    var par = rb.paragraphs;
                    for (var q = 0; q < par.length; q++) {
                        tabula(par[q], T.colonne_x, T.w, false);
                        try {
                            var w0 = par[q].words[0];
                            w0.fillColor = VERDE; w0.fontStyle = "Bold";
                            w0.pointSize = T.corpo_codice;
                        } catch (e5) {}
                        try {
                            var ult = par[q].words.item(-1);
                            ult.fontStyle = "Bold"; ult.pointSize = T.corpo_prezzo;
                        } catch (e6) {}
                    }
                    if (rb.overflows) traboccati++;
                }
            }
            // tutti i pezzi del prodotto diventano un oggetto solo
            if (pezzi.length > 1) {
                try {
                    var gr = pag.groups.add(pezzi);
                    gr.label = "pos " + e.posizione + " cod " + e.codice;
                    raggruppati++;
                } catch (eGr) {}
            }
            fatti++;
          } catch (errProd) {
            falliti.push((el[i] ? el[i].codice : i) + ": " + errProd);
          }
        }

        // ---- riga dei prezzi indicativi, una per pagina, nel margine basso ----
        if (NOTA_PREZZI) {
            var G2 = dati.gabbia || {};
            var ph = N(G2.pagina_h, 841.8898), pw = N(G2.pagina_w, 595.2756);
            var mb = N(G2.margine_basso, 34.0157);
            var est2 = N(G2.margine_esterno, 25.5118), int2 = N(G2.margine_interno, 8.5039);
            for (var np in paginaUsata) {
                var pp = paginaUsata[np];
                var sx2 = false;
                try { sx2 = (pp.side === PageSideOptions.LEFT_HAND); } catch (eS) {}
                var x2 = sx2 ? est2 : int2;
                var w2 = pw - est2 - int2;
                var nt = pp.textFrames.add(layer, {
                    geometricBounds: [ph - mb + 9, x2, ph - mb + 22, x2 + w2] });
                try { nt.textFramePreferences.insetSpacing = [0, 0, 0, 0]; } catch (eN1) {}
                nt.contents = NOTA_PREZZI;
                try {
                    var st2 = nt.parentStory;
                    st2.appliedFont = FONT; st2.fontStyle = "Italic";
                    st2.pointSize = 6; st2.leading = 7.5; st2.fillColor = GRIGIO;
                    st2.justification = sx2 ? Justification.LEFT_ALIGN : Justification.RIGHT_ALIGN;
                } catch (eN2) {}
                note++;
            }
        }
    }, ScriptLanguage.JAVASCRIPT, [], UndoModes.ENTIRE_SCRIPT, "Box nativi");

    function tabula(p, xs, larghezza, intest) {
        for (var c = 1; c < xs.length - 2; c++)
            p.tabStops.add({ alignment: TabStopAlignment.CENTER_ALIGN,
                             position: (xs[c] + xs[c + 1]) / 2 });
        p.tabStops.add({ alignment: TabStopAlignment.RIGHT_ALIGN, position: larghezza });
    }

    var secondi = (new Date().getTime() - t0) / 1000;
    ripristina();

    alert("BOX NATIVI COSTRUITI  (script v5, 9 agosto)\n\n" +
          fatti + " prodotti in " + secondi.toFixed(1) + " secondi\n" +
          "= " + (secondi / Math.max(1, fatti)).toFixed(2) + " secondi a prodotto\n\n" +
          (senzaFoto ? senzaFoto + " senza foto\n" : "") +
          (traboccati ? traboccati + " tabelle in eccedenza\n" : "") +
          (specchiate ? specchiate + " box rimessi dal lato giusto della pagina\n" : "") +
          (raggruppati ? raggruppati + " box raggruppati (si spostano interi)\n" : "") +
          (stretti ? stretti + " titoli stretti quel tanto che basta per non tagliarli\n" : "") +
          (note ? note + " righe 'prezzi indicativi'\n" : "") +
          inquadrate + " foto con l'inquadratura: linea + tacca verde + filetto\n" +
          (ricostruite ? "  (" + ricostruite + " ricostruite dallo script: i dati erano vecchi)\n" : "") +
          (falliti.length ? "\nNON RIUSCITI: " + falliti.length + "\n" +
                            falliti.slice(0, 8).join("\n") + "\n" : "") +
          "\nLivello BOX NATIVI: cancellalo per tornare indietro.");

})();
