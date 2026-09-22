import random
import math
import copy
import statistics
from typing import List, Dict, Tuple, Optional, Set
from data import ROUTES, Trip, SLOT_LABELS, DAY_LABELS

# penalty weights 
P_HARD_OVERLAP      = 100_000
P_HARD_MAINTENANCE  = 100_000
P_HARD_LEAVE        = 100_000
P_HARD_TELEPORT     = 100_000
P_TRIP_LIMIT        = 8_000
P_NO_RESOURCE       = 100_000
P_WORKLOAD_VAR      = 50.0
P_IDLE_KM           = 3.0

R_COVERAGE  = 12_000
R_EFF_BUS   = 300
R_EFF_DRV   = 200
R_EFF_CND   = 200
R_BALANCE   = 500
SLOT_HOURS  = {0: 6, 1: 12, 2: 18, 3: 0}

_N_ROUTES     = len(ROUTES)
_ROUTE_ORIGIN = [r["origin"] for r in ROUTES]
_ROUTE_DEST   = [r["dest"]   for r in ROUTES]
_ROUTE_DIST   = [r["dist"]   for r in ROUTES]

# Inter-city distance matrix
def _build_city_distance_matrix() -> Dict[Tuple[str, str], int]:
    dm: Dict[Tuple[str, str], int] = {}
    for r in ROUTES:
        key  = (r["origin"], r["dest"])
        dm[key]  = min(dm.get(key,  9999), r["dist"])
        key2 = (r["dest"], r["origin"])
        dm[key2] = min(dm.get(key2, 9999), r["dist"])

    cities = set()
    for r in ROUTES:
        cities.add(r["origin"])
        cities.add(r["dest"])
    for c in cities:
        dm[(c, c)] = 0

    city_list = list(cities)
    for k in city_list: # kota penghubung
        for i in city_list: # kota asal 
            for j in city_list: # kota tujuan
                d_ij = dm.get((i, j), 9999)
                d_ik = dm.get((i, k), 9999)
                d_kj = dm.get((k, j), 9999)
                if d_ik + d_kj < d_ij:
                    dm[(i, j)] = d_ik + d_kj
    return dm

CITY_DIST = _build_city_distance_matrix()

def _idle_dist(city_from: str, city_to: str, fallback: int = 100) -> int:
    if city_from == city_to:
        return 0
    return CITY_DIST.get((city_from, city_to), fallback)

# Stage schedule
_C_SCHEDULE = [
    # (progress/threshold, c1, c2, mutation/levy)
    (0.20, 2.5, 0.5, 0.30), #20% iterasi pertama
    (0.40, 2.2, 1.2, 0.20), #40%
    (0.60, 1.8, 1.8, 0.15), #60%
    (0.80, 1.2, 2.3, 0.08), #80%
    (1.01, 0.8, 2.8, 0.05), #100% adaptive
]

def _get_stage_params(progress: float) -> Tuple[float, float, float]:
    for thresh, c1, c2, levy in _C_SCHEDULE: # loop schedule
        if progress <= thresh:
            return c1, c2, levy
    return 0.8, 2.8, 0.05 # default 

_RESTART_STAGES = [0.10, 0.20, 0.35] # kl stagnan diinisialisasi ulang particlenya

# Lévy flight -> untuk step lebih besar (ningkatkan eksplorasi)
def _levy_step(beta: float = 1.5) -> float:
    num   = math.gamma(1 + beta) * math.sin(math.pi * beta / 2)
    den   = math.gamma((1 + beta) / 2) * beta * (2 ** ((beta - 1) / 2))
    sigma = (num / den) ** (1 / beta)
    u = random.gauss(0, sigma)
    v = abs(random.gauss(0, 1)) + 1e-9
    return u / (v ** (1 / beta))

# Workload statistics
def _workload_stats(trip_dict: Dict[int, int], total_resources: int) -> Dict:
    vals = list(trip_dict.values())
    vals += [0] * max(0, total_resources - len(vals))
    if not vals:
        return {"max": 0, "min": 0, "avg": 0.0, "std_dev": 0.0, "cv": 0.0, "variance": 0.0}
    mx  = max(vals)
    mn  = min(vals)
    avg = sum(vals) / len(vals)
    std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    cv  = (std / avg) if avg > 0 else 0.0
    var = std ** 2
    return {"max": mx, "min": mn, "avg": round(avg, 2),
            "std_dev": round(std, 3), "cv": round(cv, 3), "variance": round(var, 3)}

