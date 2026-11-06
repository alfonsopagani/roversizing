"""Struttura: massa della cabina pressurizzata.

Parametri: Scheda dati, sezioni *Struttura* e *Controllo termico* (aerogel).
Requisito: MR-22. Equazioni e ipotesi: MODELLI.md, §6.
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
    """Masse di guscio, interni e isolamento della cabina [kg] (MODELLI §6).

        m_guscio     = A·w_guscio,  oppure  m_FEM·(1 + f_non modellata) se fem_shell_kg > 0
        m_interni    = A·w_interni
        m_isolamento = A·t_isol·ρ_isol
    """
    if cab.fem_shell > 0.0:
        shell = cab.fem_shell * (1.0 + cab.fem_nonmodeled_fraction)
        source = "FEM"
    else:
        shell = area * cab.shell_areal
        source = "massa areale"
    interior = area * cab.interior_areal
    insulation = area * cab.insulation_thickness * cab.insulation_density
    return CabinMasses(shell, interior, insulation, source)

