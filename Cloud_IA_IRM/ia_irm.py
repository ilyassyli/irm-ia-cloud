import requests
import pandas as pd
import xgboost as xgb
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ==========================================
# 1. CONFIGURATION
# ==========================================
TS_CHANNEL_ID = '3320495' # MET TON VRAI CHANNEL ID ICI
TS_READ_API_KEY = 'FCMJY57R7S9HY7W4' # MET TA VRAIE CLE ICI

MODELE_PATH = "modele_siemens_v1.json"
FICHIER_ETAT = "etat_alerte.txt" # Fichier pour l'anti-spam

EMAIL_SENDER = "ilyassayli033@gmail.com"
EMAIL_PASSWORD = "yxwcmybrdliatcpx"
EMAIL_RECEIVER = "ilyassnbihi8@gmail.com"

# ==========================================
# 2. CHARGEMENT DU MODÈLE
# ==========================================
try:
    modele = xgb.XGBRegressor()
    modele.load_model(MODELE_PATH)
except Exception as e:
    print(f"Erreur chargement modèle: {e}")
    exit()

# ==========================================
# 3. RÉCUPÉRATION DES DONNÉES THINGSPEAK
# ==========================================
try:
    url = f"https://api.thingspeak.com/channels/{TS_CHANNEL_ID}/feeds.json?results=10&api_key={TS_READ_API_KEY}"
    reponse = requests.get(url, timeout=10).json()
    df_brut = pd.DataFrame(reponse['feeds'])
except Exception as e:
    print(f"Erreur réseau ThingSpeak: {e}")
    exit()

# Renomme les champs (ADAPTE LES fieldX SI NECESSAIRE)
# On utilise errors='coerce' pour transformer les valeurs vides en NaN
df_capteurs = pd.DataFrame({
    'He_Level_L': pd.to_numeric(df_brut['field1'], errors='coerce'),
    'CHT_Temp_K': pd.to_numeric(df_brut['field2'], errors='coerce'),
    'Link_Temp_K': pd.to_numeric(df_brut['field3'], errors='coerce'),
    'Bore_Temp_K': pd.to_numeric(df_brut['field4'], errors='coerce'),
    'Magnet_Pressure_psiA': pd.to_numeric(df_brut['field5'], errors='coerce')
})

# ==========================================
# 4. FEATURE ENGINEERING (Mémoire IA)
# ==========================================
try:
    donnees_ia = pd.DataFrame([{
        'He_Level_L': df_capteurs.iloc[-1]['He_Level_L'],
        'CHT_Temp_K': df_capteurs.iloc[-1]['CHT_Temp_K'],
        'Link_Temp_K': df_capteurs.iloc[-1]['Link_Temp_K'],
        'Bore_Temp_K': df_capteurs.iloc[-1]['Bore_Temp_K'],
        'Magnet_Pressure_psiA': df_capteurs.iloc[-1]['Magnet_Pressure_psiA'],
        'CHT_Temp_Lag1': df_capteurs.iloc[-2]['CHT_Temp_K'],
        'CHT_Temp_Lag5': df_capteurs.iloc[-6]['CHT_Temp_K'],
        'Pressure_Lag1': df_capteurs.iloc[-2]['Magnet_Pressure_psiA'],
        'Vitesse_Chauffe_CHT': df_capteurs.iloc[-1]['CHT_Temp_K'] - df_capteurs.iloc[-2]['CHT_Temp_K'],
        'Vitesse_Pression': df_capteurs.iloc[-1]['Magnet_Pressure_psiA'] - df_capteurs.iloc[-2]['Magnet_Pressure_psiA'],
        'CHT_Moyenne_10': df_capteurs['CHT_Temp_K'].mean(),
        'He_Level_Moyenne_10': df_capteurs['He_Level_L'].mean()
    }])
    # Remplacer les NaN potentiels par 0 pour ne pas faire planter XGBoost
    donnees_ia = donnees_ia.fillna(0)
except Exception as e:
    print(f"Erreur Feature Engineering: {e}")
    exit()

# ==========================================
# 5. PRÉDICTION ET VERDICT
# ==========================================
prediction_jours = float(modele.predict(donnees_ia)[0])

if prediction_jours >= 1.2:
    statut = "NORMAL"
    couleur = "#28a745" # Vert
    emoji_statut = "🟢"
    message_alerte = "L'aimant est sain. Aucune anomalie critique détectée par l'IA."
    envoyer_email_flag = False
