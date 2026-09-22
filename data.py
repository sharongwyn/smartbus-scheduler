import random
from dataclasses import dataclass
from typing import Optional, List

random.seed(42)

@dataclass
class Trip:
    trip_id: int
    route_id: int
    bus_id: Optional[int] = None
    driver_id: Optional[int] = None
    conductor_id: Optional[int] = None
    day_id: Optional[int] = None    # 0=Senin - 6=Minggu
    slot_id: Optional[int] = None   # 0=00:00, 1=06:00, 2=12:00, 3=18:00

# Schedule constants
N_DAYS          = 7
N_SLOTS         = 4
BUSES_PER_SLOT  = 2
TOTAL_TRIPS     = N_DAYS * N_SLOTS * BUSES_PER_SLOT   # = 56

# Route network 
ROUTES = [
    {"id": 0,  "origin": "Surabaya",   "dest": "Malang",      "dist": 90},
    {"id": 1,  "origin": "Malang",     "dest": "Surabaya",    "dist": 90},
    {"id": 2,  "origin": "Surabaya",   "dest": "Madiun",      "dist": 160},
    {"id": 3,  "origin": "Madiun",     "dest": "Surabaya",    "dist": 160},
    {"id": 4,  "origin": "Malang",     "dest": "Kediri",      "dist": 120},
    {"id": 5,  "origin": "Kediri",     "dest": "Malang",      "dist": 120},
    {"id": 6,  "origin": "Kediri",     "dest": "Blitar",      "dist": 50},
    {"id": 7,  "origin": "Blitar",     "dest": "Kediri",      "dist": 50},
    {"id": 8,  "origin": "Madiun",     "dest": "Solo",        "dist": 100},
    {"id": 9,  "origin": "Solo",       "dest": "Madiun",      "dist": 100},
    {"id": 10, "origin": "Solo",       "dest": "Yogyakarta",  "dist": 60},
    {"id": 11, "origin": "Yogyakarta", "dest": "Solo",        "dist": 60},
    {"id": 12, "origin": "Solo",       "dest": "Semarang",    "dist": 100},
    {"id": 13, "origin": "Semarang",   "dest": "Solo",        "dist": 100},
    {"id": 14, "origin": "Semarang",   "dest": "Yogyakarta",  "dist": 130},
    {"id": 15, "origin": "Yogyakarta", "dest": "Semarang",    "dist": 130},
    {"id": 16, "origin": "Yogyakarta", "dest": "Purwokerto",  "dist": 140},
    {"id": 17, "origin": "Purwokerto", "dest": "Yogyakarta",  "dist": 140},
    {"id": 18, "origin": "Purwokerto", "dest": "Tegal",       "dist": 120},
    {"id": 19, "origin": "Tegal",      "dest": "Purwokerto",  "dist": 120},
    {"id": 20, "origin": "Tegal",      "dest": "Cirebon",     "dist": 80},
    {"id": 21, "origin": "Cirebon",    "dest": "Tegal",       "dist": 80},
    {"id": 22, "origin": "Cirebon",    "dest": "Bandung",     "dist": 180},
    {"id": 23, "origin": "Bandung",    "dest": "Cirebon",     "dist": 180},
    {"id": 24, "origin": "Bandung",    "dest": "Jakarta",     "dist": 150},
    {"id": 25, "origin": "Jakarta",    "dest": "Bandung",     "dist": 150},
    {"id": 26, "origin": "Jakarta",    "dest": "Bekasi",      "dist": 30},
    {"id": 27, "origin": "Bekasi",     "dest": "Jakarta",     "dist": 30},
    {"id": 28, "origin": "Jakarta",    "dest": "Serang",      "dist": 80},
    {"id": 29, "origin": "Serang",     "dest": "Jakarta",     "dist": 80},
    {"id": 30, "origin": "Surabaya",   "dest": "Semarang",    "dist": 350},
    {"id": 31, "origin": "Semarang",   "dest": "Surabaya",    "dist": 350},
    {"id": 32, "origin": "Semarang",   "dest": "Cirebon",     "dist": 200},
    {"id": 33, "origin": "Cirebon",    "dest": "Semarang",    "dist": 200},
    {"id": 34, "origin": "Cirebon",    "dest": "Jakarta",     "dist": 220},
    {"id": 35, "origin": "Jakarta",    "dest": "Cirebon",     "dist": 220},
]

