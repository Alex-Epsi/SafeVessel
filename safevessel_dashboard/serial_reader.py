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
import threading
import time

from state import state, sensor_state, INCIDENT_LEVELS
from db import log_event

RE_DETECTION = re.compile(r"^\[DETECTION\]\s*(.+?)\s*-\s*t=(\d+)$")
RE_ESCALADE = re.compile(r"^\[ESCALADE\]\s*(.+)$")
RE_RESOLUTION = re.compile(r"^\[RESOLUTION\]\s*(.+?)\s*-\s*duree\(ms\)=(\d+)\s*-\s*escalade=(oui|non)$")
RE_FILE_ATTENTE = re.compile(r"^\[FILE D'ATTENTE\]")
RE_CAPTEURS = re.compile(r"^\[CAPTEURS\]\s*(.+)$")
RE_NOMBRE = re.compile(r"[-+]?[0-9]*\.?[0-9]+")

# Reference partagee vers la connexion serie ouverte, pour pouvoir lui ecrire
# des commandes (ex: RESET) depuis les routes Flask, sans ouvrir un 2e port.
_serial_lock = threading.Lock()
_current_serial = None


def send_command(command: str) -> bool:
    """Envoie une commande texte a l'Arduino via le port serie deja ouvert.
    Retourne True si l'envoi a reussi, False si aucun port n'est connecte."""
    with _serial_lock:
        if _current_serial is None or not _current_serial.is_open:
            return False
        try:
            _current_serial.write((command + "\n").encode("utf-8"))
            return True
        except Exception:
            return False


def parse_line(line: str):
    line = line.strip()
    if not line:
        return

    m = RE_CAPTEURS.match(line)
    if m:
        # Mise a jour de l'etat en memoire seulement -- pas de log_event ici :
        # a 1 ligne/seconde, journaliser chaque rapport gonflerait la base
        # inutilement (le journal reste reserve aux vrais evenements).
        valeurs = {}
        for token in m.group(1).split():
            if "=" not in token:
                continue
            cle, brut = token.split("=", 1)
            nombre = RE_NOMBRE.match(brut)
            if nombre:
                valeurs[cle] = float(nombre.group(0))
        sensor_state.update(valeurs)
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
        log_event("RESOLUTION", name, level, f"duree={duree_ms}ms, escalade={escalade}",
                   duration_ms=int(duree_ms), escalade=(escalade == "oui"))
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
    global _current_serial
    import serial  # import local : evite de casser le mode simulation si pyserial absent

    while not stop_event.is_set():
        try:
            with serial.Serial(port, baud, timeout=1) as ser:
                with _serial_lock:
                    _current_serial = ser
                state.set_connected(True)

                # Correction du bug de "cache" : une reconnexion serie reset
                # presque toujours physiquement l'Arduino (comportement standard
                # de l'Uno a l'ouverture du port). Son etat reel est donc
                # "normal" a ce moment precis, meme si le Raspberry Pi avait
                # encore une alerte en memoire suite a la coupure. On
                # resynchronise systematiquement pour eviter une alerte
                # fantome bloquee jusqu'au prochain redemarrage du service.
                snap = state.snapshot()
                if snap["current"] is not None or snap["queue"]:
                    log_event("INFO", "-", "-",
                              "Reconnexion detectee : alerte(s) en cache effacee(s) pour resynchronisation")
                    state.reset_all()

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
            with _serial_lock:
                _current_serial = None
            time.sleep(3)  # nouvelle tentative dans 3s