"""dimensionamento: modelli di ordine ridotto per il progetto preliminare di un rover pressurizzato per Marte.

Strumento di calcolo dell'esercitazione E2 del corso Progetto di Velivoli
Aerospaziali (Politecnico di Torino). Uso:

    python -m dimensionamento progetti/esempio.toml

Moduli:
    inputs        lettura e validazione dei file TOML, unità
    habitability  volume pressurizzato e geometria della cabina
    eclss         consumabili e serbatoi del supporto vitale
    radiation     riparo per l'evento solare
    structure     masse della cabina (massa areale o FEM)
    mobility      potenza ed energia di trazione, azionamento
    power         carichi, generazione, batteria, rientri
    thermal       radiatore e dispersioni
    margins       margini di massa (MR-21)
    sizing        ciclo di massa
    requirements  verifiche dei requisiti
    sensitivity   studi di sensitività
    report        tabelle, CSV, Markdown, grafici
"""

__version__ = "1.0.0"
