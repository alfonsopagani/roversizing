# Modelli

Questo documento raccoglie le equazioni usate dallo strumento, modulo per modulo, con le unità, la sezione della *Scheda dati di riferimento* da cui vengono i parametri e le ipotesi del modello. I modelli sono di ordine ridotto: servono a esplorare rapidamente lo spazio del progetto e a renderne coerenti i budget, non a sostituire le analisi di dettaglio.

All'interno del codice tutte le grandezze sono in unità SI (kg, m, s, W, J, Pa, K); i risultati sono riportati in kg, kW, kWh, m², m³. I simboli fra parentesi tonde rimandano alla chiave del file di input.

## 1. Ciclo di massa (`sizing.py`)

Diverse voci dipendono dalla massa totale m del rover: la potenza di trazione, e quindi l'azionamento e il sistema di potenza, e le voci dichiarate come frazione della massa totale. Si cerca la massa che soddisfa

  m* = F(m*)

dove F(m) è la massa totale a pieno carico, margini compresi, calcolata supponendo che il rover pesi m. L'iterazione a punto fisso

  m₍ₖ₊₁₎ = F(mₖ)

parte dal limite di MR-20 e si arresta quando |m₍ₖ₊₁₎ − mₖ| < 0,1 kg.

Vicino alla soluzione F(m) ≈ A + k·m. La pendenza k = dF/dm è la *somma delle frazioni*: la quota di ogni kg aggiunto che ritorna come altra massa, margini compresi. Se k < 1 l'iterazione converge a m* = A/(1 − k), e 1/(1 − k) è il fattore di crescita della massa: ogni kg aggiunto a una voce fissa (per esempio al carico utile) fa crescere la massa totale di 1/(1 − k) kg. Se k ≥ 1 non esiste una soluzione finita. Lo strumento stima k numericamente, con una differenza finita di 1 kg, e riporta il contributo di ciascuna voce.

## 2. Margini (`margins.py`) — MR-21

  massa prevista       = Σᵢ (1 + MGAᵢ) · m_base,i
  margine di sistema   = 0,15 · Σᵢ m_base,i
  massa totale         = masse fisse + massa prevista + margine di sistema

con le somme estese alle voci con margine, escluse le masse fisse.

MGAᵢ dipende dalla maturità dichiarata: 20% (`da_progettare`), 10% (`derivato`), 5% (`esistente`). Le masse fisse (carico scientifico, equipaggio, tute, consumabili) non ricevono margini. La somma è confrontata con il limite di 7.500 kg di MR-20. I valori dei margini sono in `common.toml`.

## 3. Abitabilità e geometria della cabina (`habitability.py`)

Parametri: Scheda, *Abitabilità e volumi*.

Volume pressurizzato richiesto:

  V_p = NHV / f_NHV + V_stivaggio + V_altro

con NHV volume abitabile netto (`nhv_m3`), f_NHV rapporto fra volume abitabile e pressurizzato (`nhv_fraction`), V_stivaggio capacità di stivaggio interna (`stowage_m3`), V_altro altri volumi pressurizzati, per esempio un airlock interno (`other_pressurized_m3`).

Cabina cilindrica di raggio R = D/2 con due fondi:

- fondi semisferici: V_fondi = 4/3·π·R³, A_fondi = 4·π·R²;
- fondi ellittici di profondità h = k·R (`head_ratio`): V_fondi = 4/3·π·R²·h, A_fondi = 2·π·R²·[1 + (1 − e²)/e · artanh(e)], con e² = 1 − k².

Se la lunghezza non è dichiarata (`length_m = 0`) il tratto cilindrico si ricava dal volume:

  L_c = (V_p − V_fondi) / (π·R²),   A = π·D·L_c + A_fondi

altrimenti si usa la lunghezza dichiarata e si confronta il volume risultante con quello richiesto.

Volume da stivare: cibo (0,0048 m³ per persona-giorno, Scheda, *Equipaggio ed ECLSS*), acqua se i serbatoi sono interni (1 m³ ogni 1.000 kg), altre voci dichiarate (`stowage_items_m3`). Va confrontato con lo stivaggio disponibile.

