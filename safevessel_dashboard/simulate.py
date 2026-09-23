"""
Mode simulation : genere des incidents factices pour tester et repeter
la demo sans avoir l'Arduino branche. Active avec SAFEVESSEL_SIMULATE=1.
"""
import random
import threading
import time

from state import state, sensor_state, INCIDENT_LEVELS
from db import log_event

NAMES = list(INCIDENT_LEVELS.keys())


def _simuler_capteurs_loop(stop_event):
    """Genere des valeurs de capteurs plausibles qui varient doucement,
    pour que le panneau 'Capteurs en direct' du dashboard ait quelque
    chose a afficher meme sans materiel branche."""
    temperature = 23.0
    eco2 = 420.0
    while not stop_event.is_set():
        temperature += random.uniform(-0.3, 0.3)
        eco2 += random.uniform(-15, 15)
        eco2 = max(400, eco2)
        sensor_state.update({
            "T": round(temperature, 1),
            "H": round(45 + random.uniform(-3, 3), 1),
            "ECO2": round(eco2),
            "TVOC": round(max(0, eco2 - 400) / 4),
            "AIR": 0,
            "PIR": 0,
        })
        time.sleep(1)


def _resolve_later(name: str, level: str):
    t_debut = time.time()
    escalade_survenue = False
    time.sleep(random.uniform(4, 12))
    if random.random() < 0.35:
        escalade_survenue = True
        state.escalated(name)
        log_event("ESCALADE", name, level, "action d'escalade (simulation)")
        time.sleep(random.uniform(2, 5))
    duree_ms = int((time.time() - t_debut) * 1000)
    state.resolved(name)
    log_event("RESOLUTION", name, level, "resolu (simulation)",
              duration_ms=duree_ms, escalade=escalade_survenue)


def run_simulation_loop(stop_event):
    state.set_connected(True)
    log_event("INFO", "-", "-", "mode simulation actif (pas de materiel reel)")
    threading.Thread(target=_simuler_capteurs_loop, args=(stop_event,), daemon=True).start()

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