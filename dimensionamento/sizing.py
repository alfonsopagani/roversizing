"""Ciclo di massa: chiusura della spirale di massa con un'iterazione a punto fisso.

Molte voci dipendono dalla massa totale del rover: la potenza di trazione, e
quindi l'azionamento e il sistema di potenza, e le voci dichiarate come
frazione della massa totale (per esempio telaio e ruote). La massa totale,
però, è la somma delle voci. Si cerca quindi il valore m* tale che

    m* = F(m*)

dove F(m) è la massa totale, margini compresi, calcolata supponendo che il
rover pesi m. Si parte da un valore iniziale e si itera

    m_(k+1) = F(m_k)

fino a quando la differenza fra due iterazioni è minore della tolleranza.

Convergenza. Vicino alla soluzione F(m) ≈ A + k·m, dove k = dF/dm è la
"somma delle frazioni": la parte di ogni kg aggiunto al rover che ritorna
come massa di azionamento, potenza, telaio e così via, margini compresi. Se
k < 1 l'iterazione converge a m* = A / (1 - k) e 1/(1 - k) è il fattore di
crescita della massa. Se k ≥ 1 non esiste una soluzione finita: ogni kg in
più ne richiede almeno un altro, e la massa diverge.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import SimpleNamespace

from . import eclss, habitability, mobility, power, radiation, structure, thermal
from .margins import Item, MassBudget, apply_margins


class SizingError(Exception):
    """Errore del modello (dati incoerenti), con un messaggio leggibile."""


# ---------------------------------------------------------------------------
# Parte indipendente dalla massa totale
# ---------------------------------------------------------------------------
def fixed_part(c, d) -> SimpleNamespace:
    """Calcola le grandezze che non dipendono dalla massa totale del rover."""
    m, env, ops = c.mission, c.environment, d.operations
    out = SimpleNamespace()
    duration_sols = sum(s.count for s in ops.sol_types)
    if duration_sols != m.excursion_sols:
        raise SizingError(f"[[operations.sol_types]]: i sol tipo sommano a {duration_sols} sol, "
                          f"ma l'escursione dura {m.excursion_sols} sol (MR-03).")
    for s in ops.sol_types:
        total = s.drive + s.day + s.night + s.eva
        if abs(total - env.sol) > 0.05 * 3600:
            raise SizingError(f"sol tipo '{s.name}': le ore dei modi sommano a {total / 3600:.2f} h, "
                              f"ma un sol dura {env.sol / 3600:.2f} h.")
    if power.drive_time(ops.sol_types) <= 0:
        raise SizingError("[[operations.sol_types]]: nessun sol prevede ore di guida.")
    if d.eva_access.suitport_evas + d.eva_access.airlock_evas <= 0:
        raise SizingError("[eva_access]: suitport_evas + airlock_evas deve essere almeno 1 (MR-04).")

    # Consumabili e serbatoi
    out.cons = eclss.consumables(c, d)
    out.tanks = eclss.tank_mass(out.cons, d.eclss)

    # Volume e geometria della cabina
    h = d.habitability
    out.v_required = habitability.pressurized_volume(h.nhv, h.nhv_fraction, h.stowage,
                                                     h.other_pressurized)
    try:
        out.geom = habitability.cabin_geometry(out.v_required, d.cabin.diameter, d.cabin.heads,
                                               d.cabin.head_ratio, d.cabin.length)
        out.geom = habitability.apply_cad(out.geom, d.cabin.cad_volume, d.cabin.cad_area)
    except ValueError as exc:
        raise SizingError(str(exc)) from None
    out.v_stowage_need = habitability.stowage_required(
        out.cons.food_volume, out.cons.water / 1000.0, h.water_inside, h.stowage_items)

    # Struttura della cabina
    out.cabin = structure.cabin_masses(out.geom.area, d.cabin)

    # Radiazioni
    r = d.radiation
    out.shelter = radiation.shelter_mass(r.shield, r.shelter_area, out.cons.water,
                                         r.water_fraction, r.other_shielding)
    # Dosi informative, riportate accanto alla verifica di MR-16 (Scheda, Radiazioni)
    out.spe_dose_shelter = radiation.spe_dose(r.shield, env.spe_dose_unshielded, env.spe_dose_shelter,
                                              env.spe_shelter_shield)
    out.spe_dose_unshielded = env.spe_dose_unshielded
    out.gcr_dose = env.gcr_dose * m.excursion_sols * env.sol

    # Carichi di servizio e controllo termico
    out.p_service = power.service_loads(d.loads, c.margins.power)
    out.e_service = power.service_energy(ops.sol_types, out.p_service)
    t = d.thermal
    out.t_sink = thermal.sink_temperature(env.ground_hot, env.sky_hot, t.ground_view_factor)
    heat_nominal = thermal.heat_load(m.crew, d.eclss.metabolic, max(out.p_service.values()),
                                     t.dissipated_fraction)
    heat_emergency = thermal.heat_load(m.emergency_crew, d.eclss.metabolic,
                                       (1.0 + c.margins.power) * d.emergency.load, t.dissipated_fraction)
    out.heat = max(heat_nominal, heat_emergency)
    out.heat_case = (f"nominale, {m.crew} persone" if heat_nominal >= heat_emergency
                     else f"emergenza, {m.emergency_crew} persone")
    try:
        out.radiator_area = thermal.radiator_area(out.heat, t.radiator_temperature, out.t_sink,
                                                  t.emissivity)
    except ValueError as exc:
        raise SizingError(str(exc)) from None
    out.heat_loss = thermal.insulation_heat_loss(out.geom.area, d.cabin.insulation_conductivity,
                                                 d.cabin.insulation_thickness,
                                                 d.eclss.cabin_temperature, env.ground_cold)
    return out


# ---------------------------------------------------------------------------
# Parte dipendente dalla massa totale: trazione e sistema di potenza
# ---------------------------------------------------------------------------
def traction_distance(c, d) -> float:
    """Distanza su cui si calcola l'energia di trazione [m].

        d = max(d_MR-08, t_guida · v_media)

    È la percorrenza pianificata dalla ConOps (ore di guida per velocità
    media), con il minimo di MR-08 (100 km).
    """
    planned = power.drive_time(d.operations.sol_types) * d.operations.v_mean
    return max(c.mission.distance, planned)


def mass_dependent(c, d, fx, mass: float) -> SimpleNamespace:
    """Trazione, generazione e batteria per un rover di massa ``mass`` [kg]."""
    m, env, mob, ops = c.mission, c.environment, d.mobility, d.operations
    arch = d.architecture.power
    out = SimpleNamespace()

    # Trazione (MR-08, MR-10, MR-11)
    out.p_peak, out.peak_case = mobility.peak_power(mass, env.g, mob.crr, mob.eta, m.v_flat,
                                                    m.slope, m.v_slope)
    out.distance = traction_distance(c, d)
    out.e_traction = mobility.traction_energy(mass, env.g, mob.crr, mob.eta, out.distance,
                                              ops.climb, ops.maneuver_margin)
    out.drive_mass = mobility.drive_mass(out.p_peak, mob.drive_specific_mass)

    # Generazione e simulazione dell'escursione
    t_drive = power.drive_time(ops.sol_types)
    traction_rate = out.e_traction / t_drive                  # potenza media di trazione in guida [W]
    out.traction_rate = traction_rate
    e_total = sum(fx.e_service.values()) + out.e_traction
    duration = m.excursion_sols * env.sol
    out.e_total = e_total
    try:
        out.gen = power.generation(arch, d, ops.sol_types, fx.p_service, traction_rate,
                                   e_total, duration, env.sol)
    except ValueError as exc:
        raise SizingError(str(exc)) from None
    sun = d.pv.sun_hours if hasattr(d, "pv") else 1.0
    pv_moving = d.pv.deployed_while_driving if hasattr(d, "pv") else False
    out.sim = power.simulate(power.sol_sequence(ops.sol_types, ops.sequence), fx.p_service, traction_rate,
                             out.gen, env.sol, sun, arch == "celle_combustibile", pv_moving)

    # Batteria: energia utile, potenza di picco, DOD
    b = d.battery
    out.p_peak_electric = out.p_peak + fx.p_service["drive"]       # picco di trazione + servizio in guida
    out.battery_capacity, out.battery_criterion = power.battery_capacity(
        out.sim.max_deficit, b.dod_max, out.p_peak_electric,
        out.gen.rps + out.gen.fc_energy / duration, b.c_rate_max)
    out.battery_mass = out.battery_capacity / b.specific_energy
    out.rps_mass = out.gen.rps / d.rps.specific_power if out.gen.rps > 0 else 0.0
    out.pv_mass = out.gen.pv / d.pv.specific_power if out.gen.pv > 0 else 0.0
    out.pv_area = out.gen.pv / d.pv.power_density if out.gen.pv > 0 else 0.0
    out.fc_mass = (d.fuel_cell.fixed + d.fuel_cell.specific_mass * out.gen.fc_energy
                   if arch == "celle_combustibile" else 0.0)
    return out


# ---------------------------------------------------------------------------
# Budget di massa per una massa totale assegnata
# ---------------------------------------------------------------------------
def build_items(c, d, fx, dep, mass: float) -> list[Item]:
    """Elenco delle voci del budget di massa, con l'origine di ciascun valore.

    Le posizioni vengono da [positions]; più voci condividono la stessa chiave
    quando stanno nello stesso punto del layout (vedi ``inputs.POSITION_KEYS``).
    """
    pos = getattr(d, "positions", SimpleNamespace())
    p = lambda key: getattr(pos, key, None)                      # noqa: E731
    cab, ecl = d.cabin, d.eclss
    items = [
        Item("Guscio della cabina", "struttura", fx.cabin.shell, cab.shell_maturity,
             fx.cabin.shell_source, p("cabin")),
        Item("Pavimento e pareti interne", "struttura", fx.cabin.interior, cab.interior_maturity,
             "massa areale", p("cabin")),
        Item("Isolamento della cabina", "termico", fx.cabin.insulation, cab.insulation_maturity,
             "spessore x densità", p("cabin")),
        Item("Serbatoi di O2, N2 e acqua", "eclss", fx.tanks, ecl.tanks_maturity,
             "fattori dei serbatoi", p("tanks")),
        Item("Radiatore della cabina", "termico", fx.radiator_area * d.thermal.radiator_areal,
             d.thermal.maturity, "bilancio radiativo", p("radiator")),
        Item("Azionamento (motori, riduttori, controllori)", "mobilita", dep.drive_mass,
             d.mobility.drive_maturity, "kg/kW x potenza di picco", p("drive")),
        Item("Batteria", "potenza", dep.battery_mass, d.battery.maturity,
             f"dimensionata su {dep.battery_criterion}", p("battery")),
    ]
    if fx.shelter.added > 0:
        items.append(Item("Schermo aggiuntivo del riparo", "radiazioni", fx.shelter.added,
                          d.radiation.maturity, "g/cm2 x superficie", p("shield")))
    if dep.rps_mass > 0:
        items.append(Item("RPS", "potenza", dep.rps_mass, d.rps.maturity, "W/kg", p("rps")))
    if dep.pv_mass > 0:
        items.append(Item("Ala fotovoltaica", "potenza", dep.pv_mass, d.pv.maturity, "W/kg", p("pv")))
    if dep.fc_mass > 0:
        items.append(Item("Celle a combustibile, serbatoi e reagenti", "potenza", dep.fc_mass,
                          d.fuel_cell.maturity, "parte fissa + kg/kWh", p("fuel_cell")))
    for it in d.items:
        base = it.mass if it.mass is not None else it.fraction * mass
        source = it.source or ("frazione della massa totale" if it.mass is None else "dichiarata")
        items.append(Item(it.name, it.subsystem, base, it.maturity, source, it.position))

    # Masse fisse, senza margini (MR-21)
    m, cons = c.mission, fx.cons
    items += [
        Item("Carico scientifico", "carico utile", m.payload, None, "MR-06", p("payload"), True),
        Item("Equipaggio", "equipaggio", m.crew * ecl.body_mass, None, "MR-01", p("crew"), True),
        Item("Tute EVA", "eva", d.suits.count * d.suits.mass, None, "dichiarata", p("suits"), True),
        Item("O2", "consumabili", cons.o2, None, "ECLSS", p("tanks"), True),
        Item("N2", "consumabili", cons.n2, None, "ECLSS", p("tanks"), True),
        Item("Acqua", "consumabili", cons.water, None, "ECLSS", p("tanks"), True),
        Item("Cibo", "consumabili", cons.food, None, "ECLSS", p("crew"), True),
    ]
    if cons.sorbent > 0:
        items.append(Item("Assorbitore di CO2", "consumabili", cons.sorbent, None, "ECLSS",
                          p("crew"), True))
    return items


def evaluate(c, d, fx, mass: float) -> tuple[MassBudget, SimpleNamespace]:
    """F(m): budget di massa, margini compresi, per un rover di massa ``mass``."""
    dep = mass_dependent(c, d, fx, mass)
    budget = apply_margins(build_items(c, d, fx, dep, mass), c.margins)
    return budget, dep


# ---------------------------------------------------------------------------
# Iterazione a punto fisso
# ---------------------------------------------------------------------------
@dataclass
class LoopResult:
    converged: bool
    mass: float
    iterations: int
    history: list[float]
    gain: float                       # k = dF/dm, "somma delle frazioni"
    message: str = ""
    contributions: dict[str, float] = field(default_factory=dict)   # dF/dm per voce


def loop_gain(c, d, fx, mass: float, step: float = 1.0) -> tuple[float, dict[str, float]]:
    """Stima numerica di k = dF/dm e del contributo di ciascuna voce.

        k ≈ [F(m + Δm) - F(m)] / Δm
    Il contributo di una voce comprende il suo MGA e la sua quota del margine
    di sistema.
    """
    b0, _ = evaluate(c, d, fx, mass)
    b1, _ = evaluate(c, d, fx, mass + step)
    sys = c.margins.system
    contrib = {}
    for i0, i1 in zip(b0.items, b1.items):
        delta = (i1.predicted - i0.predicted + (0 if i0.fixed else sys * (i1.base - i0.base))) / step
        if abs(delta) > 1e-6:
            contrib[i0.name] = delta
    return (b1.total - b0.total) / step, contrib


def close_mass_loop(c, d, fx=None, start: float | None = None,
                    tol: float = 0.1, max_iter: int = 200) -> LoopResult:
    """Chiude il ciclo di massa con l'iterazione m_(k+1) = F(m_k).

    Si arresta quando |m_(k+1) - m_k| < tol [kg]. Se la massa supera dieci
    volte il limite di MR-20, o se dopo ``max_iter`` iterazioni non c'è
    convergenza, restituisce converged = False con un messaggio che riporta la
    somma delle frazioni k e le voci che vi contribuiscono.
    """
    fx = fx or fixed_part(c, d)
    limit = c.mission.mass_limit
    m = start if start is not None else limit          # valore iniziale: il limite di MR-20
    history = [m]
    for k in range(1, max_iter + 1):
        m_new = evaluate(c, d, fx, m)[0].total
        history.append(m_new)
        if not math.isfinite(m_new) or m_new > 10 * limit:
            break
        if abs(m_new - m) < tol:
            gain, contrib = loop_gain(c, d, fx, m_new)
            return LoopResult(True, m_new, k, history, gain, contributions=contrib)
        m = m_new
    # Non convergenza: si stima k sull'ultimo valore finito
    m_last = next(v for v in reversed(history) if math.isfinite(v))
    gain, contrib = loop_gain(c, d, fx, min(m_last, 10 * limit))
    top = sorted(contrib.items(), key=lambda kv: -kv[1])[:5]
    lines = "\n".join(f"    {name:45s} {v:6.3f} kg/kg" for name, v in top)
    if gain >= 1.0:
        msg = (f"Il ciclo di massa non converge: la somma delle frazioni è k = {gain:.3f} ≥ 1.\n"
               f"Ogni kg aggiunto al rover richiede {gain:.2f} kg di altre voci, quindi non esiste una\n"
               f"massa finita che chiuda il bilancio. Voci che dipendono dalla massa totale:\n{lines}")
    else:
        msg = (f"Il ciclo di massa non converge entro {max_iter} iterazioni o supera dieci volte il\n"
               f"limite di MR-20 (ultimo valore {m_last:,.0f} kg; somma delle frazioni k = {gain:.3f}).\n"
               f"Voci che dipendono dalla massa totale:\n{lines}")
    return LoopResult(False, m_last, len(history) - 1, history, gain, msg, contrib)


# ---------------------------------------------------------------------------
# Esecuzione completa
# ---------------------------------------------------------------------------
def return_cases(c, d, dep, mass: float) -> tuple[power.Return, power.Return]:
    """Rientri dal punto più lontano: emergenza con quattro persone (MR-14) e
    tempesta di polvere (MR-15). La salita del rientro è la quota della salita
    cumulata proporzionale alla distanza."""
    m, env, mob, ops = c.mission, c.environment, d.mobility, d.operations
    climb = ops.climb * m.max_radius / traction_distance(c, d)
    stored_full = dep.battery_capacity * d.battery.dod_max + dep.gen.fc_energy
    sun = d.pv.sun_hours if hasattr(d, "pv") else 1.0
    pv_moving = d.pv.deployed_while_driving if hasattr(d, "pv") else False
    light = env.sol - max(s.night for s in ops.sol_types)     # giorno più corto dei sol tipo
    cases = []
    for case, extra_crew, pv_factor in ((d.emergency, m.emergency_crew - m.crew, 1.0),
                                        (d.storm, 0, m.storm_irradiance_fraction)):
        m_case = mass + extra_crew * d.eclss.body_mass
        e_tr = mobility.traction_energy(m_case, env.g, mob.crr, mob.eta, m.max_radius, climb,
                                        ops.maneuver_margin)
        cases.append(power.return_trip(m.max_radius, case.v_return, case.drive_per_sol, env.sol,
                                       (1.0 + c.margins.power) * case.load, e_tr, dep.gen,
                                       pv_factor, sun, case.soc_initial * stored_full,
                                       light, pv_moving))
    return cases[0], cases[1]


def center_of_gravity(items: list[Item]) -> tuple[list[float] | None, list[str]]:
    """Baricentro [x, y, z] delle masse previste, se tutte le voci hanno una posizione.

        x_G = Σ m_i·x_i / Σ m_i   (e analoghe per y e z)

    Assi: x longitudinale, y laterale, z verticale dal suolo. Il margine di
    sistema non ha una posizione e non entra nel calcolo.
    """
    missing = [it.name for it in items if it.position is None and it.predicted > 0]
    if missing:
        return None, missing
    located = [it for it in items if it.predicted > 0]
    total = sum(it.predicted for it in located)
    cg = [sum(it.predicted * it.position[k] for it in located) / total for k in range(3)]
    return cg, []


@dataclass
class Result:
    common: SimpleNamespace
    design: SimpleNamespace
    fixed: SimpleNamespace
    loop: LoopResult
    budget: MassBudget | None = None
    dep: SimpleNamespace | None = None
    emergency: power.Return | None = None
    storm: power.Return | None = None
    cg: list[float] | None = None
    cg_missing: list[str] = field(default_factory=list)
    cg_height: float | None = None
    design_nominal: SimpleNamespace | None = None   # solo nella verifica fuori progetto


def run(c, d) -> Result:
    """Esegue il dimensionamento: parte fissa, ciclo di massa, budget finale."""
    fx = fixed_part(c, d)
    loop = close_mass_loop(c, d, fx)
    result = Result(c, d, fx, loop)
    if loop.converged:
        result.budget, result.dep = evaluate(c, d, fx, loop.mass)
        result.emergency, result.storm = return_cases(c, d, result.dep, loop.mass)
        result.cg, result.cg_missing = center_of_gravity(result.budget.items)
        result.cg_height = result.cg[2] if result.cg else None
    return result


# ---------------------------------------------------------------------------
# Verifica fuori progetto (progetto congelato)
# ---------------------------------------------------------------------------
def off_design(c, d_nominal, d_changed) -> tuple[Result, Result]:
    """Verifica fuori progetto: il rover dimensionato con ``d_nominal`` opera
    nelle condizioni di ``d_changed`` (per esempio C_rr = 0,6).

    Restano quelli del progetto nominale: massa totale e budget di massa,
    potenza di trazione installata, capacità della batteria, generazione (RPS,
    ala, reagenti delle celle). Con i dati di ``d_changed`` si ricalcolano:
    energia di trazione, carichi di servizio, bilancio di energia
    dell'escursione con la batteria installata, rientri di MR-14 e MR-15.
    Le verifiche dei requisiti dicono allora quali requisiti il progetto
    congelato non rispetta più.
    """
    if d_changed.architecture.power != d_nominal.architecture.power:
        raise SizingError("verifica fuori progetto: l'architettura di potenza non si può cambiare "
                          "(cambierebbe il progetto, non le condizioni operative).")
    nominal = run(c, d_nominal)
    if not nominal.loop.converged:
        raise SizingError("verifica fuori progetto: il progetto nominale non converge.")
    env, mob, ops = c.environment, d_changed.mobility, d_changed.operations
    mass, dep0 = nominal.loop.mass, nominal.dep
    fx = fixed_part(c, d_changed)
    dep = SimpleNamespace(**vars(dep0))                          # dimensionamento congelato
    dep.distance = traction_distance(c, d_changed)
    dep.e_traction = mobility.traction_energy(mass, env.g, mob.crr, mob.eta, dep.distance,
                                              ops.climb, ops.maneuver_margin)
    dep.traction_rate = dep.e_traction / power.drive_time(ops.sol_types)
    dep.e_total = sum(fx.e_service.values()) + dep.e_traction
    sun = d_changed.pv.sun_hours if hasattr(d_changed, "pv") else 1.0
    pv_moving = d_changed.pv.deployed_while_driving if hasattr(d_changed, "pv") else False
    dep.sim = power.simulate(power.sol_sequence(ops.sol_types, ops.sequence), fx.p_service,
                             dep.traction_rate, dep0.gen, env.sol, sun,
                             d_changed.architecture.power == "celle_combustibile", pv_moving)
    off = Result(c, d_changed, fx, nominal.loop, nominal.budget, dep)
    off.design_nominal = d_nominal
    off.emergency, off.storm = return_cases(c, d_changed, dep, mass)
    off.cg, off.cg_missing, off.cg_height = nominal.cg, nominal.cg_missing, nominal.cg_height
    return nominal, off