# Simulation core 
def _simulate_assignments(
    position: List[List[int]],
    route_chain: List[int],
    buses_pos: Dict[int, str],
    drivers_pos: Dict[int, str],
    conductors_pos: Dict[int, str],
    bus_meta: Dict[int, Dict],
    drv_meta: Dict[int, Dict],
    cnd_meta: Dict[int, Dict],
    total_buses: int,
    total_drivers: int,
    total_conductors: int,
) -> Tuple[float, Dict]:
    b_pos = buses_pos.copy()
    d_pos = drivers_pos.copy()
    c_pos = conductors_pos.copy()

    penalty = 0
    raw = {
        "teleport_bus": 0, "teleport_drv": 0, "teleport_cnd": 0,
        "maintenance": 0, "leave_drv": 0, "leave_cnd": 0,
        "overlap": 0, "trip_limit": 0, "no_resource": 0,
    }

    bookings: Set[Tuple] = set()
    trip_counts: Dict[Tuple, int] = {}
    total_dist      = 0
    total_idle_km   = 0
    trips_covered: Set[int] = set()

    bus_trips: Dict[int, int] = {}
    drv_trips: Dict[int, int] = {}
    cnd_trips: Dict[int, int] = {}

    # Cache penalty constants sebagai local var 
    _P_NO   = P_NO_RESOURCE
    _P_TEL  = P_HARD_TELEPORT
    _P_MAINT= P_HARD_MAINTENANCE
    _P_OVL  = P_HARD_OVERLAP
    _P_LIM  = P_TRIP_LIMIT
    _P_LV   = P_HARD_LEAVE

    for gene, route_id in zip(position, route_chain):
        bus_id, drv_id, cnd_id, day_id, slot_id = gene
        origin = _ROUTE_ORIGIN[route_id]
        dest   = _ROUTE_DEST[route_id]
        dist   = _ROUTE_DIST[route_id]
        total_dist += dist
        trips_covered.add(route_id)

        # Bus
        bm = bus_meta.get(bus_id)
        if bm is None:
            penalty += _P_NO; raw["no_resource"] += 1
        else:
            curr_pos = b_pos[bus_id]
            if curr_pos != origin:
                total_idle_km += CITY_DIST.get((curr_pos, origin), 100)
                penalty += _P_TEL; raw["teleport_bus"] += 1
            if day_id in bm.get("maintenance_days", ()):
                penalty += _P_MAINT; raw["maintenance"] += 1

            bk = (bus_id, 0, day_id, slot_id)
            if bk in bookings:
                penalty += _P_OVL; raw["overlap"] += 1
            else:
                bookings.add(bk)

            bday = (bus_id, 0, day_id)
            cnt = trip_counts.get(bday, 0) + 1
            trip_counts[bday] = cnt
            if cnt > 2:
                penalty += _P_LIM; raw["trip_limit"] += 1
            b_pos[bus_id] = dest
            bus_trips[bus_id] = bus_trips.get(bus_id, 0) + 1

        # Driver
        dm = drv_meta.get(drv_id)
        if dm is None:
            penalty += _P_NO; raw["no_resource"] += 1
        else:
            curr_pos = d_pos[drv_id]
            if curr_pos != origin:
                total_idle_km += CITY_DIST.get((curr_pos, origin), 100)
                penalty += _P_TEL; raw["teleport_drv"] += 1
            if day_id in dm.get("leave_days", ()):
                penalty += _P_LV; raw["leave_drv"] += 1

            dk = (drv_id, 1, day_id, slot_id) 
            if dk in bookings:
                penalty += _P_OVL; raw["overlap"] += 1
            else:
                bookings.add(dk)

            dday = (drv_id, 1, day_id)
            cnt = trip_counts.get(dday, 0) + 1
            trip_counts[dday] = cnt
            if cnt > 2:
                penalty += _P_LIM; raw["trip_limit"] += 1
            d_pos[drv_id] = dest
            drv_trips[drv_id] = drv_trips.get(drv_id, 0) + 1

        # Conductor
        cm = cnd_meta.get(cnd_id)
        if cm is None:
            penalty += _P_NO; raw["no_resource"] += 1
        else:
            curr_pos = c_pos[cnd_id]
            if curr_pos != origin:
                total_idle_km += CITY_DIST.get((curr_pos, origin), 100)
                penalty += _P_TEL; raw["teleport_cnd"] += 1
            if day_id in cm.get("leave_days", ()):
                penalty += _P_LV; raw["leave_cnd"] += 1

            ck = (cnd_id, 2, day_id, slot_id)   # 2 = "cnd"
            if ck in bookings:
                penalty += _P_OVL; raw["overlap"] += 1
            else:
                bookings.add(ck)

            cday = (cnd_id, 2, day_id)
            cnt = trip_counts.get(cday, 0) + 1
            trip_counts[cday] = cnt
            if cnt > 2:
                penalty += _P_LIM; raw["trip_limit"] += 1
            c_pos[cnd_id] = dest
            cnd_trips[cnd_id] = cnd_trips.get(cnd_id, 0) + 1

    # Fitness
    coverage      = len(trips_covered) / _N_ROUTES
    unique_buses  = len(set(p[0] for p in position))
    unique_drvs   = len(set(p[1] for p in position))
    unique_cnds   = len(set(p[2] for p in position))

    eff_bonus = (
        (total_buses      - unique_buses) * R_EFF_BUS +
        (total_drivers    - unique_drvs)  * R_EFF_DRV +
        (total_conductors - unique_cnds)  * R_EFF_CND
    )
    idle_penalty = total_idle_km * P_IDLE_KM

    ws_bus = _workload_stats(bus_trips, total_buses)
    ws_drv = _workload_stats(drv_trips, total_drivers)
    ws_cnd = _workload_stats(cnd_trips, total_conductors)

    total_var   = ws_bus["variance"] + ws_drv["variance"] + ws_cnd["variance"]
    balance_pen = total_var * P_WORKLOAD_VAR
    balance_bonus = R_BALANCE if total_var < 1.0 else 0.0

    util_bus = round(unique_buses / max(1, total_buses) * 100, 1)
    util_drv = round(unique_drvs  / max(1, total_drivers) * 100, 1)
    util_cnd = round(unique_cnds  / max(1, total_conductors) * 100, 1)
    load_balance_score = round(max(0.0, 1.0 - (total_var / max(1.0, total_var + 1))), 3)

    fitness = (
        coverage * R_COVERAGE
        - total_dist * 0.05
        - penalty
        + eff_bonus
        - idle_penalty
        - balance_pen
        + balance_bonus
    )

    stats = {
        **raw,
        "coverage_pct":   round(coverage * 100, 1),
        "unique_buses":   unique_buses, "unique_drivers": unique_drvs, "unique_conductors": unique_cnds,
        "penalty":        penalty, "total_distance": total_dist, "fitness": fitness,
        "hard_overlap":   raw["overlap"],
        "leave_violations": raw["leave_drv"] + raw["leave_cnd"],
        "bus_teleports":  raw["teleport_bus"],
        "crew_teleports": raw["teleport_drv"] + raw["teleport_cnd"],
        "trip_limit_violations": raw["trip_limit"],
        "idle_distance":  round(total_idle_km, 1),
        "deadhead_distance": round(total_idle_km, 1),
        "avg_idle_distance": round(total_idle_km / max(1, len(position)), 2),
        "trips_per_bus":   bus_trips, "trips_per_driver": drv_trips, "trips_per_conductor": cnd_trips,
        "workload_bus": ws_bus, "workload_drv": ws_drv, "workload_cnd": ws_cnd,
        "max_trips_bus": ws_bus["max"], "min_trips_bus": ws_bus["min"], "avg_trips_bus": ws_bus["avg"], "stddev_trips_bus": ws_bus["std_dev"], "cv_trips_bus": ws_bus["cv"],
        "max_trips_drv": ws_drv["max"], "min_trips_drv": ws_drv["min"], "avg_trips_drv": ws_drv["avg"], "stddev_trips_drv": ws_drv["std_dev"], "cv_trips_drv": ws_drv["cv"],
        "max_trips_cnd": ws_cnd["max"], "min_trips_cnd": ws_cnd["min"], "avg_trips_cnd": ws_cnd["avg"], "stddev_trips_cnd": ws_cnd["std_dev"], "cv_trips_cnd": ws_cnd["cv"],
        "load_var_bus": ws_bus["variance"], "load_var_drv": ws_drv["variance"], "load_var_cnd": ws_cnd["variance"],
        "balance_penalty": round(balance_pen, 1), "balance_bonus": balance_bonus, "load_balance_score": load_balance_score,
        "util_bus_pct": util_bus, "util_drv_pct": util_drv, "util_cnd_pct": util_cnd,
        "repair_swap_success": 0, "repair_replacement_success": 0, "repair_overlap": 0,
        "repair_teleport": 0, "repair_leave": 0, "repair_maintenance": 0, "repair_fail": 0,
        "teleport_before_repair": 0,
        "teleport_after_repair": raw["teleport_bus"] + raw["teleport_drv"] + raw["teleport_cnd"],
        "restart_stage": 0, "adaptive_stage": 0,
    }
    return fitness, stats

