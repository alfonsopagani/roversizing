"""Abitabilità: volume pressurizzato e geometria della cabina.

Parametri: Scheda dati, sezioni *Abitabilità e volumi* ed *Equipaggio ed
ECLSS* (volume del cibo). Equazioni e ipotesi: MODELLI.md, §3.

La cabina è un cilindro con due fondi, semisferici o ellittici. Altre forme
si aggiungono con una funzione che abbia la stessa interfaccia di
``cabin_geometry``, documentando la modifica in MODIFICHE.md, oppure
dichiarando volume e superficie del modello CAD/FEM (``apply_cad``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def pressurized_volume(nhv: float, nhv_fraction: float, stowage: float,
                       other: float = 0.0) -> float:
    """Volume pressurizzato richiesto [m^3] (MODELLI §3).

        V_p = NHV / f_NHV + V_stivaggio + V_altro
    """
    return nhv / nhv_fraction + stowage + other


def head_volume_area(radius: float, ratio: float, heads: str) -> tuple[float, float]:
    """Volume [m^3] e superficie [m^2] dei DUE fondi della cabina (MODELLI §3).

        semisferici: V = 4/3·π·R^3,     A = 4·π·R^2
        ellittici:   V = 4/3·π·R^2·h,   A = 2·π·R^2·[1 + (1 - e^2)/e · artanh(e)],   e^2 = 1 - k^2

    Con k ≥ 0,999 si usano le formule della sfera.
    """
    if heads == "semisferici" or ratio >= 0.999:
        return 4.0 / 3.0 * math.pi * radius**3, 4.0 * math.pi * radius**2
    h = ratio * radius
    e = math.sqrt(1.0 - ratio**2)
    volume = 4.0 / 3.0 * math.pi * radius**2 * h
    area = 2.0 * math.pi * radius**2 * (1.0 + (1.0 - e**2) / e * math.atanh(e))
    return volume, area


@dataclass
class CabinGeometry:
    diameter: float          # m
    length: float            # lunghezza totale, fondi compresi [m]
    cylinder_length: float   # lunghezza del tratto cilindrico [m]
    volume: float            # volume interno [m^3]
    area: float              # superficie del guscio [m^2]
    source: str = "cilindro" # origine di volume e superficie: "cilindro" oppure "CAD"


def cabin_geometry(volume_required: float, diameter: float, heads: str,
                   head_ratio: float = 1.0, length: float = 0.0) -> CabinGeometry:
    """Geometria della cabina cilindrica con due fondi (MODELLI §3).

        L_c = (V_p - V_fondi) / (π·R^2)      (se length = 0)
        A   = π·D·L_c + A_fondi

    Con ``length`` > 0 si usa la lunghezza totale dichiarata. Se il tratto
    cilindrico risulta negativo si solleva ValueError.
    """
    radius = diameter / 2.0
    v_heads, a_heads = head_volume_area(radius, head_ratio, heads)
    depth = radius if heads == "semisferici" else head_ratio * radius
    if length > 0.0:
        l_cyl = length - 2.0 * depth
        if l_cyl < 0.0:
            raise ValueError(f"cabina: la lunghezza dichiarata ({length:.2f} m) è minore "
                             f"della profondità dei due fondi ({2 * depth:.2f} m).")
    else:
        l_cyl = (volume_required - v_heads) / (math.pi * radius**2)
        if l_cyl < 0.0:
            raise ValueError(f"cabina: con D = {diameter:.2f} m i soli fondi hanno un volume "
                             f"({v_heads:.1f} m^3) maggiore di quello richiesto "
                             f"({volume_required:.1f} m^3). Ridurre il diametro.")
    volume = math.pi * radius**2 * l_cyl + v_heads
    area = math.pi * diameter * l_cyl + a_heads
    return CabinGeometry(diameter, l_cyl + 2.0 * depth, l_cyl, volume, area)


def apply_cad(geom: CabinGeometry, cad_volume: float, cad_area: float) -> CabinGeometry:
    """Volume e superficie della cabina dal modello CAD/FEM del gruppo (MODELLI §3).

    Ciascun valore maggiore di zero sostituisce quello del cilindro; diametro e
    lunghezza restano quelli del cilindro dichiarato.
    """
    if cad_volume <= 0.0 and cad_area <= 0.0:
        return geom
    parts = []
    if cad_volume > 0.0:
        parts.append("volume")
    if cad_area > 0.0:
        parts.append("superficie")
    return CabinGeometry(geom.diameter, geom.length, geom.cylinder_length,
                         cad_volume if cad_volume > 0.0 else geom.volume,
                         cad_area if cad_area > 0.0 else geom.area,
                         "CAD (" + " e ".join(parts) + ")")


def stowage_required(food: float, water: float, water_inside: bool,
                     items: float) -> float:
    """Volume da stivare in cabina [m^3] (MODELLI §3).

        V = V_cibo + V_acqua (se i serbatoi sono interni) + V_altre voci
    """
    return food + (water if water_inside else 0.0) + items
