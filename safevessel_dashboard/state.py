"""
Etat partage du vaisseau : incident actuellement traite + file d'attente.
Thread-safe : lu par les routes Flask, ecrit par le lecteur serie (ou le simulateur).
"""
import threading
import time

# Correspondance nom d'incident -> niveau de criticite (doit rester coherent
# avec les noms utilises dans le code Arduino SafeVessel.ino)
INCIDENT_LEVELS = {
    "Fuite d'air (O2)": "critique",
    "Incendie": "haute",
    "Panne electrique": "haute",
    "Intrusion": "moyenne",
}

# Ordre de priorite : plus petit = traite en premier
LEVEL_ORDER = {"critique": 0, "haute": 1, "moyenne": 2, "inconnue": 9}


class VesselState:
    def __init__(self):
        self._lock = threading.Lock()
        self.connected = False
        self.active = {}  # nom -> {"level": str, "since": epoch, "escalated": bool}

    def set_connected(self, value: bool):
        with self._lock:
            self.connected = value

    def detected(self, name: str, level: str):
        with self._lock:
            if name not in self.active:
                self.active[name] = {"level": level, "since": time.time(), "escalated": False}

    def escalated(self, name: str):
        with self._lock:
            if name in self.active:
                self.active[name]["escalated"] = True

    def resolved(self, name: str):
        with self._lock:
            self.active.pop(name, None)

    def reset_all(self):
        """Vide tous les incidents actifs d'un coup (bouton reset du dashboard,
        utilise uniquement en mode simulation — en mode reel c'est l'Arduino
        qui decide et confirme via ses propres messages [RESOLUTION])."""
        with self._lock:
            self.active = {}

    def snapshot(self):
        with self._lock:
            items = [{"name": n, **v} for n, v in self.active.items()]
            connected = self.connected

        items.sort(key=lambda i: (LEVEL_ORDER.get(i["level"], 9), i["since"]))
        current = items[0] if items else None
        queue = items[1:]
        return {
            "connected": connected,
            "current": current,
            "queue": queue,
            "server_time": time.time(),
        }


state = VesselState()


class SensorState:
    """Dernieres valeurs brutes des capteurs, rapportees periodiquement par
    l'Arduino (ligne [CAPTEURS] du journal serie)."""

    def __init__(self):
        self._lock = threading.Lock()
        self.values = {}
        self.last_update = None

    def update(self, values: dict):
        with self._lock:
            self.values = values
            self.last_update = time.time()

    def snapshot(self):
        with self._lock:
            return {
                "values": dict(self.values),
                "last_update": self.last_update,
                "server_time": time.time(),
            }


sensor_state = SensorState()