/*
  ============================================================
  SafeVessel — Système Autonome de Gestion des Incidents Critiques
  Workshop ESA Horizon 2080 — Machine à états v0.2
  Version complète : boutons + LEDs (breadboard) + buzzer + servo + écran OLED
  ============================================================

  Ce sketch REMPLACE l'ancien SafeVessel.ino ET le SafeVessel_OLED_test.ino :
  c'est le seul fichier a téléverser sur l'Arduino a partir de maintenant.

  Cablage — directement sur l'Arduino (boutons avec resistance de pull-down
  externe 10kOhm : une patte vers 5V, l'autre vers la broche + une resistance
  10k vers GND) :
    D6  Bouton 1 - Fuite d'air     D10 Bouton 5 - Resolution
    D7  Bouton 2 - Incendie         D11 Buzzer
    D8  Bouton 3 - Panne electrique D12 Servomoteur (PWM)
    D9  Bouton 4 - Intrusion        A4  Ecran OLED - SDA
                                     A5  Ecran OLED - SCL

  ATTENTION : l'ordre Bouton 1->Fuite d'air, 2->Incendie, 3->Panne electrique,
  4->Intrusion, 5->Resolution est une supposition basee sur l'ordre historique
  du projet. Si vos 5 boutons physiques ne sont pas cables dans cet ordre-la,
  dites-le pour qu'on corrige le tableau "incidents[]" plus bas.

  Cablage — sur la breadboard (les 4 LEDs, chacune avec sa resistance 220ohm
  entre la broche et la LED, cathode vers le rail GND de la breadboard) :
    D2  LED rouge   (fuite d'air)
    D3  LED jaune   (incendie / panne electrique)
    D4  LED bleue   (intrusion)
    D5  LED verte   (etat normal)

  Librairies necessaires (Croquis > Inclure une bibliotheque > Gerer les
  bibliotheques) :
    - Servo               (incluse d'office avec l'IDE Arduino)
    - Adafruit SSD1306
    - Adafruit GFX Library (installee automatiquement comme dependance)
*/

#include <Servo.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ---------- Ecran OLED ----------
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define SCREEN_ADDRESS 0x3C
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// ---------- Broches ----------
const int BTN_AIR        = 6;
const int BTN_FIRE       = 7;
const int BTN_POWER      = 8;
const int BTN_INTRUSION  = 9;
const int BTN_RESOLVE    = 10;

const int LED_RED    = 2;   // fuite d'air
const int LED_JAUNE  = 3;   // incendie / panne electrique
const int LED_BLUE   = 4;   // intrusion
const int LED_GREEN  = 5;   // etat normal
const int BUZZER     = 11;
const int SERVO_PIN  = 12;
const int LED_LOISIRS = LED_BUILTIN; // D13, module symbolique

Servo trappe;

// ---------- Modele d'un incident ----------
enum IncidentId { AIR_LEAK = 0, FIRE = 1, POWER_FAILURE = 2, INTRUSION = 3, NB_INCIDENTS = 4 };

struct Incident {
  const char* nom;         // nom complet (pour le port serie)
  const char* nomCourt;    // nom court (pour l'ecran OLED, largeur limitee)
  int priorite;             // 1 = Critique, 2 = Haute, 3 = Moyenne
  const char* niveauTxt;
  unsigned long delaiEscalade;
  int btnPin;
  bool actif;
  bool escalade;
  unsigned long tDebut;
};

Incident incidents[NB_INCIDENTS] = {
  { "Fuite d'air (O2)", "Fuite d'air", 1, "CRITIQUE", 10000, BTN_AIR,       false, false, 0 },
  { "Incendie",         "Incendie",    2, "HAUTE",    15000, BTN_FIRE,      false, false, 0 },
  { "Panne electrique", "Panne elec.", 2, "HAUTE",    12000, BTN_POWER,     false, false, 0 },
  { "Intrusion",        "Intrusion",   3, "MOYENNE",  20000, BTN_INTRUSION, false, false, 0 }
};

