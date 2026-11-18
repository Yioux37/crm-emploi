"""Public discovery targets for the career radar.

A listed site is a discovery target, not a claim of direct API access,
permission to crawl, coverage guarantee, or currently active vacancy.
Only indexed public results are queried for SEARCH_SITES; no site login,
profiles, anti-bot bypass, or scraping of the destination page.
"""

# Label, public domain, channel, query language, daily-priority flag.
SEARCH_SITES = [
    # Highest-yield sources: checked on every scheduled scan.
    ('FashionJobs France', 'fr.fashionjobs.com', 'Portails sp\u00e9cialis\u00e9s', 'fr', True),
    ('FashionJobs Suisse', 'ch.fashionjobs.com', 'Portails sp\u00e9cialis\u00e9s', 'fr', True),
    ('FashionJobs Italie', 'it.fashionjobs.com', 'Portails sp\u00e9cialis\u00e9s', 'it', True),
    ('APEC', 'apec.fr', 'Portails cadres', 'fr', True),
    ('Jobs.ch', 'jobs.ch', 'Portails cadres', 'en', True),
    ('Jobup Suisse', 'jobup.ch', 'Portails cadres', 'fr', True),

    # Jobboards and specialized luxury/watchmaking platforms.
    ('Cadremploi', 'cadremploi.fr', 'Portails cadres', 'fr', True),
    ('Welcome to the Jungle', 'welcometothejungle.com', 'Portails cadres', 'fr', True),
    ('HelloWork', 'hellowork.com', 'Portails cadres', 'fr', True),
    ('France Travail (index public)', 'francetravail.fr', 'Portails cadres', 'fr', False),
    ('JobScout24', 'jobscout24.ch', 'Portails cadres', 'en', False),
    ('Jobwatch Horlogerie', 'jobwatch.ch', 'Portails sp\u00e9cialis\u00e9s', 'fr', False),
    ('Cerulean Suisse luxe', 'ceruleanjobs.ch', 'Portails sp\u00e9cialis\u00e9s', 'en', False),
    ('Indeed France (index public)', 'fr.indeed.com', 'Portails cadres', 'fr', True),
    ('Indeed Suisse (index public)', 'ch.indeed.com', 'Portails cadres', 'en', True),
    ('Indeed Italie (index public)', 'it.indeed.com', 'Portails cadres', 'it', True),
    ('InfoJobs Italie', 'infojobs.it', 'Portails cadres', 'it', False),
    ('Monster Italie', 'monster.it', 'Portails cadres', 'it', False),
    ('Experteer', 'experteer.com', 'Portails cadres', 'en', False),
    ('Business of Fashion Careers', 'businessoffashion.com', 'Portails sp\u00e9cialis\u00e9s', 'en', False),
    ('FashionUnited Careers', 'fashionunited.com', 'Portails sp\u00e9cialis\u00e9s', 'en', False),


    # Mainstream general job boards and aggregators: INDEX ONLY. No direct
    # crawling or private account access, and no guarantee of fresh results.
    ('Meteojob France', 'meteojob.com', 'Portails cadres', 'fr', False),
    ('Monster France', 'monster.fr', 'Portails cadres', 'fr', False),
    ('Jobijoba France', 'jobijoba.com', 'Portails cadres', 'fr', False),
    ('Jobrapido France', 'fr.jobrapido.com', 'Portails cadres', 'fr', False),
    ('Jooble France', 'fr.jooble.org', 'Portails cadres', 'fr', False),
    ('Figaro Emploi', 'emploi.lefigaro.fr', 'Portails cadres', 'fr', False),
    ('Optioncarriere France', 'optioncarriere.com', 'Portails cadres', 'fr', False),
    ('Talent.com France', 'talent.com', 'Portails cadres', 'fr', False),
    ('Glassdoor France', 'glassdoor.fr', 'Portails cadres', 'fr', False),
    ('Leboncoin Emploi', 'leboncoin.fr', 'Portails cadres', 'fr', False),
    ('Experteer France', 'experteer.fr', 'Portails cadres', 'fr', False),

    # Switzerland: Job-Room public service and French/German-speaking boards.
    ('Job-Room Suisse', 'job-room.ch', 'Portails cadres', 'fr', False),
    ('Jobwinner Suisse', 'jobwinner.ch', 'Portails cadres', 'fr', False),
    ('Jobtic Suisse', 'jobtic.ch', 'Portails cadres', 'fr', False),
    ('Jobeo Suisse', 'jobeo.ch', 'Portails cadres', 'fr', False),
    ('Careerjet Suisse', 'careerjet.ch', 'Portails cadres', 'fr', False),
    ('Optioncarriere Suisse', 'optioncarriere.ch', 'Portails cadres', 'fr', False),
    ('Jobagent Suisse', 'jobagent.ch', 'Portails cadres', 'fr', False),
    ('Emploi Romand', 'emploi-romand.ch', 'Portails cadres', 'fr', False),

    # Italy: national portals, meta-search and local recruiters.
    ('Trovolavoro Italie', 'trovolavoro.corriere.it', 'Portails cadres', 'it', False),
    ('Cliclavoro Italie', 'cliclavoro.gov.it', 'Portails cadres', 'it', False),
    ('Jooble Italie', 'it.jooble.org', 'Portails cadres', 'it', False),
    ('Jobrapido Italie', 'it.jobrapido.com', 'Portails cadres', 'it', False),
    ('Experteer Italie', 'experteer.it', 'Portails cadres', 'it', False),
    ('Glassdoor Italie', 'glassdoor.it', 'Portails cadres', 'it', False),
    ('Adecco Italie', 'adecco.it', 'Cabinets de Recrutement', 'it', False),
    ('Gi Group Italie', 'gigroup.it', 'Cabinets de Recrutement', 'it', False),
    ('Manpower Italie', 'manpower.it', 'Cabinets de Recrutement', 'it', False),

    # Additional recruiters and cross-border portals for executive functions.
    ('Adecco France', 'adecco.fr', 'Cabinets de Recrutement', 'fr', False),
    ('Randstad France', 'randstad.fr', 'Cabinets de Recrutement', 'fr', False),
    ('Manpower France', 'manpower.fr', 'Cabinets de Recrutement', 'fr', False),
    ('Expectra France', 'expectra.fr', 'Cabinets de Recrutement', 'fr', False),
    ('Adecco Suisse', 'adecco.ch', 'Cabinets de Recrutement', 'fr', False),
    ('EURES Europe', 'eures.europa.eu', 'Portails cadres', 'en', False),

    # Recruiters and retained executive-search firms. Many missions are confidential;
    # search coverage does NOT imply that their mandates are available online.
    ('Michael Page France', 'michaelpage.fr', 'Cabinets de Recrutement', 'fr', False),
    ('Michael Page Suisse', 'michaelpage.ch', 'Cabinets de Recrutement', 'en', False),
    ('Michael Page Italie', 'michaelpage.it', 'Cabinets de Recrutement', 'it', False),
    ('Robert Walters France', 'robertwalters.fr', 'Cabinets de Recrutement', 'fr', False),
    ('Robert Walters Suisse', 'robertwalters.ch', 'Cabinets de Recrutement', 'en', False),
    ('Robert Walters Italie', 'robertwalters.it', 'Cabinets de Recrutement', 'it', False),
    ('Hays France', 'hays.fr', 'Cabinets de Recrutement', 'fr', False),
    ('Hays Suisse', 'hays.ch', 'Cabinets de Recrutement', 'en', False),
    ('Hays Italie', 'hays.it', 'Cabinets de Recrutement', 'it', False),
    ('Morgan Philips', 'morganphilips.com', 'Cabinets de Recrutement', 'en', False),
    ('Luxe Talent', 'luxetalent.net', 'Cabinets de Recrutement', 'en', False),
    ('Luxury Talents (direction luxe)', 'luxurytalents.com', 'Cabinets de Recrutement', 'fr', False),
    ('Page Executive', 'pageexecutive.com', 'Cabinets de Recrutement', 'en', False),
    ('LHH', 'lhh.com', 'Cabinets de Recrutement', 'en', False),
    ('Korn Ferry', 'kornferry.com', 'Cabinets de Recrutement', 'en', False),
    ('Egon Zehnder', 'egonzehnder.com', 'Cabinets de Recrutement', 'en', False),
    ('Spencer Stuart', 'spencerstuart.com', 'Cabinets de Recrutement', 'en', False),
    ('Russell Reynolds', 'russellreynolds.com', 'Cabinets de Recrutement', 'en', False),
    ('Heidrick & Struggles', 'heidrick.com', 'Cabinets de Recrutement', 'en', False),
    ('Alexander Hughes', 'alexanderhughes.com', 'Cabinets de Recrutement', 'en', False),
    ('Randstad Italie', 'randstad.it', 'Cabinets de Recrutement', 'it', False),
    ('Fed Supply', 'fedsupply.fr', 'Cabinets de Recrutement', 'fr', False),

    # Companies and brands: checked EVERY DAY. Recherche ouverte sur le nom de la
    # maison (toutes plateformes), pas seulement sur son domaine officiel.
    ('LVMH', 'lvmh.com', 'Sites Maisons de Luxe', 'fr', True),
    ('Kering', 'kering.com', 'Sites Maisons de Luxe', 'fr', True),
    ('Richemont', 'richemont.com', 'Sites Maisons de Luxe', 'en', True),
    ('Swatch Group', 'swatchgroup.com', 'Sites Maisons de Luxe', 'en', True),
    ('Hermes', 'hermes.com', 'Sites Maisons de Luxe', 'fr', True),
    ('Chanel', 'chanel.com', 'Sites Maisons de Luxe', 'fr', True),
    ('Rolex', 'rolex.com', 'Sites Maisons de Luxe', 'fr', True),
    ('Patek Philippe', 'patek.com', 'Sites Maisons de Luxe', 'fr', True),
    ('Audemars Piguet', 'audemarspiguet.com', 'Sites Maisons de Luxe', 'fr', True),
    ('Breitling', 'breitling.com', 'Sites Maisons de Luxe', 'en', True),
    ('Cartier', 'cartier.com', 'Sites Maisons de Luxe', 'fr', True),
    ('Prada Group', 'pradagroup.com', 'Sites Maisons de Luxe', 'it', True),
    ('Moncler Group', 'monclergroup.com', 'Sites Maisons de Luxe', 'it', True),
    ('Gucci', 'gucci.com', 'Sites Maisons de Luxe', 'it', True),
    ('Louis Vuitton', 'louisvuitton.com', 'Sites Maisons de Luxe', 'fr', True),
    ('Dior', 'dior.com', 'Sites Maisons de Luxe', 'fr', True),
    ('Chopard', 'chopard.com', 'Sites Maisons de Luxe', 'fr', True),
    ('TAG Heuer', 'tagheuer.com', 'Sites Maisons de Luxe', 'fr', True),
    ('Loro Piana', 'loropiana.com', 'Sites Maisons de Luxe', 'it', True),
    ('Zegna Group', 'zegnagroup.com', 'Sites Maisons de Luxe', 'it', True),
    ('Longines', 'longines.com', 'Sites Maisons de Luxe', 'fr', True),
    ('Bulgari', 'bulgari.com', 'Sites Maisons de Luxe', 'it', True),
    ('Armani', 'armani.com', 'Sites Maisons de Luxe', 'it', True),
    ('Valentino', 'valentino.com', 'Sites Maisons de Luxe', 'it', True),

    # Hosted job boards found in search index; optional direct ATS connectors
    # use exact, separately verified organization identifiers.
    ('Greenhouse Jobs', 'job-boards.greenhouse.io', 'Sites Maisons de Luxe', 'en', False),
    ('Lever EU', 'jobs.eu.lever.co', 'Sites Maisons de Luxe', 'en', False),
    ('Lever Global', 'jobs.lever.co', 'Sites Maisons de Luxe', 'en', False),
    ('Ashby Jobs', 'jobs.ashbyhq.com', 'Sites Maisons de Luxe', 'en', False),
    ('SmartRecruiters Jobs', 'jobs.smartrecruiters.com', 'Sites Maisons de Luxe', 'en', False),
    ('Workday Careers', 'myworkdayjobs.com', 'Sites Maisons de Luxe', 'en', False),
    ('Teamtailor Careers', 'teamtailor.com', 'Sites Maisons de Luxe', 'en', False),
    ('Recruitee Careers', 'recruitee.com', 'Sites Maisons de Luxe', 'en', False),
]

