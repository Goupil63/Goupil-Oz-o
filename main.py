import requests
import json
from bs4 import BeautifulSoup
import os
import logging
import time
import random


# ----------------------
# 1. CONFIGURATION
# ----------------------

# URL de la page Les Demeures de l'Épouvante (2nde Édition)
URL_OKKAZE = "https://www.okkazeo.com/jeux/41095/les-demeures-de-l-epouvante-mansions-of-madness-2eme-edition"

# Nom du fichier pour la mémoire des annonces vues
SEEN_FILE = "seen.json"

# Définition du fichier contenant les listes d'URLs
URLS_FILE = "urls.txt" 

# Récupération de l'URL du Webhook Discord depuis les variables d'environnement
# (Doit être configuré en tant que "Secret" dans GitHub Actions pour la sécurité)
DISCORD_WEBHOOK_OKKAZEO = os.environ.get("DISCORD_WEBHOOK_OKKAZEO") 

RUN_DURATION = 1 * 3600 + 50 * 60  # 1 * 3600 + 50 * 60 Durée du run en secondes (1h50)


# ----------------------
# 2. LOGGING
# ----------------------
# Configuration de base pour l'affichage des logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("OkkazeoScraper") 


# ----------------------
# 3. SESSION HTTP
# ----------------------
# Utilisation d'une session pour réutiliser la connexion et les headers
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    # Mettre un Referer plus neutre/générique
    "Referer": "https://www.google.com/", 
    "Connection": "keep-alive",
    "DNT": "1", 
    "Upgrade-Insecure-Requests": "1",
})


# ----------------------
# 4. MEMOIRE PERSISTANTE
# ----------------------
def load_seen_items(filename):
    """Charge les identifiants d'annonces déjà vues depuis le fichier JSON."""
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except json.JSONDecodeError:
            logger.warning(f"Le fichier {filename} est vide ou corrompu. Recommence à zéro.")
            return set()
    return set()

def save_seen_items(filename, items_set):
    """Sauvegarde les identifiants d'annonces actuels dans le fichier JSON."""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(list(items_set), f, indent=4)


# ----------------------
# 4.bis LECTURE URL
# ----------------------

def read_urls(filename):
    """Lit une liste d'URLs depuis un fichier."""
    urls = []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                url = line.strip()
                # Ignore les lignes vides ou de commentaires
                if url and not url.startswith('#'):
                    urls.append(url)
        # Ajout d'un log pour confirmer la lecture
        logger.info(f"Fichier URLs lu : {len(urls)} URLs trouvées.")
    except FileNotFoundError:
        logger.error(f"Le fichier {filename} est introuvable. Veuillez le créer à la racine du dépôt.")
    return urls

# ----------------------
# 5. DISCORD
# ----------------------


def send_to_discord(title, price, link, seller_location, img_url=""):
    if not title or not link:
        logger.warning("Titre ou lien vide, notification Discord ignorée")
        return

    embed = {
        "title": f"{title} - {price}",
        "url": link,
        "description": seller_location,
        "color": 3447003
    }

    if img_url:
        embed["image"] = {"url": img_url}

    data = {"embeds": [embed]}

    try:
        resp = session.post(DISCORD_WEBHOOK_OKKAZEO, json=data, timeout=10)
        if resp.status_code // 100 != 2:
            logger.warning(f"Discord Webhook a renvoyé {resp.status_code} : {resp.text}")
        else:
            logger.info(f"✅ Notification envoyée à Discord : {title}")
    except Exception as e:
        logger.error(f"Erreur en envoyant à Discord : {e}")




# 6. SCRAPING
# --- Fonctions de Scraping et d'Alerte ---

