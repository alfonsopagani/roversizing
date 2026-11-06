"""Protezione dalle radiazioni: riparo per l'evento solare (MR-16).

Parametri: Scheda dati, sezione *Radiazioni*. Equazioni e ipotesi:
MODELLI.md, §5.
"""
from __future__ import annotations

from dataclasses import dataclass


def spe_dose(shield: float, dose_unshielded: float, dose_ref: float, shield_ref: float) -> float:
    """Dose efficace stimata per l'evento solare di riferimento [mSv], informativa (MODELLI §5).

        D(σ) = D_0·(D_1/D_0)^(σ/σ_1)   per 0 ≤ σ ≤ σ_1;   D = D_1 per σ > σ_1
    """
    if shield <= 0.0:
        return dose_unshielded
    if shield >= shield_ref:
        return dose_ref
    return dose_unshielded * (dose_ref / dose_unshielded) ** (shield / shield_ref)


@dataclass
class Shelter:
    required: float          # massa di schermo necessaria [kg]
    from_water: float        # quota coperta dall'acqua di bordo [kg]
    from_other: float        # quota coperta da altri materiali di bordo [kg]
    added: float             # massa aggiuntiva dedicata [kg]


def shelter_mass(areal_density: float, area: float, water: float,
                 water_fraction: float, other: float) -> Shelter:
    """Massa dello schermo del riparo [kg] (MODELLI §5).

        m_schermo = σ·A,   m_agg = max(0, m_schermo - f_w·m_H2O - m_altri)

    σ in kg/m^2 (10 g/cm^2 = 100 kg/m^2). Lo schermo si copre prima con l'acqua,
    poi con gli altri materiali.
    """
    required = areal_density * area
    from_water = min(required, water_fraction * water)
    from_other = min(required - from_water, other)
    return Shelter(required, from_water, from_other, required - from_water - from_other)
