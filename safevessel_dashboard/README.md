# SafeVessel — Dashboard web

Console de bord web pour le projet SafeVessel : visualisation en temps réel de
l'incident en cours, de la file d'attente, et journal des événements
(consultable, exportable en CSV, purgeable).

## 1. Tester sur votre PC (sans Raspberry Pi ni Arduino)

```bash
cd safevessel_dashboard
python3 -m venv venv
source venv/bin/activate          # sous Windows : venv\Scripts\activate
pip install -r requirements.txt

# Mode simulation : génère de faux incidents, aucun matériel requis
SAFEVESSEL_SIMULATE=1 python3 app.py
```

Ouvrez ensuite **http://localhost:5000** dans votre navigateur. C'est le mode
idéal pour avancer sur l'interface pendant que le câblage n'est pas encore prêt.

## 2. Déployer sur le Raspberry Pi (avec l'Arduino branché en USB)

1. **Copier le projet sur le Pi** (clé USB, `scp`, ou `git clone` si vous
   avez mis le code sur GitHub) dans `/home/pi/safevessel_dashboard`.

2. **Installer les dépendances** :
   ```bash
   cd /home/pi/safevessel_dashboard
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Identifier le port série de l'Arduino** une fois branché en USB :
   ```bash
   ls /dev/tty*
   # cherchez /dev/ttyACM0 ou /dev/ttyUSB0
   ```
   Si besoin, ajoutez votre utilisateur au groupe `dialout` pour avoir le
   droit de lire le port série sans `sudo` :
   ```bash
   sudo usermod -a -G dialout pi
   # puis redémarrez la session (ou le Pi)
   ```

4. **Lancer le dashboard** en pointant vers le bon port :
   ```bash
   SAFEVESSEL_PORT=/dev/ttyACM0 python3 app.py
   ```
   (Ajustez `/dev/ttyACM0` si votre port est différent.)

5. **Trouver l'adresse IP du Raspberry Pi** :
   ```bash
   hostname -I
   ```

6. **Accéder au dashboard** depuis n'importe quel appareil sur le même
   réseau (PC, téléphone, PC portable du jury...) :
   ```
   http://<ip_du_raspberry>:5000
   ```
   Exemple : `http://192.168.1.42:5000`

## 3. Démarrage automatique (optionnel mais recommandé pour la démo)

Pour que le dashboard démarre tout seul à l'allumage du Pi, sans commande à
taper le jour de la soutenance :

```bash
sudo cp safevessel-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable safevessel-dashboard
sudo systemctl start safevessel-dashboard
```

Adaptez d'abord les chemins (`WorkingDirectory`, `ExecStart`) dans le fichier
`safevessel-dashboard.service` si votre projet n'est pas dans
`/home/pi/safevessel_dashboard`.

Vérifier que ça tourne : `sudo systemctl status safevessel-dashboard`
Voir les logs du service : `journalctl -u safevessel-dashboard -f`

## 4. Variables d'environnement disponibles

| Variable | Défaut | Usage |
|---|---|---|
| `SAFEVESSEL_PORT` | `/dev/ttyACM0` | Port série de l'Arduino |
| `SAFEVESSEL_BAUD` | `9600` | Vitesse série (doit correspondre à `Serial.begin()` dans le .ino) |
| `SAFEVESSEL_HTTP_PORT` | `5000` | Port web du dashboard |
| `SAFEVESSEL_SIMULATE` | `0` | `1` pour générer des incidents factices sans matériel |
| `SAFEVESSEL_DB_PATH` | `safevessel_logs.db` (local) | Emplacement du fichier de journal SQLite |

## 5. Structure du projet

```
safevessel_dashboard/
├── app.py                 # application Flask (routes page + API)
├── state.py                # état courant (incident traité, file d'attente)
├── db.py                   # journal persistant (SQLite, export CSV, purge)
├── serial_reader.py         # lecture et parsing du port série Arduino
├── simulate.py              # générateur d'incidents factices pour tester
├── requirements.txt
├── safevessel-dashboard.service   # service systemd pour démarrage auto
├── templates/dashboard.html
└── static/
    ├── style.css
    └── app.js
```

## 6. Le journal Arduino attendu

Ce dashboard parse les lignes envoyées par `SafeVessel.ino` sur le port
série (9600 bauds) :

```
[DETECTION] Fuite d'air (O2) - t=12345
[ESCALADE] Fuite d'air (O2)
[RESOLUTION] Fuite d'air (O2) - duree(ms)=15320 - escalade=oui
[FILE D'ATTENTE] Incendie ; Intrusion ;
```

Si vous changez les noms d'incidents dans le code Arduino, mettez aussi à
jour le dictionnaire `INCIDENT_LEVELS` dans `state.py` pour que les niveaux
de criticité (et les couleurs) restent corrects côté dashboard.