Se la cabina del modello CAD/FEM del gruppo non è un cilindro con fondi, volume e superficie si possono dichiarare (`cad_volume_m3`, `cad_area_m2`): ciascun valore maggiore di zero sostituisce quello del cilindro (V = V_CAD, A = A_CAD) nella verifica del volume, nelle masse di interni e isolamento (e del guscio, finché manca la massa del FEM) e nella dispersione termica. Diametro e lunghezza restano quelli del cilindro dichiarato. In alternativa, altre forme della cabina (pareti piane, più moduli) si aggiungono con una funzione che restituisca gli stessi campi di `cabin_geometry`. Per una cabina a pareti piane la massa areale va aumentata per la flessione (Scheda, *La cabina pressurizzata*).

## 4. Supporto vitale (`eclss.py`)

Parametri: Scheda, *Equipaggio ed ECLSS*. Requisiti: MR-03, MR-04, MR-05, MR-13, MR-14.

Tempo-persona da rifornire:

  T = n·t_esc + (n_em − n)·t_em + n·t_riserva

con n = 2 persone (MR-01), t_esc = 14 sol (MR-03), n_em = 4 persone per t_em = 72 h (MR-14), t_riserva riserva facoltativa (`reserve_d`). I consumi BVAD sono per giorno terrestre; l'escursione dura 14 sol di 24 h 39 min.

Miscela della cabina (MR-13), con frazione molare di O₂ x = 0,34:

  M = x·M_O₂ + (1 − x)·M_N₂,   ρ = p·M/(R·T),   w_O₂ = x·M_O₂/M

Consumabili, con r i consumi per persona e per unità di tempo e ρ i gradi di rigenerazione:

  O₂ = r_O₂·T·(1 − ρ_O₂) + N_EVA·n_EVA·(r_O₂,EVA·t_EVA + m_O₂,fisso) + w_O₂·(m_perdite + m_cicli)
  N₂ = (1 − w_O₂)·(m_perdite + m_cicli)
  H₂O = [(r_potabile + r_igiene)·T + N_EVA·n_EVA·r_H₂O,EVA·t_EVA]·(1 − ρ_H₂O)
  cibo = r_cibo·T + N_EVA·n_EVA·r_cibo,EVA·t_EVA
  assorbitore di CO₂ = k_CO₂ · r_CO₂·T

con N_EVA il numero di EVA dichiarato dal gruppo (suitport + airlock, almeno 10 per MR-04), n_EVA = 2 persone per EVA e t_EVA = 8 h (durata massima di MR-04), m_perdite = perdita della cabina × durata dell'escursione. Il gas perso nei cicli di uscita (MR-05) è

  suitport: m_cicli = N_EVA,sp · n_EVA · c_sp · m_ciclo
  airlock:  m_cicli = N_EVA,al · c_al · f · V_gas · ρ

con c numero di cicli per EVA, m_ciclo gas perso per persona e per ciclo, f frazione del gas dell'airlock persa a ogni ciclo, V_gas volume di gas libero dell'airlock.

k_CO₂ (`co2_sorbent_ratio`) è la massa di assorbitore consumato per kg di CO₂, contenitori compresi: il valore teorico per l'idrossido di litio è 1/0,92 kg/kg (Scheda), quello reale è maggiore. Per un sistema rigenerabile k_CO₂ = 0 e l'hardware va fra le voci dichiarate.

Serbatoi:

  m_serbatoi = k_O₂·m_O₂ + k_N₂·m_N₂ + k_H₂O·m_H₂O

con k_O₂ = 1,45 e k_N₂ = 1,93 per serbatoi in pressione (Scheda); k_H₂O è un'ipotesi del gruppo.

I consumabili sono masse fisse; serbatoi e hardware ricevono l'MGA.

## 5. Riparo dalle radiazioni (`radiation.py`) — MR-16

Parametri: Scheda, *Radiazioni*.

  m_schermo = σ · A,   m_agg = max(0, m_schermo − f_w·m_H₂O − m_altri)

σ è la schermatura in kg/m² (10 g/cm² = 100 kg/m²), A la superficie del riparo per i due membri dell'equipaggio da schermare nelle direzioni non coperte dal suolo (MR-16), f_w la frazione dell'acqua di bordo disponibile come schermo nel momento più sfavorevole, m_altri altri materiali di bordo riconfigurati. La verifica di MR-16 confronta σ con la schermatura minima del requisito (10 g/cm² di acqua equivalente).

