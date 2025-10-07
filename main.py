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
        response.raise_for_status() # Lève une exception pour les erreurs HTTP
    except requests.exceptions.RequestException as e:
        print(f"Erreur de requête HTTP : {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    announcements = []

    # Le sélecteur clé ici est la classe CSS qui englobe chaque annonce.
    # Dans l'exemple d'Okkazeo, les annonces sont souvent dans des divs avec des classes spécifiques.
    # ATTENTION : Ce sélecteur ('div.divannonce') est un exemple et DOIT être ajusté 
    # en fonction de la structure HTML actuelle de la page.
    for element in soup.select('div.divannonce'):
        # Tente d'extraire un ID unique pour l'annonce. C'est CRUCIAL.
        # Un bon ID pourrait être l'attribut 'id' du div ou un lien vers l'annonce.
        # Ici, on utilise l'URL complète comme ID pour simplifier, 
        # mais idéalement, on chercherait l'ID numérique interne de l'annonce.
        link_tag = element.find('a', href=True)
        if not link_tag:
             continue # Saute si pas de lien trouvé

        # Construction des données de l'annonce
        item_id = link_tag['href'] # Utilisons le lien comme identifiant unique
        title = element.find('h4').text.strip() if element.find('h4') else "Titre non trouvé"
        
        # Exemple d'extraction du prix (à ajuster)
        price_tag = element.find('div', class_='price')
        price = price_tag.text.strip() if price_tag else "Prix non spécifié"

        announcements.append({
            'id': item_id,
            'title': title,
            'price': price,
            'url': f"https://www.okkazeo.com{item_id}" # Reconstituer l'URL complète
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