# Repair 
def _is_resource_feasible_fast(
    res_pos: str, res_constraint: set,
    origin: str, day_id: int, slot_id: int,
    res_id: int, rtype_int: int,
    bookings: Set, trip_counts: Dict,
) -> bool:
    if res_pos != origin:
        return False
    if day_id in res_constraint:
        return False
    if (res_id, rtype_int, day_id, slot_id) in bookings:
        return False
    if trip_counts.get((res_id, rtype_int, day_id), 0) >= 2:
        return False
    return True

def _find_replacement_fast(
    res_ids: List[int], res_positions: Dict[int, str], res_constraints: Dict[int, set],
    origin: str, day_id: int, slot_id: int, rtype_int: int,
    bookings: Set, trip_counts: Dict,
) -> Optional[int]:
    candidates = [
        rid for rid in res_ids
        if (res_positions.get(rid) == origin
            and day_id not in res_constraints.get(rid, set())
            and (rid, rtype_int, day_id, slot_id) not in bookings
            and trip_counts.get((rid, rtype_int, day_id), 0) < 2)
    ]
    return random.choice(candidates) if candidates else None

def _try_swap_repair_fast(
    pos: List[List[int]], trip_i: int, dim: int, rtype_int: int,
    route_chain: List[int],
    res_positions: Dict[int, str], res_constraints: Dict[int, set],
    bookings: Set, trip_counts: Dict,
) -> bool:
    origin_i = _ROUTE_ORIGIN[route_chain[trip_i]]
    res_id_i = pos[trip_i][dim]

    day_i  = pos[trip_i][3]
    slot_i = pos[trip_i][4]

    for j, gene_j in enumerate(pos):
        if j == trip_i:
            continue
        res_id_j = gene_j[dim]
        if res_id_j == res_id_i:
            continue

        if res_positions.get(res_id_j) != origin_i:
            continue

        origin_j = _ROUTE_ORIGIN[route_chain[j]]
        if res_positions.get(res_id_i) != origin_j:
            continue

        day_j  = gene_j[3]
        slot_j = gene_j[4]

        if (res_id_j, rtype_int, day_i, slot_i) in bookings:
            continue
        if (res_id_i, rtype_int, day_j, slot_j) in bookings:
            continue
        if day_i in res_constraints.get(res_id_j, set()):
            continue
        if day_j in res_constraints.get(res_id_i, set()):
            continue

        pos[trip_i][dim] = res_id_j
        pos[j][dim]      = res_id_i
        return True
    return False

