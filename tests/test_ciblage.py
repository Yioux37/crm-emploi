"""Page Ciblage : validation, requête LinkedIn, et effet réel sur le radar et le score."""
import json
import os
from datetime import date, timedelta

import pytest

import ciblage


@pytest.fixture
def fichier(tmp_path, monkeypatch):
    """Un ciblage de test, isolé du vrai ciblage.json."""
    path = tmp_path / "ciblage.json"
    path.write_text(json.dumps({
        "secteurs": [
            {"nom": "Maroquinerie", "prioritaire": True, "mots_cles": ["maroquinerie", "leather goods"]},
            {"nom": "Luxe", "prioritaire": False, "mots_cles": ["luxe"]},
        ],
        "societes": [
            {"nom": "Tolomei", "secteur": "Maroquinerie", "type": "Atelier / façonnier", "priorite": "Haute"},
            {"nom": "SIS", "secteur": "Maroquinerie", "priorite": "Haute"},
            {"nom": "Christian Dior", "alias": ["Dior"], "secteur": "Luxe", "priorite": "Moyenne"},
        ],
        "linkedin": {"postes": ["Directeur"], "fonctions": [], "secteurs": ["Luxe", "Horlogerie"],
                     "signaux": ["Mandat"], "exclure": ["Stage"]},
    }), encoding="utf-8")
    monkeypatch.setenv("CIBLAGE_PATH", str(path))
    return path


def test_validation_nettoie_sans_bloquer():
    propre, avert = ciblage.valider({
        "secteurs": [{"nom": "Luxe", "mots_cles": "luxe, it, Luxe"},
                     {"nom": "luxe", "mots_cles": ["x"]}],
        "societes": [{"nom": "Hermès", "secteur": "Inconnu", "priorite": "Urgent", "alias": "Hermes, Hermès"}],
    })
    assert propre["secteurs"] == [{"nom": "Luxe", "prioritaire": True, "mots_cles": ["luxe"]}]
    soc = propre["societes"][0]
    assert soc["secteur"] == "" and soc["priorite"] == "Moyenne" and soc["alias"] == []
    assert any("trop court" in a for a in avert) and any("double" in a for a in avert)


def test_le_vrai_fichier_du_depot_est_valide():
    brut = json.loads((ciblage.ROOT / "ciblage.json").read_text(encoding="utf-8"))
    propre, avert = ciblage.valider(brut)
    assert avert == []
    assert propre == brut  # ce que l'appli relit est exactement ce qui est versionné


def test_requete_linkedin(fichier):
    cfg = ciblage.charger()
    q = ciblage.requete_linkedin(cfg)
    assert q == '("Directeur") AND ("Luxe" OR "Horlogerie") AND ("Mandat") NOT ("Stage")'
    assert "Mandat" not in ciblage.requete_linkedin(cfg, avec_signaux=False)
    assert ciblage.lien_linkedin_posts(q).startswith("https://www.linkedin.com/search/results/content/?keywords=%28")


def test_societe_reconnue_en_mot_entier(fichier):
    assert ciblage.societe_reconnue("Directeur industriel - SIS")["nom"] == "SIS"
    assert ciblage.societe_reconnue("Supply chain analysis") is None
    assert ciblage.societe_reconnue("Poste chez DIOR à Paris")["nom"] == "Christian Dior"


def test_radar_classe_avec_le_ciblage(fichier):
    import scraper
    secteur = scraper.valider_et_classer_offre("Directeur des opérations", "Tolomei", "Florence, Italie")
    assert secteur == "Maroquinerie, Luxe"
    # Un mot-clé ajouté par papa suffit à faire entrer une offre dans un secteur.
    assert "Maroquinerie" in scraper.valider_et_classer_offre(
        "Directeur industriel", "Atelier XYZ", "leather goods manufacture")
    assert scraper.detecter_maison_exacte("Directeur supply chain chez Tolomei") == "Tolomei"