elif prediction_jours >= 0.5:
    statut = "ATTENTION"
    couleur = "#ffc107" # Orange
    emoji_statut = "🟠"
    message_alerte = "Dérive thermique anormale détectée par l'IA. Surveillance renforcée requise."
    envoyer_email_flag = True
else:
    statut = "CRITIQUE"
    couleur = "#dc3545" # Rouge
    emoji_statut = "🔴"
    message_alerte = "Risque de Quench imminent détecté par l'IA ! Intervention immédiate requise."
    envoyer_email_flag = True
# ==========================================
# 6. LOGIQUE ANTI-SPAM INTELLIGENTE
# ==========================================
etat_precedent = "NORMAL"
if os.path.exists(FICHIER_ETAT):
    with open(FICHIER_ETAT, "r") as f:
        etat_precedent = f.read().strip()

# Si l'état n'a pas changé (et que ce n'est pas critique), on n'envoie pas d'email pour ne pas spammer
if statut == etat_precedent:
    envoyer_email_flag = False

# Si l'état change (ex: Normal vers Attention), on met à jour le fichier et on autorise l'envoi
if envoyer_email_flag:
    with open(FICHIER_ETAT, "w") as f:
        f.write(statut)
elif statut == "NORMAL":
    # Si on revient à la normal, on efface le fichier d'alerte
    if os.path.exists(FICHIER_ETAT):
        os.remove(FICHIER_ETAT)

# ==========================================
# 7. ENVOI DE L'EMAIL FORMATÉ PROFESSIONNEL
# ==========================================
if envoyer_email_flag:
    heure_actuelle = datetime.now().strftime("%d/%m/%Y %H:%M")
    sujet = f"[ALERTE IA - {statut}] Diagnostic IRM Siemens"
    
    # Création d'un email HTML très propre
    html_content = f"""
    <div style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; border: 1px solid #ddd; padding: 20px;">
        <div style="background-color: {couleur}; color: white; padding: 15px; text-align: center;">
            <h2 style="margin: 0;">{emoji_statut} SYSTÈME DE MAINTENANCE PRÉDICTIVE</h2>
        </div>
        <div style="padding: 20px;">
            <h3>Diagnostic de l'Intelligence Artificielle (XGBoost)</h3>
            <p><strong>Statut :</strong> <span style="color: {couleur}; font-weight: bold;">{statut}</span></p>
            <p><strong>Analyse :</strong> {message_alerte}</p>
            
            <hr style="border: 0; border-top: 1px solid #eee;">
            <h4>Données Capteurs brutes ({heure_actuelle})</h4>
            <table style="width: 100%; border-collapse: collapse;">
                <tr style="background-color: #f9f9f9;"><td style="padding: 8px; border: 1px solid #ddd;"><strong>Hélium</strong></td><td style="padding: 8px; border: 1px solid #ddd;">{donnees_ia.iloc[0]['He_Level_L']} L</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>Température CHT</strong></td><td style="padding: 8px; border: 1px solid #ddd;">{donnees_ia.iloc[0]['CHT_Temp_K']} K</td></tr>
                <tr style="background-color: #f9f9f9;"><td style="padding: 8px; border: 1px solid #ddd;"><strong>Pression</strong></td><td style="padding: 8px; border: 1px solid #ddd;">{donnees_ia.iloc[0]['Magnet_Pressure_psiA']} psiA</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>Vitesse Chauffe</strong></td><td style="padding: 8px; border: 1px solid #ddd;">{donnees_ia.iloc[0]['Vitesse_Chauffe_CHT']:.2f} K/min</td></tr>
            </table>
            <p style="color: #888; font-size: 12px; text-align: center; margin-top: 20px;">Email généré automatiquement par le Serveur Cloud IA - PFE IRM Monitoring</p>
        </div>
    </div>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER
        msg['Subject'] = sujet
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        serveur = smtplib.SMTP('smtp.gmail.com', 587)
        serveur.starttls()
        serveur.login(EMAIL_SENDER, EMAIL_PASSWORD)
        serveur.send_message(msg)
        serveur.quit()
        print(f"[{heure_actuelle}]  Email {statut} envoyé !")
    except Exception as e:
        print(f"[{heure_actuelle}]  Erreur envoi email: {e}")
else:
    print(f"[{heure_actuelle}]  Statut {statut} (Pas de changement, pas d'email envoyé).")
    
