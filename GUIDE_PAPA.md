# Guide simple du CRM Carrière (pour papa)

**Ouvre : https://crm-emploi.streamlit.app**

Ce site est ton **carnet privé de recherche d'emploi** pour les postes de direction, les opérations, la supply chain et les manufactures du luxe. Il surveille notamment la France, la Suisse et l'Italie.

## Chaque matin : 5 minutes

1. **Connecte-toi** avec le mot de passe communiqué en privé.
2. **Va dans Accueil.** Regarde les nouvelles annonces et les scores les plus élevés.
3. **Va dans Opportunités.** Ouvre une offre intéressante, puis lis l'annonce originale pour vérifier qu'elle est bien ouverte et pertinente.
4. **Note ce que tu as fait.** Dans la fiche, indique le statut (A analyser, A postuler, Candidature envoyee, Entretien 1, etc.), une note et une **date de prochaine action**.
5. **Va dans Relances.** C'est ta liste des appels, messages et suivis à faire aujourd'hui.

## Offres expirées et liens qui ne mènent plus au poste

À chaque « Rechercher de nouvelles offres », le CRM ouvre chaque offre en cours et vérifie qu'elle est encore ouverte. Il ne se contente plus de voir si la page répond : il repère aussi « les candidatures ne sont plus acceptées », les pages supprimées, et les liens qui retombent sur l'accueil du site carrière.

- **Offre que tu n'avais pas encore traitée** : elle passe toute seule dans « Écarté », avec une note qui explique pourquoi.
- **Offre où tu as déjà postulé** : rien ne bouge. Un bandeau rouge sur la fiche et une alerte sur le tableau de bord te préviennent.
- **Lien mort, mais la même offre existe ailleurs** (LinkedIn, site de la maison) : le CRM remplace le lien par celui qui marche.
- **« À vérifier »** : le site bloque les robots (FashionJobs, Jooble...). Le CRM ne conclut pas : ouvre le lien toi-même.

Tu tombes quand même sur une annonce morte ? Ouvre la fiche et clique **« Signaler un lien mort »**. Le bouton **« Vérifier les liens des offres »**, dans la barre de gauche, relance le contrôle à tout moment.

## Que signifient les autres pages ?

- **Signaux marché :** actualités d'entreprises (investissement, nouvelle manufacture, acquisition, nomination). Ce sont des **pistes de mise en relation**, pas des offres d'emploi. Lis l'article et vérifie sa date avant de contacter quelqu'un.
- **Sources surveillées :** la liste des sites d'emploi, des maisons et des médias suivis par le radar. Certains ont des flux publics ; les autres sont recherchés via un moteur de recherche en rotation.
- **Statistiques :** le suivi des offres, candidatures et entretiens.
- **Ciblage :** les secteurs, sociétés et la recherche LinkedIn que suit le radar (voir plus bas).
- **Réglages :** les pays, métiers et le seuil d'alerte.

## Modifier ce que le radar cherche : page Ciblage

Tu peux changer toi-même les secteurs, les sociétés et ta recherche LinkedIn, sans passer par moi.

- **Secteurs :** une ligne par secteur, avec ses mots-clés séparés par des virgules. Un début de mot suffit : « joaill » trouve joaillerie, joaillier et joaillière. Coche **Prioritaire** pour les secteurs qui comptent le plus.
- **Sociétés :** ajoute une maison, un atelier ou un façonnier en bas du tableau. En priorité **Haute**, la société gagne des points dans le score et le radar la recherche par son nom. **Autres noms** sert aux variantes (Dior pour Christian Dior).
- **Recherche LinkedIn :** un terme par ligne dans chaque bloc. La requête booléenne se construit toute seule. Clique sur **Chercher dans les posts LinkedIn** ou **Chercher dans les offres LinkedIn** pour l'ouvrir directement.

- **Les résultats arrivent seuls dans le CRM :** le bouton **Rechercher de nouvelles offres** lance aussi ta recherche LinkedIn (France, Suisse, Italie). Les offres d'un secteur reconnu entrent dans le Pipeline en « À analyser ». Une même offre vue sur LinkedIn et sur le site de la maison n'apparaît qu'une fois.

Termine toujours par **Enregistrer le ciblage**. Tant que tu n'as pas cliqué, rien n'est changé. **Annuler les modifications** remet la dernière version enregistrée.

## Le score sur 100

Un score élevé signifie **« ce poste correspond bien à mes critères »**. Ce n'est **pas** une probabilité de recrutement. Lis toujours la description du poste avant de prendre une décision.

## Deux exemples

**Une annonce :** tu trouves un poste de Directeur des opérations en Suisse. Ouvre l'annonce, puis, si tu postules, note le statut **Candidature envoyee** (nom du statut dans le CRM) et fixe une date de relance.

**Une actualité :** une maison annonce un investissement dans une manufacture. Lis la source, vérifie que l'information est récente, puis réfléchis à une prise de contact. **Cela ne signifie pas qu'elle recrute.**

## Ce que tu n'as pas à faire

Tu n'as pas besoin de toucher à **GitHub**, d'installer **Python** ou de lancer toi-même le scanner. La veille est programmée par l'administrateur. Tu peux te concentrer sur la lecture et le suivi des opportunités.

**Important :** le responsable de l'application doit configurer une base PostgreSQL persistante avant de conserver des informations personnelles importantes dans Streamlit Cloud. Ne partage jamais le mot de passe dans une capture d'écran ou une conversation.

## Où sont cherchées les offres ?

Le radar tente de rechercher chaque jour via un moteur de recherche public les grandes plateformes : **Indeed**, **Welcome to the Jungle**, **APEC**, **Cadremploi**, **HelloWork**, **FashionJobs**, **jobs.ch** et **Jobup.ch**. Des maisons de luxe et des cabinets de recrutement sont ensuite interrogés à tour de rôle. Certains sites ne permettent pas une collecte directe ; une absence de résultat ne signifie pas qu'il n'existe aucune offre.

**Ton geste utile :** dans l'onglet *Sources surveillées*, tu peux ouvrir directement les sites, puis vérifier les offres qui t'intéressent. Le lien de chaque offre dans *Opportunités* permet de consulter la publication d'origine avant de postuler.


## D'ou viennent les offres ?
Le radar cherche sur les grands sites d'emploi (Indeed, Welcome to the Jungle, APEC, Cadremploi, HelloWork), les plateformes suisses et italiennes, les sites des maisons de luxe et les cabinets de recrutement. Il ne garantit pas de trouver toutes les offres. Ouvre **Sources surveillees** pour voir le catalogue. Une opportunite doit toujours etre confirmee sur le site d'origine.

## Si le radar indique « source en erreur »

Cela **ne veut pas dire qu'il n'y a plus d'emploi** : un site ou le moteur gratuit n'a peut-être pas répondu ce jour-là. Tes offres déjà repérées sont conservées. Tu peux ouvrir **Sources surveillées → Santé du radar** pour consulter l'état du dernier passage ; tu n'as aucune réparation technique à faire, l'administrateur s'en charge.
