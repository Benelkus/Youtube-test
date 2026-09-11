# YouTube Niche Finder

Outil de détection de niches YouTube à fort potentiel. Il cherche les **outliers** :
des vidéos qui explosent alors que la chaîne qui les publie est encore petite —
le signal le plus fiable qu'une niche a de la demande non servie.

## Les 3 critères

| Critère | Valeur par défaut | Pourquoi |
|---|---|---|
| Vues minimum | **100 000** | preuve qu'il y a une audience réelle |
| Âge maximum | **21 jours** | la tendance est encore vivante, réplicable maintenant |
| Abonnés de la chaîne | **< 20 000** | la vidéo a percé grâce au sujet, pas grâce à la notoriété |

Les trois sont modifiables dans l'interface.

## Utilisation

1. Ouvre `niche-finder.html` **depuis ton ordinateur** (double-clic). Aucune installation,
   aucun serveur : c'est un seul fichier HTML.
2. Colle ta clé API YouTube Data v3 en haut de la page (onglet **Aide** pour l'obtenir,
   gratuit, 3 minutes).
3. Coche quelques sous-niches (ou clique sur *10 au hasard*) et lance la recherche.

La clé et les résultats restent dans ton navigateur (`localStorage`). Rien n'est envoyé
ailleurs qu'à l'API de Google.

## Ce que l'outil produit

- **Vidéos détectées** — chaque outlier avec son multiplicateur (vues ÷ abonnés),
  sa vitesse (vues/jour) et un score d'opportunité sur 100. Export CSV.
- **Classement des niches** — les 91 sous-niches de la bibliothèque intégrée notées
  sur le nombre d'outliers trouvés, le multiplicateur médian et le volume de vues.
- **Idées & titres** — pour une niche donnée : le plan de réplication chiffré
  (format qui gagne, durée cible, objectif de vues), les patterns des titres gagnants
  réels, les thèmes connexes à explorer, et des titres classés par potentiel de clic.

## Lecture des métriques

**Multiplicateur** = vues ÷ abonnés. C'est *le* signal. Au-delà de ×10, YouTube pousse la
vidéo vers des gens qui ne connaissent pas la chaîne : le sujet porte tout seul.

**Vues/jour** = vitesse. Une vidéo à 30 000 vues/jour est encore en ascension.

**Score** = synthèse (multiplicateur, vitesse, volume, engagement, fraîcheur), sur 100.
🔥 ≥ 70 pépite · ✅ ≥ 52 solide · 🟡 ≥ 34 à creuser.

## Quota

L'API YouTube offre 10 000 unités/jour. Une recherche coûte 100 unités, les détails
vidéos/chaînes 1 unité. Une sous-niche = 2 mots-clés ≈ 202 unités (404 en mode
« vidéos longues », qui interroge deux plages de durée). Soit ~25 à 50 sous-niches par jour.
Le compteur en bas de l'onglet Recherche suit la consommation.

## Bibliothèque intégrée

16 thématiques, 91 sous-niches, en français et en anglais : Finance, Tech & IA,
Fitness, Cuisine, Gaming, Divertissement, Développement personnel, Maison & DIY,
Voyage, Beauté, Animaux, Auto & Moto, Créatif, Sciences, Famille, Niches curieuses.
Des mots-clés personnalisés peuvent être ajoutés.
