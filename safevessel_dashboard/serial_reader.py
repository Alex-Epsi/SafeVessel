"""
Lit en continu le port serie sur lequel l'Arduino SafeVessel est branche,
parse les lignes de journal qu'il envoie et met a jour l'etat partage + la BDD.

Formats de lignes produits par SafeVessel.ino :
  [DETECTION] <nom> - t=<millis>
  [ESCALADE] <nom>
  [RESOLUTION] <nom> - duree(ms)=<n> - escalade=<oui|non>
  [FILE D'ATTENTE] <nom1> ; <nom2> ;
Toute autre ligne est journalisee telle quelle en tant qu'evenement INFO.
"""
import re
import time

from state import state, INCIDENT_LEVELS
from db import log_event

RE_DETECTION = re.compile(r"^\[DETECTION\]\s*(.+?)\s*-\s*t=(\d+)$")
RE_ESCALADE = re.compile(r"^\[ESCALADE\]\s*(.+)$")
RE_RESOLUTION = re.compile(r"^\[RESOLUTION\]\s*(.+?)\s*-\s*duree\(ms\)=(\d+)\s*-\s*escalade=(oui|non)$")
RE_FILE_ATTENTE = re.compile(r"^\[FILE D'ATTENTE\]")


def parse_line(line: str):
    line = line.strip()
    if not line:
        return

    m = RE_DETECTION.match(line)
    if m:
        name, t_ms = m.group(1), m.group(2)
        level = INCIDENT_LEVELS.get(name, "inconnue")
        state.detected(name, level)
        log_event("DETECTION", name, level, f"declenche (t={t_ms} ms cote Arduino)")
        return

    m = RE_RESOLUTION.match(line)
    if m:
        name, duree_ms, escalade = m.group(1), m.group(2), m.group(3)
        level = INCIDENT_LEVELS.get(name, "inconnue")
        state.resolved(name)
        log_event("RESOLUTION", name, level, f"duree={duree_ms}ms, escalade={escalade}")
        return

    m = RE_ESCALADE.match(line)
    if m:
        name = m.group(1)
        level = INCIDENT_LEVELS.get(name, "inconnue")
        state.escalated(name)
        log_event("ESCALADE", name, level, "action d'escalade declenchee")
        return

    if RE_FILE_ATTENTE.match(line):
        # Informatif seulement : la file d'attente est deja recalculee
        # automatiquement a partir des incidents actifs connus.
        return

    # Ligne non reconnue (ex: sous-message d'escalade, message de demarrage...)
    log_event("INFO", "-", "-", line)


def run_serial_loop(port: str, baud: int, stop_event):
    """Boucle de connexion/lecture au port serie, avec reconnexion automatique."""
    import serial  # import local : evite de casser le mode simulation si pyserial absent

    while not stop_event.is_set():
        try:
            with serial.Serial(port, baud, timeout=1) as ser:
                state.set_connected(True)
                log_event("INFO", "-", "-", f"connecte au port serie {port}")
                while not stop_event.is_set():
                    raw = ser.readline()
                    if not raw:
                        continue
                    try:
                        line = raw.decode("utf-8", errors="replace")
                    except Exception:
                        continue
                    parse_line(line)
        except Exception as exc:  # port absent, deconnexion, permissions...
            state.set_connected(False)
            time.sleep(3)  # nouvelle tentative dans 3s
