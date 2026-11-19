"""Offres expirées et liens qui ne mènent plus au poste (retour de papa).

Aucun appel réseau : un faux client HTTP rejoue les réponses observées en vrai
sur LinkedIn, Workday, SmartRecruiters et les agrégateurs (novembre 2026).
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import link_health as lh
from link_health import (A_VERIFIER, ACCESSIBLE, EXPIREE, REDIRIGE, Verdict,
                         verifier_lot, verifier_offre)
from matching import source_depuis_lien
from merge_feed import appliquer_verdicts_flux, liens_a_verifier
from storage import CRMStore, SCRAPER_COLUMNS


class FakeResp:
    def __init__(self, status=200, body="", location=None, payload=None):
        self.status_code = status
        self.headers = {"Location": location} if location else {}
        self._body = body.encode("utf-8")
        self._payload = payload
        self.encoding = "utf-8"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_content(self, size):
        yield self._body

    def json(self):
        if self._payload is None:
            raise ValueError("pas de JSON")
        return self._payload


class FakeSession:
    """routes : {url exacte: FakeResp ou liste de FakeResp (une par appel)}."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, **_):
        self.calls.append(url)
        r = self.routes.get(url, FakeResp(404))
        return r.pop(0) if isinstance(r, list) else r

    def close(self):
        pass


@pytest.fixture(autouse=True)
def sans_dns(monkeypatch):
    # public_url fait une résolution DNS : coupée pendant les tests.
    monkeypatch.setattr(lh, "public_url", lambda url: url.startswith("https://"))


PAGE_OFFRE = "<html><body><h1>Directeur Supply Chain</h1>" + "Missions et profil. " * 80 + "</body></html>"


# --- LinkedIn ------------------------------------------------------------------

def test_linkedin_offre_fermee_redirigee_vers_une_recherche():
    # Comportement réel : /jobs/view/3130224652 -> /jobs/j2ee-developer-jobs?trk=expired_jd_redirect
    s = FakeSession({
        "https://www.linkedin.com/jobs/view/3130224652/": FakeResp(
            302, location="https://www.linkedin.com/jobs/j2ee-developer-jobs?trk=expired_jd_redirect"),
        "https://www.linkedin.com/jobs/j2ee-developer-jobs?trk=expired_jd_redirect": FakeResp(200, "<html>liste</html>"),
    })
    v = verifier_offre("https://fr.linkedin.com/jobs/view/j2ee-developer-at-x-3130224652", session=s)
    assert v.statut == EXPIREE and v.mort


def test_linkedin_candidatures_closes_et_offre_ouverte():
    ferme = FakeSession({"https://www.linkedin.com/jobs/view/4000000001/": FakeResp(
        200, "<figure class='closed-job'>Les candidatures ne sont plus acceptées</figure>")})
    assert verifier_offre("https://www.linkedin.com/jobs/view/4000000001/", session=ferme).statut == EXPIREE
    ouvert = FakeSession({"https://www.linkedin.com/jobs/view/4000000002/": FakeResp(200, PAGE_OFFRE)})
    assert verifier_offre("https://www.linkedin.com/jobs/view/4000000002/", session=ouvert).statut == ACCESSIBLE


def test_linkedin_429_n_est_pas_une_offre_expiree():
    s = FakeSession({"https://www.linkedin.com/jobs/view/4000000003/": FakeResp(429)})
    v = verifier_offre("https://www.linkedin.com/jobs/view/4000000003/", session=s)
    assert v.statut == A_VERIFIER and v.limite and not v.mort


# --- Workday et SmartRecruiters : API publique ---------------------------------

WD = "https://richemont.wd3.myworkdayjobs.com/fr-FR/Richemont/job/MEYRIN/Head-of-Logistics_JR1"
WD_API = "https://richemont.wd3.myworkdayjobs.com/wday/cxs/richemont/Richemont/job/MEYRIN/Head-of-Logistics_JR1"


@pytest.mark.parametrize("reponse, attendu", [
    (FakeResp(404, payload={"errorCode": "S21"}), EXPIREE),
    (FakeResp(200, payload={"jobPostingInfo": {"canApply": False}}), EXPIREE),
    (FakeResp(200, payload={"jobPostingInfo": {"canApply": True,
                                               "endDate": (date.today() - timedelta(days=2)).isoformat()}}), EXPIREE),
    (FakeResp(200, payload={"jobPostingInfo": {"canApply": True, "endDate": None}}), ACCESSIBLE),
    (FakeResp(500), A_VERIFIER),
])
def test_workday(reponse, attendu):
    s = FakeSession({WD_API: reponse})
    assert verifier_offre(WD, session=s).statut == attendu
    assert s.calls == [WD_API]  # la locale « fr-FR » est bien retirée de l'adresse d'API


