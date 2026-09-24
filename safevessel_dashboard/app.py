"""
SafeVessel — Dashboard web
Sert la console de bord (page web) et son API, a heberger sur le Raspberry Pi.

Lancement :
  python app.py                          -> lit le vrai port serie (Arduino branche)
  SAFEVESSEL_SIMULATE=1 python app.py     -> mode simulation, sans materiel

Acces depuis un navigateur (PC ou telephone sur le meme reseau) :
  http://<ip_du_raspberry>:5000
"""
import os
import secrets
import threading

from flask import Flask, render_template, jsonify, request, Response, session, redirect, url_for

from state import state, sensor_state
from db import init_db, fetch_events, clear_events, export_csv, log_event, fetch_stats
import serial_reader
from serial_reader import run_serial_loop
from simulate import run_simulation_loop
import auth

SIMULATE = os.environ.get("SAFEVESSEL_SIMULATE", "0") == "1"
SERIAL_PORT = os.environ.get("SAFEVESSEL_PORT", "/dev/ttyACM0")
SERIAL_BAUD = int(os.environ.get("SAFEVESSEL_BAUD", "9600"))
HTTP_PORT = int(os.environ.get("SAFEVESSEL_HTTP_PORT", "5000"))

# Incidents declenchables depuis le dashboard : meme commande que celle
# ecoutee par SafeVessel_complet.ino (lireCommandeSerie). La cle est
# utilisee dans l'URL (/api/trigger/<cle>) et par les boutons du site.
INCIDENT_TRIGGERS = {
    "air":       {"command": "TOGGLE_AIR",        "name": "Fuite d'air (O2)",    "level": "critique"},
    "fire":      {"command": "TRIGGER_FIRE",       "name": "Incendie",            "level": "haute"},
    "power":     {"command": "TRIGGER_POWER",      "name": "Panne electrique",    "level": "haute"},
    "intrusion": {"command": "TRIGGER_INTRUSION",  "name": "Intrusion",           "level": "moyenne"},
}

app = Flask(__name__)
# Cle de session : fixe-la via SAFEVESSEL_SECRET_KEY pour que les connexions
# survivent aux redemarrages du service ; sinon une cle aleatoire est
# generee a chaque demarrage (tout le monde est deconnecte au redemarrage).
app.secret_key = os.environ.get("SAFEVESSEL_SECRET_KEY", secrets.token_hex(32))

_stop_event = threading.Event()
_started = False


@app.route("/")
@auth.login_required
def dashboard():
    return render_template(
        "dashboard.html", simulate=SIMULATE, port=SERIAL_PORT, username=session.get("username")
    )


@app.route("/historique")
@auth.login_required
def historique():
    return render_template("historique.html", username=session.get("username"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if auth.verify_login(username, password):
            session["username"] = username
            next_url = request.args.get("next") or url_for("dashboard")
            return redirect(next_url)
        return render_template("login.html", error="Identifiant ou mot de passe incorrect.")
    return render_template("login.html", error=None)


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("username", None)
    return redirect(url_for("dashboard"))


@app.route("/api/status")
@auth.login_required
def api_status():
    return jsonify(state.snapshot())


@app.route("/api/sensors")
@auth.login_required
def api_sensors():
    return jsonify(sensor_state.snapshot())


@app.route("/api/stats")
@auth.login_required
def api_stats():
    return jsonify(fetch_stats())


@app.route("/api/trigger/<key>", methods=["POST"])
@auth.login_required
def api_trigger(key):
    info = INCIDENT_TRIGGERS.get(key)
    if not info:
        return jsonify({"ok": False, "error": "Incident inconnu"}), 404

    if SIMULATE:
        state.detected(info["name"], info["level"])
        log_event("DETECTION", info["name"], info["level"], "declenche depuis le dashboard (simulation)")
        return jsonify({"ok": True})

    ok = serial_reader.send_command(info["command"])
    if not ok:
        return jsonify({"ok": False, "error": "Arduino non connecté"}), 503
    return jsonify({"ok": True})


@app.route("/api/clear_cache", methods=["POST"])
@auth.login_required
def api_clear_cache():
    # Vide uniquement l'etat affiche (incident en cours + file d'attente),
    # sans envoyer aucune commande a l'Arduino et sans toucher au journal.
    # A utiliser si l'affichage semble bloque sur une alerte qui n'existe
    # plus reellement, typiquement apres une coupure du cable USB.
    state.reset_all()
    log_event("INFO", "-", "-", "Cache d'affichage vide manuellement depuis le dashboard")
    return jsonify({"ok": True})


@app.route("/api/reset", methods=["POST"])
@auth.login_required
def api_reset():
    if SIMULATE:
        snap = state.snapshot()
        incidents_actifs = ([snap["current"]] if snap["current"] else []) + snap["queue"]
        for inc in incidents_actifs:
            duree_ms = int((state.snapshot()["server_time"] - inc["since"]) * 1000)
            log_event("RESOLUTION", inc["name"], inc["level"],
                      "resolu (reset dashboard, simulation)",
                      duration_ms=duree_ms, escalade=inc.get("escalated", False))
        state.reset_all()
        return jsonify({"ok": True})

    ok = serial_reader.send_command("RESET")
    if not ok:
        return jsonify({"ok": False, "error": "Arduino non connecté"}), 503
    return jsonify({"ok": True})


@app.route("/api/logs")
@auth.login_required
def api_logs():
    limit = int(request.args.get("limit", 200))
    return jsonify(fetch_events(limit=limit))


@app.route("/api/logs/clear", methods=["POST"])
@auth.login_required
def api_logs_clear():
    clear_events()
    return jsonify({"ok": True})


@app.route("/api/logs/export")
@auth.login_required
def api_logs_export():
    csv_data = export_csv()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=safevessel_logs.csv"},
    )


def start_background_worker():
    global _started
    if _started:
        return
    _started = True
    init_db()
    auth.init_auth_db()
    auth.ensure_default_admin()
    if SIMULATE:
        threading.Thread(target=run_simulation_loop, args=(_stop_event,), daemon=True).start()
    else:
        threading.Thread(
            target=run_serial_loop, args=(SERIAL_PORT, SERIAL_BAUD, _stop_event), daemon=True
        ).start()


start_background_worker()

if __name__ == "__main__":
    mode = "SIMULATION" if SIMULATE else f"serie ({SERIAL_PORT} @ {SERIAL_BAUD} bauds)"
    print(f"SafeVessel dashboard — mode {mode} — http://0.0.0.0:{HTTP_PORT}")
    app.run(host="0.0.0.0", port=HTTP_PORT, debug=False)