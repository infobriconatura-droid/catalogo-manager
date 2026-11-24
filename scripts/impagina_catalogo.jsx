/*
    IMPAGINA CATALOGO  —  Catalogo Manager v3
    ------------------------------------------------------------
    Legge _piano.csv (generato dall'app) e piazza ogni box alla sua
    coordinata esatta, a grandezza reale (100%).

    COME SI USA
      1. apri in InDesign il documento della sezione
      2. Finestra > Utilita > Script  ->  doppio click su questo file
      3. scegli il file _piano.csv dentro export_catalogo/NOMESEZIONE/
      4. indica da quale pagina partire

    Le pagine nuove vengono AGGIUNTE: il documento esistente non viene
    toccato, cosi puoi confrontare e cancellare le vecchie quando vuoi.
*/

#target indesign

(function () {

    if (app.documents.length === 0) {
        alert("Apri prima il documento InDesign della sezione.");
        return;
    }
    var doc = app.activeDocument;

    // --- unita di misura: punti, origine sulla pagina ------------------
    var oldUnit = app.scriptPreferences.measurementUnit;
    app.scriptPreferences.measurementUnit = MeasurementUnits.POINTS;
    var vp = doc.viewPreferences;
    var oldH = vp.horizontalMeasurementUnits, oldV = vp.verticalMeasurementUnits;
    var oldOrigin = vp.rulerOrigin;
    vp.horizontalMeasurementUnits = MeasurementUnits.POINTS;
    vp.verticalMeasurementUnits = MeasurementUnits.POINTS;
    vp.rulerOrigin = RulerOrigin.PAGE_ORIGIN;

    function ripristina() {
        vp.horizontalMeasurementUnits = oldH;
        vp.verticalMeasurementUnits = oldV;
        vp.rulerOrigin = oldOrigin;
        app.scriptPreferences.measurementUnit = oldUnit;
    }

    // --- 1. il piano ---------------------------------------------------
    var csv = File.openDialog("Scegli il file _piano.csv", "*.csv");
    if (!csv) { ripristina(); return; }
    var cartella = csv.parent;

    csv.encoding = "UTF-8";
    csv.open("r");
    var testo = csv.read();
    csv.close();
    if (testo.charCodeAt(0) === 65279) testo = testo.substring(1);   // BOM

    var linee = testo.split(/\r\n|\r|\n/);
    var intest = linee[0].split(";");
    var col = {};
    for (var i = 0; i < intest.length; i++) col[intest[i]] = i;

    var righe = [];
    for (var i = 1; i < linee.length; i++) {
        if (!linee[i] || linee[i].replace(/\s/g, "") === "") continue;
        var c = linee[i].split(";");
        righe.push({
            pagina: parseInt(c[col["Pagina"]], 10),
            colonna: parseInt(c[col["Colonna"]], 10),
            tipo: (col["Tipo"] !== undefined ? c[col["Tipo"]] : "colonna"),
            posizione: c[col["Posizione"]],
            codice: c[col["Codice"]],
            file: c[col["File"]],
            x: parseFloat(c[col["X_pt"]]),
            y: parseFloat(c[col["Y_pt"]]),
            w: parseFloat(c[col["W_pt"]]),
            h: parseFloat(c[col["H_pt"]])
        });
    }
    if (righe.length === 0) { alert("Il piano e vuoto."); ripristina(); return; }

    var nPagine = 0;
    for (var i = 0; i < righe.length; i++) if (righe[i].pagina > nPagine) nPagine = righe[i].pagina;

    // --- 2. da dove partire --------------------------------------------
    var partenza = prompt(
        "Il piano contiene " + righe.length + " box su " + nPagine + " pagine.\n\n" +
        "Da quale pagina del documento comincio?\n" +
        "(le pagine che mancano vengono aggiunte in fondo)",
        String(doc.pages.length + 1));
    if (partenza === null) { ripristina(); return; }
    partenza = parseInt(partenza, 10);
    if (isNaN(partenza) || partenza < 1) partenza = doc.pages.length + 1;

    var serve = partenza + nPagine - 1;
    while (doc.pages.length < serve) doc.pages.add(LocationOptions.AT_END);

    // --- 3. da che lato cade la pagina ------------------------------------
    // Il CSV porta la x supponendo che la prima pagina del piano sia una
    // destra. Se il documento e' lungo diversamente, tutto si specchia e la
    // prima colonna finisce sotto la banda verde. Qui la decide InDesign.
    var GAB = { esterno: 25.5118, interno: 8.5039, colonna: 277.7712, grondaia: 5.7175 };
    function ascissa(pagina, r) {
        var sinistra = false;
        try { sinistra = (pagina.side === PageSideOptions.LEFT_HAND); } catch (err) {}
        if (r.tipo === "fascia") return sinistra ? GAB.esterno : 0;
        var col = isNaN(r.colonna) ? 1 : r.colonna;
        if (col < 1) col = 1;
        return (sinistra ? GAB.esterno : GAB.interno) +
               (col - 1) * (GAB.colonna + GAB.grondaia);
    }

    // --- 4. piazza -------------------------------------------------------
    var messi = 0, mancanti = [], specchiate = 0;
    var layer;
    try { layer = doc.layers.itemByName("BOX CATALOGO"); layer.name; }
    catch (e) { layer = doc.layers.add({ name: "BOX CATALOGO" }); }

    app.doScript(function () {
        for (var i = 0; i < righe.length; i++) {
            var r = righe[i];
            var f = File(cartella.fsName + "/" + r.file);
            if (!f.exists) { mancanti.push(r.file); continue; }

            var pagina = doc.pages[partenza - 2 + r.pagina];
            var rx = ascissa(pagina, r);
            if (Math.abs(rx - r.x) > 0.5) specchiate++;
            var rect = pagina.rectangles.add(layer, {
                geometricBounds: [r.y, rx, r.y + r.h, rx + r.w],
                strokeWeight: 0,
                strokeColor: doc.swatches.itemByName("None"),
                fillColor: doc.swatches.itemByName("None"),
                label: "pos " + r.posizione + " cod " + r.codice
            });
            rect.place(f);
            // il JPG e generato esattamente alla misura del riquadro:
            // adattandolo al riquadro resta al 100% senza deformarsi
            rect.fit(FitOptions.CONTENT_TO_FRAME);
            messi++;
        }
    }, ScriptLanguage.JAVASCRIPT, [], UndoModes.ENTIRE_SCRIPT, "Impagina catalogo");

    ripristina();

    var msg = "Fatto.\n\n" + messi + " box piazzati su " + nPagine +
              " pagine, dalla pagina " + partenza + ".";
    if (specchiate) msg += "\n\n" + specchiate + " box rimessi dal lato giusto della pagina.";
    if (mancanti.length) {
        msg += "\n\nMancano " + mancanti.length + " file:\n" +
               mancanti.slice(0, 12).join("\n");
        if (mancanti.length > 12) msg += "\n...";
    }
    alert(msg);

})();