def test_smartrecruiters():
    api = "https://api.smartrecruiters.com/v1/companies/AudemarsPiguet/postings/744000152655250"
    url = "https://jobs.smartrecruiters.com/AudemarsPiguet/744000152655250"
    assert verifier_offre(url, session=FakeSession({api: FakeResp(404)})).statut == EXPIREE
    assert verifier_offre(url, session=FakeSession({api: FakeResp(200, payload={"active": True})})).statut == ACCESSIBLE
    assert verifier_offre(url, session=FakeSession({api: FakeResp(200, payload={"active": False})})).statut == EXPIREE


# --- Sites carrière et agrégateurs --------------------------------------------

def test_page_supprimee_410():
    # ch.trabajo.org répond vraiment 410 sur les copies expirées.
    url = "https://ch.trabajo.org/stellenangebot-4112-2ec61e39"
    assert verifier_offre(url, session=FakeSession({url: FakeResp(410)})).statut == EXPIREE


@pytest.mark.parametrize("texte", [
    "Désolé, cette offre n'est plus disponible.",
    "This job is no longer available",
    "Diese Stelle ist nicht mehr verfügbar",
    "L'offerta è scaduta. Offerta scaduta il 3 marzo.",
    "Le poste a été pourvu, merci de votre intérêt.",
])
def test_page_200_qui_dit_offre_fermee(texte):
    url = "https://careers.example.com/fr/offre/123456-directeur-supply-chain"
    v = verifier_offre(url, "Directeur Supply Chain",
                       session=FakeSession({url: FakeResp(200, f"<p>{texte}</p>")}))
    assert v.statut == EXPIREE


def test_lien_qui_retombe_sur_l_accueil_carriere():
    # Le cas décrit par papa : on arrive sur le site carrière, mais plus sur le poste.
    url = "https://jobs.maison.com/fr/job/directeur-operations-LVM33450"
    s = FakeSession({url: FakeResp(301, location="https://jobs.maison.com/fr/search-page"),
                     "https://jobs.maison.com/fr/search-page": FakeResp(200, PAGE_OFFRE)})
    v = verifier_offre(url, "Directeur Opérations", session=s)
    assert v.statut == REDIRIGE and v.mort


def test_redirection_vers_une_autre_fiche_reste_a_verifier():
    url = "https://jobs.maison.com/job/1234567"
    s = FakeSession({url: FakeResp(302, location="https://jobs.maison.com/job/7654321"),
                     "https://jobs.maison.com/job/7654321": FakeResp(200, PAGE_OFFRE)})
    assert verifier_offre(url, "Directeur Supply Chain", session=s).statut == A_VERIFIER


def test_redirection_qui_garde_le_poste_est_ouverte():
    url = "https://jobs.smartrecruiters.example.com/job/1234567"
    finale = "https://jobs.smartrecruiters.example.com/job/1234567-directeur-supply-chain"
    s = FakeSession({url: FakeResp(301, location=finale), finale: FakeResp(200, PAGE_OFFRE)})
    assert verifier_offre(url, "Directeur Supply Chain", session=s).statut == ACCESSIBLE


def test_site_protege_ne_conclut_pas():
    url = "https://ch.fashionjobs.com/emploi/rolex/Manager-de-production,11148570.html"
    v = verifier_offre(url, session=FakeSession({url: FakeResp(403, "<title>Attention Required! | Cloudflare</title>")}))
    assert v.statut == A_VERIFIER and not v.mort


def test_page_pleine_sans_le_poste_reste_a_verifier():
    url = "https://careers.example.com/offre/987654"
    page = "<html>" + "Découvrez nos métiers et notre histoire. " * 60 + "</html>"
    assert verifier_offre(url, "Directeur Supply Chain",
                          session=FakeSession({url: FakeResp(200, page)})).statut == A_VERIFIER


def test_adresse_non_web():
    assert verifier_offre("manuel://reseau/1").statut == A_VERIFIER


# --- Vérification par lot ----------------------------------------------------

