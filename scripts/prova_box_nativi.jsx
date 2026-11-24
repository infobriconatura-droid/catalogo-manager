/*
    PROVA BOX NATIVI  —  Catalogo Manager v3
    ------------------------------------------------------------
    Costruisce i box come OGGETTI INDESIGN veri (testo modificabile)
    e CRONOMETRA, per sapere quanto costa rigenerare la sezione.

    Le proporzioni sono le stesse dei box a immagine: tutte le misure
    derivano dal disegno a 1158 px riportato in punti.

    USO
      1. app: Posizioni -> Impaginazione -> "Dati per box nativi"
      2. apri il documento InDesign
      3. Finestra > Utilita > Script -> doppio click
      4. scegli _dati.json e quanti prodotti costruire

    Tutto finisce sul livello "BOX NATIVI": cancellalo per tornare indietro.
*/

#target indesign

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

    // ---------------- dati ----------------
    var f = File.openDialog("Scegli _dati.json", "*.json");
    if (!f) { ripristina(); return; }
    f.encoding = "UTF-8"; f.open("r");
    var txt = f.read(); f.close();
    if (txt.charCodeAt(0) === 65279) txt = txt.substring(1);
    var dati = eval("(" + txt + ")");
    var el = dati.elementi;
    if (!el || !el.length) { alert("Nessun elemento nei dati."); ripristina(); return; }

    var quanti = prompt("Il file contiene " + el.length + " prodotti.\n\nQuanti ne costruisco?",
                        String(Math.min(20, el.length)));
    if (quanti === null) { ripristina(); return; }
    quanti = parseInt(quanti, 10);
    if (isNaN(quanti) || quanti < 1) quanti = 20;
    quanti = Math.min(quanti, el.length);

    // ---------------- colori ----------------
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
    var ZEBRA     = tinta("CAT Zebra", 6, 0, 4, 0);
    var NIENTE    = doc.swatches.itemByName("None");

    var FONT = app.fonts.item("Arial");

    // ---------------- stili ----------------
    function stile(nome, prop) {
        var s;
        try { s = doc.paragraphStyles.itemByName(nome); s.name; }
        catch (e) { s = doc.paragraphStyles.add({ name: nome }); }
        for (var k in prop) { try { s[k] = prop[k]; } catch (e2) {} }
        return s;
    }

    // ---------------- geometria (dal disegno a 1158 px) ----------------
    var PX = {
        pad: 36, head: 120, img: 364, riga: 64, intest: 49,
        titolo: 49, titoloMin: 27, desc: 27, descMin: 18,
        th: 24, td: 33, codice: 35, prezzo: 33,
        accento: 3, sotto: 19, gapDesc: 6, gapTab: 24
    };
    var COLS = dati.colonne_tabella;

    var layer;
    try { layer = doc.layers.itemByName("BOX NATIVI"); layer.name; }
    catch (e) { layer = doc.layers.add({ name: "BOX NATIVI" }); }

    var maxPag = 0;
    for (var i = 0; i < quanti; i++) if (el[i].pagina > maxPag) maxPag = el[i].pagina;
    var partenza = doc.pages.length + 1;
    while (doc.pages.length < partenza + maxPag - 1) doc.pages.add(LocationOptions.AT_END);

    function testo(pagina, x, y, w, h, contenuto, stileP) {
        var t = pagina.textFrames.add(layer, { geometricBounds: [y, x, y + h, x + w] });
        t.textFramePreferences.insetSpacing = [0, 0, 0, 0];
        t.textFramePreferences.firstBaselineOffset = FirstBaseline.CAP_HEIGHT;
        t.contents = contenuto;
        t.parentStory.appliedParagraphStyle = stileP;
        return t;
    }
    function barra(pagina, x, y, w, h, colore) {
        return pagina.rectangles.add(layer, {
            geometricBounds: [y, x, y + h, x + w],
            strokeWeight: 0, strokeColor: NIENTE, fillColor: colore });
    }

    // ---------------- costruzione ----------------
    var t0 = new Date().getTime();
    var fatti = 0, senzaFoto = 0, traboccati = 0;

    app.doScript(function () {
        for (var i = 0; i < quanti; i++) {
            var e = el[i];
            var pagina = doc.pages[partenza - 2 + e.pagina];
            var S = e.w / 1158;                       // punti per pixel del disegno
            var pad = PX.pad * S;
            var x0 = e.x + pad, x1 = e.x + e.w - pad;
            var interno = x1 - x0;

            // stili dimensionati su questa larghezza (una volta sola)
            if (i === 0) {
                stile("CAT Titolo", { appliedFont: FONT, fontStyle: "Bold",
                    pointSize: PX.titolo * S, leading: PX.titolo * S * 1.1,
                    fillColor: NERO_K, tracking: 12 });
                stile("CAT Descrizione", { appliedFont: FONT, fontStyle: "Italic",
                    pointSize: PX.desc * S, leading: PX.desc * S * 1.32,
                    fillColor: GRIGIO, justification: Justification.LEFT_ALIGN });
                stile("CAT Intestazione tabella", { appliedFont: FONT, fontStyle: "Bold",
                    pointSize: PX.th * S, leading: PX.intest * S,
                    fillColor: VERDE_MED, tracking: 25 });
                stile("CAT Riga", { appliedFont: FONT, fontStyle: "Regular",
                    pointSize: PX.td * S, leading: PX.riga * S, fillColor: NERO_K });
            }
            var ST_TIT = doc.paragraphStyles.itemByName("CAT Titolo");
            var ST_DES = doc.paragraphStyles.itemByName("CAT Descrizione");
            var ST_INT = doc.paragraphStyles.itemByName("CAT Intestazione tabella");
            var ST_RIG = doc.paragraphStyles.itemByName("CAT Riga");

            var head = PX.head * S;
            var sotto = PX.sotto * S;
            var nVar = e.varianti.length;
            var hTab = PX.intest * S + nVar * PX.riga * S;
            var yTab = e.y + e.h - sotto - hTab;

            // ---- logo ----
            var largLogo = 0;
            if (e.logo) {
                var maxL = 190 * S * 1.072, maxA = 78 * S * 1.072;
                var lg = pagina.rectangles.add(layer, {
                    geometricBounds: [e.y + 18 * S, x1 - maxL, e.y + 18 * S + maxA, x1],
                    strokeWeight: 0, strokeColor: NIENTE, fillColor: NIENTE });
                try {
                    lg.place(File(e.logo));
                    lg.fit(FitOptions.PROPORTIONALLY);
                    lg.fit(FitOptions.FRAME_TO_CONTENT);
                    lg.geometricBounds = [lg.geometricBounds[0], x1 - (lg.geometricBounds[3] - lg.geometricBounds[1]),
                                          lg.geometricBounds[2], x1];
                    largLogo = (lg.geometricBounds[3] - lg.geometricBounds[1]) + 10 * S;
                } catch (err) { lg.remove(); }
            }

            // ---- titolo: si rimpicciolisce finche' sta su una riga ----
            var tf = testo(pagina, x0, e.y + 22 * S, interno - largLogo, PX.titolo * S * 1.4,
                           e.titolo, ST_TIT);
            var corpo = PX.titolo * S;
            while (tf.lines.length > 1 && corpo > PX.titoloMin * S) {
                corpo -= 0.4;
                tf.parentStory.pointSize = corpo;
                tf.parentStory.leading = corpo * 1.1;
            }

            // ---- filetto accento ----
            barra(pagina, x0, e.y + head - 14 * S, interno, PX.accento * S, ACCENTO);

            // ---- descrizione: appoggiata sopra la tabella ----
            var descFondo = yTab - PX.gapTab * S;
            var df = testo(pagina, x0, e.y + head, interno, descFondo - (e.y + head),
                           e.descrizione, ST_DES);
            df.textFramePreferences.verticalJustification = VerticalJustification.BOTTOM_ALIGN;
            var righeDesc = df.lines.length;
            var corpoD = PX.desc * S;
            while (righeDesc > 5 && corpoD > PX.descMin * S) {
                corpoD -= 0.3;
                df.parentStory.pointSize = corpoD;
                df.parentStory.leading = corpoD * 1.32;
                righeDesc = df.lines.length;
            }
            var altDesc = righeDesc * corpoD * 1.32 + 2;
            df.geometricBounds = [descFondo - altDesc, x0, descFondo, x1];
            if (righeDesc <= 2) df.parentStory.justification = Justification.CENTER_ALIGN;

            // ---- foto: quello che resta fra intestazione e descrizione ----
            var fotoAlto = e.y + head, fotoBasso = descFondo - altDesc - PX.gapDesc * S;
            if (e.foto && fotoBasso - fotoAlto > 12) {
                var fr = pagina.rectangles.add(layer, {
                    geometricBounds: [fotoAlto, x0 + 20 * S, fotoBasso, x1 - 20 * S],
                    strokeWeight: 0, strokeColor: NIENTE, fillColor: NIENTE });
                try { fr.place(File(e.foto)); fr.fit(FitOptions.PROPORTIONALLY); }
                catch (err) { senzaFoto++; fr.remove(); }
            } else if (!e.foto) senzaFoto++;

            // ---- elenco varianti: testo tabulato ----
            var xs = [], acc = 0;
            for (var c = 0; c < COLS.length; c++) { xs.push(acc); acc += interno * COLS[c][1]; }
            xs.push(interno);

            var righe = [];
            var intest = [];
            for (var c2 = 0; c2 < COLS.length; c2++) intest.push(COLS[c2][0]);
            righe.push(intest.join("\t"));
            for (var v = 0; v < nVar; v++) {
                var va = e.varianti[v];
                righe.push([va.codice, va.modello, va.um, va.mv, va.cf, va.listino].join("\t"));
            }

            var tb = testo(pagina, x0, yTab, interno, hTab + 2, righe.join("\r"), ST_RIG);
            var par = tb.paragraphs;
            par[0].appliedParagraphStyle = ST_INT;

            for (var q = 0; q < par.length; q++) {
                var p = par[q];
                for (var c3 = 1; c3 < COLS.length - 1; c3++)
                    p.tabStops.add({ alignment: TabStopAlignment.CENTER_ALIGN,
                                     position: (xs[c3] + xs[c3 + 1]) / 2 });
                p.tabStops.add({ alignment: TabStopAlignment.RIGHT_ALIGN, position: interno });
                if (q > 0) {
                    // codice in verde e grassetto, prezzo in grassetto
                    try {
                        var t1 = p.words[0];
                        t1.fillColor = VERDE; t1.fontStyle = "Bold";
                        t1.pointSize = PX.codice * S;
                    } catch (e3) {}
                    if (q % 2 === 0) {                       // righe alternate
                        try { p.shadingOn = true; p.shadingColor = ZEBRA; } catch (e4) {}
                    }
                }
            }
            if (tb.overflows) traboccati++;

            // ---- filetti tabella ----
            barra(pagina, x0, yTab - 4 * S, interno, 4 * S, VERDE);
            barra(pagina, x0, e.y + e.h - sotto + 2 * S, interno, 2 * S, VERDE_MED);

            fatti++;
        }
    }, ScriptLanguage.JAVASCRIPT, [], UndoModes.ENTIRE_SCRIPT, "Prova box nativi");

    var secondi = (new Date().getTime() - t0) / 1000;
    ripristina();

    var perProdotto = secondi / Math.max(1, fatti);
    var stima = perProdotto * el.length / 60;

    alert("PROVA COMPLETATA\n\n" +
          fatti + " prodotti in " + secondi.toFixed(1) + " secondi\n" +
          "= " + perProdotto.toFixed(2) + " secondi a prodotto\n\n" +
          "Stima su tutti i " + el.length + " prodotti:\n" +
          "circa " + stima.toFixed(1) + " minuti\n\n" +
          (senzaFoto ? senzaFoto + " senza foto\n" : "") +
          (traboccati ? traboccati + " tabelle che non ci stanno\n" : "") +
          "\nLivello BOX NATIVI: cancellalo per tornare indietro.");

})();
