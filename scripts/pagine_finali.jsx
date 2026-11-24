/*
    PARTE FINALE DEL CATALOGO  —  Catalogo Manager v3
    ============================================================
    Le pagine che chiudono il volume, nello stesso stile delle
    pagine editoriali di apertura:

       1. INDICE ALFABETICO  (multicolonna, si impagina da solo
          su quante pagine servono, con le lettere di richiamo
          e i puntini fino al numero di pagina)
       2. I NOSTRI MARCHI    (griglia con tutti i loghi)
       3. RETE COMMERCIALE   (aree, agenti, recapiti)
       4. NOTE               (pagine rigate, per il cliente)
       5. COLOPHON           (ultima pagina: logo, pay-off, note legali)

    L'INDICE SI PRENDE DAI DATI VERI
       nell'app: Impaginazione -> "Indice alfabetico"
       ti scrive  indice_alfabetico.txt  con dentro
            voce <TAB> pagine
       e le lettere da sole su una riga. Qui lo scegli e basta.
       Se non lo scegli, costruisco lo scheletro con delle voci
       finte, cosi vedi la forma.

    USO
       Finestra > Utilita > Script -> doppio click.
       Tutto sul livello "FINALE": cancellalo per rifare.
*/

#target indesign

// =====================================================================
// CONTENUTI
// =====================================================================
var RETE = {
    occhiello: "dove siamo",
    t1: "RETE",
    t2: "COMMERCIALE",
    intro: "Ogni zona ha il suo referente. Se non sai chi chiamare, chiama la sede: " +
           "ti mettiamo in contatto con l'agente della tua area.",
    aree: [
        { t: "Calabria nord",     n: "XXX XXX",  tel: "000 0000000" },
        { t: "Calabria sud",      n: "XXX XXX",  tel: "000 0000000" },
        { t: "Basilicata",        n: "XXX XXX",  tel: "000 0000000" },
        { t: "Puglia",            n: "XXX XXX",  tel: "000 0000000" },
        { t: "Campania",          n: "XXX XXX",  tel: "000 0000000" },
        { t: "Sicilia",           n: "XXX XXX",  tel: "000 0000000" }
    ],
    piede: "Vuoi diventare nostro cliente? commerciale@pugliesegroupsrl.com · tel. 0984 000000"
};

var NOTE_PAGINE = 2;          // quante pagine rigate
var NOTE_TITOLO = "NOTE";

var COLOPHON = {
    payoff: "Ci vediamo\rall'edizione prossima.",
    dati: "Pugliese Group S.r.l.\r" +
          "Contrada Fria, 8 — 87043 Bisignano (CS)\r" +
          "P. IVA 00000000000 — REA CS-000000\r" +
          "tel. 0984 000000 · info@pugliesegroupsrl.com\r" +
          "www.pugliesegroupsrl.com",
    legale: "Catalogo generale, edizione 2026. Chiuso in redazione nel mese di 0000. " +
            "Prezzi indicativi, IVA esclusa, soggetti a variazione senza preavviso. " +
            "Fotografie, misure e dati tecnici non sono impegnativi. " +
            "I marchi citati appartengono ai rispettivi proprietari. " +
            "Riproduzione, anche parziale, vietata."
};

var MARCHI_TITOLO = { occhiello: "fornitori", t1: "I NOSTRI", t2: "MARCHI" };

// ---- stile (uguale alle pagine editoriali) --------------------------
var BLU     = [90, 55, 0, 0];
var GR_TIT  = [0, 0, 0, 82];
var GR_TXT  = [0, 0, 0, 74];
var GR_TENUE= [0, 0, 0, 12];

var MARG = { sopra: 24, sotto: 20, interno: 20, esterno: 16 };   // mm
var MM = 2.834645669;

var IND_COLONNE = 2;          // colonne dell'indice alfabetico
// (2 e non 3: le voci sono i titoli interi dei prodotti, e sono lunghi)
var IND_CORPO   = 7.6;
var IND_INTER   = 10.4;