# News sources are used ONLY for potential market signals, NEVER job offers.
NEWS_SITES = [
    ('FashionNetwork', 'fashionnetwork.com'),
    ('Journal du Luxe', 'journalduluxe.fr'),
    ('WorldTempus', 'worldtempus.com'),
    ('WatchPro', 'watchpro.com'),
    ('Bilan', 'bilan.ch'),
    ('Les Echos', 'lesechos.fr'),
    ('Il Sole 24 Ore', 'ilsole24ore.com'),
    ('Europa Star', 'europastar.com'),
    ('Federation horlogere suisse', 'fhs.swiss'),
    ('Business of Fashion', 'businessoffashion.com'),
    ('FashionUnited', 'fashionunited.com'),
    ('Le Temps', 'letemps.ch'),
    ('RTS Suisse', 'rts.ch'),
    ('Swissinfo', 'swissinfo.ch'),
    ('Watchonista', 'watchonista.com'),
    ('Fashionmag', 'fr.fashionnetwork.com'),
    ('Pambianconews Italie', 'pambianconews.com'),
    ('L Usine Nouvelle', 'usinenouvelle.com'),
]

# Clearly excluded from automated direct access. Links are read-only pointers.
# Never represent a restricted API as an enabled connector.
MANUAL_OR_RESTRICTED = [
    ('France Travail API Offres', 'Acces soumis a autorisation; recherche dans index public seulement'),
    ('LinkedIn comptes / profils', 'Pas de collecte de profils, contacts ou espace connecte'),
    ('Missions confidentielles de chasse', 'Approche relationnelle manuelle, annonces non necessairement publiques'),
    ('Sites sous login ou CAPTCHA', 'Aucune tentative de contournement'),
]


def catalog_totals() -> dict[str, int]:
    return {
        'index_targets': len(SEARCH_SITES),
        'priority_daily': sum(site[4] for site in SEARCH_SITES),
        'news_targets': len(NEWS_SITES),
    }