def test_score_utilise_le_ciblage(fichier):
    from scoring import calculate_score
    prefs = ciblage.preferences_effectives({"preferred_brands": ""})
    assert prefs["preferred_sectors"] == ["Maroquinerie"]
    offre = {"title": "Directeur Supply Chain", "company": "Tolomei", "sector": "Maroquinerie",
             "country": "Italie", "detected_on": date.today().isoformat()}
    _, raisons = calculate_score(offre, prefs)
    assert "Maison favorite (+10)" in raisons and "Secteur recherché (+15)" in raisons
    # « sis » est une maison Haute mais ne doit pas favoriser « Sisley ».
    _, raisons = calculate_score({**offre, "company": "Sisley"}, prefs)
    assert "Maison favorite (+10)" not in raisons


def test_rotation_couvre_toutes_les_societes():
    items = list(range(24))
    vus = set()
    for i in range(3):
        jour = ciblage.rotation_du_jour(items, 8, date(2026, 11, 19) + timedelta(days=i))
        assert len(jour) == 8
        vus.update(jour)
    assert vus == set(items)


def test_societes_prioritaires_limitees_dans_l_index(fichier, monkeypatch):
    from sources_plus import _cibles_prioritaires, select_search_sites
    extra = _cibles_prioritaires(date(2026, 11, 19))
    assert [e[0] for e in extra] == ["Tolomei"]  # SIS : trop court pour une recherche dédiée
    assert extra[0][1] == "tolomei.ciblage"
    assert any(s[0] == "Tolomei" for s in select_search_sites(date(2026, 11, 19), budget=60))


def test_enregistrer_puis_publier(fichier):
    propre, _ = ciblage.enregistrer({**ciblage.charger(), "linkedin": {"postes": "Head of\nVP"}})
    assert ciblage.charger()["linkedin"]["postes"] == ["Head of", "VP"]

    class Reponse:
        def __init__(self, code, data=None):
            self.status_code, self._data = code, data or {}
        def json(self):
            return self._data

    class Session:
        def __init__(self):
            self.put_body = None
        def get(self, *a, **k):
            return Reponse(404)
        def put(self, url, headers, json, timeout):
            self.put_body = json
            return Reponse(201)

    session = Session()
    ok, _ = ciblage.publier_sur_github(propre, "jeton", "moi/crm", session=session)
    assert ok and session.put_body["branch"] == "main" and "sha" not in session.put_body


def test_resultat_linkedin_ciblage_vers_crm(fichier, tmp_path):
    from scraper import normaliser_ciblage_linkedin
    carte = {"title": "Directeur des opérations", "company": "Tolomei", "location": "Bourguébus",
             "url": "https://www.linkedin.com/jobs/view/42/", "search_country": "France"}
    ligne = normaliser_ciblage_linkedin(carte)
    # Petite ville sans pays : on garde le pays de la recherche LinkedIn.
    assert ligne["Pays"] == "France" and ligne["Secteur"] == "Maroquinerie, Luxe"
    # Employeur inconnu : secteur laissé vide plutôt qu'un faux « Luxe ».
    autre = normaliser_ciblage_linkedin({**carte, "company": "Cuisines Industrielles SA"})
    assert autre["Secteur"] == ""
    assert normaliser_ciblage_linkedin({**carte, "title": "Stage supply chain"}) is None


DOUBLONS = [  # (titre A, maison A, titre B, maison B, pays)
    ("Directeur Supply Chain H/F", "ROLEX SA", "Directeur Supply Chain H/F", "Rolex", "Suisse"),
    ("Directeur Supply Chain (F/H/X)", "Chanel", "Directeur Supply Chain", "CHANEL SAS", "France"),
    ("Head of Operations (m/w/d)", "Audemars Piguet", "Head of Operations", "Audemars Piguet", "Suisse"),
    ("Directeur Supply Chain - Paris", "Hermès", "Directeur Supply Chain", "Hermès Sellier", "France"),
    ("Directeur.rice Fashion Operations", "CHANEL", "Directeur Fashion Operations", "Chanel", "France"),
    ("Plant Manager", "Louis Vuitton Malletier", "Plant Manager", "Louis Vuitton", "Italie"),
]
DIFFERENTS = [
    ("Directeur Supply Chain", "Hermès", "Directeur Industriel", "Hermès", "France"),
    ("Directeur Supply Chain", "Rolex", "Directeur Supply Chain", "Tudor", "Suisse"),
]


