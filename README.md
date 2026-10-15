# roversizing

Strumento di calcolo per l'esercitazione E2 del corso *Progetto di Velivoli Aerospaziali* (Politecnico di Torino): dimensionamento di ordine ridotto di un rover pressurizzato per l'esplorazione di Marte.

Lo strumento stima masse, volumi, potenza ed energia del rover a partire dalle scelte del gruppo, chiude numericamente la spirale di massa e verifica i requisiti quantitativi del Design brief. Non sceglie l'architettura e non contiene una soluzione: calcola le conseguenze delle ipotesi che il gruppo dichiara.

Il codice fa parte del materiale didattico. È scritto per essere letto: ogni funzione riporta nella docstring l'equazione usata, le unità e la sezione della *Scheda dati di riferimento* da cui vengono i parametri. Le equazioni sono raccolte in [MODELLI.md](MODELLI.md).

**Indice**

1. [Contenuto del repository](#contenuto-del-repository)
2. [Installazione](#installazione)
3. [Eseguire lo strumento](#eseguire-lo-strumento)
4. [I file di input](#i-file-di-input)
5. [Come leggere il report](#come-leggere-il-report)
6. [Modificare lo strumento](#modificare-lo-strumento)
7. [Licenza](#licenza)

## Contenuto del repository

```
progetti/          file di input: le decisioni di progetto di ogni gruppo (esempio.toml e i file dei gruppi)
dimensionamento/   codice dei modelli e dati comuni (common.toml)
tests/             test con pytest e file di input dei test (riferimento.toml, da non modificare)
.vscode/           configurazioni di avvio e dei test per VS Code
MODELLI.md         equazioni e ipotesi dei modelli
MODIFICHE.md       registro delle modifiche allo strumento
```

## Installazione

Lo strumento non va installato come pacchetto: basta scaricare la cartella ed eseguirlo dalla cartella principale. Servono:

- Python 3.11 o successivo (con Python 3.10 serve anche il pacchetto `tomli`);
- facoltativi: `matplotlib` per i grafici, `pytest` per i test.

### Python

1. Installare Python da [python.org](https://www.python.org/downloads/). Su Windows, nella prima schermata dell'installatore, spuntare *Add python.exe to PATH*.
2. Controllare la versione da un terminale:

   ```
   python --version
   ```

   Su alcuni sistemi il comando è `python3` invece di `python`.
3. Installare i pacchetti facoltativi:

   ```
   python -m pip install matplotlib pytest
   ```

### VS Code (consigliato)

Lo strumento si può usare da qualunque terminale. Con [Visual Studio Code](https://code.visualstudio.com/) si hanno in più l'avvio con un tasto, il debugger e il pannello dei test; la cartella `.vscode/` contiene già le configurazioni.

1. Installare VS Code e, dal pannello *Estensioni* (Ctrl+Shift+X), l'estensione **Python** di Microsoft. Il debugger (*Python Debugger*) si installa insieme.
2. *File → Apri cartella…* e scegliere la cartella principale del repository, quella che contiene `README.md` e `pyproject.toml`. Va aperta la cartella principale e non una sottocartella: le configurazioni e i percorsi partono da lì.
3. Ctrl+Shift+P → *Python: Seleziona interprete* → scegliere il Python 3.11 o successivo installato.
4. Il terminale integrato (*Terminale → Nuovo terminale*) si apre già nella cartella principale: lì si danno i comandi di questo README.

## Eseguire lo strumento

### Primo avvio

Dalla cartella principale del repository:

```
python -m dimensionamento progetti/esempio.toml
```

Il comando stampa il report completo del rover di esempio. I valori servono solo a mostrare il formato e la lettura del report: non sono ottimizzati, non soddisfano tutti i requisiti e non vanno presi come riferimento.

### Opzioni della riga di comando

Negli esempi `progetti/ares.toml` è il file del gruppo (vedi [I file di input](#i-file-di-input)).

```
python -m dimensionamento progetti/ares.toml                          # report a terminale
python -m dimensionamento progetti/ares.toml --out risultati          # salva report.md e i CSV
python -m dimensionamento progetti/ares.toml --out risultati --plot   # e i grafici PNG
python -m dimensionamento progetti/ares.toml --set mobility.crr=0.6   # variante, senza modificare il file
python -m dimensionamento progetti/ares.toml --sweep mobility.crr 0.1 0.6 11 --plot --out risultati
python -m dimensionamento progetti/ares.toml --fuori-progetto mobility.crr=0.6
python -m dimensionamento progetti/ares.toml --sweep mobility.crr 0.1 0.6 11 --congelato --plot --out risultati
```

- `--set sezione.chiave=valore` modifica un valore solo per quell'esecuzione; si può ripetere. Per i testi servono le virgolette: `--set architecture.power='"fotovoltaico"'`.
- `--sweep sezione.chiave DA A N` ripete il dimensionamento per N valori equispaziati della chiave, lasciando invariato il resto: a ogni valore il rover è riprogettato. È lo studio di sensitività da usare nei trade-off; la tabella riporta anche i requisiti non soddisfatti. I valori sono nelle unità del file di input.
- `--fuori-progetto sezione.chiave=valore` è la verifica fuori progetto, per esempio la verifica a C_rr = 0,6 richiesta dal brief. Il rover resta quello dimensionato con il file di input (massa, potenza di trazione installata, batteria, generazione); con il valore indicato si ricalcolano velocità, energia dell'escursione, notte e rientri, e il report dice quali requisiti non sono più soddisfatti. Si può ripetere.
- `--congelato`, insieme a `--sweep`, fa la verifica fuori progetto per tutti i valori della scansione: la tabella mostra a quale valore ciascun requisito smette di essere soddisfatto, cioè quale cede per primo.
- `--out` salva un file `report.md`, da cui copiare le tabelle nelle presentazioni, e un file CSV per tabella. Con `--sweep` salva la tabella della scansione (`sensitivita_<chiave>.md`, oppure `fuori_progetto_<chiave>.md` con `--congelato`); con `--fuori-progetto` salva `fuori_progetto.md`. I CSV usano il punto e virgola come separatore e la virgola decimale, e si aprono direttamente in Excel.
- `--plot` salva i grafici della massa per sottosistema e dell'energia per escursione o, con `--sweep`, quelli della scansione (con `--congelato`: velocità con la potenza installata e debito di energia rispetto all'accumulo utile). Richiede matplotlib.

### Da VS Code

Gli stessi comandi si danno dal terminale integrato. In alternativa, nel pannello *Esegui e debug* (Ctrl+Shift+D) si sceglie una configurazione dal menu in alto e si preme F5:

- *Esempio: report a terminale*;
- *Esempio: report, CSV e grafici in risultati/*;
- *Esempio: sensitività su C_rr*;
- *Esempio: verifica fuori progetto a C_rr 0,6*;
- *Esempio: sensitività su C_rr a rover congelato*;
- *File TOML aperto nell'editor*: esegue il file TOML della scheda attiva. È la più comoda per lavorare sul file del gruppo: lo si tiene aperto, lo si modifica, si salva e si preme F5.

Per aggiungere configurazioni (per esempio un'altra sensitività) basta copiare un blocco in `.vscode/launch.json` e cambiare `name` e `args`.

## I file di input

Il calcolo legge due file TOML: quello del gruppo, in `progetti/`, con tutte le scelte di progetto, e `dimensionamento/common.toml`, con i dati uguali per tutti.

Il formato TOML è semplice: `chiave = valore`, sezioni fra parentesi quadre, testo fra virgolette, commenti dopo `#`. Gli elenchi di tabelle, come i sol tipo e le voci di massa, si scrivono con doppie parentesi quadre (`[[items]]`).

### Il file del gruppo

Ogni gruppo descrive il proprio rover in un file nella cartella `progetti/`:

1. copiare `progetti/esempio.toml` in un nuovo file nella stessa cartella, chiamato con il nome della missione scelto dal gruppo, in minuscolo e senza spazi: per esempio `progetti/ares.toml`;
2. compilare la sezione `[group]` con il nome della missione, la versione e gli studenti (cognome e nome, matricola, ruolo);
3. sostituire i valori con le scelte del gruppo, aggiornando il commento di ciascuna riga.

Ogni valore deve avere accanto un commento con la sua origine:

- un requisito: `# MR-10`;
- una sezione della Scheda dati: `# Scheda, Mobilità`;
- un'ipotesi: `# ipotesi del gruppo: ...`, seguita da una breve motivazione.

Il suffisso del nome indica l'unità: `v_mean_kmh` è in km/h, `power_kw` in kW, `climb_m` in metri, `shield_g_cm2` in g/cm². Lo strumento converte tutto in unità SI al momento della lettura. Le chiavi senza suffisso sono adimensionali (frazioni, rendimenti, conteggi).

### Sezioni del file

| Sezione | Contenuto |
| --- | --- |
| `[group]` | nome, versione, studenti |
| `[architecture]` | architettura di potenza: `batterie`, `rps`, `fotovoltaico`, `celle_combustibile`, `ibrido` |
| `[operations]`, `[[operations.sol_types]]` | ConOps: velocità media, salita cumulata, sol tipo con le ore di guida, EVA, sosta e notte, sequenza facoltativa dei sol |
| `[loads]` | carichi di servizio per modo operativo, prima del margine del 30% |
| `[emergency]`, `[storm]` | rientro dal punto più lontano per MR-14 e MR-15 |
| `[habitability]`, `[cabin]` | volumi, geometria e materiali della cabina |
| `[eclss]`, `[eva_access]`, `[suits]` | consumi, rigenerazione, serbatoi, suitport e airlock, tute |
| `[radiation]` | riparo per l'evento solare |
| `[mobility]` | resistenza al moto, rendimento, azionamento, ruote, carreggiata |
| `[battery]`, `[rps]`, `[pv]`, `[fuel_cell]` | dati delle tecnologie di potenza |
| `[thermal]` | radiatore della cabina |
| `[[items]]` | voci di massa dichiarate dal gruppo (avionica, telaio, accesso EVA, ...) |
| `[positions]`, `[envelope]` | posizioni delle voci calcolate (facoltative), ingombro al lancio per MR-19 (vedi *Posizioni, baricentro e ingombro*) |

Le sezioni delle tecnologie di potenza non usate dall'architettura scelta possono restare nel file: vengono lette ma non entrano nel calcolo.

### Voci di massa dichiarate

Le voci che lo strumento non calcola si aggiungono come `[[items]]`:

```toml
[[items]]
name = "Avionica, comunicazioni e comandi"
subsystem = "avionica"
mass_kg = 250                     # Scheda, Ripartizione delle masse
maturity = "derivato"             # MR-21: MGA del 10%
```

Al posto di `mass_kg` si può indicare `fraction`, la frazione della massa totale: è utile per telaio, ruote e sospensioni, la cui massa cresce con quella del rover. La maturità determina il margine di crescita (MR-21): `da_progettare` 20%, `derivato` 10%, `esistente` 5%. Carico scientifico, equipaggio, tute e consumabili sono masse fisse senza margini e lo strumento le tratta come tali.

Ogni voce ha un nome, un sottosistema, la massa (`mass_kg` oppure `fraction`, non entrambe) e la maturità; facoltative la posizione (`position_m`, vedi *Posizioni, baricentro e ingombro*) e l'origine della massa (`source`): è un testo libero, per esempio `"FEM"`, `"CAD"` o `"catalogo"`, che il report riporta nella colonna dell'origine del budget di massa e che non entra nel calcolo. I sottosistemi ammessi sono: `struttura`, `mobilita`, `potenza`, `termico`, `eclss`, `abitabilita`, `avionica`, `comunicazioni`, `eva`, `radiazioni`, `altro`. Come per tutti i valori del file, il commento indica l'origine della massa.

Le voci calcolate dallo strumento (guscio, batteria, radiatore, ...) hanno la maturità nella sezione corrispondente.

### Masse dal modello FEM (MR-22)

Quando il modello a elementi finiti del gruppo è disponibile, la massa della struttura della cabina calcolata dal FEM sostituisce la stima con la massa areale. Il modello comprende il guscio ed eventualmente pavimento e paratie: se li comprende, la loro massa va in `fem_shell_kg`, e la voce "Pavimento e pareti interne" va azzerata (`interior_areal_kg_m2 = 0`) oppure ridotta alla sola parte non modellata, per non contarla due volte.

```toml
fem_shell_kg = 310                # MR-22: massa del guscio dal modello FEM, versione del ...
fem_nonmodeled_fraction = 0.15    # ipotesi del gruppo: giunzioni e struttura secondaria non modellate
```

I risultati del modello servono anche alla verifica di MR-22, che lo strumento confronta con le soglie del brief (margini positivi, frequenze ≥ 8 Hz laterale e ≥ 15 Hz assiale); finché non sono dichiarati, le righe di MR-22 risultano `NON VERIFICATO`:

```toml
fem_min_margin = 0.12             # MR-22: margine di sicurezza minimo fra tutti i casi di carico
fem_freq_lateral_hz = 9.5         # MR-22: prima frequenza propria laterale, configurazione di lancio
fem_freq_axial_hz = 22.0          # MR-22: prima frequenza propria assiale, configurazione di lancio
```

Se la cabina del modello non è un cilindro con fondi semisferici o ellittici, anche volume interno e superficie del guscio si prendono dal modello, e sostituiscono quelli del cilindro:

```toml
cad_volume_m3 = 14.2              # volume interno dal modello CAD/FEM
cad_area_m2 = 36.5                # superficie del guscio dal modello CAD/FEM
```

Anche una voce dichiarata modellata nel FEM si aggiorna con la massa del modello, indicando `mass_kg` e `source = "FEM"`. La maturità resta quella dichiarata: un'analisi più accurata non rende il componente più definito.

Il report contiene la tabella *Masse per il modello FEM*, con le masse previste a pieno carico di tutte le voci, da inserire nel modello come masse concentrate nella loro posizione: allestimenti interni (sedili, cuccette, armadi, hardware dell'ECLSS), serbatoi, batteria, carico scientifico e così via, collegati alla struttura nei punti di attacco. Il sistema di mobilità, telaio compreso, è di norma fra queste masse non strutturali; se il gruppo modella il telaio a travi, la sua massa entra in `fem_shell_kg` e la voce "Telaio" si toglie da `[[items]]`. Fanno eccezione le voci della cabina: il guscio, e pavimento e paratie se modellati, sono la struttura del modello e non vanno aggiunti come masse; l'isolamento è distribuito sull'involucro e va inserito come massa non strutturale per unità di superficie.

### Posizioni, baricentro e ingombro

Le due sezioni `[positions]` e `[envelope]` descrivono la configurazione del rover. Le posizioni sono facoltative; l'ingombro serve alla verifica di MR-19, che è obbligatoria e resta `NON VERIFICATO` finché la sezione non è compilata.

**Posizioni e baricentro.** Se si indicano le posizioni di tutte le voci con massa, lo strumento calcola anche il baricentro. Le voci dichiarate hanno la posizione in `position_m = [x, y, z]`; quelle calcolate la prendono dalla sezione `[positions]`, dove ogni chiave raggruppa le voci che stanno nello stesso punto del layout:

| Chiave | Voci |
| --- | --- |
| `cabin` | guscio, pavimento e pareti interne, isolamento |
| `tanks` | serbatoi e loro contenuto (O₂, N₂, acqua) |
| `crew` | equipaggio, cibo, assorbitore di CO₂ |
| `suits` | tute EVA |
| `shield` | schermo aggiuntivo del riparo, se presente |
| `radiator`, `drive`, `payload` | radiatore, azionamento, carico scientifico |
| `battery`, `rps`, `pv`, `fuel_cell` | solo le tecnologie dell'architettura scelta |

Gli assi sono: x longitudinale, da un punto di riferimento scelto dal gruppo (per esempio l'estremità anteriore del rover), lo stesso per tutte le voci e per il modello FEM; y laterale, dal piano di simmetria longitudinale; z verticale, dal suolo, con il rover a pieno carico su terreno piano. L'altezza del baricentro entra nella verifica di ribaltamento di MR-11, che assume il baricentro sul piano di simmetria. Finché il layout non è definito, le posizioni si possono omettere: l'altezza del baricentro per MR-11 è allora quella di `cg_height_m` in `[mobility]`. Quando tutte le voci hanno una posizione, MR-11 usa il baricentro calcolato e `cg_height_m` non conta; la riga di MR-11 del report indica quale altezza è stata usata. Se ne mancano solo alcune, il report elenca le voci senza posizione.

**Ingombro al lancio (MR-19).** La sezione `[envelope]` descrive l'ingombro del rover in configurazione di lancio:

```toml
[envelope]
length_m = 7.0                    # lunghezza (valori illustrativi)
width_m = 3.5                     # larghezza
height_m = 3.8                    # altezza
orientation = "perpendicolare"    # "perpendicolare" o "parallelo" all'asse della carenatura
```

La verifica è geometrica e semplificata: la diagonale che conta deve stare nel diametro utile della carenatura SLS da 10 m (9,1 m, MR-19); la compatibilità con la carenatura da 8,4 m del Block 1B (diametro interno 7,5 m) è facoltativa e compare in una riga a parte. Con il rover perpendicolare all'asse conta la diagonale della pianta, √(L² + B²). Con il rover parallelo all'asse conta la diagonale della sezione, √(B² + H²), ma la sezione deve stare nel cerchio insieme a quella del lander, che lo strumento non conosce: l'esito è quindi `INFORMATIVO` e la verifica va completata a parte, come il confronto della lunghezza con lo spazio disponibile sopra il lander. MR-19 è obbligatorio: finché la sezione non è compilata risulta `NON VERIFICATO`.

### Dati comuni: `common.toml`

I requisiti di missione (MR-01…MR-22), le ipotesi comuni del brief e l'ambiente di Marte sono in `dimensionamento/common.toml`, uguale per tutti i gruppi. Le ipotesi comuni compaiono nella verifica dei requisiti come due righe a parte: C_rr di progetto fra 0,1 e 0,3 e carichi di servizio, senza margine, fra 1,8 e 3,4 kW (si confronta il modo con i carichi più alti). Nella verifica fuori progetto si controllano i valori del progetto, non quelli del caso di verifica. Il file non va modificato: il report verifica che il contenuto coincida con la versione distribuita e, in caso contrario, lo segnala nell'intestazione. È questo controllo che rende confrontabili i progetti dei gruppi.

## Come leggere il report

Il report contiene, nell'ordine:

1. **intestazione**: missione, versione, studenti, architettura e stato di `common.toml`;
2. **budget di massa** per voce (base, MGA, prevista), totali con margine di sistema e riserva rispetto a MR-20, massa per sottosistema;
3. **budget di potenza** per modo operativo, **budget di energia** per escursione e dimensionamento del **sistema di potenza**;
4. **budget di volume** e geometria della cabina;
5. **prestazioni**: velocità in piano e in pendenza, coppia alle ruote, percorrenza, autonomia, durata dei rientri;
6. dettagli di **ECLSS**, **riparo**, **struttura** e **controllo termico**;
7. **ciclo di massa**: iterazioni, somma delle frazioni k e voci che vi contribuiscono;
8. **verifica dei requisiti**, con valore richiesto, valore ottenuto ed esito;
9. **masse per il modello FEM**.

Gli esiti delle verifiche sono:

- `OK`: requisito soddisfatto;
- `NON SODDISFATTO`: requisito violato;
- `INFORMATIVO`: stima riportata senza esito, per esempio la dose di MR-16, ottenuta con un modello molto semplificato, o l'ingombro di MR-19 con il rover parallelo all'asse della carenatura;
- `NON VERIFICATO`: mancano i dati, per esempio i risultati del FEM per MR-22, o la sezione `[envelope]` per MR-19.

Alcuni requisiti sono soddisfatti per costruzione, perché sono i dati di partenza del dimensionamento: la tabella riporta comunque i valori, che vanno presentati alla review.

Un budget che non si chiude è un risultato, non un errore: va riportato, indicando che cosa servirebbe per chiuderlo (Design brief, Indicazioni di metodo).

### Quando il ciclo di massa non converge

Il ciclo di massa cerca la massa m che soddisfa m = F(m), dove F(m) è la massa totale calcolata supponendo che il rover pesi m. Se la *somma delle frazioni* k = dF/dm è maggiore o uguale a 1, ogni kg aggiunto al rover ne richiede almeno un altro e non esiste una soluzione finita. Lo strumento lo segnala ed elenca le voci che dipendono dalla massa totale, in ordine di contributo: sono quelle su cui agire.

## Modificare lo strumento

Lo strumento può essere modificato, a condizione che ogni modifica sia documentata e che i risultati restino confrontabili.

### Struttura del codice

```
dimensionamento/
  common.toml      requisiti di missione, ipotesi comuni e ambiente di Marte (non modificare)
  constants.py     costanti fisiche
  inputs.py        lettura e validazione dei file TOML, conversione delle unità
  habitability.py  volume pressurizzato e geometria della cabina
  eclss.py         consumabili e serbatoi del supporto vitale
  radiation.py     riparo per l'evento solare
  structure.py     masse della cabina (massa areale o FEM)
  mobility.py      potenza ed energia di trazione, azionamento, stabilità
  power.py         carichi, generazione, batteria, rientri
  thermal.py       radiatore e dispersioni dell'isolamento
  margins.py       margini di massa (MR-21)
  sizing.py        ciclo di massa e verifica fuori progetto
  requirements.py  verifiche dei requisiti
  sensitivity.py   studi di sensitività e verifica fuori progetto al variare di una chiave
  report.py        tabelle, CSV, Markdown, grafici
  __main__.py      riga di comando
```

Il percorso del calcolo è in `sizing.py`:

1. `fixed_part` calcola le grandezze indipendenti dalla massa totale: consumabili, serbatoi, cabina, riparo, radiatore;
2. `mass_dependent` calcola, per una massa assegnata, trazione, generazione e batteria;
3. `build_items` compone il budget e `margins.apply_margins` applica i margini;
4. `close_mass_loop` itera fino alla convergenza.

### Seguire un calcolo con il debugger

Per capire da dove viene un numero conviene fermare il calcolo in VS Code e guardare le variabili:

1. aprire il modulo che interessa (per esempio `dimensionamento/power.py`) e fare clic a sinistra del numero di riga per mettere un punto di interruzione (pallino rosso);
2. avviare con F5: l'esecuzione si ferma su quella riga;
3. nel pannello *Variabili* si leggono i valori, in unità SI; F10 avanza di una riga, F11 entra nella funzione chiamata, F5 riprende.

Il ciclo di massa chiama i modelli dipendenti dalla massa a ogni iterazione: un punto di interruzione in `mass_dependent` (in `sizing.py`) si ferma più volte, una per ogni stima della massa.

### Procedura di modifica

1. individuare la funzione da cambiare (le equazioni sono nelle docstring e in MODELLI.md);
2. modificarla, oppure aggiungerne una nuova accanto, aggiornando la docstring con l'equazione, le unità e l'origine dei parametri;
3. se servono nuovi dati di ingresso, aggiungere la chiave allo schema in `inputs.py` (sezione `SCHEMA`), con il suffisso dell'unità;
4. aggiungere in `tests/` un test che controlli la nuova formula su un caso calcolato a mano;
5. eseguire i test (vedi sotto);
6. registrare la modifica in [MODIFICHE.md](MODIFICHE.md): che cosa cambia, perché, con quale fonte, e come cambiano i risultati del proprio rover rispetto alla versione originale.

Alla review va presentato, accanto ai risultati, l'elenco delle modifiche apportate allo strumento. Per mostrarne l'effetto conviene eseguire lo stesso file di input con la versione originale e con quella modificata.

Esempi di estensioni utili: una cabina a pareti piane o a più moduli in `habitability.py` e `structure.py`; un profilo dei carichi più dettagliato in `power.py`; una correlazione per la resistenza al moto in funzione del carico sulla ruota in `mobility.py`.

### Test

Dal terminale:

```
python -m pytest
```

In VS Code, il pannello *Test* (icona della provetta) trova da solo i test in `tests/` e li esegue con un clic.

I test controllano le formule elementari su casi calcolati a mano, la lettura dei file e i messaggi d'errore, la convergenza del ciclo di massa e l'esecuzione della riga di comando. Lavorano sul file `tests/riferimento.toml`, una copia congelata di `progetti/esempio.toml` che non va modificata: i test ne confrontano i risultati con valori noti. L'esempio in `progetti/` e i file dei gruppi non sono usati dai test; un file di input si controlla eseguendolo con lo strumento. Vanno eseguiti dopo ogni modifica: un test che fallisce indica che la modifica ha cambiato un risultato che prima era verificato.

## Licenza

Codice: licenza MIT. Documentazione ed esempi: licenza CC BY 4.0. Copyright © 2026 Alfonso Pagani, Politecnico di Torino. Vedi [LICENSE](LICENSE).
