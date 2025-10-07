import requests
from bs4 import BeautifulSoup
import json
import time
import os

CONFIG_FILE = "config.json"
SEEN_FILE = "seen.json"

# --- Charger la configuration ---
with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

OKKAZEO_URL = config["okkazeo_url"]
DISCORD_WEBHOOK = config["discord_webhook"]
POLL_INTERVAL = config.get("poll_interval", 300)

# --- Charger les annonces déjà vues ---
if os.path.exists(SEEN_FILE):
    with open(SEEN_FILE, "r") as f:
        seen_annonces = set(json.load(f))
else:
    seen_annonces = set()


def fetch_annonces():
    """Récupère les annonces présentes sur la page Okkazeo"""
    resp = requests.get(OKKAZEO_URL, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    annonces = []
    # Chaque annonce est dans un élément <a> avec href contenant "/annonces/"
    for a in soup.select("a[href*='/annonces/']"):
        title = a.get_text(strip=True)
        href = a["href"]
        full_url = requests.compat.urljoin(resp.url, href)
        if "annonces" in href:
            annonces.append((full_url, title))
    return annonces


def send_discord_alert(url, title):
    """Envoie une alerte sur Discord"""
    data = {
        "content": f"🆕 Nouvelle annonce détectée sur Okkazeo !\n**{title}**\n🔗 {url}"
    }
    headers = {"Content-Type": "application/json"}
    resp = requests.post(DISCORD_WEBHOOK, headers=headers, data=json.dumps(data))
    if resp.status_code >= 400:
        print("❌ Erreur en envoyant le webhook :", resp.text)


def save_seen():
    """Sauvegarde les annonces déjà vues"""
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen_annonces), f)


def main():
    print("🔍 Surveillance démarrée sur :", OKKAZEO_URL)
    print("⏱ Intervalle :", POLL_INTERVAL, "secondes")

    while True:
        try:
            annonces = fetch_annonces()
            new_found = False

            for url, title in annonces:
                if url not in seen_annonces:
                    print("✅ Nouvelle annonce :", title)
                    send_discord_alert(url, title)
                    seen_annonces.add(url)
                    new_found = True

            if new_found:
                save_seen()

        except Exception as e:
            print("⚠️ Erreur :", e)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
