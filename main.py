import requests
import json
from bs4 import BeautifulSoup
import os

# --- Configurations ---
URL_OKKAZE = "https://www.okkazeo.com/jeux/41095/les-demeures-de-l-epouvante-mansions-of-madness-2eme-edition"
FILE_SEEN = "seen.json"

# Assurez-vous d'avoir défini ceci comme une variable d'environnement
# dans votre workflow GitHub Actions pour des raisons de sécurité.
# Dans un environnement de test local, vous pouvez le décommenter pour tester :
# WEBHOOK_DISCORD_OKKAZEO = "VOTRE_URL_DE_WEBHOOK_DISCORD" 
# Pour l'usage avec GitHub Actions :
WEBHOOK_DISCORD_OKKAZEO = os.environ.get("WEBHOOK_DISCORD_OKKAZEO") 


# --- Fonctions de Gestion de Fichier ---

def load_seen_items(filename):
    """Charge les identifiants d'annonces déjà vues depuis le fichier JSON."""
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    return set()

def save_seen_items(filename, items_set):
    """Sauvegarde les identifiants d'annonces actuels dans le fichier JSON."""
    with open(filename, 'w', encoding='utf-8') as f:
        # Convertir le set en liste pour l'écriture en JSON
        json.dump(list(items_set), f, indent=4)


# --- Fonctions de Scraping et d'Alerte ---

def fetch_and_parse(url):
    """Récupère la page et extrait les informations des annonces."""
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Erreur de requête HTTP : {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    announcements = []

    # Le sélecteur cible désormais la DIV principale de chaque annonce
    # qui porte la classe 'grid-x box_article'.
    for element in soup.select('div.box_article'):
        
        # --- 1. Extraction de l'ID et du lien (CRUCIAL) ---
        # Le lien <a> englobant est le premier enfant du div.box_article
        link_tag = element.select_one('a')
        if not link_tag or 'href' not in link_tag.attrs:
             continue 

        item_path = link_tag['href']  # Ex: /annonces/1307762/...
        
        # On extrait l'ID numérique pour le seen.json
        try:
             # Cible le numéro au milieu de l'URL (ex: 1307762)
             item_id = item_path.split('/')[2]
        except IndexError:
             # Si le format de l'URL est inattendu, on saute
             continue

        # --- 2. Extraction du Prix ---
        # Le prix est dans la balise span.prix (dans la div 'show-for-medium')
        # On vérifie dans la div 'show-for-medium' car elle est la plus fiable
        price_tag_medium = element.select_one('.show-for-medium span.prix')
        price = price_tag_medium.text.strip() if price_tag_medium else "Prix non spécifié"
        
        # --- 3. Extraction du Vendeur ---
        # On cherche le lien dont le titre commence par "Voir le profil"
        seller_tag = element.select_one('a[title^="Voir le profil"]')
        seller_name = seller_tag.text.strip() if seller_tag else "Vendeur non spécifié"
        
        # --- 4. Extraction du Lieu ---
        # On cherche l'élément qui contient l'icône de localisation
        location_element = element.find('i', class_='fa-map-marker-alt')
        location = "Lieu non spécifié"
        if location_element:
             # On remonte au parent (div) et on cherche la balise texte après l'image du drapeau
             parent_div = location_element.parent
             # Le texte du lieu est juste après le drapeau (ou avant la balise <br>)
             if parent_div.text:
                 # Extraction du texte du lieu (ex: Paris (75015))
                 # On prend le texte de la div, puis on retire le texte du vendeur/évaluation
                 location = parent_div.text.split(')')[-2].split('(')[0].strip() + parent_div.text.split(')')[-2].split('(')[1].strip()
                 # Une méthode plus simple : trouver le nœud de texte après le drapeau
                 # location_text_node = parent_div.find('img', class_='drapeau').next_sibling
                 # location = location_text_node.strip() if location_text_node else "Lieu non spécifié"

        
        announcements.append({
            'id': item_id,
            'title': f"Annonce par {seller_name} ({location})",
            'price': price,
            'url': f"https://www.okkazeo.com{item_path}" 
        })
    
    return announcements

def send_discord_alert(item):
    """Envoie un message formaté via le Webhook Discord."""
    if not WEBHOOK_DISCORD_OKKAZEO:
        print("Erreur : WEBHOOK_DISCORD_OKKAZEO n'est pas configuré.")
        return

    print(f"Alerte : Nouvelle annonce détectée : {item['title']} - {item['price']}")

    data = {
        "content": "@here Nouvelle Annonce Okkazeo !",
        "embeds": [
            {
                "title": item['title'],
                "url": item['url'],
                "description": f"**Prix :** {item['price']}",
                "color": 3447003 # Une couleur bleue
            }
        ]
    }

    try:
        response = requests.post(WEBHOOK_DISCORD_OKKAZEO, json=data)
        response.raise_for_status()
        print("Alerte Discord envoyée avec succès.")
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de l'envoi à Discord : {e}")


# --- Fonction Principale ---

def main():
    """Fonction principale pour exécuter la surveillance."""
    print("--- Démarrage de la surveillance Okkazeo ---")
    
    # 1. Charger les identifiants déjà vus
    seen_ids = load_seen_items(FILE_SEEN)
    print(f"Annonces déjà vues : {len(seen_ids)}")
    
    # 2. Scraper les annonces actuelles
    current_announcements = fetch_and_parse(URL_OKKAZE)
    
    if not current_announcements:
        print("Aucune annonce trouvée ou erreur de scraping.")
        return

    new_ids = set()
    new_announcements = []

    # 3. Identifier les nouvelles annonces
    for item in current_announcements:
        if item['id'] not in seen_ids:
            new_announcements.append(item)
        new_ids.add(item['id'])

    # 4. Traiter et alerter les nouvelles annonces
    if new_announcements:
        print(f"!!! {len(new_announcements)} NOUVELLE(S) ANNONCE(S) DÉTECTÉE(S) !!!")
        for item in new_announcements:
            send_discord_alert(item)
    else:
        print("Aucune nouvelle annonce détectée.")

    # 5. Mettre à jour le fichier de mémoire
    save_seen_items(FILE_SEEN, new_ids)
    print("Fichier de mémoire mis à jour.")
    print("--- Surveillance terminée ---")

if __name__ == "__main__":
    main()