unsigned long dernierAppui[NB_INCIDENTS + 1] = {0};
const unsigned long DEBOUNCE_MS = 250;

unsigned long dernierToggleBuzzer = 0;
bool buzzerEtat = false;

unsigned long dernierRafraichissementEcran = 0;
const unsigned long RAFRAICHISSEMENT_ECRAN_MS = 300; // evite de saturer le bus I2C

void setup() {
  Serial.begin(9600);

  // Boutons cables avec resistances de pull-down externes 10kOhm (pin -> bouton -> 5V,
  // et pin -> resistance 10k -> GND). Au repos la pin lit LOW, un appui la fait
  // passer a HIGH -- c'est l'inverse d'un montage INPUT_PULLUP classique.
  for (int i = 0; i < NB_INCIDENTS; i++) {
    pinMode(incidents[i].btnPin, INPUT);
  }
  pinMode(BTN_RESOLVE, INPUT);

  pinMode(LED_RED, OUTPUT);
  pinMode(LED_JAUNE, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_LOISIRS, OUTPUT);
  pinMode(BUZZER, OUTPUT);

  trappe.attach(SERVO_PIN);
  trappe.write(0);

  digitalWrite(LED_GREEN, HIGH);
  digitalWrite(LED_LOISIRS, HIGH);

  if (!display.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
    Serial.println(F("Echec de l'initialisation de l'ecran OLED (verifiez le cablage/adresse)."));
  } else {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.println(F("SafeVessel"));
    display.println(F("Demarrage..."));
    display.display();
  }

  Serial.println(F("=== SafeVessel — Systeme pret ==="));
  delay(800);
}

void loop() {
  lireCommandeSerie();
  lireBoutonsDetection();
  lireBoutonResolution();
  gererEscalades();
  gererInterconnexion();
  int idTraite = trouverIncidentPrioritaire();
  mettreAJourSortiesVisuellesEtSonores(idTraite);
  afficherFileAttente(idTraite);
  mettreAJourEcran(idTraite);
}

// ---------- Commande recue depuis le dashboard web (via port serie) ----------
void lireCommandeSerie() {
  if (!Serial.available()) return;
  String commande = Serial.readStringUntil('\n');
  commande.trim();
  if (commande.length() == 0) return;

  // Echo de diagnostic : confirme EXACTEMENT ce que l'Arduino a recu,
  // visible dans le journal du dashboard (utile pour verifier qu'une
  // commande envoyee depuis le site arrive bien intacte).
  Serial.print(F("[COMMANDE RECUE] "));
  Serial.println(commande);

  if (commande == "RESET") {
    reinitialiserToutesLesAlertes();
  } else if (commande == "TRIGGER_AIR") {
    declencherIncidentSiPossible(AIR_LEAK);
  } else if (commande == "TRIGGER_FIRE") {
    declencherIncidentSiPossible(FIRE);
  } else if (commande == "TRIGGER_POWER") {
    declencherIncidentSiPossible(POWER_FAILURE);
  } else if (commande == "TRIGGER_INTRUSION") {
    declencherIncidentSiPossible(INTRUSION);
  }
}

// Declenche un incident depuis une commande distante, EXACTEMENT comme un
// appui sur le bouton physique correspondant (meme fonction, meme etat
// partage) : aucun risque de collision entre web et boutons physiques,
// puisque c'est la meme logique de priorisation qui s'applique ensuite.
void declencherIncidentSiPossible(int id) {
  if (!incidents[id].actif) {
    declencherIncident(id);
    Serial.println(F("[COMMANDE] Declenchement depuis le dashboard"));
  } else {
    Serial.print(F("[COMMANDE] "));
    Serial.print(incidents[id].nom);
    Serial.println(F(" deja actif, commande ignoree"));
  }
}

