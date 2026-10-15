"""Struttura: massa della cabina pressurizzata.

Parametri: Scheda dati, sezione *Struttura* (massa areale della parete) e
*Controllo termico* (isolamento in aerogel). Requisito: MR-22 (verifica con
il modello a elementi finiti del gruppo).

Finché il modello FEM non è disponibile, la massa della cabina è stimata
dalla superficie:
    m_guscio  = A · w_guscio       (guscio pressurizzato)
    m_interni = A · w_interni      (pavimento e pareti interne)
    m_isol    = A · t_isol · ρ_isol
Portelli, suitport e finestre sono voci dichiarate a parte.

Telaio (chassis), ruote e sospensioni sono voci dichiarate dal gruppo, come massa o
come frazione della massa totale (Scheda, Ripartizione delle masse e Mobilità);
nel modello FEM sono di norma masse non strutturali. Se il gruppo modella il
telaio, la sua massa è compresa in ``fem_shell_kg`` e la voce dichiarata si toglie.

Quando il modello FEM del gruppo (MR-22) è disponibile, la massa del guscio
calcolata dal FEM sostituisce la stima areale; se il modello comprende anche
pavimento e paratie, la massa areale degli interni va azzerata. Il FEM contiene solo la
struttura modellata: giunzioni, bulloneria, telai delle aperture e struttura
secondaria si aggiungono con la frazione ``fem_nonmodeled_fraction``. La
maturità (e quindi l'MGA) resta quella dichiarata: un'analisi più accurata
non rende il componente più definito.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CabinMasses:
    shell: float            # kg
    interior: float         # kg
    insulation: float       # kg
    shell_source: str       # "massa areale" oppure "FEM"


def cabin_masses(area: float, cab) -> CabinMasses:
    """Masse di guscio, interni e isolamento della cabina [kg] (vedi docstring del modulo)."""
    if cab.fem_shell > 0.0:
        shell = cab.fem_shell * (1.0 + cab.fem_nonmodeled_fraction)
        source = "FEM"
    else:
        shell = area * cab.shell_areal
        source = "massa areale"
    interior = area * cab.interior_areal
    insulation = area * cab.insulation_thickness * cab.insulation_density
    return CabinMasses(shell, interior, insulation, source)

