"""
Mode simulation : genere des incidents factices pour tester et repeter
la demo sans avoir l'Arduino branche. Active avec SAFEVESSEL_SIMULATE=1.
"""
import random
import threading
import time

from state import state, INCIDENT_LEVELS
from db import log_event

NAMES = list(INCIDENT_LEVELS.keys())


def _resolve_later(name: str, level: str):
    time.sleep(random.uniform(4, 12))
    if random.random() < 0.35:
        state.escalated(name)
        log_event("ESCALADE", name, level, "action d'escalade (simulation)")
        time.sleep(random.uniform(2, 5))
    state.resolved(name)
    log_event("RESOLUTION", name, level, "resolu (simulation)")


def run_simulation_loop(stop_event):
    state.set_connected(True)
    log_event("INFO", "-", "-", "mode simulation actif (pas de materiel reel)")

    while not stop_event.is_set():
        time.sleep(random.uniform(5, 10))

        snap = state.snapshot()
        active_names = set()
        if snap["current"]:
            active_names.add(snap["current"]["name"])
        active_names |= {q["name"] for q in snap["queue"]}

        available = [n for n in NAMES if n not in active_names]
        if not available:
            continue

        name = random.choice(available)
        level = INCIDENT_LEVELS[name]
        state.detected(name, level)
        log_event("DETECTION", name, level, "declenche (simulation)")

        threading.Thread(target=_resolve_later, args=(name, level), daemon=True).start()
