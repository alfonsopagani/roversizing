"""Verifica dei requisiti quantitativi del Design brief.

Ogni verifica restituisce il valore richiesto, il valore ottenuto e l'esito:
    OK               requisito soddisfatto dal progetto calcolato
    NON SODDISFATTO  requisito violato
    NON VERIFICATO   il modello non ha i dati per verificarlo (per esempio
                     MR-22 senza la massa del modello FEM)
    INFORMATIVO      stima riportata accanto alla verifica, senza esito (per
                     esempio la dose di MR-16, stimata con un modello molto
                     semplificato)
Alcuni requisiti sono soddisfatti per costruzione (per esempio la percorrenza
di MR-08 è il dato con cui si calcola l'energia di trazione): la verifica
riporta comunque i valori, perché vanno presentati alla review.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import eclss, mobility, power
from .constants import HOUR, KWH

OK, KO, NV, INFO = "OK", "NON SODDISFATTO", "NON VERIFICATO", "INFORMATIVO"
COMMON = "Ipotesi comuni"
TOL = 1e-9                     # tolleranza sui confronti con gli estremi degli intervalli


@dataclass
class Check:
    mr: str
    description: str
    required: str
    obtained: str
    status: str


def _n(x: float, nd: int = 0) -> str:
    """Numero in formato italiano (punto per le migliaia, virgola per i decimali)."""
    s = f"{x:,.{nd}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def _status(ok: bool) -> str:
    return OK if ok else KO


def check_all(res) -> list[Check]:
    """Esegue tutte le verifiche sul risultato di ``sizing.run``."""
    c, d, fx, dep, b = res.common, res.design, res.fixed, res.dep, res.budget
    m, env = c.mission, c.environment
    mass = res.loop.mass
    checks: list[Check] = []

    # Ipotesi comuni del brief, sui valori di progetto (nella verifica fuori
    # progetto restano quelli del rover dimensionato)
    a = c.assumptions
    dn = res.design_nominal or d
    crr = dn.mobility.crr
    checks.append(Check(COMMON, "C_rr di progetto",
                        f"{_n(a.crr_min, 1)}-{_n(a.crr_max, 1)}", _n(crr, 2),
                        _status(a.crr_min - TOL <= crr <= a.crr_max + TOL)))
    load_mode = max(power.MODES, key=lambda mode: getattr(dn.loads, mode))
    load = getattr(dn.loads, load_mode)
    checks.append(Check(COMMON, "Carichi di servizio, massimo fra i modi, senza margine",
                        f"{_n(a.service_load_min / 1e3, 1)}-{_n(a.service_load_max / 1e3, 1)} kW",
                        f"{_n(load / 1e3, 1)} kW ({power.MODE_LABELS[load_mode]})",
                        _status(a.service_load_min - TOL <= load <= a.service_load_max + TOL)))

    # MR-04: EVA per escursione (almeno il minimo del brief)
    n_eva = eclss.eva_count(d)
    checks.append(Check("MR-04", "EVA a due persone per escursione (suitport + airlock)",
                        f"≥ {m.eva_count}", f"{n_eva}", _status(n_eva >= m.eva_count)))

    # MR-07: vita a cicli della batteria
    cap = dep.battery_capacity
    cycles = dep.sim.cycles
    n_exc = d.operations.excursions
    checks.append(Check("MR-07", "Escursioni nella vita operativa usate nel calcolo",
                        f"{m.excursions_min}-{m.excursions_max}", f"{n_exc}",
                        _status(m.excursions_min <= n_exc <= m.excursions_max)))
    if cycles:
        dod = max(cycles) / cap
        need = n_exc * len(cycles)
        top = max(d.battery.cycle_dod)
        if dod > top + 1e-9:
            # Il debito supera la capacità utilizzabile: la vita a cicli non ha
            # senso, la batteria è insufficiente (lo dicono anche MR-08 e MR-12).
            checks.append(Check("MR-07", "Cicli della batteria nella vita operativa",
                                f"debito ≤ {_n(top * 100)}% della capacità",
                                f"debito al {_n(dod * 100)}% della capacità: batteria insufficiente",
                                KO))
        else:
            allowed, row = power.allowed_cycles(dod, d.battery.cycle_dod, d.battery.cycle_count)
            checks.append(Check("MR-07", "Cicli della batteria nella vita operativa",
                                f"≤ {_n(allowed)} cicli (tabella, DOD {_n(row * 100)}%)",
                                f"{_n(need)} cicli ({len(cycles)} per escursione), DOD {_n(dod * 100)}%",
                                _status(need <= allowed)))
    else:
        checks.append(Check("MR-07", "Cicli della batteria nella vita operativa",
                            "cicli ≤ tabella della Scheda", "nessun ciclo di scarica profonda", OK))

    # MR-08: percorrenza
    t_drive = power.drive_time(d.operations.sol_types)
    planned = t_drive * d.operations.v_mean
    checks.append(Check("MR-08", "Percorrenza dell'escursione (ore di guida × velocità media)",
                        f"≥ {_n(m.distance / 1e3)} km",
                        f"{_n(planned / 1e3)} km ({_n(t_drive / HOUR)} h a {_n(d.operations.v_mean * 3.6, 1)} km/h)",
                        _status(planned >= m.distance - 1.0)))

    # MR-08: l'energia dell'escursione è disponibile a bordo. Nel progetto
    # nominale è soddisfatto per costruzione (la batteria o i reagenti sono
    # dimensionati su questo); conta nella verifica fuori progetto.
    if dep.gen.fc_energy > 0:
        checks.append(Check("MR-08", "Energia dell'escursione con le risorse a bordo",
                            f"≤ {_n(dep.gen.fc_energy / KWH)} kWh (reagenti)",
                            f"{_n(dep.e_total / KWH)} kWh",
                            _status(dep.e_total <= dep.gen.fc_energy * 1.0001)))
    else:
        usable_b = cap * d.battery.dod_max
        checks.append(Check("MR-08", "Energia dell'escursione con le risorse a bordo",
                            f"debito ≤ {_n(usable_b / KWH, 1)} kWh (accumulo utile)",
                            f"debito massimo {_n(dep.sim.max_deficit / KWH, 1)} kWh",
                            _status(dep.sim.max_deficit <= usable_b + 1.0)))

    # MR-10: velocità in piano con la potenza di picco installata
    v_flat = mobility.max_speed(dep.p_peak, mass, env.g, d.mobility.crr, 0.0, d.mobility.eta)
    checks.append(Check("MR-10", "Velocità in piano con la potenza di trazione installata",
                        f"≥ {_n(m.v_flat * 3.6, 1)} km/h", f"{_n(v_flat * 3.6, 1)} km/h",
                        _status(v_flat >= m.v_flat * 0.999)))
    v_mean = d.operations.v_mean
    checks.append(Check("MR-10", "Velocità media usata per la pianificazione",
                        f"= {_n(m.v_plan * 3.6, 1)} km/h (≤ velocità in piano)", f"{_n(v_mean * 3.6, 1)} km/h",
                        _status(abs(v_mean - m.v_plan) <= 0.01 * m.v_plan and v_mean <= v_flat)))

    # MR-11: pendenza e stabilità statica
    v_slope = mobility.max_speed(dep.p_peak, mass, env.g, d.mobility.crr, m.slope, d.mobility.eta)
    checks.append(Check("MR-11", f"Velocità sulla pendenza di {_n(math.degrees(m.slope))}°",
                        f"≥ {_n(m.v_slope * 3.6, 1)} km/h", f"{_n(v_slope * 3.6, 1)} km/h",
                        _status(v_slope >= m.v_slope * 0.999)))
    # Altezza del baricentro: quella calcolata dalle posizioni, se tutte le voci
    # ne hanno una; altrimenti quella dichiarata in cg_height_m.
    h_cg, h_origin = cg_height_used(d, res)
    if h_cg:
        phi = mobility.tipping_angle(d.mobility.track, h_cg)
        checks.append(Check("MR-11", "Angolo di ribaltamento laterale statico",
                            f"≥ {_n(math.degrees(m.stability))}°",
                            f"{_n(math.degrees(phi), 1)}° (h_G = {_n(h_cg, 2)} m, {h_origin})",
                            _status(phi >= m.stability)))
    else:
        checks.append(Check("MR-11", "Angolo di ribaltamento laterale statico",
                            f"≥ {_n(math.degrees(m.stability))}°",
                            "manca l'altezza del baricentro (posizioni o cg_height_m)", NV))

    # Budget di volume (nessun requisito numerico: confronto con le scelte del gruppo)
    checks.append(Check("Volume", "Volume della cabina rispetto al volume pressurizzato richiesto",
                        f"≥ {_n(fx.v_required, 2)} m³", f"{_n(fx.geom.volume, 2)} m³",
                        _status(fx.geom.volume >= fx.v_required * 0.999)))
    checks.append(Check("Volume", "Volume da stivare rispetto allo stivaggio disponibile",
                        f"≤ {_n(d.habitability.stowage, 2)} m³", f"{_n(fx.v_stowage_need, 2)} m³",
                        _status(fx.v_stowage_need <= d.habitability.stowage)))

    # MR-12: notte. Durata della notte nei sol tipo non inferiore a quella di
    # common.toml (circa 12 h); l'energia si verifica sulla notte più lunga fra
    # quella dichiarata e quella di common.toml.
    night_min = env.night
    shortest = min(d.operations.sol_types, key=lambda s: s.night)
    checks.append(Check("MR-12", "Durata della notte nei sol tipo",
                        f"≥ {_n(night_min / HOUR, 1)} h",
                        f"{_n(shortest.night / HOUR, 1)} h (sol tipo '{shortest.name}')",
                        _status(shortest.night >= night_min - 1.0)))
    usable = cap * d.battery.dod_max + dep.gen.fc_energy
    night_hours = max(max(s.night for s in d.operations.sol_types), night_min)
    worst_night = fx.p_service["night"] * night_hours
    available = usable + dep.gen.rps * night_hours
    checks.append(Check("MR-12", "Energia per la notte con equipaggio a bordo",
                        f"≥ {_n(worst_night / KWH, 1)} kWh",
                        f"{_n(available / KWH, 1)} kWh (accumulo utile + generazione notturna)",
                        _status(available >= worst_night and dep.sim.max_deficit <= usable + 1.0)))

    # MR-14: emergenza con quattro persone
    em = res.emergency
    checks.append(Check("MR-14", "Posti a bordo in emergenza", f"≥ {m.emergency_crew}",
                        f"{d.habitability.seats}", _status(d.habitability.seats >= m.emergency_crew)))
    checks.append(Check("MR-14", f"Rientro di {m.emergency_crew} persone da {_n(m.max_radius / 1e3)} km",
                        f"≤ {_n(m.emergency_duration / HOUR)} h; energia ≤ disponibile",
                        f"{_n(em.duration / HOUR, 1)} h; {_n(em.energy_need / KWH)} di "
                        f"{_n(em.energy_available / KWH)} kWh",
                        _status(em.duration <= m.emergency_duration
                                and em.energy_need <= em.energy_available)))

    # MR-15: rientro in tempesta
    st = res.storm
    checks.append(Check("MR-15", f"Rientro in tempesta ({_n(m.storm_irradiance_fraction * 100)}% di irraggiamento)",
                        f"energia richiesta ≤ disponibile",
                        f"{_n(st.energy_need / KWH)} di {_n(st.energy_available / KWH)} kWh "
                        f"in {_n(st.duration / HOUR, 1)} h",
                        _status(st.energy_need <= st.energy_available)))

    # MR-16: schermatura del riparo
    checks.append(Check("MR-16", "Schermatura del riparo per i due membri dell'equipaggio",
                        f"≥ {_n(m.spe_shield / 10)} g/cm² nelle direzioni non coperte dal suolo",
                        f"{_n(d.radiation.shield / 10, 1)} g/cm² su {_n(d.radiation.shelter_area, 1)} m²",
                        _status(d.radiation.shield >= m.spe_shield)))
    checks.append(Check("MR-16", "Dose efficace stimata per l'evento di riferimento",
                        f"< {_n(m.spe_dose_limit)} mSv (origine di MR-16)",
                        f"circa {_n(fx.spe_dose_shelter)} mSv nel riparo, {_n(fx.spe_dose_unshielded)} mSv senza",
                        INFO))

    # MR-19: ingombro al lancio (facoltativo)
    checks.extend(envelope_checks(d, m))

    # MR-20: massa a pieno carico
    checks.append(Check("MR-20", "Massa a pieno carico, margini compresi",
                        f"≤ {_n(m.mass_limit)} kg", f"{_n(b.total)} kg (riserva {_n(m.mass_limit - b.total)} kg)",
                        _status(b.total <= m.mass_limit)))

    # MR-21: margini
    mga_mean = b.mga / b.base_dry if b.base_dry else 0.0
    checks.append(Check("MR-21", "Margini di massa e di potenza applicati",
                        f"MGA {_n(c.margins.mga_existing * 100)}/{_n(c.margins.mga_modified * 100)}/{_n(c.margins.mga_new * 100)}% per voce, "
                        f"sistema {_n(c.margins.system * 100)}%, carichi +{_n(c.margins.power * 100)}%",
                        f"MGA medio {_n(mga_mean * 100, 1)}%, sistema {_n(b.system_margin)} kg",
                        OK))

    # MR-22: verifica strutturale con il modello FEM del gruppo. Lo strumento
    # riporta la massa e confronta con le soglie del brief i risultati dichiarati
    # (margine di sicurezza minimo fra i casi di carico, prime frequenze proprie).
    cab = d.cabin
    fem = fx.cabin.shell_source == "FEM"
    checks.append(Check("MR-22", "Massa della struttura dal modello FEM",
                        "massa del modello FEM nel budget",
                        "inserita" if fem else "stima con la massa areale",
                        INFO if fem else NV))
    for label, value, limit, unit, nd in (
            ("Margine di sicurezza minimo (casi di carico della Scheda)",
             cab.fem_min_margin, m.fem_margin_min, "", 2),
            ("Prima frequenza propria laterale, configurazione di lancio",
             cab.fem_freq_lateral, m.fem_freq_lateral_min, " Hz", 1),
            ("Prima frequenza propria assiale, configurazione di lancio",
             cab.fem_freq_axial, m.fem_freq_axial_min, " Hz", 1)):
        if value is None:
            checks.append(Check("MR-22", label, f"≥ {_n(limit, nd)}{unit}", "non dichiarato", NV))
        else:
            checks.append(Check("MR-22", label, f"≥ {_n(limit, nd)}{unit}", f"{_n(value, nd)}{unit}",
                                _status(value >= limit)))
    return checks


def cg_height_used(d, res) -> tuple[float | None, str]:
    """Altezza del baricentro usata per MR-11 [m] e sua origine.

    Se tutte le voci con massa hanno una posizione vale il baricentro
    calcolato; altrimenti l'altezza dichiarata in ``cg_height_m`` (se > 0).
    """
    if getattr(res, "cg_height", None):
        return res.cg_height, "dalle posizioni"
    if d.mobility.cg_height > 0:
        return d.mobility.cg_height, "da cg_height_m"
    return None, ""


def envelope_checks(d, m) -> list[Check]:
    """MR-19: ingombro nella carenatura (verifica geometrica semplificata).

    Rover perpendicolare all'asse della carenatura: la diagonale della pianta
    deve stare nel cerchio di diametro utile,  √(L² + B²) ≤ D.
    Rover parallelo all'asse: la sezione del rover deve stare nel cerchio
    insieme a quella del lander, che lo strumento non conosce. Il confronto
    √(B² + H²) ≤ D è quindi solo indicativo (INFORMATIVO).
    Il requisito chiede la carenatura SLS da 10 m (diametro utile 9,1 m); la
    compatibilità con la carenatura da 8,4 m del Block 1B (7,5 m) è facoltativa.
    """
    env = getattr(d, "envelope", None)
    if env is None:
        return [Check("MR-19", "Carenatura SLS da 10 m: ingombro al lancio", f"≤ {_n(m.fairing_diameter, 1)} m",
                      "sezione [envelope] non compilata", NV)]
    if env.orientation == "perpendicolare":
        size, what = math.hypot(env.length, env.width), "diagonale della pianta"
        status = lambda limit: _status(size <= limit)                    # noqa: E731
        note = ""
    else:
        size, what = math.hypot(env.width, env.height), "diagonale della sezione"
        status = lambda limit: INFO                                      # noqa: E731
        note = "; da verificare con la sezione del lander"
    return [Check("MR-19", f"Carenatura SLS da 10 m: {what}",
                  f"≤ {_n(m.fairing_diameter, 1)} m", f"{_n(size, 2)} m{note}", status(m.fairing_diameter)),
            Check("MR-19", f"Facoltativo, carenatura Block 1B: {what}",
                  f"≤ {_n(m.fairing_b1b_diameter, 1)} m", f"{_n(size, 2)} m{note}",
                  status(m.fairing_b1b_diameter))]
