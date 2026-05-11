import requests
import pandas as pd
import xgboost as xgb
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import pytz

# ==========================================
# 1. CONFIGURATION
# ==========================================
TS_CHANNEL_ID   = '3320504'
TS_READ_API_KEY = 'K1GSWZYVTBEO852O'
MODELE_PATH     = "modele_siemens_v4_classVF_orange.json"
FICHIER_ETAT    = "etat_alerte.txt"

EMAIL_SENDER    = "ilyassayli033@gmail.com"
EMAIL_PASSWORD  = "yxwcmybrdliatcpx"
EMAIL_RECEIVER  = "ilyassnbihi8@gmail.com"

# Ordre exact des 19 features du modèle entraîné (NE PAS MODIFIER)
FEATURES = [
    'He_Level_L', 'He_Level_Perc',
    'CHT_Temp_K', 'Link_Temp_K', 'Bore_Temp_K',
    'Magnet_Pressure_psiA', 'Heater_Power_W',
    'CHT_Temp_Lag1', 'CHT_Temp_Lag5',
    'Pressure_Lag1', 'Heater_Lag1', 'He_Level_Lag1',
    'Vitesse_Chauffe_CHT', 'Vitesse_Pression',
    'Vitesse_Heater', 'Vitesse_He_Level',
    'CHT_Moyenne_10', 'He_Level_Moyenne_10', 'Pression_Moyenne_10'
]

# ==========================================
# 2. CHARGEMENT DU MODÈLE
# Zone de risque 1 : fichier manquant ou corrompu
# ==========================================
try:
    modele = xgb.XGBClassifier()
    modele.load_model(MODELE_PATH)
    print(f"Modèle V4 Classifier chargé depuis '{MODELE_PATH}'.")
except Exception as e:
    print(f"ERREUR FATALE — Modèle introuvable ou corrompu : {e}")
    print(f"Vérifiez que '{MODELE_PATH}' est bien dans le même dossier que ce script.")
    exit(1)  # Arrêt propre avec code d'erreur