# Main repair operator
def _repair_position(
    position: List[List[int]],
    route_chain: List[int],
    buses: List[Dict],
    drivers: List[Dict],
    conductors: List[Dict],
) -> Tuple[List[List[int]], Dict]:
    pos = [gene.copy() for gene in position]

    # Bangun struktur ringan: hanya posisi & constraint (bukan deepcopy full dict)
    bus_pos:  Dict[int, str]  = {b["id"]: b["current_position"] for b in buses}
    drv_pos:  Dict[int, str]  = {d["id"]: d["current_position"] for d in drivers}
    cnd_pos:  Dict[int, str]  = {c["id"]: c["current_position"] for c in conductors}

    bus_con:  Dict[int, set]  = {b["id"]: set(b.get("maintenance_days", [])) for b in buses}
    drv_con:  Dict[int, set]  = {d["id"]: set(d.get("leave_days", []))       for d in drivers}
    cnd_con:  Dict[int, set]  = {c["id"]: set(c.get("leave_days", []))       for c in conductors}

    bus_ids = [b["id"] for b in buses]
    drv_ids = [d["id"] for d in drivers]
    cnd_ids = [c["id"] for c in conductors]

    bookings:    Set[Tuple]      = set()
    trip_counts: Dict[Tuple, int] = {}
    rs = {"swap_success": 0, "replacement_success": 0, "overlap": 0,
          "teleport": 0, "leave": 0, "maintenance": 0, "fail": 0}

    for i, (gene, route_id) in enumerate(zip(pos, route_chain)):
        bus_id, drv_id, cnd_id, day_id, slot_id = gene
        origin = _ROUTE_ORIGIN[route_id]
        dest   = _ROUTE_DEST[route_id]

        # Bus Teleport
        if bus_id in bus_pos and bus_pos[bus_id] != origin:
            rs["teleport"] += 1
            if _try_swap_repair_fast(pos, i, 0, 0, route_chain, bus_pos, bus_con, bookings, trip_counts):
                rs["swap_success"] += 1
                bus_id = pos[i][0]
            else:
                repl = _find_replacement_fast(bus_ids, bus_pos, bus_con, origin, day_id, slot_id, 0, bookings, trip_counts)
                if repl is not None:
                    pos[i][0] = bus_id = repl; rs["replacement_success"] += 1
                else:
                    rs["fail"] += 1

        # Bus Maintenance
        if day_id in bus_con.get(pos[i][0], set()):
            rs["maintenance"] += 1
            repl = _find_replacement_fast(bus_ids, bus_pos, bus_con, origin, day_id, slot_id, 0, bookings, trip_counts)
            if repl is not None:
                pos[i][0] = repl; rs["replacement_success"] += 1
            else:
                rs["fail"] += 1

        # Driver Teleport
        if drv_id in drv_pos and drv_pos[drv_id] != origin:
            rs["teleport"] += 1
            if _try_swap_repair_fast(pos, i, 1, 1, route_chain, drv_pos, drv_con, bookings, trip_counts):
                rs["swap_success"] += 1
                drv_id = pos[i][1]
            else:
                repl = _find_replacement_fast(drv_ids, drv_pos, drv_con, origin, day_id, slot_id, 1, bookings, trip_counts)
                if repl is not None:
                    pos[i][1] = drv_id = repl; rs["replacement_success"] += 1
                else:
                    rs["fail"] += 1

        # Driver Leave
        if day_id in drv_con.get(pos[i][1], set()):
            rs["leave"] += 1
            repl = _find_replacement_fast(drv_ids, drv_pos, drv_con, origin, day_id, slot_id, 1, bookings, trip_counts)
            if repl is not None:
                pos[i][1] = repl; rs["replacement_success"] += 1
            else:
                rs["fail"] += 1

        # Conductor Teleport
        if cnd_id in cnd_pos and cnd_pos[cnd_id] != origin:
            rs["teleport"] += 1
            if _try_swap_repair_fast(pos, i, 2, 2, route_chain, cnd_pos, cnd_con, bookings, trip_counts):
                rs["swap_success"] += 1
                cnd_id = pos[i][2]
            else:
                repl = _find_replacement_fast(cnd_ids, cnd_pos, cnd_con, origin, day_id, slot_id, 2, bookings, trip_counts)
                if repl is not None:
                    pos[i][2] = cnd_id = repl; rs["replacement_success"] += 1
                else:
                    rs["fail"] += 1

        # Conductor Leave
        if day_id in cnd_con.get(pos[i][2], set()):
            rs["leave"] += 1
            repl = _find_replacement_fast(cnd_ids, cnd_pos, cnd_con, origin, day_id, slot_id, 2, bookings, trip_counts)
            if repl is not None:
                pos[i][2] = repl; rs["replacement_success"] += 1
            else:
                rs["fail"] += 1

        # Fix slot overlaps
        for dim_idx, rtype_int in ((0, 0), (1, 1), (2, 2)):
            rid = pos[i][dim_idx]
            bk  = (rid, rtype_int, day_id, slot_id)
            if bk in bookings:
                rs["overlap"] += 1
                for s in range(4):
                    nk = (rid, rtype_int, day_id, s)
                    if nk not in bookings:
                        pos[i][4] = s
                        slot_id   = s
                        bookings.add(nk)
                        rs["replacement_success"] += 1
                        break
                else:
                    rs["fail"] += 1
            else:
                bookings.add(bk)

        # Update trip_counts & posisi 
        for dim_idx, rtype_int in ((0, 0), (1, 1), (2, 2)):
            key = (pos[i][dim_idx], rtype_int, day_id)
            trip_counts[key] = trip_counts.get(key, 0) + 1

        bus_pos[pos[i][0]] = dest
        drv_pos[pos[i][1]] = dest
        cnd_pos[pos[i][2]] = dest

    return pos, rs

