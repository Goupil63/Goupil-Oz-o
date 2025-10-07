import requests
import json
from bs4 import BeautifulSoup
import os
import logging


# ----------------------
# 1. CONFIGURATION
# ----------------------

# URL de la page Les Demeures de l'Épouvante (2nde Édition)
URL_OKKAZE = "https://www.okkazeo.com/jeux/41095/les-demeures-de-l-epouvante-mansions-of-madness-2eme-edition"

# Nom du fichier pour la mémoire des annonces vues
SEEN_FILE = "seen.json"

# Récupération de l'URL du Webhook Discord depuis les variables d'environnement
# (Doit être configuré en tant que "Secret" dans GitHub Actions pour la sécurité)
DISCORD_WEBHOOK_OKKAZEO = os.environ.get("DISCORD_WEBHOOK_OKKAZEO") 


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
# 7. FONCTION PRINCIPALE
# ----------------------

def main():
    """Fonction principale pour exécuter la surveillance."""
    logger.info("--- Démarrage de la surveillance Okkazeo ---")

    # Nouvelle vérification pour debug
    if not DISCORD_WEBHOOK_OKKAZEO:
        # Ceci sera imprimé si la variable est vide
        logger.error("Arrêt : Le Secret DISCORD_WEBHOOK_OKKAZEO n'est pas chargé (valeur vide).")
        return

    # Si nous arrivons ici, la variable a été lue.
    logger.info("Webhook Discord chargé avec succès.")
    
    # 1. Charger les identifiants déjà vus
    seen_ids = load_seen_items(SEEN_FILE)
    logger.info(f"Annonces déjà vues : {len(seen_ids)}")

    
    # 2. Lire les URLs à surveiller
    target_urls = read_urls(URLS_FILE)
    if not target_urls:
        logger.warning("Aucune URL trouvée dans le fichier urls.txt. Arrêt.")
        return

    # Nouvelle liste d'IDs vus après cette exécution
    new_ids = set()
    total_new_announcements = 0

    # 3. ITÉRER SUR TOUTES LES URLS
    for url in target_urls:
        logger.info(f"Scraping de l'URL : {url}")
        
        current_announcements = fetch_and_parse(url)
        
        if not current_announcements:
            logger.warning(f"Aucune annonce trouvée pour {url} ou erreur de scraping.")
            continue

        # 4. Identifier les nouvelles annonces pour cette URL
        for item in current_announcements:
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

    # 5. Résultat global et mise à jour de la mémoire
    if total_new_announcements > 0:
        logger.info(f"!!! TOTAL : {total_new_announcements} NOUVELLE(S) ANNONCE(S) ENVOYÉE(S) !!!")
    else:
        logger.info("Aucune nouvelle annonce détectée sur toutes les URL.")

    # 6. Mettre à jour le fichier de mémoire
    save_seen_items(SEEN_FILE, new_ids)
    logger.info("Fichier de mémoire mis à jour.")
    logger.info("--- Surveillance terminée ---")

if __name__ == "__main__":
    main()