void reinitialiserToutesLesAlertes() {
  Serial.println(F("[COMMANDE] RESET recu depuis le dashboard"));
  for (int i = 0; i < NB_INCIDENTS; i++) {
    if (incidents[i].actif) {
      unsigned long duree = millis() - incidents[i].tDebut;
      Serial.print(F("[RESOLUTION] "));
      Serial.print(incidents[i].nom);
      Serial.print(F(" - duree(ms)="));
      Serial.print(duree);
      Serial.print(F(" - escalade="));
      Serial.println(incidents[i].escalade ? F("oui") : F("non"));

      incidents[i].actif = false;
      incidents[i].escalade = false;
    }
  }
  trappe.write(0); // remet la trappe/servo en position normale
}

// ---------- Lecture des boutons de declenchement ----------
void lireBoutonsDetection() {
  for (int i = 0; i < NB_INCIDENTS; i++) {
    bool appuye = (digitalRead(incidents[i].btnPin) == HIGH); // pull-down externe : appui = HIGH
    if (appuye && !incidents[i].actif && (millis() - dernierAppui[i] > DEBOUNCE_MS)) {
      dernierAppui[i] = millis();
      declencherIncident(i);
    }
  }
}

void declencherIncident(int id) {
  incidents[id].actif = true;
  incidents[id].escalade = false;
  incidents[id].tDebut = millis();

  Serial.print(F("[DETECTION] "));
  Serial.print(incidents[id].nom);
  Serial.print(F(" - t="));
  Serial.println(millis());
}

// ---------- Bouton resolution ----------
void lireBoutonResolution() {
  bool appuye = (digitalRead(BTN_RESOLVE) == HIGH); // pull-down externe : appui = HIGH
  if (appuye && (millis() - dernierAppui[NB_INCIDENTS] > DEBOUNCE_MS)) {
    dernierAppui[NB_INCIDENTS] = millis();
    int id = trouverIncidentPrioritaire();
    if (id != -1) {
      unsigned long duree = millis() - incidents[id].tDebut;
      Serial.print(F("[RESOLUTION] "));
      Serial.print(incidents[id].nom);
      Serial.print(F(" - duree(ms)="));
      Serial.print(duree);
      Serial.print(F(" - escalade="));
      Serial.println(incidents[id].escalade ? F("oui") : F("non"));

      incidents[id].actif = false;
      incidents[id].escalade = false;

      if (id == AIR_LEAK) trappe.write(0);
    }
  }
}

// ---------- Incident actuellement traite (priorite la plus haute) ----------
int trouverIncidentPrioritaire() {
  int meilleurId = -1;
  for (int i = 0; i < NB_INCIDENTS; i++) {
    if (!incidents[i].actif) continue;
    if (meilleurId == -1) {
      meilleurId = i;
    } else if (incidents[i].priorite < incidents[meilleurId].priorite) {
      meilleurId = i;
    } else if (incidents[i].priorite == incidents[meilleurId].priorite &&
               incidents[i].tDebut < incidents[meilleurId].tDebut) {
      meilleurId = i;
    }
  }
  return meilleurId;
}

// ---------- Escalade automatique ----------
void gererEscalades() {
  for (int i = 0; i < NB_INCIDENTS; i++) {
    if (incidents[i].actif && !incidents[i].escalade &&
        (millis() - incidents[i].tDebut > incidents[i].delaiEscalade)) {
      incidents[i].escalade = true;
      declencherActionEscalade(i);
    }
  }
}

void declencherActionEscalade(int id) {
  Serial.print(F("[ESCALADE] "));
  Serial.println(incidents[id].nom);

  switch (id) {
    case AIR_LEAK:
      trappe.write(90);
      break;
    case FIRE:
      Serial.println(F("  -> Coupure electrique du secteur (a implementer via relais)"));
      break;
    case POWER_FAILURE:
      Serial.println(F("  -> Redistribution automatique de l'energie vers systemes vitaux"));
      break;
    case INTRUSION:
      trappe.write(90);
      Serial.println(F("  -> Verrouillage de la zone"));
      break;
  }
}

// ---------- Interconnexion ----------
void gererInterconnexion() {
  if (incidents[POWER_FAILURE].actif) {
    digitalWrite(LED_LOISIRS, LOW);
  } else {
    digitalWrite(LED_LOISIRS, HIGH);
  }
}

