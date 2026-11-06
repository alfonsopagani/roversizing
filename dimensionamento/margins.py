"""Margini di massa secondo MR-21 (MODELLI §2).

    massa prevista       = Σ (1 + MGA_i)·m_base,i
    margine di sistema   = f_sis·Σ m_base,i
    massa totale         = masse fisse + massa prevista + margine di sistema

I valori di MGA e f_sis sono in [margins] di common.toml.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Item:
    """Una voce del budget di massa."""
    name: str
    subsystem: str
    base: float                       # massa di base [kg]
    maturity: str | None = None       # None per le masse fisse
    source: str = ""                  # origine del valore (modello, FEM, ipotesi...)
    position: list[float] | None = None
    fixed: bool = False               # True: senza margini (MR-21)
    mga: float = 0.0                  # frazione, assegnata da apply_margins

    @property
    def predicted(self) -> float:
        return self.base * (1.0 + self.mga)


@dataclass
class MassBudget:
    items: list[Item]
    system_margin_fraction: float
    base_dry: float = 0.0
    mga: float = 0.0
    predicted_dry: float = 0.0
    system_margin: float = 0.0
    fixed: float = 0.0
    total: float = 0.0
    by_subsystem: dict[str, float] = field(default_factory=dict)


def mga_fraction(maturity: str, margins) -> float:
    """MGA in funzione della maturità (MR-21)."""
    return {"da_progettare": margins.mga_new,
            "derivato": margins.mga_modified,
            "esistente": margins.mga_existing}[maturity]


def apply_margins(items: list[Item], margins) -> MassBudget:
    """Applica MGA e margine di sistema e calcola i totali del budget di massa."""
    budget = MassBudget(items, margins.system)
    for it in items:
        it.mga = 0.0 if it.fixed else mga_fraction(it.maturity, margins)
        if it.fixed:
            budget.fixed += it.base
        else:
            budget.base_dry += it.base
            budget.mga += it.base * it.mga
        budget.by_subsystem[it.subsystem] = budget.by_subsystem.get(it.subsystem, 0.0) + it.predicted
    budget.predicted_dry = budget.base_dry + budget.mga
    budget.system_margin = margins.system * budget.base_dry
    budget.total = budget.fixed + budget.predicted_dry + budget.system_margin
    return budget