def test_lot_une_seule_requete_par_offre_linkedin():
    appels = []

    def faux(url, titre, session=None):
        appels.append(url)
        return Verdict(ACCESSIBLE)

    res = verifier_lot([("https://fr.linkedin.com/jobs/view/directeur-at-hermes-4414141544", "D"),
                        ("https://www.linkedin.com/jobs/view/4414141544/", "D")],
                       verifier=faux, sleep=lambda s: None)
    assert len(appels) == 1 and len(res) == 2 and all(v.statut == ACCESSIBLE for v in res.values())


def test_lot_429_repete_reporte_le_reste_du_site():
    appels = []

    def faux(url, titre, session=None):
        appels.append(url)
        return Verdict(A_VERIFIER, "429", limite=True)

    urls = [f"https://www.linkedin.com/jobs/view/40000000{i}/" for i in range(5)]
    res = verifier_lot([(u, "") for u in urls], verifier=faux, sleep=lambda s: None)
    assert len(appels) == 2  # un essai + une seule nouvelle tentative, puis on s'arrête
    assert all(not v.mort for v in res.values()) and len(res) == 5


# --- Flux public --------------------------------------------------------------

def ligne(lien, source="Sites Maisons de Luxe", alts=()):
    return {"Titre": "Head of Supply Chain", "Entreprise": "Swatch Group", "Secteur": "Horlogerie",
            "Pays": "Suisse", "Source": source, "Lien": lien, "Niveau estimé": "Management senior",
            "Date de détection": "2026-11-16", "Dernière détection": "2026-11-17",
            "Liens alternatifs": json.dumps([{"url": u, "source": s} for u, s in alts])}


def test_flux_lien_mort_remplace_par_l_alternatif_ouvert():
    row = ligne("https://ch.trabajo.org/x-1", "Portails spécialisés",
                [("https://ch.linkedin.com/jobs/view/head-of-supply-chain-4463041468", "LinkedIn (Offres)")])
    verdicts = {"https://ch.trabajo.org/x-1": Verdict(EXPIREE, "410"),
                "https://ch.linkedin.com/jobs/view/head-of-supply-chain-4463041468": Verdict(ACCESSIBLE)}
    rows, bilan = appliquer_verdicts_flux([row], verdicts)
    assert rows[0]["Lien"].startswith("https://ch.linkedin.com") and rows[0]["Source"] == "LinkedIn (Offres)"
    assert json.loads(rows[0]["Liens alternatifs"]) == []
    assert bilan["liens_remplaces"] == 1 and bilan["offres_retirees"] == 0


def test_flux_offre_morte_retiree_et_offre_douteuse_gardee():
    morte = ligne("https://ch.trabajo.org/x-2")
    douteuse = ligne("https://ch.jooble.org/jdp/1")
    rows, bilan = appliquer_verdicts_flux([morte, douteuse], {
        "https://ch.trabajo.org/x-2": Verdict(EXPIREE, "410"),
        "https://ch.jooble.org/jdp/1": Verdict(A_VERIFIER, "Cloudflare")})
    assert [r["Lien"] for r in rows] == ["https://ch.jooble.org/jdp/1"]
    assert bilan["offres_retirees"] == 1 and bilan["retirees"][0]["raison"] == "410"


def test_liens_a_verifier_offres_du_jour_en_premier():
    vieille = {**ligne("https://a.example.com/1"), "Dernière détection": "2026-10-01"}
    neuve = {**ligne("https://b.example.com/2"), "Dernière détection": "2026-11-19"}
    assert [u for u, _ in liens_a_verifier([vieille, neuve], "2026-11-19", maximum=1)] == ["https://b.example.com/2"]


def test_scan_complet_retire_les_offres_expirees(monkeypatch):
    import scraper
    rows = [ligne("https://ch.trabajo.org/x-3"), ligne("https://jobs.smartrecruiters.com/AP/744000000000009")]
    verdicts = {"https://ch.trabajo.org/x-3": Verdict(EXPIREE, "410"),
                "https://jobs.smartrecruiters.com/AP/744000000000009": Verdict(ACCESSIBLE)}
    gardees, bilan = scraper.verifier_liens_du_flux(rows, "2026-11-19", verifier=lambda items, **_: verdicts)
    assert len(gardees) == 1 and bilan["offres_retirees"] == 1 and bilan["verifies"] == 2


