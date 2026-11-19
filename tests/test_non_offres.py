"""Articles, fiches de personnes et pages de resultats ne doivent jamais entrer au CRM."""
from merge_feed import merge_feed
from matching import est_une_offre, raison_non_offre
from sources_plus import looks_like_job_page
from storage import CRMStore


FAUX_POSITIFS = [
    # Article de presse remonte par la recherche « LVMH directeur industriel »
    ("LVMH nomme Ludovic Pauchard directeur industriel groupe",
     "https://www.zonebourse.com/cours/action/LVMH-4669/actualite/LVMH-nomme-Ludovic-Pauchard-50311822/"),
    # Fiche d'organigramme d'une personne
    ("Sandro Bertato - Direttore Operations at Moncler | The Org",
     "https://theorg.com/org/moncler-spa/org-chart/sandro-bertato"),
    # Page de resultats d'un jobboard, pas une annonce
    ("Offre (s) d'emploi Responsable de production PARIS",
     "https://fr.fashionjobs.com/fr/s/emploi/responsable-de-production-paris.html"),
    ("Hermès appoints new Chief Operating Officer", "https://www.unknown-blog.com/2026/hermes"),
]

VRAIES_OFFRES = [
    ("Responsable Logistique (F/H)",
     "https://jobs.louisvuitton.com/en/search-page/job/responsable-logistique-f-h-france-paris-LVM33450"),
    ("Head of Supply Chain", "https://ch.linkedin.com/jobs/view/head-of-supply-chain-at-swatch-group-4463041468"),
    ("Responsable Logistique VDJ",
     "https://richemont.wd3.myworkdayjobs.com/fr-FR/Richemont/job/LE-BRASSUS/Responsable-Logistique-VDJ_JR132609"),
    ("Emploi Directeur de Production, SAINT-JUST-SAINT-RAMBERT",
     "https://fr.fashionjobs.com/emploi/french-tex/Directeur-de-production,12089239.html"),
    ("Rolex Directeur de Production – Genève – Cerulean",
     "https://ceruleanjobs.ch/emplois/rolex-production-manager-geneva-2026-03-01/"),
]


def test_faux_positifs_rejetes():
    for titre, url in FAUX_POSITIFS:
        assert raison_non_offre(titre, url), titre


def test_vraies_offres_conservees():
    for titre, url in VRAIES_OFFRES:
        assert est_une_offre(titre, url), titre


def test_collecte_refuse_presse_et_organigrammes():
    assert not looks_like_job_page("https://theorg.com/org/moncler-spa/org-chart/x")
    assert not looks_like_job_page("https://www.zonebourse.com/cours/action/LVMH/actualite/x/")
    assert looks_like_job_page("https://jobs.smartrecruiters.com/AudemarsPiguet/744000152655250")


def _ligne(titre, entreprise, lien):
    return {"Titre": titre, "Entreprise": entreprise, "Pays": "France", "Secteur": "Luxe",
            "Source": "Sites Maisons de Luxe", "Lien": lien, "Niveau estimé": "Management senior",
            "Date de détection": "2026-11-19"}


def test_merge_feed_nettoie_l_historique():
    ancien = [_ligne(FAUX_POSITIFS[0][0], "LVMH", FAUX_POSITIFS[0][1])]
    nouveau = [_ligne("Directeur Supply Chain", "Hermès", "https://fr.linkedin.com/jobs/view/123")]
    titres = [r["Titre"] for r in merge_feed(ancien, nouveau, "2026-11-19")]
    assert titres == ["Directeur Supply Chain"]


def test_purge_base_garde_les_fiches_travaillees(tmp_path):
    store = CRMStore(db_path=tmp_path / "crm.sqlite3")
    csv = tmp_path / "flux.csv"
    import pandas as pd
    pd.DataFrame([_ligne("Directeur Supply Chain", "Hermès", "https://fr.linkedin.com/jobs/view/123")]).to_csv(csv, index=False)
    store.import_csv(csv)
    # Deux faux positifs deja en base (import d'avant le correctif), simules en mode legacy.
    from storage import _row_values
    with store.engine.begin() as conn:
        store._insert_or_match(conn, _row_values(_ligne(FAUX_POSITIFS[0][0], "LVMH", FAUX_POSITIFS[0][1])), "legacy")
        store._insert_or_match(conn, _row_values(_ligne(FAUX_POSITIFS[1][0], "Moncler", FAUX_POSITIFS[1][1])), "legacy")
    offres = store.list_offers()
    moncler = offres[offres["company"] == "Moncler"].iloc[0]
    # Papa a annote la fiche Moncler : elle ne doit pas disparaitre.
    store.update_offer(moncler["id"], {"notes": "Contact utile"}, expected_updated_at=moncler["updated_at"])
    assert store.purge_non_offers() == 1
    restantes = set(store.list_offers()["company"])
    assert restantes == {"Hermès", "Moncler"}
    store.close()