# Slot labels: index 0=00:00, 1=06:00, 2=12:00, 3=18:00
SLOT_LABELS = {0: "00:00", 1: "06:00", 2: "12:00", 3: "18:00"}
DAY_LABELS  = {0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis",
               4: "Jumat", 5: "Sabtu",  6: "Minggu"}
DAY_NAMES   = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
CITIES      = sorted(set(r["origin"] for r in ROUTES))

# ─── Default data generators ──────────────────────────────────────────────────

def _random_leave(n_days: int = 1) -> List[int]:
    if random.random() < 0.3:
        return []
    return random.sample(range(7), random.randint(1, n_days))

def _random_maintenance() -> List[int]:
    return [random.randint(0, 6)]

def _gen_buses(n: int = 12) -> List[dict]:
    bus_names = [
        "Rajawali 01","Rajawali 02","Rajawali 03",
        "Garuda 01","Garuda 02","Garuda 03",
        "Nusantara 01","Nusantara 02","Nusantara 03",
        "Merdeka 01","Merdeka 02","Merdeka 03",
    ]
    buses = []
    for i in range(n):
        city = random.choice(CITIES)
        buses.append({
            "id": i,
            "bus_id": f"BUS{i+1:03d}",
            "name": bus_names[i % len(bus_names)],
            "capacity": random.choice([32, 40, 44, 48]),
            "homebase": city,
            "current_position": city,
            "maintenance_days": _random_maintenance(),
        })
    return buses

def _gen_drivers(n: int = 15) -> List[dict]:
    first = ["Budi","Eko","Joko","Hasan","Rudi","Tono","Agus","Wahyu","Slamet","Doni",
             "Arif","Fajar","Rizky","Bayu","Hendra"]
    last  = ["Santoso","Wibowo","Susanto","Prasetyo","Kurniawan","Wijaya","Saputra",
             "Nugroho","Utomo","Firmansyah","Raharjo","Setiawan","Purnomo","Hidayat","Gunawan"]
    drivers = []
    for i in range(n):
        city = random.choice(CITIES)
        drivers.append({
            "id": i,
            "driver_id": f"DRV{i+1:03d}",
            "name": f"{first[i % len(first)]} {last[i % len(last)]}",
            "homebase": city,
            "current_position": city,
            "leave_days": _random_leave(1),
        })
    return drivers

def _gen_conductors(n: int = 15) -> List[dict]:
    first = ["Siti","Dewi","Ani","Rina","Yuli","Novi","Lina","Mega","Dian","Putri",
             "Wati","Nurul","Fitri","Ayu","Indah"]
    last  = ["Rahayu","Kusuma","Hartati","Lestari","Andriani","Permatasari","Handayani",
             "Sulistyowati","Wahyuningsih","Kristiani","Purwanti","Oktaviani","Astuti","Cahyani","Murni"]
    conductors = []
    for i in range(n):
        city = random.choice(CITIES)
        conductors.append({
            "id": i,
            "conductor_id": f"CON{i+1:03d}",
            "name": f"{first[i % len(first)]} {last[i % len(last)]}",
            "homebase": city,
            "current_position": city,
            "leave_days": _random_leave(1),
        })
    return conductors

DEFAULT_BUSES      = _gen_buses(12)
DEFAULT_DRIVERS    = _gen_drivers(15)
DEFAULT_CONDUCTORS = _gen_conductors(15)