Accanto alla verifica, a titolo informativo, lo strumento stima la dose efficace dall'evento solare di riferimento interpolando fra i due valori della Scheda per la superficie di Marte (D₀ senza schermatura, D₁ con il riparo di riferimento σ₁; dati in `common.toml`):

  D(σ) = D₀ · (D₁/D₀)^(σ/σ₁)   per σ ≤ σ₁;   D = D₁ per σ > σ₁

Oltre σ₁ non si estrapola: il valore è un limite superiore. La stima non considera la quota del sito, che cambia lo spessore dell'atmosfera sovrastante (Scheda, *Radiazioni*), né la schermatura del resto della cabina. La dose da raggi cosmici nell'escursione è il prodotto della dose giornaliera della Scheda (minimo solare) per la durata dell'escursione.

## 6. Struttura (`structure.py`)

Parametri: Scheda, *Struttura*. Requisito: MR-22.

Finché il modello FEM non è disponibile, le masse della cabina sono stimate dalla superficie:

  m_guscio = A·w_guscio,   m_interni = A·w_interni,   m_isolamento = A·t_isol·ρ_isol

Se è disponibile la massa del guscio dal modello FEM del gruppo (MR-22):

  m_guscio = m_FEM · (1 + f_non modellata)

Il modello FEM comprende eventualmente anche pavimento e paratie: in tal caso la loro massa è in m_FEM, e la massa areale degli interni (w_interni) va azzerata o ridotta alla parte non modellata.

Telaio (lo chassis che porta la cabina e le sospensioni), ruote e sospensioni sono voci dichiarate, come massa o come frazione della massa totale (Scheda, *Ripartizione delle masse*, *Mobilità*). Nel modello FEM entrano di norma come masse non strutturali; se il gruppo modella il telaio a travi, la sua massa è compresa in m_FEM e la voce dichiarata si toglie.

## 7. Mobilità (`mobility.py`)

Parametri: Scheda, *Mobilità*. Requisiti: MR-08, MR-10, MR-11. Ipotesi comuni del brief: C_rr fra 0,1 e 0,3, verifica a 0,6.

Potenza elettrica assorbita dalla trazione su una pendenza θ alla velocità v:

  P = (C_rr·cosθ + sinθ) · m·g · v / η

con η rendimento complessivo della catena di trazione. Potenza di picco:

  P_picco = max[P(0, 5 km/h), P(15°, 1 km/h)]

Energia di trazione per l'escursione, su una distanza d con salita cumulata Δh:

  E_tr = (1 + k_man) · (C_rr·m·g·d + m·g·Δh) / η,   d = max(100 km, t_guida·v_media)

d è la percorrenza pianificata dalla ConOps (ore di guida per velocità media), con il minimo di MR-08.

k_man è il margine per manovre e percorso non rettilineo. Nell'esempio vale il 5% che lo studio GRC applica alla potenza di trazione (Scheda, *Potenza ed energia*); lo strumento lo applica all'energia. In discesa l'energia non viene recuperata.

Massa dell'azionamento (motori, riduttori, controllori): m_az = k_az·P_picco, con k_az in kg/kW (Scheda: 6-13 kg/kW).

Grandezze informative e di verifica:

  coppia per ruota motrice   M_r = (C_rr·cosθ + sinθ)·m·g·R / n,   R = D_ruota/2, n ruote motrici
  velocità raggiungibile     v = P_picco·η / [(C_rr·cosθ + sinθ)·m·g]
  angolo di ribaltamento     tanφ = (b/2) / h_G

h_G è l'altezza del baricentro calcolato dalle posizioni, se tutte le voci ne hanno una; altrimenti quella dichiarata (`cg_height_m`).

Motori e riduttori si dimensionano anche sulla coppia in pendenza, che il modello di potenza non considera.

## 8. Potenza ed energia (`power.py`)

Parametri: Scheda, *Potenza ed energia* e *Vita a cicli delle batterie*. Requisiti: MR-07, MR-08, MR-12, MR-14, MR-15, MR-21.

**Profilo dell'escursione.** Il gruppo descrive l'escursione con alcuni sol tipo: per ciascuno le ore di guida, EVA, sosta di giorno e notte (che sommano a un sol) e il numero di ripetizioni (che sommano a 14 sol). I sol si succedono nella sequenza dichiarata in `sequence` oppure, in mancanza, alternando i sol tipo nell'ordine del file.

**Carichi di servizio.** Per ogni modo operativo

  P_modo = (1 + 0,30) · P_modo,stimata