# --- Étiquette de source ------------------------------------------------------

@pytest.mark.parametrize("lien, attendu", [
    ("https://ch.trabajo.org/stellenangebot-4112", "Portails spécialisés"),
    ("https://ch.jooble.org/jdp/1747748906343332360", "Portails spécialisés"),
    ("https://ch.linkedin.com/jobs/view/head-of-supply-chain-4463041468", "LinkedIn (Offres)"),
    ("https://jobs.louisvuitton.com/en/search-page/job/x-LVM33450", "Sites Maisons de Luxe"),
    ("https://richemont.wd3.myworkdayjobs.com/fr-FR/Richemont/job/X_JR1", "Sites Maisons de Luxe"),
])
def test_source_jugee_sur_le_vrai_domaine(lien, attendu):
    assert source_depuis_lien(lien, "Sites Maisons de Luxe") == attendu
    assert source_depuis_lien(lien, "Portails cadres") == "Portails cadres"  # les autres étiquettes ne bougent pas


# --- CRM -----------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    s = CRMStore(db_path=tmp_path / "crm.sqlite3")
    feed = pd.DataFrame([
        {**ligne("https://ch.trabajo.org/a-1"), "Titre": "Directeur Industriel", "Entreprise": "Rolex"},
        {**ligne("https://jobs.maison.com/job/222222"), "Titre": "Head of Planning", "Entreprise": "Dior"},
        {**ligne("https://jobs.maison.com/job/333333", alts=[("https://www.linkedin.com/jobs/view/4333333333/",
                                                               "LinkedIn (Offres)")]),
         "Titre": "Directeur Logistique", "Entreprise": "Cartier"},
    ], columns=SCRAPER_COLUMNS)
    feed.to_csv(tmp_path / "offres_detectees.csv", index=False)
    s.import_csv(tmp_path / "offres_detectees.csv")
    yield s
    s.close()


def _par_entreprise(store, nom):
    df = store.list_offers()
    return df[df["company"] == nom].iloc[0].to_dict()


def test_crm_offre_expiree_non_traitee_passe_en_ecarte(store):
    rolex = _par_entreprise(store, "Rolex")
    assert store.apply_link_verdicts(rolex["id"], {rolex["link"]: Verdict(EXPIREE, "410")}) == "ecartee"
    apres = store.offer(rolex["id"])
    assert apres["status"] == "Ecarte" and apres["link_status"] == EXPIREE and "410" in apres["notes"]


def test_crm_candidature_en_cours_jamais_deplacee(store):
    dior = _par_entreprise(store, "Dior")
    store.update_offer(dior["id"], {"status": "Candidature envoyee", "notes": "Envoyée le 12/11"})
    assert store.apply_link_verdicts(dior["id"], {dior["link"]: Verdict(REDIRIGE, "accueil")}) == "expiree"
    apres = store.offer(dior["id"])
    assert apres["status"] == "Candidature envoyee" and apres["notes"] == "Envoyée le 12/11"
    assert apres["link_status"] == REDIRIGE


def test_crm_lien_mort_remplace_par_l_annonce_ouverte(store):
    cartier = _par_entreprise(store, "Cartier")
    verdicts = {cartier["link"]: Verdict(REDIRIGE, "accueil"),
                "https://www.linkedin.com/jobs/view/4333333333/": Verdict(ACCESSIBLE)}
    assert store.apply_link_verdicts(cartier["id"], verdicts) == "remplace"
    apres = store.offer(cartier["id"])
    assert apres["link"] == "https://www.linkedin.com/jobs/view/4333333333/" and apres["status"] == "A analyser"


def test_crm_revérification_ignore_ecartees_et_recentes(store):
    vus = []

    def faux(items, **_):
        vus.extend(u for u, _ in items)
        return {u: Verdict(EXPIREE, "410") if "trabajo" in u else Verdict(ACCESSIBLE) for u, _ in items}

    bilan = store.verify_open_offers(verifier=faux)
    assert bilan["ecartee"] == 1 and bilan["ok"] == 2
    vus.clear()
    # Tout vient d'être vérifié, et Rolex est écartée : rien à refaire.
    assert store.verify_open_offers(verifier=faux)["verifiees"] == 0 and vus == []
    # Bouton « Vérifier les liens » : force la revérification des offres ouvertes.
    assert store.verify_open_offers(verifier=faux, older_than_hours=0)["verifiees"] == 2
