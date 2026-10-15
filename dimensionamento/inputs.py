"""Lettura e validazione dei dati di ingresso.

Lo strumento legge due file TOML:

* ``common.toml`` (nel pacchetto): requisiti di missione e ambiente di Marte,
  uguali per tutti i gruppi;
* il file del gruppo (per esempio ``progetti/esempio.toml``): tutte le scelte e
  le ipotesi di progetto.

Convenzione sulle unità
-----------------------
Nel file di input il suffisso della chiave indica l'unità: ``v_flat_kmh = 5``
è una velocità in km/h. Dopo la lettura ogni grandezza è convertita in SI e
il suffisso viene tolto: nel codice ``mission.v_flat`` vale 5/3,6 m/s.
La tabella ``UNIT_SUFFIXES`` elenca i suffissi riconosciuti e il fattore di
conversione. Le chiavi senza suffisso sono adimensionali o sono numeri puri
(conteggi, frazioni, rendimenti).

I dati letti diventano oggetti ``SimpleNamespace``: si accede ai valori con il
punto, per esempio ``design.mobility.crr``.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

try:                                   # Python >= 3.11
    import tomllib
except ModuleNotFoundError:            # Python 3.10: serve il pacchetto tomli
    try:
        import tomli as tomllib        # type: ignore[no-redef]
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Questo strumento richiede Python 3.11 o successivo. Con Python 3.10 "
            "installare il pacchetto tomli:  python -m pip install tomli"
        ) from exc

from .constants import DAY, G_CM2, HOUR, KWH


class InputError(Exception):
    """Errore nei dati di ingresso, con un messaggio leggibile."""


# ---------------------------------------------------------------------------
# Unità: suffisso -> fattore moltiplicativo verso SI.
# L'ordine conta: i suffissi più lunghi vanno controllati per primi.
# ---------------------------------------------------------------------------
UNIT_SUFFIXES = [
    ("_msv_d", 1.0 / DAY),       # mSv al giorno -> mSv/s
    ("_kg_cmd", 1.0 / DAY),      # kg per persona al giorno  -> kg/(persona s)
    ("_kg_cmh", 1.0 / HOUR),     # kg per persona all'ora    -> kg/(persona s)
    ("_m3_cmd", 1.0 / DAY),      # m^3 per persona al giorno -> m^3/(persona s)
    ("_wh_kg", HOUR),            # Wh/kg  -> J/kg
    ("_kg_kwh", 1.0 / KWH),      # kg/kWh -> kg/J
    ("_kg_kw", 1.0e-3),          # kg/kW  -> kg/W
    ("_kg_m2", 1.0),             # kg/m^2
    ("_kg_m3", 1.0),             # kg/m^3
    ("_g_cm2", G_CM2),           # g/cm^2 -> kg/m^2
    ("_w_kg", 1.0),              # W/kg
    ("_w_m2", 1.0),              # W/m^2
    ("_kg_d", 1.0 / DAY),        # kg al giorno -> kg/s
    ("_kmh", 1.0 / 3.6),         # km/h -> m/s
    ("_kwh", KWH),               # kWh -> J
    ("_kpa", 1.0e3),             # kPa -> Pa
    ("_mpa", 1.0e6),             # MPa -> Pa
    ("_deg", math.pi / 180.0),   # gradi -> rad
    ("_msv", 1.0),               # mSv (lasciato in mSv)
    ("_km", 1.0e3),              # km -> m
    ("_kw", 1.0e3),              # kW -> W
    ("_m3", 1.0),                # m^3
    ("_m2", 1.0),                # m^2
    ("_kg", 1.0),                # kg
    ("_h", HOUR),                # ore -> s
    ("_d", DAY),                 # giorni -> s
    ("_w", 1.0),                 # W
    ("_hz", 1.0),                # Hz
    ("_k", 1.0),                 # kelvin
    ("_m", 1.0),                 # m
]


def si_name(key: str) -> tuple[str, float]:
    """Restituisce il nome senza suffisso e il fattore di conversione in SI."""
    for suffix, factor in UNIT_SUFFIXES:
        if key.endswith(suffix):
            return key[: -len(suffix)], factor
    return key, 1.0


# ---------------------------------------------------------------------------
# Schema del file del gruppo
# ---------------------------------------------------------------------------
@dataclass
class Spec:
    """Descrizione di una chiave: tipo, obbligatorietà, limiti, scelte ammesse."""
    kind: str                       # float, int, str, bool, floats, ints, vec3
    required: bool = True
    lo: float | None = None
    hi: float | None = None
    choices: tuple[str, ...] | None = None
    default: object = None


MATURITY = ("da_progettare", "derivato", "esistente")
ARCHITECTURES = ("batterie", "rps", "fotovoltaico", "celle_combustibile", "ibrido")
SUBSYSTEMS = ("struttura", "mobilita", "potenza", "termico", "eclss", "abitabilita",
              "avionica", "comunicazioni", "eva", "radiazioni", "altro")
HEADS = ("semisferici", "ellittici")

F = lambda lo=0.0, hi=None, **kw: Spec("float", lo=lo, hi=hi, **kw)   # noqa: E731
FRAC = Spec("float", lo=0.0, hi=1.0)
MAT = Spec("str", choices=MATURITY)

SCHEMA: dict[str, dict[str, Spec]] = {
    "group": {
        "name": Spec("str"),
        "version": Spec("str"),
    },
    "architecture": {
        "power": Spec("str", choices=ARCHITECTURES),
    },
    "operations": {
        "v_mean_kmh": F(lo=0.01),
        "climb_m": F(),
        "maneuver_margin": FRAC,
        "reserve_d": F(),
        "excursions": Spec("int", lo=1),
        "sequence": Spec("strs", required=False),
    },
    "loads": {
        "drive_kw": F(), "day_kw": F(), "night_kw": F(), "eva_kw": F(),
    },
    "emergency": {
        "v_return_kmh": F(lo=0.01),
        "drive_per_sol_h": F(lo=0.1),
        "load_kw": F(),
        "soc_initial": FRAC,
    },
    "storm": {
        "v_return_kmh": F(lo=0.01),
        "drive_per_sol_h": F(lo=0.1),
        "load_kw": F(),
        "soc_initial": FRAC,
    },
    "habitability": {
        "nhv_m3": F(lo=0.1),
        "nhv_fraction": Spec("float", lo=0.01, hi=1.0),
        "stowage_m3": F(),
        "stowage_items_m3": F(),
        "other_pressurized_m3": F(),
        "water_inside": Spec("bool"),
        "seats": Spec("int", lo=1),
    },
    "cabin": {
        "heads": Spec("str", choices=HEADS),
        "head_ratio": Spec("float", required=False, lo=0.05, hi=1.0, default=1.0),
        "diameter_m": F(lo=0.5),
        "length_m": F(),
        "shell_areal_kg_m2": F(),
        "interior_areal_kg_m2": F(),
        "insulation_thickness_m": F(),
        "insulation_density_kg_m3": F(),
        "insulation_conductivity": F(),
        "shell_maturity": MAT,
        "interior_maturity": MAT,
        "insulation_maturity": MAT,
        "fem_shell_kg": Spec("float", required=False, lo=0.0, default=0.0),
        "fem_nonmodeled_fraction": Spec("float", required=False, lo=0.0, default=0.0),
        "fem_min_margin": Spec("float", required=False),
        "fem_freq_lateral_hz": Spec("float", required=False, lo=0.0),
        "fem_freq_axial_hz": Spec("float", required=False, lo=0.0),
        "cad_volume_m3": Spec("float", required=False, lo=0.0, default=0.0),
        "cad_area_m2": Spec("float", required=False, lo=0.0, default=0.0),
    },
    "eclss": {
        "o2_kg_cmd": F(), "co2_kg_cmd": F(), "food_kg_cmd": F(), "food_volume_m3_cmd": F(),
        "potable_water_kg_cmd": F(), "hygiene_water_kg_cmd": F(),
        "eva_o2_kg_cmh": F(), "eva_o2_fixed_kg": F(),
        "eva_water_kg_cmh": F(), "eva_food_kg_cmh": F(),
        "cabin_leak_kg_d": F(), "metabolic_w": F(), "body_mass_kg": F(lo=1.0),
        "o2_recovery": FRAC, "water_recovery": FRAC,
        "co2_sorbent_ratio": F(),
        "o2_tank_ratio": F(), "n2_tank_ratio": F(), "water_tank_ratio": F(),
        "cabin_temperature_k": F(lo=200.0, hi=350.0),
        "tanks_maturity": MAT,
    },
    "eva_access": {
        "suitport_evas": Spec("int", lo=0),
        "airlock_evas": Spec("int", lo=0),
        "suitport_loss_kg": F(),
        "suitport_cycles_per_eva": Spec("int", lo=0),
        "airlock_gas_m3": F(),
        "airlock_loss_fraction": FRAC,
        "airlock_cycles_per_eva": Spec("int", lo=0),
    },
    "suits": {
        "count": Spec("int", lo=0),
        "mass_kg": F(),
    },
    "radiation": {
        "shield_g_cm2": F(),
        "shelter_area_m2": F(),
        "water_fraction": FRAC,
        "other_shielding_kg": F(),
        "maturity": MAT,
    },
    "mobility": {
        "crr": Spec("float", lo=0.0, hi=1.0),
        "eta": Spec("float", lo=0.05, hi=1.0),
        "drive_specific_mass_kg_kw": F(),
        "drive_maturity": MAT,
        "wheel_diameter_m": F(lo=0.1),
        "driven_wheels": Spec("int", lo=1),
        "track_m": F(lo=0.1),
        "cg_height_m": F(),
    },
    "battery": {
        "specific_energy_wh_kg": F(lo=1.0),
        "dod_max": Spec("float", lo=0.05, hi=1.0),
        "c_rate_max": F(lo=0.01),
        "maturity": MAT,
        "cycle_dod": Spec("floats"),
        "cycle_count": Spec("ints"),
    },
    "rps": {
        "specific_power_w_kg": F(lo=0.01),
        "power_kw": F(),
        "maturity": MAT,
    },
    "pv": {
        "specific_power_w_kg": F(lo=0.01),
        "power_density_w_m2": F(lo=0.01),
        "optical_depth": F(),
        "sun_hours_h": F(lo=0.1),
        "deployed_while_driving": Spec("bool", required=False, default=False),
        "power_kw": F(),
        "maturity": MAT,
    },
    "fuel_cell": {
        "fixed_kg": F(),
        "specific_mass_kg_kwh": F(),
        "maturity": MAT,
    },
    "envelope": {                     # facoltativa: verifica di MR-19
        "length_m": F(lo=0.1),
        "width_m": F(lo=0.1),
        "height_m": F(lo=0.1),
        "orientation": Spec("str", choices=("perpendicolare", "parallelo")),
    },
    "thermal": {
        "radiator_temperature_k": F(lo=1.0),
        "emissivity": Spec("float", lo=0.01, hi=1.0),
        "ground_view_factor": FRAC,
        "radiator_areal_kg_m2": F(),
        "dissipated_fraction": FRAC,
        "maturity": MAT,
    },
}

# Sezioni richieste solo da alcune architetture di potenza
ARCH_SECTIONS = {
    "rps": ("rps",),
    "fotovoltaico": ("pv",),
    "celle_combustibile": ("fuel_cell",),
    "ibrido": ("rps", "pv"),
    "batterie": (),
}
OPTIONAL_SECTIONS = {"rps", "pv", "fuel_cell", "positions", "envelope"}

SOL_TYPE_SPEC = {
    "name": Spec("str"),
    "count": Spec("int", lo=0),
    "drive_h": F(), "day_h": F(), "night_h": F(), "eva_h": F(),
}
STUDENT_SPEC = {
    "name": Spec("str"),
    "id": Spec("str"),
    "role": Spec("str", required=False, default=""),
}
ITEM_SPEC = {
    "name": Spec("str"),
    "subsystem": Spec("str", choices=SUBSYSTEMS),
    "mass_kg": Spec("float", required=False, lo=0.0),
    "fraction": Spec("float", required=False, lo=0.0, hi=1.0),
    "maturity": MAT,
    "source": Spec("str", required=False, default=""),
    "position_m": Spec("vec3", required=False),
}
# Voci calcolate dallo strumento a cui si può assegnare una posizione [x, y, z]
POSITION_KEYS = ("cabin", "tanks", "crew", "suits", "shield", "radiator", "drive",
                 "payload", "battery", "rps", "pv", "fuel_cell")
"""Chiavi di [positions]. Ogni chiave raggruppa le voci calcolate che stanno
nello stesso punto del layout:
    cabin      guscio, pavimento e pareti interne, isolamento (masse distribuite
               sull'involucro: baricentro circa al centro geometrico della cabina)
    tanks      serbatoi e loro contenuto (O2, N2, acqua)
    crew       equipaggio, cibo e assorbitore di CO2 (in cabina)
    suits      tute EVA (ai suitport o nell'airlock)
    shield     schermo aggiuntivo del riparo (solo se presente)
    radiator, drive, payload
    battery, rps, pv, fuel_cell   solo le tecnologie dell'architettura scelta
"""


# ---------------------------------------------------------------------------
# Validazione
# ---------------------------------------------------------------------------
def _where(file: str, section: str, key: str | None = None) -> str:
    loc = f"{file}, sezione [{section}]"
    return loc + (f", chiave '{key}'" if key else "")


def _check_value(value, spec: Spec, where: str):
    """Controlla tipo, limiti e scelte di un valore; restituisce il valore."""
    kind = spec.kind
    if kind == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InputError(f"{where}: atteso un numero, trovato {value!r}.")
        value = float(value)
    elif kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise InputError(f"{where}: atteso un numero intero, trovato {value!r}.")
    elif kind == "str":
        if not isinstance(value, str):
            raise InputError(f"{where}: attesa una stringa fra virgolette, trovato {value!r}.")
    elif kind == "bool":
        if not isinstance(value, bool):
            raise InputError(f"{where}: atteso true o false, trovato {value!r}.")
    elif kind in ("floats", "ints"):
        if not isinstance(value, list) or not value:
            raise InputError(f"{where}: attesa una lista non vuota, per esempio [1, 2, 3].")
        num = (int,) if kind == "ints" else (int, float)
        if any(isinstance(v, bool) or not isinstance(v, num) for v in value):
            raise InputError(f"{where}: la lista contiene valori non numerici.")
        value = [float(v) for v in value] if kind == "floats" else value
    elif kind == "strs":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise InputError(f"{where}: attesa una lista di nomi fra virgolette.")
    elif kind == "vec3":
        if (not isinstance(value, list) or len(value) != 3
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value)):
            raise InputError(f"{where}: attesa una posizione [x, y, z] in metri.")
        value = [float(v) for v in value]
    if spec.choices is not None and value not in spec.choices:
        scelte = ", ".join(f'"{c}"' for c in spec.choices)
        raise InputError(f"{where}: valore {value!r} non ammesso. Valori possibili: {scelte}.")
    if kind in ("float", "int"):
        if spec.lo is not None and value < spec.lo:
            raise InputError(f"{where}: il valore {value} è minore del minimo ammesso ({spec.lo}).")
        if spec.hi is not None and value > spec.hi:
            raise InputError(f"{where}: il valore {value} è maggiore del massimo ammesso ({spec.hi}).")
    return value


def _check_table(table: dict, specs: dict[str, Spec], where: str) -> dict:
    """Valida una tabella TOML rispetto a uno schema e converte le unità in SI."""
    if not isinstance(table, dict):
        raise InputError(f"{where}: attesa una tabella.")
    unknown = set(table) - set(specs)
    if unknown:
        raise InputError(f"{where}: chiave non riconosciuta {sorted(unknown)}. "
                         "Controllare l'ortografia o lo schema in inputs.py.")
    out = {}
    for key, spec in specs.items():
        if key not in table:
            if spec.required:
                raise InputError(f"{where}: manca la chiave obbligatoria '{key}'.")
            value = spec.default
        else:
            value = _check_value(table[key], spec, f"{where}, chiave '{key}'")
        name, factor = si_name(key)
        if name in out:
            raise InputError(f"{where}: le chiavi '{key}' e un'altra hanno lo stesso nome "
                             f"senza unità ('{name}'). Rinominare una delle due nello schema.")
        if isinstance(value, float) and spec.kind == "float":
            value = value * factor
        out[name] = value
    return out


def _ns(obj):
    """Converte ricorsivamente dizionari in SimpleNamespace."""
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _ns(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_ns(v) for v in obj]
    return obj


def _parse_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        raise InputError(f"File non trovato: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise InputError(f"Errore di sintassi TOML in {path.name}: {exc}") from None


# ---------------------------------------------------------------------------
# Dati comuni
# ---------------------------------------------------------------------------
COMMON_PATH = Path(__file__).with_name("common.toml")

# Impronta del contenuto di common.toml distribuito con lo strumento. Si calcola
# sul contenuto letto (non sui byte del file), quindi non cambia con gli a capo
# di Windows o con i commenti.
COMMON_FINGERPRINT = "53679c09ebcaf73e"


def fingerprint(data: dict) -> str:
    text = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()[:16]


def load_common(path: Path = COMMON_PATH) -> SimpleNamespace:
    """Legge i requisiti comuni e l'ambiente di Marte, convertiti in SI."""
    raw = _parse_toml(path)
    out = {}
    for section in ("mission", "assumptions", "margins", "environment"):
        if section not in raw:
            raise InputError(f"{path.name}: manca la sezione [{section}].")
        conv = {}
        for key, value in raw[section].items():
            name, factor = si_name(key)
            if name in conv:
                raise InputError(f"{path.name}, sezione [{section}]: due chiavi diventano '{name}' "
                                 "dopo la rimozione del suffisso di unità.")
            numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
            conv[name] = value * factor if numeric and factor != 1.0 else value
        out[section] = conv
    common = _ns(out)
    common.fingerprint = fingerprint(raw)
    common.unchanged = common.fingerprint == COMMON_FINGERPRINT
    return common


# ---------------------------------------------------------------------------
# File del gruppo
# ---------------------------------------------------------------------------
def apply_override(raw: dict, assignment: str) -> None:
    """Applica una modifica del tipo 'sezione.chiave=valore' (opzione --set)."""
    if "=" not in assignment:
        raise InputError(f"--set {assignment}: usare la forma sezione.chiave=valore.")
    path, text = assignment.split("=", 1)
    parts = path.strip().split(".")
    if len(parts) != 2:
        raise InputError(f"--set {assignment}: indicare sezione e chiave, per esempio mobility.crr=0.6.")
    section, key = parts
    try:
        value = tomllib.loads(f"v = {text.strip()}")["v"]
    except tomllib.TOMLDecodeError:
        value = text.strip()          # stringa senza virgolette
    known = key in raw.get(section, {}) or key in SCHEMA.get(section, {}) or (
        section == "operations" and key == "sequence")
    if not known:
        raise InputError(f"--set {assignment}: la chiave '{key}' non esiste nella sezione [{section}].")
    raw.setdefault(section, {})[key] = value


def validate(raw: dict, file: str = "input") -> SimpleNamespace:
    """Valida il contenuto del file del gruppo e lo restituisce in SI."""
    arch = raw.get("architecture", {}).get("power")
    needed = set(SCHEMA) - OPTIONAL_SECTIONS
    if arch in ARCH_SECTIONS:
        needed |= set(ARCH_SECTIONS[arch])
    allowed = set(SCHEMA) | {"positions", "items"}
    unknown = set(raw) - allowed
    if unknown:
        raise InputError(f"{file}: sezione non riconosciuta {sorted(unknown)}.")
    missing = sorted(s for s in needed if s not in raw)
    if missing:
        raise InputError(f"{file}: mancano le sezioni {missing}.")

    out: dict = {}
    for section, specs in SCHEMA.items():
        if section not in raw:
            continue
        table = dict(raw[section])
        if section == "group":
            students = table.pop("students", None)
            if not isinstance(students, list) or not students:
                raise InputError(f"{_where(file, 'group', 'students')}: indicare almeno uno studente.")
            out_students = [_check_table(s, STUDENT_SPEC, f"{_where(file, 'group')}, studente {i + 1}")
                            for i, s in enumerate(students)]
        if section == "operations":
            sol_types = table.pop("sol_types", None)
            if not isinstance(sol_types, list) or not sol_types:
                raise InputError(f"{_where(file, 'operations')}: manca l'elenco [[operations.sol_types]].")
            out_sols = [_check_table(s, SOL_TYPE_SPEC, f"{_where(file, 'operations.sol_types')} n. {i + 1}")
                        for i, s in enumerate(sol_types)]
        out[section] = _check_table(table, specs, _where(file, section))
        if section == "group":
            out[section]["students"] = out_students
        if section == "operations":
            out[section]["sol_types"] = out_sols

    items = []
    if not isinstance(raw.get("items", []), list):
        raise InputError(f"{file}: le voci di massa vanno scritte come [[items]].")
    for i, item in enumerate(raw.get("items", [])):
        where = f"{file}, voce [[items]] n. {i + 1}"
        it = _check_table(item, ITEM_SPEC, where)
        if (it["mass"] is None) == (it["fraction"] is None):
            raise InputError(f"{where} ('{item.get('name', '?')}'): indicare mass_kg oppure fraction, non entrambi.")
        items.append(it)
    out["items"] = items

    positions = {}
    for key, value in raw.get("positions", {}).items():
        if key not in POSITION_KEYS:
            raise InputError(f"{_where(file, 'positions', key)}: voce sconosciuta. "
                             f"Voci ammesse: {', '.join(POSITION_KEYS)}.")
        positions[key] = _check_value(value, Spec("vec3"), _where(file, "positions", key))
    out["positions"] = positions

    ops = out["operations"]
    if ops["sequence"] is not None:
        names = [s["name"] for s in ops["sol_types"]]
        unknown_names = sorted(set(ops["sequence"]) - set(names))
        if unknown_names:
            raise InputError(f"{_where(file, 'operations', 'sequence')}: sol tipo sconosciuti {unknown_names}.")
        for s in ops["sol_types"]:
            n = ops["sequence"].count(s["name"])
            if n != s["count"]:
                raise InputError(f"{_where(file, 'operations', 'sequence')}: il sol tipo '{s['name']}' "
                                 f"compare {n} volte, ma count = {s['count']}.")

    bat = out["battery"]
    if len(bat["cycle_dod"]) != len(bat["cycle_count"]):
        raise InputError(f"{_where(file, 'battery')}: cycle_dod e cycle_count devono avere la stessa lunghezza.")
    return _ns(out)


def load_design(path, overrides: list[str] | None = None) -> tuple[SimpleNamespace, dict]:
    """Legge il file del gruppo, applica le eventuali modifiche --set e lo valida.

    Restituisce il progetto in SI e il contenuto grezzo del file (utile per i
    report e per gli studi di sensitività).
    """
    path = Path(path)
    raw = _parse_toml(path)
    raw = copy.deepcopy(raw)
    for assignment in overrides or []:
        apply_override(raw, assignment)
    return validate(raw, path.name), raw