@pytest.mark.parametrize("ta,ca,tb,cb,pays", DOUBLONS)
def test_anti_doublon_linkedin_et_site_maison(ta, ca, tb, cb, pays):
    from matching import same_opportunity
    a = {"title": ta, "company": ca, "country": pays, "link": "https://www.linkedin.com/jobs/view/4012345678/"}
    b = {"title": tb, "company": cb, "country": pays, "link": "https://careers.exemple.com/job/1"}
    assert same_opportunity(a, b)


@pytest.mark.parametrize("ta,ca,tb,cb,pays", DIFFERENTS)
def test_postes_differents_restent_separes(ta, ca, tb, cb, pays):
    from matching import same_opportunity
    assert not same_opportunity({"title": ta, "company": ca, "country": pays, "link": ""},
                                {"title": tb, "company": cb, "country": pays, "link": ""})


def test_republication_linkedin_fusionnee_dans_la_base(tmp_path):
    """LinkedIn republie l'offre avec un nouvel identifiant : une seule fiche, statut conservé."""
    from storage import CRMStore, _row_values
    store = CRMStore(db_path=tmp_path / "crm.sqlite3")
    ligne = {"Titre": "Directeur Supply Chain H/F", "Entreprise": "Hermès", "Pays": "France",
             "Source": "LinkedIn (Offres)", "Lien": "https://www.linkedin.com/jobs/view/4000000001/"}
    with store.engine.begin() as conn:
        assert store._insert_or_match(conn, _row_values(ligne), "feed")
    offre = store.list_offers().iloc[0]
    store.update_offer(offre["id"], {"status": "Ecarte"})
    repost = {**ligne, "Titre": "CDI - Directeur Supply Chain (F/H/X)", "Entreprise": "HERMES SAS",
              "Lien": "https://www.linkedin.com/jobs/view/4999999999/"}
    with store.engine.begin() as conn:
        assert not store._insert_or_match(conn, _row_values(repost), "feed")
    offres = store.list_offers()
    assert len(offres) == 1 and offres.iloc[0]["status"] == "Ecarte"  # ne revient pas


def test_scan_inclut_la_recherche_linkedin_du_ciblage(fichier, monkeypatch):
    import scraper
    cartes = [
        {"title": "Directeur des opérations", "company": "Tolomei", "location": "Florence, Italie",
         "url": "https://www.linkedin.com/jobs/view/4000000042/", "search_country": "Italie"},
        {"title": "Plant Director", "company": "Cuisines Industrielles", "location": "Modène, Italie",
         "url": "https://www.linkedin.com/jobs/view/4000000043/", "search_country": "Italie"},
    ]
    vu = {}

    def faux_fetch(requete, pages, on_progress=None):
        vu["requete"], vu["pages"] = requete, pages
        return cartes, {"requetes": 2, "bloque": False, "erreurs": 0, "sautees": 0}

    monkeypatch.setattr("linkedin_guest.fetch_ciblage_jobs", faux_fetch)
    monkeypatch.setenv("LINKEDIN_CIBLAGE_PAGES", "2")
    scraper.EXTRA_SOURCE_STATS.clear()
    lignes = scraper.fetch_linkedin_ciblage()
    assert vu == {"requete": '("Directeur") AND ("Luxe" OR "Horlogerie") NOT ("Stage")', "pages": 2}
    assert [l["Entreprise"] for l in lignes] == ["Tolomei"]  # le bruit sans secteur reste dehors
    assert scraper.EXTRA_SOURCE_STATS["LinkedIn Ciblage"]["retenues"] == 1
