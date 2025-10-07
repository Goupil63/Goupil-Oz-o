import requests
import json
from bs4 import BeautifulSoup
import os

# --- Configurations ---
# URL de la page Les Demeures de l'Épouvante (2nde Édition)
URL_OKKAZE = "https://www.okkazeo.com/jeux/41095/les-demeures-de-l-epouvante-mansions-of-madness-2eme-edition"
# Nom du fichier pour la mémoire des annonces vues
FILE_SEEN = "seen.json"

# Récupération de l'URL du Webhook Discord depuis les variables d'environnement
# (Doit être configuré en tant que "Secret" dans GitHub Actions pour la sécurité)
WEBHOOK_DISCORD_OKKAZEO = os.environ.get("WEBHOOK_DISCORD_OKKAZEO") 


# --- Fonctions de Gestion de Fichier ---

def load_seen_items(filename):
    """Charge les identifiants d'annonces déjà vues depuis le fichier JSON."""
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except json.JSONDecodeError:
            print(f"Avertissement : Le fichier {filename} est vide ou corrompu. Recommence à zéro.")
            return set()
    return set()

def save_seen_items(filename, items_set):
    """Sauvegarde les identifiants d'annonces actuels dans le fichier JSON."""
    with open(filename, 'w', encoding='utf-8') as f:
        # Convertir le set en liste pour l'écriture en JSON
        json.dump(list(items_set), f, indent=4)


# --- Fonctions de Scraping et d'Alerte ---

def fetch_and_parse(url):
    """Récupère la page et extrait les informations des annonces en ciblant div.box_article."""
    try:
        # Utilisation d'un User-Agent pour se faire passer pour un navigateur
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        response.raise_for_status() # Lève une exception pour les erreurs HTTP
    except requests.exceptions.RequestException as e:
        print(f"Erreur de requête HTTP : {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    announcements = []

    # Cible : la div principale de chaque annonce ('grid-x box_article')
    for element in soup.select('div.box_article'):
        
        # --- 1. ID et Lien ---
        link_tag = element.select_one('a') # Premier lien englobant
        if not link_tag or 'href' not in link_tag.attrs:
             continue 

        item_path = link_tag['href']
        
        # Extrait l'ID numérique (ex: 1307762)
        try:
             item_id = item_path.split('/')[2]
        except (IndexError, AttributeError):
             continue

        # --- 2. Prix ---
        # Le prix est dans la balise span.prix (dans la colonne du milieu ou de droite)
        price_tag = element.select_one('span.prix') 
        price = price_tag.text.strip() if price_tag else "Prix non spécifié"
        
        # --- 3. Vendeur ---
        seller_tag = element.select_one('a[title^="Voir le profil"]')
        seller_name = seller_tag.text.strip() if seller_tag else "Vendeur non spécifié"
        
        # --- 4. Lieu ---
        # On essaie de cibler le texte après l'icône de localisation
        location = "Lieu non spécifié"
        location_element = element.find('i', class_='fa-map-marker-alt')
        if location_element:
             # Le texte du lieu est le texte de la div parente
             parent_div = location_element.parent
             # Simplification de l'extraction : on prend le texte et on le nettoie
             text_content = parent_div.get_text(strip=True, separator=' ')
             # Le lieu est souvent juste avant <br> ou après le drapeau
             # Cette approche nécessite souvent des ajustements manuels mais c'est un bon début:
             try:
                 location = text_content.split(')')[1].split('<br>')[0].strip()
             except IndexError:
                 # Si l'extraction échoue, on prend le texte brut
                 location = text_content 

        
        announcements.append({
            'id': item_id,
            'title': f"Annonce par {seller_name} à {location}",
            'price': price,
            'url': f"https://www.okkazeo.com{item_path}" 
        })
    
    return announcements

def send_discord_alert(item):
    """Envoie un message formaté via le Webhook Discord."""
    if not WEBHOOK_DISCORD_OKKAZEO:
        print("Erreur : WEBHOOK_DISCORD_OKKAZEO n'est pas configuré. Impossible d'envoyer l'alerte.")
        return

    print(f"Alerte : Nouvelle annonce détectée : {item['title']} - {item['price']}")

    data = {
        # Ping spécifique pour attirer l'attention
        "content": "@here 🚨 Nouvelle Annonce Les Demeures de l'Épouvante !", 
        "embeds": [
            {
                "title": item['title'], # Ex: Annonce par Ronywan à Paris (75015)
                "url": item['url'],
                "description": f"**Prix :** {item['price']}\n[Cliquez pour voir l'annonce]({item['url']})",
                "color": 16752384 # Couleur orange pour l'alerte
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
        # S'il y a une erreur de scraping, on ne touche pas à seen.json
        return

    new_ids = set()
    new_announcements = []

    # 3. Identifier les nouvelles annonces
    for item in current_announcements:
        # Ajoute tous les IDs actuels à new_ids pour la sauvegarde
        new_ids.add(item['id'])
        
        # Vérifie la nouveauté
        if item['id'] not in seen_ids:
            new_announcements.append(item)

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
