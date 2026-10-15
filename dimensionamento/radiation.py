"""Protezione dalle radiazioni: riparo per l'evento solare (MR-16).

Parametri: Scheda dati, sezione *Radiazioni* (schermatura raccomandata in
g/cm^2 di acqua equivalente, uso dell'acqua di bordo come schermo).

Il riparo è una zona della cabina per i due membri dell'equipaggio (MR-16),
con uno schermo di spessore areale σ nelle direzioni non coperte dal suolo;
la superficie A da schermare è dichiarata dal gruppo. Una parte dell'acqua di bordo,
sistemata attorno al riparo, conta come schermo; il resto va aggiunto come
massa dedicata.
"""
from __future__ import annotations

from dataclasses import dataclass


def spe_dose(shield: float, dose_unshielded: float, dose_ref: float, shield_ref: float) -> float:
    """Dose efficace stimata per l'evento solare di riferimento [mSv] (informativa).

    La Scheda (sezione Radiazioni) riporta, per la superficie di Marte, la dose
    senza schermatura D_0 e quella in un riparo di riferimento D_1 con
    schermatura σ_1. Fra i due punti si interpola con una legge esponenziale:

        D(σ) = D_0 · (D_1 / D_0)^(σ / σ_1)        per 0 ≤ σ ≤ σ_1

    Oltre σ_1 i dati non permettono di estrapolare: si restituisce D_1, che è
    quindi un limite superiore. La stima non tiene conto della quota del sito
    né della schermatura offerta dal resto della cabina, e serve solo come
    ordine di grandezza accanto alla verifica di MR-16.
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
    """Massa dello schermo del riparo [kg].

        m_schermo = σ · A                      (σ in kg/m^2: 10 g/cm^2 = 100 kg/m^2)
        m_agg     = max(0, m_schermo - f_w·m_H2O - m_altri)

    f_w è la frazione dell'acqua di bordo disponibile come schermo nel momento
    più sfavorevole (per esempio a fine escursione); m_altri sono altri
    materiali già a bordo che il gruppo riconfigura attorno al riparo.
    """
    required = areal_density * area
    from_water = min(required, water_fraction * water)
    from_other = min(required - from_water, other)
    return Shelter(required, from_water, from_other, required - from_water - from_other)