// =====================================================================
(function () {

    if (app.documents.length === 0) { alert("Apri prima il documento InDesign."); return; }
    var doc = app.activeDocument;

    var oldUnit = app.scriptPreferences.measurementUnit;
    app.scriptPreferences.measurementUnit = MeasurementUnits.POINTS;
    var vp = doc.viewPreferences;
    var oldH = vp.horizontalMeasurementUnits, oldV = vp.verticalMeasurementUnits, oldO = vp.rulerOrigin;
    vp.horizontalMeasurementUnits = MeasurementUnits.POINTS;
    vp.verticalMeasurementUnits = MeasurementUnits.POINTS;
    vp.rulerOrigin = RulerOrigin.PAGE_ORIGIN;
    function ripristina() {
        try {
            vp.horizontalMeasurementUnits = oldH; vp.verticalMeasurementUnits = oldV;
            vp.rulerOrigin = oldO;
        } catch (e) {}
        app.scriptPreferences.measurementUnit = oldUnit;
    }

    var PW = doc.documentPreferences.pageWidth;
    var PH = doc.documentPreferences.pageHeight;

    var scelta = chiedi();
    if (!scelta) { ripristina(); return; }

    function tinta(nome, v) {
        var s;
        try { s = doc.colors.itemByName(nome); s.name; }
        catch (e) { s = doc.colors.add({ name: nome, model: ColorModel.PROCESS,
                                         space: ColorSpace.CMYK, colorValue: v }); }
        return s;
    }
    var C_BLU   = tinta("ED Blu", BLU);
    var C_TIT   = tinta("ED Grigio titolo", GR_TIT);
    var C_TXT   = tinta("ED Grigio testo", GR_TXT);
    var C_TENUE = tinta("ED Grigio tenue", GR_TENUE);
    var BIANCO  = doc.swatches.itemByName("Paper");
    var NIENTE  = doc.swatches.itemByName("None");

    var FAM = null;
    var candidati = ["Montserrat", "Poppins", "Gotham", "Futura", "Century Gothic", "Arial"];
    for (var q = 0; q < candidati.length && !FAM; q++) {
        try { if (app.fonts.item(candidati[q] + "\tRegular").isValid) FAM = candidati[q]; } catch (eF) {}
    }
    if (!FAM) FAM = "Arial";
    function car(stile) {
        var prova = [stile, "Regular", "Bold"];
        for (var i = 0; i < prova.length; i++) {
            try {
                var f = app.fonts.item(FAM + "\t" + prova[i]);
                if (f.isValid) return f;
            } catch (e) {}
        }
        return app.fonts.item("Arial");
    }
    var F_LIGHT = car("Light"), F_REG = car("Regular"),
        F_MED = car("Medium"), F_BOLD = car("Bold"), F_SEMI = car("SemiBold");

    var layer;
    try { layer = doc.layers.itemByName("FINALE"); layer.name; }
    catch (e) { layer = doc.layers.add({ name: "FINALE" }); }

    var avvisi = [], fatte = [], pagineIndice = 0;

    // =================================================================
    // attrezzi (gli stessi delle pagine editoriali)
    // =================================================================
    function nuovaPag() { return doc.pages.add(LocationOptions.AT_END); }

    function G(p) {
        var sinistra = false;
        try { sinistra = (p.side === PageSideOptions.LEFT_HAND); } catch (e) {}
        var mInt = MARG.interno * MM, mEst = MARG.esterno * MM;
        var x0 = sinistra ? mEst : mInt;
        var x1 = PW - (sinistra ? mInt : mEst);
        return { x0: x0, x1: x1, w: x1 - x0,
                 y0: MARG.sopra * MM, y1: PH - MARG.sotto * MM,
                 h: PH - (MARG.sopra + MARG.sotto) * MM, sinistra: sinistra };
    }
    function rett(p, x0, y0, x1, y1, riemp, bordo, peso) {
        return p.rectangles.add(layer, {
            geometricBounds: [y0, x0, y1, x1],
            fillColor: riemp || NIENTE, strokeColor: bordo || NIENTE, strokeWeight: peso || 0
        });
    }
    function txt(p, x0, y0, x1, y1, contenuto, o) {
        o = o || {};
        var t = p.textFrames.add(layer, { geometricBounds: [y0, x0, y1, x1] });
        t.contents = contenuto;
        try { t.textFramePreferences.insetSpacing = [0, 0, 0, 0]; } catch (e1) {}
        try { t.textFramePreferences.ignoreWrap = true; } catch (e2) {}
        try {
            t.textFramePreferences.verticalJustification =
                o.centraV ? VerticalJustification.CENTER_ALIGN : VerticalJustification.TOP_ALIGN;
        } catch (e3) {}
        try {
            var s = t.parentStory;
            s.appliedFont = o.font || F_REG;
            s.pointSize = o.corpo || 9.5;
            s.leading = o.interlinea || (o.corpo || 9.5) * 1.45;
            s.fillColor = o.colore || C_TXT;
            s.justification = o.allinea || Justification.LEFT_ALIGN;
            s.tracking = o.tracking || 0;
            s.hyphenation = (o.sillaba === true);
        } catch (e5) {}
        adatta(t, o.etichetta || contenuto.substring(0, 18), o.minimo, o.cresci);
        return t;
    }
    function adatta(t, etichetta, minimo, cresci) {
        try { t.recompose(); } catch (e) {}
        var giri = 0;
        try {
            while (t.overflows && giri < 90) {
                var s = t.parentStory;
                var nuovo = s.pointSize - 0.25;
                if (nuovo < (minimo || 6)) break;
                var rap = s.leading / s.pointSize;
                s.pointSize = nuovo; s.leading = nuovo * rap;
                try { t.recompose(); } catch (e2) {}
                giri++;
            }
        } catch (e3) {}
        var resta = false;
        try { resta = t.overflows; } catch (e4) {}
        if (resta && cresci !== false) {
            try {
                t.textFramePreferences.autoSizingReferencePoint = AutoSizingReferenceEnum.TOP_CENTER_POINT;
                t.textFramePreferences.autoSizingType = AutoSizingTypeEnum.HEIGHT_ONLY;
                t.recompose();
                resta = t.overflows;
            } catch (e5) {}
        }
        if (resta) avvisi.push("testo ancora in eccedenza: " + etichetta);
    }
    function testata(p, occhiello, r1, r2, numero) {
        var g = G(p);
        var y = g.y0;
        txt(p, g.x0, y, g.x0 + g.w * 0.7, y + 12, occhiello.toUpperCase(),
            { corpo: 7.5, interlinea: 10, font: F_SEMI, colore: C_BLU, tracking: 320,
              etichetta: "occhiello", cresci: false });
        y += 15;
        rett(p, g.x0, y, g.x0 + 46, y + 1.4, C_BLU);
        y += 22;
        var corpo = 30;
        var t = p.textFrames.add(layer, {
            geometricBounds: [y, g.x0, y + corpo * 1.1 * 2 + 8, g.x1]
        });
        t.contents = r1 + "\r" + r2;
        try { t.textFramePreferences.insetSpacing = [0, 0, 0, 0]; } catch (e1) {}
        try {
            var s = t.parentStory;
            s.appliedFont = F_LIGHT; s.pointSize = corpo; s.leading = corpo * 1.08;
            s.fillColor = C_TIT; s.tracking = 10; s.hyphenation = false;
        } catch (e2) {}
        try { t.paragraphs[1].appliedFont = F_BOLD; t.paragraphs[1].fillColor = C_BLU; } catch (e3) {}
        adatta(t, "titolo " + r1, 16);
        y = t.geometricBounds[2] + 18;
        if (numero) {
            var nx = g.sinistra ? g.x0 : g.x1 - 70;
            var tn = txt(p, nx, g.y0 - 6, nx + 70, g.y0 + 66, numero,
                         { corpo: 58, font: F_LIGHT, colore: C_TENUE, tracking: -20,
                           allinea: g.sinistra ? Justification.LEFT_ALIGN : Justification.RIGHT_ALIGN,
                           etichetta: "numero", cresci: false });
            try { tn.sendToBack(); } catch (e4) {}
        }
        return y;
    }
    function piede(p, etichetta) {
        var g = G(p);
        var y = PH - MARG.sotto * MM + 12;
        rett(p, g.x0, y, g.x1, y + 0.5, C_TENUE);
        var largo = 150;
        var xn = g.sinistra ? g.x0 : g.x1 - largo;
        var t = p.textFrames.add(layer, { geometricBounds: [y + 6, xn, y + 22, xn + largo] });
        t.contents = " ";
        try { t.textFramePreferences.insetSpacing = [0, 0, 0, 0]; } catch (e1) {}
        try {
            var s = t.parentStory;
            s.appliedFont = F_SEMI; s.pointSize = 8; s.leading = 10;
            s.fillColor = C_BLU; s.tracking = 60;
            s.justification = g.sinistra ? Justification.LEFT_ALIGN : Justification.RIGHT_ALIGN;
        } catch (e2) {}
        try {
            t.contents = "";
            t.insertionPoints[0].contents = SpecialCharacters.AUTO_PAGE_NUMBER;
        } catch (e3) { t.contents = "•"; }
        if (etichetta) {
            var xe = g.sinistra ? g.x1 - g.w * 0.7 : g.x0;
            txt(p, xe, y + 6, xe + g.w * 0.7, y + 22, etichetta.toUpperCase(),
                { corpo: 6.5, interlinea: 9, font: F_REG, colore: C_TXT, tracking: 220,
                  allinea: g.sinistra ? Justification.RIGHT_ALIGN : Justification.LEFT_ALIGN,
                  etichetta: "piede", cresci: false });
        }
    }

    // =================================================================
    // 1. INDICE ALFABETICO
    // =================================================================
    function leggiIndice(file) {
        if (!file) return null;
        file.encoding = "UTF-8";
        if (!file.open("r")) return null;
        var s = file.read(); file.close();
        if (s.charCodeAt(0) === 65279) s = s.substring(1);
        s = s.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
        var righe = s.split("\n"), fuori = [];
        for (var i = 0; i < righe.length; i++) {
            var r = righe[i];
            if (!r || !r.replace(/^\s+|\s+$/g, "")) continue;
            fuori.push(r);
        }
        return fuori;
    }

    function indiceFinto() {
        var f = [];
        var lettere = "ABCDEFGHILMNOPQRSTUVZ";
        var esempi = ["Accessorio", "Attrezzo", "Bidone", "Cavo", "Chiave", "Decespugliatore",
                      "Filo", "Guanto", "Manico", "Pompa", "Raccordo", "Scala", "Tubo", "Vanga"];
        for (var i = 0; i < lettere.length; i++) {
            f.push(lettere.charAt(i));
            for (var k = 0; k < 6; k++)
                f.push(esempi[(i + k) % esempi.length] + " di prova " + (k + 1) +
                       "\t" + (100 + i * 7 + k));
        }
        return f;
    }

    function pagIndice(righe) {
        var p = nuovaPag();
        var g = G(p);
        var y = testata(p, "consultazione", "INDICE", "ALFABETICO", "");

        var t = p.textFrames.add(layer, { geometricBounds: [y, g.x0, g.y1, g.x1] });
        try {
            t.textFramePreferences.textColumnCount = IND_COLONNE;
            t.textFramePreferences.textColumnGutter = 5 * MM;
            t.textFramePreferences.insetSpacing = [0, 0, 0, 0];
        } catch (e1) {}
        t.contents = righe.join("\r");
        stileIndice(t, g);
        piede(p, "indice alfabetico");
        pagineIndice = 1;

        // continua su quante pagine servono
        var prec = t, giri = 0;
        while (prec.overflows && giri < 60) {
            var p2 = nuovaPag();
            var g2 = G(p2);
            var t2 = p2.textFrames.add(layer, { geometricBounds: [g2.y0, g2.x0, g2.y1, g2.x1] });
            try {
                t2.textFramePreferences.textColumnCount = IND_COLONNE;
                t2.textFramePreferences.textColumnGutter = 5 * MM;
                t2.textFramePreferences.insetSpacing = [0, 0, 0, 0];
            } catch (e2) {}
            prec.nextTextFrame = t2;
            try { t2.recompose(); } catch (e3) {}
            piede(p2, "indice alfabetico");
            prec = t2; giri++; pagineIndice++;
        }
        if (prec.overflows) avvisi.push("l'indice non e' finito: troppe voci, alza le colonne o abbassa il corpo");
        fatte.push("Indice alfabetico (" + pagineIndice + " pagine, " + righe.length + " righe)");
    }

    function stileIndice(t, g) {
        var largheColonna = (g.w - (IND_COLONNE - 1) * 5 * MM) / IND_COLONNE;
        var s = t.parentStory;
        try {
            s.appliedFont = F_REG;
            s.pointSize = IND_CORPO;
            s.leading = IND_INTER;
            s.fillColor = C_TXT;
            s.hyphenation = false;
            s.justification = Justification.LEFT_ALIGN;
            s.rightIndent = 0;
        } catch (e1) {}
        // tabulazione con i puntini fino al numero di pagina.
        // Il numero sta in fondo alla colonna; se il titolo e' lungo e va a
        // capo, la seconda riga rientra, cosi' si capisce che e' la stessa voce.
        try {
            s.tabList = [{ alignment: TabStopAlignment.RIGHT_ALIGN,
                           position: largheColonna,
                           leader: " ." }];
            s.leftIndent = 9;
            s.firstLineIndent = -9;
        } catch (e2) {}
        // le lettere: riga con un solo carattere
        try {
            for (var k = 0; k < s.paragraphs.length; k++) {
                var pa = s.paragraphs[k];
                var c = pa.contents.replace(/[\r\n\t ]+$/g, "");
                if (c.length === 1) {
                    pa.appliedFont = F_BOLD;
                    pa.pointSize = IND_CORPO + 3;
                    pa.leading = IND_INTER + 6;
                    pa.fillColor = C_BLU;
                    pa.spaceBefore = (k === 0) ? 0 : 8;
                    pa.spaceAfter = 2;
                    pa.tracking = 60;
                    pa.keepWithNext = 2;
                    pa.leftIndent = 0;
                    pa.firstLineIndent = 0;
                }
            }
        } catch (e3) {}
        try { t.recompose(); } catch (e4) {}
    }

    // =================================================================
    // 2. I NOSTRI MARCHI
    // =================================================================
    function leggiMarchi(file) {
        if (!file) return null;
        file.encoding = "UTF-8";
        if (!file.open("r")) return null;
        var s = file.read(); file.close();
        if (s.charCodeAt(0) === 65279) s = s.substring(1);
        var dati;
        try { dati = eval("(" + s + ")"); } catch (e) { return null; }
        var m = (dati && dati.marchi) ? dati.marchi : [];
        var visti = {}, fuori = [];
        for (var i = 0; i < m.length; i++) {
            var percorso = m[i].file || "";
            if (!percorso) continue;
            var chiave = (m[i].nome || m[i].logo || percorso).toUpperCase();
            if (visti[chiave]) continue;       // lo stesso marchio una volta sola
            visti[chiave] = true;
            fuori.push({ file: new File(percorso),
                         nome: (m[i].nome || "").replace(/\s{2,}/g, " ") });
        }
        return fuori;
    }

    function pagMarchi(voci) {
        // voci = [{file, nome}] dal _marchi.json, oppure niente: griglia vuota
        var col = 4, gutt = 6 * MM, altNome = 13;
        var p = nuovaPag();
        var g = G(p);
        var y = testata(p, MARCHI_TITOLO.occhiello, MARCHI_TITOLO.t1, MARCHI_TITOLO.t2, "");
        var cw = (g.w - (col - 1) * gutt) / col;
        var ch = cw / 2.3;
        var passo = ch + altNome + gutt;

        var righePrima = Math.floor((g.y1 - y) / passo);
        var righeDopo  = Math.floor((g.y1 - g.y0) / passo);
        if (righePrima < 1) righePrima = 1;

        var quanti = voci ? voci.length : righePrima * col;
        var pagine = 1, k = 0, r = 0, yBase = y, righeQui = righePrima;

        while (k < quanti) {
            var c = k % col;
            if (c === 0 && r >= righeQui) {          // pagina piena: se ne apre un'altra
                piede(p, "i nostri marchi");
                p = nuovaPag(); g = G(p);
                yBase = g.y0; righeQui = righeDopo; r = 0; pagine++;
            }
            var bx = g.x0 + c * (cw + gutt);
            var by = yBase + r * passo;

            var box = rett(p, bx, by, bx + cw, by + ch, NIENTE, C_TENUE, 0.5);
            try { box.strokeTint = 60; } catch (e0) {}
            if (voci) {
                var q = rett(p, bx + cw * 0.10, by + ch * 0.14,
                             bx + cw * 0.90, by + ch * 0.86);
                try { q.place(voci[k].file); q.fit(FitOptions.PROPORTIONALLY); } catch (e1) {}
                if (voci[k].nome)
                    txt(p, bx, by + ch + 2, bx + cw, by + ch + altNome, voci[k].nome,
                        { corpo: 5.6, interlinea: 6.6, colore: C_TXT, tracking: 20,
                          allinea: Justification.CENTER_ALIGN,
                          etichetta: "nome marchio", minimo: 4, cresci: false });
            }
            k++;
            if (k % col === 0) r++;
        }
        piede(p, "i nostri marchi");
        fatte.push("I nostri marchi (" + (voci ? voci.length + " marchi su " + pagine +
                   (pagine === 1 ? " pagina" : " pagine") : "griglia vuota") + ")");
    }

    // =================================================================
    // 3. RETE COMMERCIALE
    // =================================================================
    function pagRete() {
        var p = nuovaPag();
        var g = G(p);
        var y = testata(p, RETE.occhiello, RETE.t1, RETE.t2, "");
        txt(p, g.x0, y, g.x1 - g.w * 0.25, y + 40, RETE.intro,
            { corpo: 11.5, interlinea: 17, font: F_LIGHT, etichetta: "intro rete" });
        y += 48;

        var colW = (g.w - 8 * MM) / 2;
        for (var i = 0; i < RETE.aree.length; i++) {
            var c = i % 2, r = Math.floor(i / 2);
            var bx = g.x0 + c * (colW + 8 * MM);
            var by = y + r * 78;
            var a = RETE.aree[i];
            rett(p, bx, by, bx + colW, by + 62, NIENTE, C_TENUE, 0.6);
            rett(p, bx, by, bx + 3, by + 62, C_BLU);
            txt(p, bx + 14, by + 10, bx + colW - 10, by + 24, a.t,
                { corpo: 11, font: F_BOLD, colore: C_TIT, etichetta: "area " + i });
            txt(p, bx + 14, by + 27, bx + colW - 10, by + 40, a.n,
                { corpo: 9.5, font: F_MED, colore: C_TXT, etichetta: "agente " + i });
            txt(p, bx + 14, by + 41, bx + colW - 10, by + 56, "tel. " + a.tel,
                { corpo: 10, font: F_MED, colore: C_BLU, etichetta: "tel area " + i });
        }
        var yb = y + 3 * 78 + 8;
        rett(p, g.x0, yb, g.x1, yb + 44, C_BLU);
        txt(p, g.x0 + 16, yb + 14, g.x1 - 16, yb + 38, RETE.piede,
            { corpo: 10, font: F_MED, colore: BIANCO, etichetta: "piede rete" });
        piede(p, "rete commerciale");
        fatte.push("Rete commerciale");
    }

    // =================================================================
    // 4. NOTE
    // =================================================================
    function pagNote(quante) {
        for (var k = 0; k < quante; k++) {
            var p = nuovaPag();
            var g = G(p);
            txt(p, g.x0, g.y0, g.x1, g.y0 + 16, NOTE_TITOLO,
                { corpo: 9, font: F_SEMI, colore: C_BLU, tracking: 320, etichetta: "note" });
            rett(p, g.x0, g.y0 + 20, g.x0 + 46, g.y0 + 21.4, C_BLU);
            var y = g.y0 + 44, passo = 22;
            while (y < g.y1) {
                rett(p, g.x0, y, g.x1, y + 0.4, C_TENUE);
                y += passo;
            }
            piede(p, "note");
        }
        fatte.push("Note (" + quante + " pagine)");
    }

    // =================================================================
    // 5. COLOPHON
    // =================================================================
    function pagColophon(logo) {
        var p = nuovaPag();
        var g = G(p);

        var t = txt(p, g.x0, PH * 0.24, g.x1, PH * 0.24 + 110, COLOPHON.payoff,
                    { corpo: 24, interlinea: 31, font: F_LIGHT, colore: C_TIT,
                      etichetta: "payoff finale", minimo: 13 });
        var gb = t.geometricBounds;
        rett(p, g.x0, gb[2] + 20, g.x0 + 46, gb[2] + 21.4, C_BLU);

        if (logo) {
            var lw = g.w * 0.34;
            var lo = rett(p, g.x0, PH * 0.52, g.x0 + lw, PH * 0.52 + 70);
            try { lo.place(logo); lo.fit(FitOptions.PROPORTIONALLY);
                  lo.fit(FitOptions.FRAME_TO_CONTENT); } catch (e1) {}
        }

        txt(p, g.x0, PH * 0.66, g.x0 + g.w * 0.5, PH * 0.66 + 90, COLOPHON.dati,
            { corpo: 9.5, interlinea: 15, font: F_MED, colore: C_TIT, etichetta: "dati" });
        txt(p, g.x0 + g.w * 0.55, PH * 0.66, g.x1, g.y1 - 10, COLOPHON.legale,
            { corpo: 7.6, interlinea: 11.5, colore: C_TXT, sillaba: true, etichetta: "legale" });

        rett(p, g.x0, g.y1 - 2, g.x1, g.y1 - 1.4, C_TENUE);
        fatte.push("Colophon");
    }

    // =================================================================
    app.doScript(function () {
        if (scelta.v[0]) pagIndice(scelta.righe || indiceFinto());
        if (scelta.v[1]) pagMarchi(scelta.loghi);
        if (scelta.v[2]) pagRete();
        if (scelta.v[3]) pagNote(scelta.note);
        if (scelta.v[4]) pagColophon(scelta.logo);
    }, ScriptLanguage.JAVASCRIPT, [], UndoModes.ENTIRE_SCRIPT, "Parte finale");

    ripristina();

    alert("Parte finale costruita.\n\n" +
          "Carattere: " + FAM + "\n\n" +
          "Fatte:\n· " + fatte.join("\n· ") +
          (avvisi.length ? "\n\nDA GUARDARE\n· " + avvisi.join("\n· ") : "") +
          "\n\nDA COMPLETARE A MANO\n" +
          "· i nomi degli agenti e i loro numeri\n" +
          "· partita IVA, REA e mese di chiusura in redazione\n" +
          (scelta.righe ? "" : "· l'indice adesso e' finto: generalo dall'app e rifallo\n") +
          "\nTutto il testo e' vivo. Livello FINALE: cancellalo per rifare.");

    // =================================================================
    function chiedi() {
        var w = new Window("dialog", "Parte finale — Pugliese Group");
        w.alignChildren = "fill";

        var pnl = w.add("panel", undefined, "Che cosa costruisco");
        pnl.alignChildren = "left"; pnl.margins = 14;
        var nomi = ["1 · indice alfabetico",
                    "2 · i nostri marchi (griglia di loghi)",
                    "3 · rete commerciale",
                    "4 · pagine di note",
                    "5 · colophon (ultima pagina)"];
        var cb = [];
        for (var i = 0; i < nomi.length; i++) {
            cb[i] = pnl.add("checkbox", undefined, nomi[i]);
            cb[i].value = true;
        }
        var gN = pnl.add("group");
        gN.add("statictext", undefined, "pagine di note:");
        var eN = gN.add("edittext", undefined, String(NOTE_PAGINE)); eN.characters = 4;

        var pnl2 = w.add("panel", undefined, "File");
        pnl2.margins = 14; pnl2.alignChildren = "left";
        var c1 = pnl2.add("checkbox", undefined, "scegli indice_alfabetico.txt (generato dall'app)");
        var c2 = pnl2.add("checkbox", undefined, "scegli _marchi.json (elenco dei marchi)");
        var c3 = pnl2.add("checkbox", undefined, "scegli il logo per l'ultima pagina");
        c1.value = true; c2.value = true; c3.value = true;
        pnl2.add("statictext", undefined,
                 "Senza il file indice costruisco uno scheletro con voci finte,\n" +
                 "giusto per farti vedere la forma.\n" +
                 "Il _marchi.json lo scrivi dall'app con \"Marchi della sezione\":\n" +
                 "la cartella loghi_brand non va bene, ha un file per prodotto.",
                 { multiline: true });

        var g3 = w.add("group");
        g3.add("button", undefined, "Costruisci", { name: "ok" });
        g3.add("button", undefined, "Annulla", { name: "cancel" });

        if (w.show() !== 1) return null;

        var v = [];
        for (i = 0; i < cb.length; i++) v[i] = cb[i].value;

        var righe = null, loghi = null, logo = null;
        if (v[0] && c1.value) {
            var f = File.openDialog("Scegli indice_alfabetico.txt", "*.txt;*.tsv;*.csv");
            righe = leggiIndice(f);
        }
        if (v[1] && c2.value) {
            var fm = File.openDialog("Scegli _marchi.json (export_catalogo\\...\\_marchi.json)", "*.json");
            loghi = leggiMarchi(fm);
        }
        if (v[4] && c3.value) logo = File.openDialog("Logo per l'ultima pagina",
                                                     "*.ai;*.eps;*.pdf;*.png;*.psd");

        return { v: v, righe: righe, loghi: loghi, logo: logo,
                 note: Math.max(0, parseInt(eN.text, 10) || 0) };
    }

})();