def fetch_and_parse(url):
    """Récupère la page et extrait les informations des annonces en ciblant div.box_article."""
    try:
        response = session.get(url)
        response.raise_for_status() 
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur de requête HTTP : {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    announcements = []

    for element in soup.select('div.box_article'):
        
        # 1. ID et Lien
        link_tag = element.select_one('a')
        if not link_tag or 'href' not in link_tag.attrs:
             continue 

        item_path = link_tag['href']
        try:
             item_id = item_path.split('/')[2]
        except (IndexError, AttributeError):
             continue
        
        full_url = f"https://www.okkazeo.com{item_path}"

        # 2. Prix
        price_tag = element.select_one('span.prix') 
        price = price_tag.text.strip() if price_tag else "Prix non spécifié"
        
        # 3. Vendeur et Lieu
        seller_tag = element.select_one('a[title^="Voir le profil"]')
        seller_name = seller_tag.text.strip() if seller_tag else "Vendeur non spécifié"
        
        location_element = element.find('i', class_='fa-map-marker-alt')
        location = "Lieu non spécifié"
        if location_element:
             # On cherche le nœud de texte après le drapeau
             drapeau = element.find('img', class_='drapeau')
             if drapeau and drapeau.next_sibling:
                 # Le lieu est souvent le nœud de texte suivant, nettoyé
                 location = drapeau.next_sibling.strip().split('<br>')[0].strip()

        seller_location = f"{seller_name} ({location})"

        # 5. Image (optionnel)
        img_tag = element.select_one('img.mts.mbs')
        img_src = img_tag['src'] if img_tag else ""
        if img_src and not img_src.startswith('http'):
            img_src = f"https://www.okkazeo.com{img_src}"
        
        announcements.append({
            'id': item_id,
            'title': f"Vente Les Demeures de l'Épouvante", 
            'price': price,
            'url': full_url,
            'seller_location': seller_location, # Nouvelle clé
            'img_url': img_src
        })
    
    return announcements



# ----------------------
# 7. LOGIQUE DE SURVEILLANCE
# ----------------------
# ----------------------
# 7. LOGIQUE DE SURVEILLANCE (appelée par la boucle)
# ----------------------
def check_okkazeo():
    """Fonction pour exécuter une seule passe complète de surveillance multi-URL."""
    
    # 1. Vérification du Webhook
    if not DISCORD_WEBHOOK_OKKAZEO:
        logger.error("Arrêt : Le Secret DISCORD_WEBHOOK_OKKAZEO n'est pas chargé (valeur vide).")
        return

    logger.info("Webhook Discord chargé avec succès.")
    
    # 2. Charger les identifiants déjà vus
    seen_ids = load_seen_items(SEEN_FILE)
    logger.info(f"Annonces déjà vues : {len(seen_ids)}")
    
    # 3. Lire les URLs à surveiller
    target_urls = read_urls(URLS_FILE)
    if not target_urls:
        logger.warning("Aucune URL trouvée dans le fichier urls.txt. Arrêt.")
        return

    # Nouvelle liste d'IDs vus après cette exécution
    new_ids = set()
    total_new_announcements = 0

    # 4. ITÉRER SUR TOUTES LES URLS
    for url in target_urls:
        logger.info(f"Scraping de l'URL : {url}")
        
        current_announcements = fetch_and_parse(url)
        
        if not current_announcements:
            logger.warning(f"Aucune annonce trouvée pour {url} ou erreur de scraping.")
            continue

        # 5. Identifier les nouvelles annonces pour cette URL
        for item in current_announcements:
            # On ajoute toujours l'ID au set des annonces vues pour cette passe
            new_ids.add(item['id']) 
            
            if item['id'] not in seen_ids:
                total_new_announcements += 1
                
                # Envoi immédiat de l'alerte
                send_to_discord(
                    item['title'], 
                    item['price'], 
                    item['url'], 
                    item['seller_location'],
                    item['img_url']
                )

    # 6. Résultat global et mise à jour de la mémoire
    if total_new_announcements > 0:
        logger.info(f"!!! TOTAL : {total_new_announcements} NOUVELLE(S) ANNONCE(S) ENVOYÉE(S) !!!")
    else:
        logger.info("Aucune nouvelle annonce détectée sur toutes les URL.")

    # 7. Mettre à jour le fichier de mémoire
    # NOTE : La sauvegarde doit se faire avec les IDs que nous avons vus dans ce run (new_ids)
    save_seen_items(SEEN_FILE, new_ids)
    logger.info("Fichier de mémoire mis à jour.")
    logger.info("--- Passe de surveillance terminée ---")



# ----------------------
# 8. BOUCLE BOT AVEC DUREE LIMITEE
# ----------------------
def bot_loop():
# ... (le code de bot_loop que vous avez est correct) ...
    logger.info(f"⏰ Démarrage de la boucle pour {RUN_DURATION / 3600:.2f} heures.")
    
    end_time = time.time() + RUN_DURATION
    
    while time.time() < end_time:
        logger.info("▶️ Nouvelle analyse...")
        
        # L'appel au scraping unique
        check_okkazeo() # L'appel est maintenant propre et contient toute la logique
        
        time_remaining = end_time - time.time()
        if time_remaining <= 0:
            break
            
        # Sleep aléatoire mais ne dépasse pas la fin du run
        delay = random.uniform(180, 360)  # 3 à 6 minutes
        sleep_time = min(delay, time_remaining)
        
        logger.info(f"🔍 Prochaine analyse dans {int(sleep_time)} secondes")
        time.sleep(sleep_time)

    logger.info("🏁 Fin du run complet.")


if __name__ == "__main__":
    # Point d'entrée unique et correct
    bot_loop()