def _smart_init_position(
    route_chain: List[int],
    buses: List[Dict], drivers: List[Dict], conductors: List[Dict],
    n_buses: int, n_drivers: int, n_conductors: int,
) -> List[List[int]]:
    # Posisi mutable 
    bus_pos = {b["id"]: b["current_position"] for b in buses}
    drv_pos = {d["id"]: d["current_position"] for d in drivers}
    cnd_pos = {c["id"]: c["current_position"] for c in conductors}

    bus_con = {b["id"]: set(b.get("maintenance_days", [])) for b in buses}
    drv_con = {d["id"]: set(d.get("leave_days", []))       for d in drivers}
    cnd_con = {c["id"]: set(c.get("leave_days", []))       for c in conductors}

    bus_ids = [b["id"] for b in buses]
    drv_ids = [d["id"] for d in drivers]
    cnd_ids = [c["id"] for c in conductors]

    position: List[List[int]] = []
    bookings:    Set[Tuple]      = set()
    trip_counts: Dict[Tuple, int] = {}
    workload:    Dict[str, int]   = {}

    def _pick(res_ids, rtype_int, pos_dict, con_dict, origin,
              day_id, slot_id, fallback_n, dest=None) -> int:
        valid = []
        for rid in res_ids:
            if pos_dict.get(rid) != origin:
                continue
            if day_id in con_dict.get(rid, set()):
                continue
            if (rid, rtype_int, day_id, slot_id) in bookings:
                continue
            if trip_counts.get((rid, rtype_int, day_id), 0) >= 2:
                continue
            load = workload.get((rtype_int, rid), 0)
            # look-ahead
            la_bonus = -10 if dest and pos_dict.get(rid) == dest else 0
            valid.append((rid, load + la_bonus))

        if valid:
            valid.sort(key=lambda x: (x[1], random.random()))
            return valid[0][0]
        return random.randint(0, max(0, fallback_n - 1))

    n = len(route_chain)
    for i, route_id in enumerate(route_chain):
        origin  = _ROUTE_ORIGIN[route_id]
        dest    = _ROUTE_DEST[route_id]
        day_id  = (i // 4) % 7
        slot_id = i % 4
        next_origin = _ROUTE_ORIGIN[route_chain[i + 1]] if i + 1 < n else None

        bus_id = _pick(bus_ids, 0, bus_pos, bus_con, origin, day_id, slot_id, n_buses, next_origin)
        drv_id = _pick(drv_ids, 1, drv_pos, drv_con, origin, day_id, slot_id, n_drivers, next_origin)
        cnd_id = _pick(cnd_ids, 2, cnd_pos, cnd_con, origin, day_id, slot_id, n_conductors, next_origin)

        bookings.add((bus_id, 0, day_id, slot_id))
        bookings.add((drv_id, 1, day_id, slot_id))
        bookings.add((cnd_id, 2, day_id, slot_id))

        for rid, rt in ((bus_id, 0), (drv_id, 1), (cnd_id, 2)):
            k = (rid, rt, day_id)
            trip_counts[k] = trip_counts.get(k, 0) + 1

        workload[(0, bus_id)] = workload.get((0, bus_id), 0) + 1
        workload[(1, drv_id)] = workload.get((1, drv_id), 0) + 1
        workload[(2, cnd_id)] = workload.get((2, cnd_id), 0) + 1

        bus_pos[bus_id] = dest
        drv_pos[drv_id] = dest
        cnd_pos[cnd_id] = dest

        position.append([bus_id, drv_id, cnd_id, day_id, slot_id])
    return position

# Particle
class Particle:
    __slots__ = ("n_trips","n_buses","n_drivers","n_conductors",
                 "position","velocity","fitness","pbest_position","pbest_fitness")

    def __init__(self, n_trips: int, n_buses: int, n_drivers: int, n_conductors: int):
        self.n_trips      = n_trips
        self.n_buses      = n_buses
        self.n_drivers    = n_drivers
        self.n_conductors = n_conductors
        self.position:        List[List[int]]   = []
        self.velocity:        List[List[float]] = []
        self.fitness:         float             = float("-inf")
        self.pbest_position:  List[List[int]]   = []
        self.pbest_fitness:   float             = float("-inf")

    def init_smart(self, route_chain, buses, drivers, conductors):
        self.position = _smart_init_position(
            route_chain, buses, drivers, conductors,
            self.n_buses, self.n_drivers, self.n_conductors,
        )
        self.velocity        = [[random.uniform(-0.5, 0.5) for _ in range(5)]
                                 for _ in range(self.n_trips)]
        self.pbest_position  = [gene.copy() for gene in self.position]

    def init_random(self):
        nb, nd, nc = self.n_buses - 1, self.n_drivers - 1, self.n_conductors - 1
        self.position = [
            [random.randint(0, max(0, nb)),
             random.randint(0, max(0, nd)),
             random.randint(0, max(0, nc)),
             random.randint(0, 6),
             random.randint(0, 3)]
            for _ in range(self.n_trips)
        ]
        self.velocity       = [[random.uniform(-1, 1) for _ in range(5)]
                                for _ in range(self.n_trips)]
        self.pbest_position = [gene.copy() for gene in self.position]

class DPSO:
    def __init__(
        self,
        n_particles:        int   = 50,
        n_iterations:       int   = 200,
        w_start:            float = 0.9,
        w_end:              float = 0.3,
        c1:                 float = 2.0,
        c2:                 float = 2.0,
        n_trips:            int   = 40,
        buses:              Optional[List[Dict]] = None,
        drivers:            Optional[List[Dict]] = None,
        conductors:         Optional[List[Dict]] = None,
        stagnation_limit:   int   = 25,
        restart_fraction:   float = 0.15,
        levy_prob:          float = 0.15,
        local_search_trips: int   = 5,
        callback=None,
    ):
        self.n_particles        = n_particles
        self.n_iterations       = n_iterations
        self.w_start            = w_start
        self.w_end              = w_end
        self.c1                 = c1
        self.c2                 = c2
        self.n_trips            = n_trips
        self.buses              = buses or []
        self.drivers            = drivers or []
        self.conductors         = conductors or []
        self.n_buses            = len(self.buses)
        self.n_drivers          = len(self.drivers)
        self.n_conductors       = len(self.conductors)
        self.stagnation_limit   = stagnation_limit
        self.restart_fraction   = restart_fraction
        self.levy_prob          = levy_prob
        self.local_search_trips = local_search_trips
        self.callback           = callback

        self.v_max = [
            max(1.0, self.n_buses      * 0.35),
            max(1.0, self.n_drivers    * 0.35),
            max(1.0, self.n_conductors * 0.35),
            2.5, 1.5,
        ]
        self.dim_bounds = [
            (0, max(0, self.n_buses      - 1)),
            (0, max(0, self.n_drivers    - 1)),
            (0, max(0, self.n_conductors - 1)),
            (0, 6), (0, 3),
        ]
        self.ring_size = max(2, n_particles // 8)

        self._rs_total = {"swap_success": 0, "replacement_success": 0, "overlap": 0,
                          "teleport": 0, "leave": 0, "maintenance": 0, "fail": 0}
        self._teleport_before  = 0
        self._restart_stage    = 0
        self._adaptive_stage   = 0

        # Pre-cache data statis resource 
        self.buses_pos_init     = {b["id"]: b.get("current_position", "Surabaya") for b in self.buses}
        self.drivers_pos_init   = {d["id"]: d.get("current_position", "Surabaya") for d in self.drivers}
        self.conductors_pos_init= {c["id"]: c.get("current_position", "Surabaya") for c in self.conductors}
        self.bus_meta           = {b["id"]: b for b in self.buses}
        self.drv_meta           = {d["id"]: d for d in self.drivers}
        self.cnd_meta           = {c["id"]: c for c in self.conductors}

        # Pre-cache dim bounds sebagai tuple untuk _clamp tight loop
        self._lo = [lo for lo, _ in self.dim_bounds]
        self._hi = [hi for _, hi in self.dim_bounds]
        self._vmax = self.v_max  # alias

    def _evaluate(self, position, route_chain):
        return _simulate_assignments(
            position, route_chain,
            self.buses_pos_init, self.drivers_pos_init, self.conductors_pos_init,
            self.bus_meta, self.drv_meta, self.cnd_meta,
            self.n_buses, self.n_drivers, self.n_conductors,
        )

    # Inline clamp untuk tight loop 
    @staticmethod
    def _clamp(val: float, lo: int, hi: int) -> int:
        v = round(val)
        if v < lo: return lo
        if v > hi: return hi
        return v

    def _repair(self, position, route_chain):
        repaired, rs = _repair_position(position, route_chain, self.buses, self.drivers, self.conductors)
        for k in self._rs_total:
            self._rs_total[k] += rs.get(k, 0)
        return repaired

    def _update_particle(self, p: Particle, gbest, lbest, w: float, progress: float):
        c1, c2, levy_prob = _get_stage_params(progress)
        lo = self._lo
        hi = self._hi
        vmax = self._vmax
        pos  = p.position
        vel  = p.velocity
        pb   = p.pbest_position

        c2_half = c2 * 0.5

        for t in range(self.n_trips):
            pt = pos[t]; vt = vel[t]; pbt = pb[t]; gt = gbest[t]; lt = lbest[t]
            r1, r2, r3 = random.random(), random.random(), random.random()
            for d in range(5):
                cog = c1 * r1 * (pbt[d] - pt[d])
                sg  = c2_half * r2 * (gt[d] - pt[d])
                sl  = c2_half * r3 * (lt[d] - pt[d])
                nv  = w * vt[d] + cog + sg + sl
                vm  = vmax[d]
                if nv > vm:  nv = vm
                elif nv < -vm: nv = -vm
                vt[d] = nv
                npos = pt[d] + nv
                if random.random() < levy_prob:
                    npos += _levy_step() * 0.4
                lo_d = lo[d]; hi_d = hi[d]
                v = round(npos)
                if v < lo_d: v = lo_d
                elif v > hi_d: v = hi_d
                pt[d] = v

    def _local_search(self, p: Particle, route_chain: List[int], cur_fit: float) -> float:
        n_probe = min(self.local_search_trips, self.n_trips)
        indices = random.sample(range(self.n_trips), n_probe)
        best_fit = cur_fit
        pos = p.position

        for t in indices:
            # Resource dims
            for dim, n_res in ((0, self.n_buses), (1, self.n_drivers), (2, self.n_conductors)):
                if n_res < 2:
                    continue
                orig_val      = pos[t][dim]
                local_best_val= orig_val
                for candidate in range(n_res):
                    if candidate == orig_val:
                        continue
                    pos[t][dim] = candidate
                    f, _ = self._evaluate(pos, route_chain)
                    if f > best_fit:
                        best_fit       = f
                        local_best_val = candidate
                pos[t][dim] = local_best_val

            # Day
            orig_day      = pos[t][3]
            local_best_day= orig_day
            for d in range(7):
                if d == orig_day:
                    continue
                pos[t][3] = d
                f, _ = self._evaluate(pos, route_chain)
                if f > best_fit:
                    best_fit       = f
                    local_best_day = d
            pos[t][3] = local_best_day

            # Slot
            orig_slot      = pos[t][4]
            local_best_slot= orig_slot
            for s in range(4):
                if s == orig_slot:
                    continue
                pos[t][4] = s
                f, _ = self._evaluate(pos, route_chain)
                if f > best_fit:
                    best_fit        = f
                    local_best_slot = s
            pos[t][4] = local_best_slot

        return best_fit

    def _ring_best(self, idx: int, particles: List[Particle]):
        n    = len(particles)
        half = self.ring_size // 2
        neighs = [(idx + k - half) % n for k in range(self.ring_size)]
        best   = max(neighs, key=lambda j: particles[j].pbest_fitness)
        return particles[best].pbest_position

    def _partial_restart(self, particles: List[Particle], route_chain: List[int], stagnation_count: int):
        n_stag_stages = min(2, stagnation_count - 1)
        frac          = _RESTART_STAGES[n_stag_stages]
        self._restart_stage = n_stag_stages + 1

        sorted_idx = sorted(range(len(particles)), key=lambda j: particles[j].pbest_fitness)
        n_restart  = max(1, int(len(particles) * frac))
        worst_idx  = sorted_idx[:n_restart]

        for idx in worst_idx:
            p = particles[idx]
            if random.random() < 0.65:
                p.init_smart(route_chain, self.buses, self.drivers, self.conductors)
            else:
                p.init_random()
            p.position       = self._repair(p.position, route_chain)
            fit, _           = self._evaluate(p.position, route_chain)
            p.fitness        = p.pbest_fitness = fit
            p.pbest_position = [gene.copy() for gene in p.position]

    # Run
    def run(self, route_chain: List[int]) -> Tuple[List[Trip], float, List[float], Dict]:
        for k in self._rs_total:
            self._rs_total[k] = 0
        self._teleport_before = 0
        self._restart_stage   = 0
        self._adaptive_stage  = 0

        particles: List[Particle] = []
        smart_cutoff = int(self.n_particles * 0.7)
        for i in range(self.n_particles):
            p = Particle(self.n_trips, self.n_buses, self.n_drivers, self.n_conductors)
            if i < smart_cutoff:
                p.init_smart(route_chain, self.buses, self.drivers, self.conductors)
            else:
                p.init_random()
            p.position       = self._repair(p.position, route_chain)
            fit, _           = self._evaluate(p.position, route_chain)
            p.fitness        = p.pbest_fitness = fit
            p.pbest_position = [gene.copy() for gene in p.position]
            particles.append(p)

        gbest_p   = max(particles, key=lambda p: p.pbest_fitness)
        gbest_pos = [gene.copy() for gene in gbest_p.pbest_position]
        gbest_fit = gbest_p.pbest_fitness

        history     = []
        stagnation  = 0
        stagnation_cnt = 0

        for it in range(self.n_iterations):
            progress = it / max(1, self.n_iterations - 1)
            w = self.w_start - (self.w_start - self.w_end) * (progress ** 0.8)

            for stage_idx, (thresh, *_) in enumerate(_C_SCHEDULE):
                if progress <= thresh:
                    self._adaptive_stage = stage_idx + 1
                    break

            improved = False
            for idx, p in enumerate(particles):
                lbest = self._ring_best(idx, particles)
                self._update_particle(p, gbest_pos, lbest, w, progress)
                p.position = self._repair(p.position, route_chain)

                fit, _ = self._evaluate(p.position, route_chain)
                fit    = self._local_search(p, route_chain, fit)
                p.fitness = fit

                if fit > p.pbest_fitness:
                    p.pbest_fitness  = fit
                    p.pbest_position = [gene.copy() for gene in p.position]

                    if fit > gbest_fit:
                        gbest_fit = fit
                        gbest_pos = [gene.copy() for gene in p.position]
                        improved  = True

            if improved:
                stagnation = 0
            else:
                stagnation += 1

            if stagnation >= self.stagnation_limit:
                stagnation_cnt += 1
                self._partial_restart(particles, route_chain, stagnation_cnt)
                stagnation = 0

            for p in particles:
                if p.pbest_fitness > gbest_fit:
                    gbest_fit = p.pbest_fitness
                    gbest_pos = [gene.copy() for gene in p.pbest_position]

            history.append(gbest_fit)
            if self.callback:
                self.callback(it + 1, self.n_iterations, gbest_fit)

        _, final_stats = self._evaluate(gbest_pos, route_chain)
        final_stats["repair_swap_success"]        = self._rs_total["swap_success"]
        final_stats["repair_replacement_success"] = self._rs_total["replacement_success"]
        final_stats["repair_overlap"]             = self._rs_total["overlap"]
        final_stats["repair_teleport"]            = self._rs_total["teleport"]
        final_stats["repair_leave"]               = self._rs_total["leave"]
        final_stats["repair_maintenance"]         = self._rs_total["maintenance"]
        final_stats["repair_fail"]                = self._rs_total["fail"]
        final_stats["repair_success"]             = (self._rs_total["swap_success"] + self._rs_total["replacement_success"])
        final_stats["teleport_before_repair"]     = self._rs_total["teleport"]
        final_stats["teleport_after_repair"]      = (final_stats.get("bus_teleports", 0) + final_stats.get("crew_teleports", 0))
        final_stats["restart_stage"]              = self._restart_stage
        final_stats["adaptive_stage"]             = self._adaptive_stage

        trips = [
            Trip(
                trip_id      = i,
                route_id     = route_id,
                bus_id       = gene[0],
                driver_id    = gene[1],
                conductor_id = gene[2],
                day_id       = gene[3],
                slot_id      = gene[4],
            )
            for i, (gene, route_id) in enumerate(zip(gbest_pos, route_chain))
        ]
        return trips, gbest_fit, history, final_stats

    # Tampilkan jadwal
    def format_assignments(
        self,
        trips: List[Trip],
        buses: List[Dict],
        drivers: List[Dict],
        conductors: List[Dict],
    ) -> str:
        # Posisi simulasi 
        b_pos = {b["id"]: b["current_position"] for b in buses}
        d_pos = {d["id"]: d["current_position"] for d in drivers}
        c_pos = {c["id"]: c["current_position"] for c in conductors}

        bus_map = {b["id"]: b for b in buses}
        drv_map = {d["id"]: d for d in drivers}
        cnd_map = {c["id"]: c for c in conductors}

        lines = []
        for t in trips:
            r   = ROUTES[t.route_id]
            bus = bus_map.get(t.bus_id, {})
            drv = drv_map.get(t.driver_id, {})
            cnd = cnd_map.get(t.conductor_id, {})

            b_before = b_pos.get(t.bus_id, "?")
            d_before = d_pos.get(t.driver_id, "?")
            c_before = c_pos.get(t.conductor_id, "?")

            b_id = bus.get("bus_id",       f"BUS{t.bus_id}")
            d_id = drv.get("driver_id",    f"DRV{t.driver_id}")
            c_id = cnd.get("conductor_id", f"CON{t.conductor_id}")

            idle_b = _idle_dist(b_before, r["origin"], r["dist"]) if b_before != r["origin"] else 0
            idle_d = _idle_dist(d_before, r["origin"], r["dist"]) if d_before != r["origin"] else 0
            idle_c = _idle_dist(c_before, r["origin"], r["dist"]) if c_before != r["origin"] else 0

            lines += [
                "", f"┌─ Trip {t.trip_id + 1:>3} [{DAY_LABELS.get(t.day_id,'?')} {SLOT_LABELS.get(t.slot_id,'?')}] ──────────────────────",
                f"│ Rute : {r['origin']} → {r['dest']} ({r['dist']} km)", "│",
                f"│ Bus : {b_id:<10} Driver : {d_id:<10} Kondektur : {c_id}", "│",
                "│ Posisi Sebelum:",
                f"│ Bus = {b_before}" + (f" (idle {idle_b} km)" if idle_b else ""),
                f"│ Driver = {d_before}" + (f" (idle {idle_d} km)" if idle_d else ""),
                f"│ Kondektur = {c_before}" + (f" (idle {idle_c} km)" if idle_c else ""),
            ]

            flags = []
            if b_before != r["origin"]:                          flags.append("⚠ BUS TELEPORT")
            if d_before != r["origin"]:                          flags.append("⚠ DRIVER TELEPORT")
            if c_before != r["origin"]:                          flags.append("⚠ KONDUKTOR TELEPORT")
            if t.day_id in bus.get("maintenance_days", []):      flags.append("⚠ BUS MAINTENANCE")
            if t.day_id in drv.get("leave_days", []):            flags.append("⚠ DRIVER CUTI")
            if t.day_id in cnd.get("leave_days", []):            flags.append("⚠ KONDUKTOR CUTI")

            # Update posisi simulasi
            b_pos[t.bus_id]       = r["dest"]
            d_pos[t.driver_id]    = r["dest"]
            c_pos[t.conductor_id] = r["dest"]

            lines += [
                "│", "│ Posisi Sesudah:",
                f"│ Bus = {r['dest']}", f"│ Driver = {r['dest']}", f"│ Kondektur = {r['dest']}",
                f"│ Status : {'⚠ ' + ' | '.join(flags) if flags else '✓ Valid'}",
                f"└{'─' * 60}",
            ]
        return "\n".join(lines)