# ==========================================
# 3. ORCHESTRATEUR PRINCIPAL
# ==========================================
def orchestrateur_ia():

    # ------------------------------------------
    # ZONE RÉSEAU — ThingSpeak
    # Zone de risque 2 : réseau absent, API down, timeout
    # ------------------------------------------
    try:
        url = (
            f"https://api.thingspeak.com/channels/{TS_CHANNEL_ID}"
            f"/feeds.json?results=20&api_key={TS_READ_API_KEY}"
        )
        data = requests.get(url, timeout=10).json()['feeds']
        df   = pd.DataFrame(data)
        print(f"{len(df)} points récupérés depuis ThingSpeak.")
    except Exception as e:
        print(f"Erreur réseau ThingSpeak : {e}")
        print("Vérifiez votre connexion internet ou la clé API.")
        return  # Arrêt propre, on réessaiera au prochain cycle

    # ------------------------------------------
    # ZONE CALCUL + PRÉDICTION
    # Zone de risque 3 : données manquantes, champs vides, erreur modèle
    # ------------------------------------------
    try:
        # Mapping des 7 fields ThingSpeak → variables modèle
        # IMPORTANT : l'ordre des fields doit correspondre à ton canal ThingSpeak
        df_c = pd.DataFrame({
            'He_Level_L'          : pd.to_numeric(df['field1'], errors='coerce'),
            'He_Level_Perc'       : pd.to_numeric(df['field2'], errors='coerce'),
            'CHT_Temp_K'          : pd.to_numeric(df['field3'], errors='coerce'),
            'Link_Temp_K'         : pd.to_numeric(df['field4'], errors='coerce'),
            'Bore_Temp_K'         : pd.to_numeric(df['field5'], errors='coerce'),
            'Magnet_Pressure_psiA': pd.to_numeric(df['field6'], errors='coerce'),
            'Heater_Power_W'      : pd.to_numeric(df['field7'], errors='coerce'),
        })

        # Vérification du nombre minimum de points pour les lags
        if len(df_c) < 6:
            print(f"Pas assez de points : {len(df_c)} reçus, 6 minimum requis pour Lag5.")
            return

        # Raccourcis pour les lignes clés
        d  = df_c.iloc[-1]   # dernière mesure  (t = maintenant)
        a1 = df_c.iloc[-2]   # avant-dernière   (t - 1 point)
        a5 = df_c.iloc[-6]   # il y a 5 points  (t - 5 points)

        # Construction des 19 features dans l'ordre exact d'entraînement
        input_ia = pd.DataFrame([{
            # --- Capteurs bruts (7) ---
            'He_Level_L'          : d['He_Level_L'],
            'He_Level_Perc'       : d['He_Level_Perc'],
            'CHT_Temp_K'          : d['CHT_Temp_K'],
            'Link_Temp_K'         : d['Link_Temp_K'],
            'Bore_Temp_K'         : d['Bore_Temp_K'],
            'Magnet_Pressure_psiA': d['Magnet_Pressure_psiA'],
            'Heater_Power_W'      : d['Heater_Power_W'],
            # --- Lags / Mémoire temporelle (5) ---
            'CHT_Temp_Lag1'       : a1['CHT_Temp_K'],
            'CHT_Temp_Lag5'       : a5['CHT_Temp_K'],
            'Pressure_Lag1'       : a1['Magnet_Pressure_psiA'],
            'Heater_Lag1'         : a1['Heater_Power_W'],
            'He_Level_Lag1'       : a1['He_Level_L'],
            # --- Gradients / Vitesses de variation (4) ---
            'Vitesse_Chauffe_CHT' : d['CHT_Temp_K']           - a1['CHT_Temp_K'],
            'Vitesse_Pression'    : d['Magnet_Pressure_psiA'] - a1['Magnet_Pressure_psiA'],
            'Vitesse_Heater'      : d['Heater_Power_W']       - a1['Heater_Power_W'],
            'Vitesse_He_Level'    : d['He_Level_L']           - a1['He_Level_L'],
            # --- Moyennes glissantes / Tendances (3) ---
            'CHT_Moyenne_10'      : df_c['CHT_Temp_K'].tail(10).mean(),
            'He_Level_Moyenne_10' : df_c['He_Level_L'].tail(10).mean(),
            'Pression_Moyenne_10' : df_c['Magnet_Pressure_psiA'].tail(10).mean(),
        }])[FEATURES].fillna(0)  # fillna(0) pour les NaN résiduels

        # --- Prédiction ---
        classe = int(modele.predict(input_ia)[0])

        # Dictionnaire de diagnostic (classe → statut, emoji, couleur, envoyer, message)
        diag = {
            0: ("NORMAL",      "🟢", "#28a745", False,
                "L'aimant est sain. Aucune anomalie détectée par l'IA."),
            1: ("DÉGRADATION", "🟠", "#ffc107", True,
                "Dégradation progressive détectée. Surveillance renforcée requise."),
            2: ("CRITIQUE",    "🔴", "#dc3545", True,
                "Risque de Quench imminent ! Intervention immédiate requise.")
        }
        statut, emoji, couleur, envoyer, message = diag[classe]

        # Heure au fuseau horaire du Maroc
        fuseau_maroc = pytz.timezone('Africa/Casablanca')
        heure = datetime.now(fuseau_maroc).strftime("%d/%m/%Y %H:%M")

        print(f"[{heure}] Diagnostic : {emoji} {statut}")

        # --- Logique Anti-Spam ---
        # On n'envoie un email que si l'état a CHANGÉ depuis la dernière exécution
        etat_precedent = "NORMAL"
        if os.path.exists(FICHIER_ETAT):
            with open(FICHIER_ETAT) as f:
                etat_precedent = f.read().strip()

        if statut == etat_precedent:
            envoyer = False  # Même état qu'avant → pas d'email

        # Mise à jour du fichier d'état
        if envoyer:
            with open(FICHIER_ETAT, "w") as f:
                f.write(statut)
        elif statut == "NORMAL" and os.path.exists(FICHIER_ETAT):
            os.remove(FICHIER_ETAT)  # Retour à la normale → on efface l'alerte

    except Exception as e:
        print(f"Erreur calcul/prédiction : {e}")
        return  # Arrêt propre, le diagnostic n'a pas pu être fait

    # ------------------------------------------
    # ZONE EMAIL
    # Zone de risque 4 : SMTP down, mot de passe expiré, réseau
    # Séparée pour ne pas bloquer si le diagnostic a réussi
    # ------------------------------------------
    if envoyer:
        try:
            html = f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;
                        margin:0 auto;border:1px solid #ddd;">

                <div style="background:{couleur};color:white;
                            padding:15px;text-align:center;">
                    <h2 style="margin:0;">{emoji} MAINTENANCE PRÉDICTIVE IRM SIEMENS</h2>
                </div>

                <div style="padding:20px;">
                    <h3>Diagnostic IA — XGBoost V4 (82.52% de précision)</h3>

                    <p><strong>Statut :</strong>
                       <span style="color:{couleur};font-weight:bold;font-size:16px;">
                       {statut}</span>
                    </p>

                    <p><strong>Analyse :</strong> {message}</p>

                    <hr style="border:0;border-top:1px solid #eee;margin:15px 0;">

                    <h4>Données capteurs — {heure} (Heure Maroc)</h4>

                    <table style="width:100%;border-collapse:collapse;">
                      <tr style="background:#f9f9f9;">
                        <td style="padding:8px;border:1px solid #ddd;width:50%;">
                          <strong>Niveau Hélium</strong></td>
                        <td style="padding:8px;border:1px solid #ddd;">
                          {d['He_Level_L']:.1f} L &nbsp;|&nbsp;
                          {d['He_Level_Perc']:.0f}%</td>
                      </tr>
                      <tr>
                        <td style="padding:8px;border:1px solid #ddd;">
                          <strong>Température CHT</strong></td>
                        <td style="padding:8px;border:1px solid #ddd;">
                          {d['CHT_Temp_K']:.2f} K</td>
                      </tr>
                      <tr style="background:#f9f9f9;">
                        <td style="padding:8px;border:1px solid #ddd;">
                          <strong>Pression aimant</strong></td>
                        <td style="padding:8px;border:1px solid #ddd;">
                          {d['Magnet_Pressure_psiA']:.3f} psiA</td>
                      </tr>
                      <tr>
                        <td style="padding:8px;border:1px solid #ddd;">
                          <strong>Température Link</strong></td>
                        <td style="padding:8px;border:1px solid #ddd;">
                          {d['Link_Temp_K']:.2f} K</td>
                      </tr>
                      <tr style="background:#f9f9f9;">
                        <td style="padding:8px;border:1px solid #ddd;">
                          <strong>Température Bore</strong></td>
                        <td style="padding:8px;border:1px solid #ddd;">
                          {d['Bore_Temp_K']:.2f} K</td>
                      </tr>
                      <tr>
                        <td style="padding:8px;border:1px solid #ddd;">
                          <strong>Puissance Heater</strong></td>
                        <td style="padding:8px;border:1px solid #ddd;">
                          {d['Heater_Power_W']:.2f} W</td>
                      </tr>
                    </table>

                    <hr style="border:0;border-top:1px solid #eee;margin:15px 0;">

                    <h4>Indicateurs dynamiques (calculés par l'IA)</h4>

                    <table style="width:100%;border-collapse:collapse;">
                      <tr style="background:#f9f9f9;">
                        <td style="padding:8px;border:1px solid #ddd;">
                          <strong>Vitesse chauffe CHT</strong></td>
                        <td style="padding:8px;border:1px solid #ddd;">
                          {input_ia.iloc[0]['Vitesse_Chauffe_CHT']:.3f} K/point</td>
                      </tr>
                      <tr>
                        <td style="padding:8px;border:1px solid #ddd;">
                          <strong>Vitesse He Level</strong></td>
                        <td style="padding:8px;border:1px solid #ddd;">
                          {input_ia.iloc[0]['Vitesse_He_Level']:.2f} L/point</td>
                      </tr>
                      <tr style="background:#f9f9f9;">
                        <td style="padding:8px;border:1px solid #ddd;">
                          <strong>Vitesse Pression</strong></td>
                        <td style="padding:8px;border:1px solid #ddd;">
                          {input_ia.iloc[0]['Vitesse_Pression']:.4f} psiA/point</td>
                      </tr>
                      <tr>
                        <td style="padding:8px;border:1px solid #ddd;">
                          <strong>Moyenne CHT (10 pts)</strong></td>
                        <td style="padding:8px;border:1px solid #ddd;">
                          {input_ia.iloc[0]['CHT_Moyenne_10']:.2f} K</td>
                      </tr>
                    </table>

                    <p style="color:#888;font-size:11px;text-align:center;
                               margin-top:20px;border-top:1px solid #eee;
                               padding-top:10px;">
                        Généré automatiquement par le Serveur Cloud IA<br>
                        PFE — Système de Maintenance Prédictive IRM Siemens<br>
                        Modèle : XGBoost Classifier V4 — 3 classes (Normal / Dégradation / Critique)
                    </p>
                </div>
            </div>"""

            msg = MIMEMultipart("alternative")
            msg['From']    = EMAIL_SENDER
            msg['To']      = EMAIL_RECEIVER
            msg['Subject'] = f"[ALERTE IA - {statut}] Diagnostic IRM Siemens — {heure}"
            msg.attach(MIMEText(html, "html", "utf-8"))

            with smtplib.SMTP('smtp.gmail.com', 587) as s:
                s.starttls()
                s.login(EMAIL_SENDER, EMAIL_PASSWORD)
                s.send_message(msg)

            print(f"[{heure}] Email '{statut}' envoyé à {EMAIL_RECEIVER}")

        except Exception as e:
            print(f"Erreur envoi email : {e}")
            print("Le diagnostic a quand même été effectué — seul l'email a échoué.")
            # On ne plante pas : le diagnostic est valide même sans email

    else:
        print(f"[{heure}] {emoji} {statut} — état inchangé, pas d'email envoyé.")


# ==========================================
# 7. POINT D'ENTRÉE
# ==========================================
if __name__ == "__main__":
    orchestrateur_ia()