e l'energia di servizio dell'escursione è E_serv = Σ_modi Σ_s n_s·t_modo,s·P_modo. Durante la guida si aggiunge la potenza media di trazione P_tr = E_tr / t_guida,totale.

**Generazione.**

- RPS: se la potenza non è dichiarata, P_RPS = (E_serv + E_tr) / t_escursione.
- Fotovoltaico: l'ala è ripiegata durante la guida e non produce (Scheda, *Potenza ed energia*: ipotesi dello studio GRC). Il gruppo può dichiararla attiva in marcia (`deployed_while_driving = true`), motivando la scelta e mettendo a budget la struttura aggiuntiva. Le ore equivalenti di sole h_sole sono riferite all'intero periodo di luce: P_FV·h_sole è l'energia di un giorno con l'ala sempre aperta. È un'ipotesi prudente: le 8,8 h della Scheda sono ricavate sulla sola sosta diurna del caso GRC, con un'ora di guida, e lo strumento toglie poi la quota della guida (circa il 2% con un'ora). Se la potenza non è dichiarata, in ogni sol tipo l'ala deve produrre l'energia del sol nelle ore in cui è aperta:

  P_FV = max_s E_s / (h_sole · f_s),   f_s = 1 − q(0, t_guida,s)

  dove E_s è l'energia del sol tipo s, f_s la quota dell'energia giornaliera raccolta (la guida è all'inizio del giorno) e q la quota sinusoidale definita più sotto. Con l'ala attiva in marcia f_s = 1. Superficie e massa dell'ala: A = P_FV/(W/m²), m = P_FV/(W/kg). I valori specifici vanno presi alla profondità ottica di progetto; la chiave `optical_depth` serve solo a documentarla e non entra nel calcolo.
- Celle a combustibile: forniscono E_serv + E_tr; m_FC = m_fissa + k·E (parte fissa per stack ed elettronica, parte proporzionale per reagenti e serbatoi).
- Ibrido: potenze di RPS e fotovoltaico dichiarate dal gruppo.

**Simulazione dell'escursione e batteria.** Il bilancio di energia si segue fase per fase. Le fasi di luce si susseguono dall'alba nell'ordine guida, EVA, sosta di giorno; poi viene la notte. Per una fase fra gli istanti t₀ e t₁ dall'alba:

  E_carico = (P_modo + P_tr)·Δt
  E_gen    = P_RPS·Δt + E_FV(t₀, t₁)
  debito   = max(0, debito + E_carico − E_gen)

Con l'ala sempre aperta la produzione di un sol sarebbe E_FV,sol = P_FV·h_sole, con andamento sinusoidale fra alba e tramonto (durata t_luce):

  E_FV(t₀, t₁) = E_FV,sol · q(t₀, t₁),   q(t₀, t₁) = [cos(π·t₀/t_luce) − cos(π·t₁/t_luce)] / 2

Nelle fasi di guida E_FV = 0, salvo che l'ala sia dichiarata attiva in marcia.

Il debito è l'energia mancante rispetto alla batteria carica. L'energia utile richiesta alla batteria è il debito massimo. Con le celle a combustibile la batteria serve solo per i picchi. La capacità nominale è

  C = max(E_utile / DOD, (P_picco,el − P_continua) / c_max)

con P_picco,el = P_picco + P_guida, P_continua la potenza erogata con continuità dai generatori (RPS; per le celle a combustibile la potenza media dell'escursione) e c_max la corrente massima di scarica in multipli della capacità (1/h; Scheda, *Potenza ed energia*: circa 0,2C nei progetti GRC). Massa: m_bat = C / e_spec. Attenzione alle unità: con C in kWh ed e_spec in Wh/kg, m = 1000·C/e_spec.

**Vita a cicli (MR-07).** Un ciclo si chiude quando il debito torna a zero; se a fine escursione il debito è positivo, la ricarica alla base conta come un ciclo. Il numero di cicli nella vita operativa (cicli per escursione × numero di escursioni) si confronta con la tabella della Scheda alla riga di DOD uguale o immediatamente superiore a quella del ciclo più profondo, senza interpolare. Se il debito supera la capacità della batteria (DOD oltre l'ultima riga della tabella, possibile nella verifica fuori progetto) la vita a cicli perde significato: la riga riporta il debito in percentuale della capacità e la batteria insufficiente, con esito NON SODDISFATTO.

**Notte (MR-12).** Ogni sol tipo deve avere una notte di almeno 12 h (`night_h` in `common.toml`, circa 12 h secondo brief e Scheda); una notte più breve dà NON SODDISFATTO. L'energia della notte, P_notte·max(t_notte,dichiarata, 12 h), si confronta con l'accumulo utile più la generazione notturna.

**Rientri (MR-14, MR-15).** Rientro dal punto più lontano (50 km) alla velocità v con t_g ore di guida per sol:

  t_guida = d/v,   n = ⌈t_guida/t_g⌉ − 1,   t_rientro = n·t_sol + (t_guida − n·t_g)
  E_rich = 1,3·P_servizio·t_rientro + E_tr(d)
  E_disp = SOC·E_acc + P_RPS·t_rientro + E_FV,   E_acc = C·DOD + E_reagenti
  E_FV   = f·P_FV·h_sole·n·[1 − q(0, t_g)]                     (ala ripiegata in marcia)
  E_FV   = f·P_FV·h_sole·[n + q(0, t_guida − n·t_g)]           (ala attiva in marcia)

Si guida dall'alba: nei sol completi l'ala produce nella parte di giorno che segue la guida, nell'ultimo sol il rientro termina all'arrivo. Per t_luce si usa il giorno più corto fra i sol tipo dichiarati.

con f = 1 per l'emergenza e f = 0,15 per la tempesta (MR-15). E_acc è l'energia utile installata: batteria fino alla DOD massima più, con le celle a combustibile, l'energia dei reagenti; coincide con il debito massimo solo se la batteria è dimensionata dall'energia. SOC è la frazione di E_acc disponibile all'inizio del rientro. Nell'emergenza (MR-14) la massa comprende le due persone soccorse e la durata va confrontata con 72 h. Velocità, ore di guida, carichi e stato di carica iniziale sono ipotesi del gruppo.

La massa del PMAD è una voce dichiarata (Scheda: quadro da 39,1 kg più il 25% di cablaggi per il rover GRC).

## 9. Controllo termico (`thermal.py`)

Parametri: Scheda, *Ambiente marziano* e *Controllo termico*.

Temperatura equivalente di pozzo, con fattore di vista verso il suolo F (0 per un radiatore orizzontale rivolto verso l'alto, 0,5 per uno verticale):

  T_pozzo⁴ = F·T_suolo⁴ + (1 − F)·T_cielo⁴

calcolata nel caso caldo. Calore da smaltire e area del radiatore:

  Q = max(2·q_met + f_diss·max(P_modo),  4·q_met + f_diss·P_emergenza)
  A = Q / [ε·σ·(T_rad⁴ − T_pozzo⁴)],   m = A·w_rad

A è la superficie radiante. La massa usa w_rad = 3,5 kg/m² (Scheda, valore per un pannello a due facce) sull'intera superficie radiante: è una stima prudente, che vale anche per un pannello che irraggia da una sola faccia. I valori per kW della Scheda (121-145 kg/kW) si riferiscono a radiatori dimensionati per una tempesta di polvere e comprendono più componenti: non sono confrontabili direttamente con la sola massa del pannello.

con q_met = 144 W per persona, f_diss frazione dei carichi di servizio dissipata in cabina e P_emergenza i carichi del rientro di emergenza con quattro persone (MR-14); tutti i carichi comprendono il margine del 30%. Il calore solare assorbito e la convezione sono trascurati. Il calore di scarto dell'RPS ha un radiatore proprio, che si considera compreso nella potenza specifica del generatore: è un'ipotesi, perché la Scheda riporta massa e superficie del radiatore senza precisarlo.

Dispersione dell'isolamento nel caso freddo, a titolo informativo:

  Q_disp = k·A·(T_cabina − T_suolo,freddo) / t_isol

È un limite superiore, perché trascura le resistenze del guscio e dello strato limite esterno, e serve a controllare l'ipotesi sui riscaldatori compresa nei carichi notturni.

## 10. Verifiche (`requirements.py`)

| Requisito | Verifica |
| --- | --- |
| Ipotesi comuni | C_rr di progetto fra 0,1 e 0,3; carichi di servizio senza margine, massimo fra i modi, fra 1,8 e 3,4 kW (valori del progetto anche nella verifica fuori progetto) |
| MR-04 | EVA dichiarate (suitport + airlock) ≥ 10 |
| MR-07 | numero di escursioni nell'intervallo 12-18; cicli della batteria nella vita operativa ≤ cicli ammessi dalla tabella |
| MR-08 | ore di guida × velocità media ≥ 100 km; energia dell'escursione disponibile a bordo (debito massimo ≤ accumulo utile, oppure energia ≤ reagenti delle celle): soddisfatta per costruzione nel progetto nominale, conta nella verifica fuori progetto |
| MR-10 | velocità in piano con la potenza di picco installata ≥ 5 km/h; velocità media di pianificazione = 3 km/h e non superiore alla velocità in piano |
| MR-11 | velocità a 15° ≥ 1 km/h; angolo di ribaltamento laterale ≥ 25° (baricentro dalle posizioni, se complete, altrimenti `cg_height_m`) |
| MR-12 | notte di ogni sol tipo ≥ 12 h; energia disponibile per la notte ≥ energia richiesta |
| MR-14 | posti ≥ 4; rientro entro 72 h; energia del rientro ≤ disponibile |
| MR-15 | energia del rientro in tempesta ≤ disponibile |
| MR-16 | schermatura del riparo ≥ 10 g/cm² nelle direzioni non coperte dal suolo; dose stimata per l'evento di riferimento, da confrontare con il limite di 250 mSv da cui deriva il requisito (informativa) |
| MR-19 | diagonale della pianta ≤ 9,1 m (carenatura SLS da 10 m), NON VERIFICATO senza la sezione `[envelope]`; facoltativo: ≤ 7,5 m (Block 1B); con il rover parallelo all'asse, diagonale della sezione riportata come INFORMATIVO (manca la sezione del lander) |
| MR-20 | massa a pieno carico ≤ 7.500 kg |
| MR-21 | margini applicati secondo il requisito |
| MR-22 | massa della struttura dal modello FEM (INFORMATIVO); margine di sicurezza minimo ≥ 0; prime frequenze proprie ≥ 8 Hz laterale e ≥ 15 Hz assiale (NON VERIFICATO finché non dichiarati) |
| Volume | volume della cabina ≥ volume pressurizzato richiesto; volume da stivare ≤ stivaggio disponibile |

I requisiti non quantitativi (per esempio MR-05, MR-17, MR-18) e le parti qualitative di quelli elencati vanno trattati nella documentazione del progetto. Restano alla documentazione anche alcune parti quantitative: MR-07 (dormienza e percorrenza nella vita operativa), MR-09 (300 km, facoltativo), MR-15 (60 sol di sosta), MR-19 (lunghezza della carenatura, 27,4 m) e MR-20 (sbarco autonomo dal lander).

**Verifica fuori progetto** (`sizing.off_design`, opzioni `--fuori-progetto` e `--congelato`). Il rover dimensionato con il file di input viene fatto operare con un valore diverso di una o più chiavi, per esempio C_rr = 0,6. Restano quelli del progetto nominale: massa e budget di massa, potenza di trazione installata, capacità della batteria, generazione (RPS, ala, reagenti). Si ricalcolano con i nuovi dati: energia di trazione, carichi di servizio, bilancio di energia dell'escursione con la batteria installata, rientri di MR-14 e MR-15. Le verifiche dicono quali requisiti il progetto congelato non rispetta più; con `--sweep … --congelato`, a quale valore ciascuno cede.

## 11. Limiti principali

- La massa del rover nella trazione è quella a pieno carico per tutta l'escursione: è una stima conservativa, perché i consumabili diminuiscono.
- Il bilancio di energia è fatto per fasi, non istante per istante; i picchi di potenza sono considerati solo nel dimensionamento della batteria.
- La resistenza al moto è rappresentata da un unico coefficiente; il suo valore è il dato più incerto (Scheda, *Mobilità*).
- La struttura è stimata con masse areali fino a quando non è disponibile il modello FEM.
- Il controllo termico considera solo il radiatore della cabina in regime stazionario.
- La stabilità è verificata solo per il ribaltamento laterale; la stabilità longitudinale in pendenza non è verificata.
- Nel sol la guida avviene all'inizio del periodo di luce, prima delle EVA e della sosta. Con l'ala ripiegata in marcia è la collocazione che perde meno produzione: un'altra ConOps va valutata modificando l'ordine delle fasi in `power.py`.
