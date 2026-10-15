"""Mobilità: potenza ed energia di trazione, massa dell'azionamento.

Parametri: Scheda dati, sezione *Mobilità* (coefficiente di resistenza al
moto, rendimento della catena di trazione, massa dell'azionamento per kW di
picco). Requisiti: MR-08 (percorrenza), MR-10 (velocità), MR-11 (pendenza e
stabilità).

Ipotesi comuni del brief: C_rr di progetto fra 0,1 e 0,3, verifica a 0,6.
"""
from __future__ import annotations

import math


def traction_power(mass: float, g: float, crr: float, slope: float,
                   speed: float, eta: float) -> float:
    """Potenza elettrica assorbita dalla trazione [W].

        P = (C_rr·cosθ + sinθ) · m · g · v / η

    m massa del rover [kg], θ pendenza [rad], v velocità [m/s], η rendimento
    complessivo della catena di trazione (potenza alle ruote / potenza
    elettrica assorbita).
    """
    return (crr * math.cos(slope) + math.sin(slope)) * mass * g * speed / eta


def peak_power(mass: float, g: float, crr: float, eta: float,
               v_flat: float, slope: float, v_slope: float) -> tuple[float, str]:
    """Potenza di picco della trazione [W] e caso che la determina.

        P_picco = max[ P(0, v_piano), P(θ_max, v_pendenza) ]

    con v_piano = 5 km/h (MR-10) e θ_max = 15° a 1 km/h (MR-11).

    Nota: motori e riduttori si dimensionano anche sulla coppia alle ruote in
    pendenza (``wheel_torque``), che può risultare più severa della potenza.
    """
    p_flat = traction_power(mass, g, crr, 0.0, v_flat, eta)
    p_slope = traction_power(mass, g, crr, slope, v_slope, eta)
    return (p_flat, "piano") if p_flat >= p_slope else (p_slope, "pendenza")


def traction_energy(mass: float, g: float, crr: float, eta: float,
                    distance: float, climb: float, margin: float) -> float:
    """Energia elettrica di trazione per un tragitto [J].

        E = (1 + k_man) · (C_rr·m·g·d + m·g·Δh) / η

    d distanza percorsa [m], Δh salita cumulata [m], k_man margine per manovre
    e percorso non rettilineo. In discesa l'energia non viene recuperata.
    """
    return (1.0 + margin) * (crr * mass * g * distance + mass * g * climb) / eta


def drive_mass(p_peak: float, specific_mass: float) -> float:
    """Massa di motori, riduttori e controllori [kg]: m = k_az · P_picco.

    k_az in kg/W (Scheda: circa 6-13 kg per kW di picco).
    """
    return specific_mass * p_peak


def wheel_torque(mass: float, g: float, crr: float, slope: float,
                 wheel_diameter: float, driven_wheels: int) -> float:
    """Coppia per ruota motrice in pendenza [N·m] (informativa).

        M_r = (C_rr·cosθ + sinθ) · m · g · R / n

    con R = D_ruota/2 raggio della ruota e n numero di ruote motrici.
    """
    return (crr * math.cos(slope) + math.sin(slope)) * mass * g * wheel_diameter / 2.0 / driven_wheels


def max_speed(p_available: float, mass: float, g: float, crr: float,
              slope: float, eta: float) -> float:
    """Velocità raggiungibile con la potenza di trazione disponibile [m/s].

        v = P·η / [(C_rr·cosθ + sinθ)·m·g]
    """
    return p_available * eta / ((crr * math.cos(slope) + math.sin(slope)) * mass * g)


def tipping_angle(track: float, cg_height: float) -> float:
    """Angolo di ribaltamento laterale statico [rad]: tanφ = (b/2) / h_G.

    b carreggiata, h_G altezza del baricentro dal suolo.
    """
    return math.atan2(track / 2.0, cg_height)