// ---------- LEDs (breadboard) + buzzer ----------
void mettreAJourSortiesVisuellesEtSonores(int idTraite) {
  digitalWrite(LED_RED, LOW);
  digitalWrite(LED_JAUNE, LOW);
  digitalWrite(LED_BLUE, LOW);
  digitalWrite(LED_GREEN, LOW);

  if (idTraite == -1) {
    digitalWrite(LED_GREEN, HIGH);
    digitalWrite(BUZZER, LOW);
    return;
  }

  switch (idTraite) {
    case AIR_LEAK:
      digitalWrite(LED_RED, HIGH);
      digitalWrite(BUZZER, HIGH);
      break;
    case FIRE:
      digitalWrite(LED_JAUNE, HIGH);
      buzzerIntermittent(300);
      break;
    case POWER_FAILURE:
      digitalWrite(LED_JAUNE, HIGH);
      digitalWrite(BUZZER, LOW);
      break;
    case INTRUSION:
      digitalWrite(LED_BLUE, HIGH);
      digitalWrite(BUZZER, LOW);
      break;
  }
}

void buzzerIntermittent(unsigned long periodeMs) {
  if (millis() - dernierToggleBuzzer > periodeMs) {
    dernierToggleBuzzer = millis();
    buzzerEtat = !buzzerEtat;
    digitalWrite(BUZZER, buzzerEtat ? HIGH : LOW);
  }
}

// ---------- Journal serie de la file d'attente ----------
unsigned long dernierAffichageFile = 0;
void afficherFileAttente(int idTraite) {
  if (millis() - dernierAffichageFile < 2000) return;
  dernierAffichageFile = millis();

  bool auMoinsUnEnAttente = false;
  for (int i = 0; i < NB_INCIDENTS; i++) {
    if (incidents[i].actif && i != idTraite) {
      if (!auMoinsUnEnAttente) {
        Serial.print(F("[FILE D'ATTENTE] "));
        auMoinsUnEnAttente = true;
      }
      Serial.print(incidents[i].nom);
      Serial.print(F(" ; "));
    }
  }
  if (auMoinsUnEnAttente) Serial.println();
}

// ---------- Affichage temps reel sur l'ecran OLED ----------
void mettreAJourEcran(int idTraite) {
  if (millis() - dernierRafraichissementEcran < RAFRAICHISSEMENT_ECRAN_MS) return;
  dernierRafraichissementEcran = millis();

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

  // Ligne 1 : titre
  display.setCursor(0, 0);
  display.println(F("SafeVessel"));
  display.drawLine(0, 10, 127, 10, SSD1306_WHITE);

  if (idTraite == -1) {
    // Etat normal
    display.setCursor(0, 20);
    display.println(F("SYSTEME NORMAL"));
    display.setCursor(0, 34);
    display.println(F("Aucun incident actif"));
  } else {
    // Incident en cours de traitement
    display.setCursor(0, 16);
    display.print(F("INCIDENT: "));
    display.println(incidents[idTraite].nomCourt);

    display.setCursor(0, 28);
    display.print(F("Niveau : "));
    display.println(incidents[idTraite].niveauTxt);

    unsigned long dureeS = (millis() - incidents[idTraite].tDebut) / 1000;
    display.setCursor(0, 40);
    display.print(F("Depuis : "));
    display.print(dureeS);
    display.println(F("s"));

    if (incidents[idTraite].escalade) {
      display.setCursor(0, 52);
      display.println(F("!! ESCALADE ACTIVE !!"));
    }
  }

  // Compte des incidents en file d'attente, affiche en bas a droite
  int nbEnAttente = 0;
  for (int i = 0; i < NB_INCIDENTS; i++) {
    if (incidents[i].actif && i != idTraite) nbEnAttente++;
  }
  if (nbEnAttente > 0) {
    display.setCursor(90, 52);
    display.print(F("File:"));
    display.print(nbEnAttente);
  }

  display.display();
}
