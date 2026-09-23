"""
Authentification simple par session Flask, pour proteger les actions
destructives du dashboard (reset, vider le journal, resynchroniser).

Comptes stockes dans la meme base SQLite que le journal (table users),
mots de passe haches avec werkzeug (jamais stockes en clair).

Rien a installer : Flask (session) et werkzeug (hachage) sont deja des
dependances de Flask lui-meme.
"""
import os
import sqlite3
import threading
from functools import wraps

from flask import session, redirect, url_for, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from db import DB_PATH

_lock = threading.Lock()


def init_auth_db():
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
            """
        )
        conn.commit()


def ensure_default_admin():
    """Cree un compte admin par defaut si la table users est vide, a partir
    des variables d'environnement SAFEVESSEL_ADMIN_USER et
    SAFEVESSEL_ADMIN_PASSWORD (sinon admin / safevessel — A CHANGER)."""
    username = os.environ.get("SAFEVESSEL_ADMIN_USER", "admin")
    password = os.environ.get("SAFEVESSEL_ADMIN_PASSWORD", "safevessel")

    with _lock, sqlite3.connect(DB_PATH) as conn:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password)),
            )
            conn.commit()
            print(f"[auth] Compte admin cree : {username} / {password}  (pensez a le changer !)")


def verify_login(username: str, password: str) -> bool:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    if not row:
        return False
    return check_password_hash(row[0], password)


def change_password(username: str, new_password: str) -> bool:
    """Utilitaire pour changer un mot de passe (voir README : change_password.py)."""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (generate_password_hash(new_password), username),
        )
        conn.commit()
        return cur.rowcount > 0


def login_required(view_func):
    """Decorateur : redirige vers /login (pages) ou renvoie 401 (API /api/...)
    si personne n'est connecte."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("username"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Authentification requise"}), 401
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)
    return wrapped
