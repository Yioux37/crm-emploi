# Guide simple du CRM Carrière (pour papa)

**Ouvre : https://crm-emploi.streamlit.app**

Ce site est ton **carnet privé de recherche d'emploi** pour les postes de direction, les opérations, la supply chain et les manufactures du luxe. Il surveille notamment la France, la Suisse et l'Italie.

## Chaque matin : 5 minutes

1. **Connecte-toi** avec le mot de passe communiqué en privé.
2. **Va dans Accueil.** Regarde les nouvelles annonces et les scores les plus élevés.
3. **Va dans Opportunités.** Ouvre une offre intéressante, puis lis l'annonce originale pour vérifier qu'elle est bien ouverte et pertinente.
4. **Note ce que tu as fait.** Dans la fiche, indique le statut (A analyser, A postuler, Candidature envoyee, Entretien 1, etc.), une note et une **date de prochaine action**.
5. **Va dans Relances.** C'est ta liste des appels, messages et suivis à faire aujourd'hui.

## Que signifient les autres pages ?

- **Signaux marché :** actualités d'entreprises (investissement, nouvelle manufacture, acquisition, nomination). Ce sont des **pistes de mise en relation**, pas des offres d'emploi. Lis l'article et vérifie sa date avant de contacter quelqu'un.
- **Sources surveillées :** la liste des sites d'emploi, des maisons et des médias suivis par le radar. Certains ont des flux publics ; les autres sont recherchés via un moteur de recherche en rotation.
- **Statistiques :** le suivi des offres, candidatures et entretiens.
- **Préférences :** les pays, maisons et métiers qui t'intéressent le plus.

## Le score sur 100

Un score élevé signifie **« ce poste correspond bien à mes critères »**. Ce n'est **pas** une probabilité de recrutement. Lis toujours la description du poste avant de prendre une décision.

## Deux exemples

**Une annonce :** tu trouves un poste de Directeur des opérations en Suisse. Ouvre l'annonce, puis, si tu postules, note le statut **Candidature envoyee** (nom du statut dans le CRM) et fixe une date de relance.

**Une actualité :** une maison annonce un investissement dans une manufacture. Lis la source, vérifie que l'information est récente, puis réfléchis à une prise de contact. **Cela ne signifie pas qu'elle recrute.**

## Ce que tu n'as pas à faire

Tu n'as pas besoin de toucher à **GitHub**, d'installer **Python** ou de lancer toi-même le scanner. La veille est programmée par l'administrateur. Tu peux te concentrer sur la lecture et le suivi des opportunités.

**Important :** le responsable de l'application doit configurer une base PostgreSQL persistante avant de conserver des informations personnelles importantes dans Streamlit Cloud. Ne partage jamais le mot de passe dans une capture d'écran ou une conversation.

## Où sont cherchées les offres ?

Le radar vérifie chaque jour via un moteur de recherche les grandes plateformes : **Indeed**, **Welcome to the Jungle**, **APEC**, **Cadremploi**, **HelloWork**, **FashionJobs**, **jobs.ch** et **Jobup.ch**. Des maisons de luxe et des cabinets de recrutement sont ensuite interrogés à tour de rôle. Certains sites ne permettent pas une collecte directe ; une absence de résultat ne signifie pas qu'il n'existe aucune offre.

**Ton geste utile :** dans l'onglet *Sources surveillées*, tu peux ouvrir directement les sites, puis vérifier les offres qui t'intéressent. Le lien de chaque offre dans *Opportunités* permet de consulter la publication d'origine avant de postuler.


## D'ou viennent les offres ?
Le radar cherche sur les grands sites d'emploi (Indeed, Welcome to the Jungle, APEC, Cadremploi, HelloWork), les plateformes suisses et italiennes, les sites des maisons de luxe et les cabinets de recrutement. Il ne garantit pas de trouver toutes les offres. Ouvre **Sources surveillees** pour voir le catalogue. Une opportunite doit toujours etre confirmee sur le site d'origine.
