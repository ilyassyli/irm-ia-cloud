import requests
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

EMAIL_SENDER    = "ilyassayli033@gmail.com"
EMAIL_PASSWORD  = "yxwcmybrdliatcpx"
EMAIL_RECEIVER  = "ilyassnbihi8@gmail.com"

def envoyer_rapport_quotidien():
    # --- HEURE MAROC ---
    fuseau_maroc = pytz.timezone('Africa/Casablanca')
    heure_actuelle = datetime.now(fuseau_maroc).strftime("%d/%m/%Y %H:%M")

    # ==========================================
    # 2. RÉCUPÉRATION DES DONNÉES (1 SEUL POINT)
    # ==========================================
    try:
        url = (f"https://api.thingspeak.com/channels/{TS_CHANNEL_ID}"
               f"/feeds.json?results=1&api_key={TS_READ_API_KEY}")
        reponse = requests.get(url, timeout=10).json()
        data = reponse['feeds'][0] # On prend la dernière donnée
    except Exception as e:
        print(f"Erreur de récupération ThingSpeak : {e}")
        return

    # Gestion des valeurs manquantes (si le capteur n'a rien envoyé)
    def val(field):
        return data.get(field) if data.get(field) is not None else "N/A"

    # ==========================================
    # 3. CONSTRUCTION DE L'EMAIL
    # ==========================================
    sujet = f" [RAPPORT QUOTIDIEN] État IRM Siemens — {heure_actuelle}"
    
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;border:1px solid #ddd;">
        <div style="background:#0056b3;color:white;padding:15px;text-align:center;">
            <h2 style="margin:0;"> RAPPORT DE SURVEILLANCE QUOTIDIEN</h2>
        </div>
        <div style="padding:20px;">
            <p>Bonjour,</p>
            <p>Voici le relevé d'état du système IRM à <strong>{heure_actuelle}</strong>.</p>
            
            <hr style="border:0;border-top:1px solid #eee;margin:15px 0;">
            
            <table style="width:100%;border-collapse:collapse;">
              <tr style="background:#f9f9f9;">
                <td style="padding:10px;border:1px solid #ddd;"><strong>Niveau Hélium (L)</strong></td>
                <td style="padding:10px;border:1px solid #ddd;">{val('field1')} L</td>
              </tr>
              <tr>
                <td style="padding:10px;border:1px solid #ddd;"><strong>Hélium (%)</strong></td>
                <td style="padding:10px;border:1px solid #ddd;">{val('field2')} %</td>
              </tr>
              <tr style="background:#f9f9f9;">
                <td style="padding:10px;border:1px solid #ddd;"><strong>Température CHT</strong></td>
                <td style="padding:10px;border:1px solid #ddd;">{val('field3')} K</td>
              </tr>
              <tr>
                <td style="padding:10px;border:1px solid #ddd;"><strong>Température Link Shield</strong></td>
                <td style="padding:10px;border:1px solid #ddd;">{val('field4')} K</td>
              </tr>
              <tr style="background:#f9f9f9;">
                <td style="padding:10px;border:1px solid #ddd;"><strong>Température Bore Shield</strong></td>
                <td style="padding:10px;border:1px solid #ddd;">{val('field5')} K</td>
              </tr>
              <tr>
                <td style="padding:10px;border:1px solid #ddd;"><strong>Pression Aimant</strong></td>
                <td style="padding:10px;border:1px solid #ddd;">{val('field6')} psiA</td>
              </tr>
              <tr style="background:#f9f9f9;">
                <td style="padding:10px;border:1px solid #ddd;"><strong>Puissance Heater</strong></td>
                <td style="padding:10px;border:1px solid #ddd;">{val('field7')} W</td>
              </tr>
            </table>

            <p style="color:#888;font-size:11px;text-align:center;margin-top:20px;">
                Ceci est un rapport automatique généré par le Cloud MLOps Siemens Healthineers.<br>
                Service Ingénierie Biomédicale.
            </p>
        </div>
    </div>
    """

    # ==========================================
    # 4. ENVOI
    # ==========================================
    try:
        msg = MIMEMultipart("alternative")
        msg['From']    = EMAIL_SENDER
        msg['To']      = EMAIL_RECEIVER
        msg['Subject'] = sujet
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls()
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.send_message(msg)
        print(f"[{heure_actuelle}] Rapport quotidien envoyé avec succès !")
    except Exception as e:
        print(f"[{heure_actuelle}] Erreur d'envoi du rapport : {e}")

if __name__ == "__main__":
    envoyer_rapport_quotidien()
