"""Verifier qu'une offre est encore ouverte, pas seulement que son lien repond.

Le probleme d'origine (retour de papa) :
  * une offre fermee renvoie souvent un code 200, pas une erreur 404 ;
  * LinkedIn redirige une offre fermee vers une page de recherche generique
    (parametre ``trk=expired_jd_redir``) ;
  * un site carriere renvoie vers son accueil ou sa liste d'offres quand le
    poste a disparu : le lien « marche », mais le poste n'y est plus.

Etape par etape, ``verifier_offre`` :
  1. passe par l'API publique de la plateforme quand elle existe
     (Workday, SmartRecruiters, Lever, Greenhouse) : la reponse est sans ambiguite ;
  2. sinon, ouvre la page en suivant les redirections une par une (anti-SSRF) ;
  3. regarde le code HTTP, puis si la redirection a perdu l'identifiant du poste,
     puis le texte de la page (« offre expiree », « no longer accepting »...) ;
  4. un blocage (403, 429, CAPTCHA) n'est JAMAIS une offre expiree : « A verifier ».
"""
from __future__ import annotations

import ipaddress
import random
import re
import socket
import time
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, wait
from threading import Lock
from dataclasses import dataclass
from datetime import date
from urllib.parse import unquote, urljoin, urlsplit

import requests

# --- Statuts ------------------------------------------------------------------
# Ils tiennent dans la colonne link_status (25 caracteres max).
ACCESSIBLE = "Accessible"
EXPIREE = "Offre expirée"          # la plateforme dit que le poste est ferme
REDIRIGE = "Lien redirigé"         # le lien tombe sur l'accueil / la liste : poste introuvable
A_VERIFIER = "À vérifier"          # blocage, CAPTCHA, page muette : on ne conclut pas
INDISPONIBLE = "Indisponible"      # ancien statut (avant cette version), garde pour compatibilite
NON_VERIFIE = "Non vérifié"

STATUTS = (ACCESSIBLE, EXPIREE, REDIRIGE, A_VERIFIER, INDISPONIBLE)
MORTS = frozenset({EXPIREE, REDIRIGE, INDISPONIBLE})

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8,it;q=0.6,de;q=0.5"}
TIMEOUT = (5, 12)
MAX_BYTES = 900_000  # une page LinkedIn pese ~300 ko ; au-dela on n'a pas besoin du reste


@dataclass(frozen=True)
class Verdict:
    statut: str
    raison: str = ""
    url_finale: str = ""
    limite: bool = False  # le site nous freine (429) : inutile d'insister sur ce site

    @property
    def mort(self) -> bool:
        return self.statut in MORTS


# --- Securite : jamais d'appel vers le reseau interne ---------------------------

def public_url(url: str) -> bool:
    """Refuse IP internes, localhost et hotes sans DNS public (anti-SSRF basique)."""
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            return False
        host = parts.hostname.lower()
        if "." not in host or host.endswith((".local", ".internal", ".test")):
            return False
        addresses = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))
        if not addresses:
            return False
        for item in addresses:
            ip = ipaddress.ip_address(item[4][0])
            if not ip.is_global:
                return False
        return True
    except (OSError, ValueError, OverflowError):
        return False


# --- Outils texte ---------------------------------------------------------------

def _fold(text: str) -> str:
    """Minuscules sans accents, apostrophes unifiees : comparaisons robustes."""
    text = unicodedata.normalize("NFKD", str(text or "")).replace("\u2019", "'")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _visible_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|template)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;|&#160;", " ", html).replace("&#39;", "'").replace("&amp;", "&")
    return re.sub(r"\s+", " ", html).strip()


# Phrases qui ne figurent QUE sur une offre fermee. Volontairement precises :
# « postuler » ou « expire » seuls apparaissent aussi sur des offres ouvertes.
_MARQUEURS_FERMEE = [_fold(m) for m in (
    # Francais
    "offre n'est plus disponible", "offre n'est plus en ligne", "offre a expire", "offre expiree",
    "annonce n'est plus disponible", "annonce n'est plus en ligne", "annonce a expire",
    "annonce expiree", "poste a ete pourvu", "poste est pourvu", "poste n'est plus disponible",
    "candidatures ne sont plus acceptees", "n'accepte plus de candidatures",
    "cette offre est cloturee", "offre est cloturee", "recrutement est termine",
    # Anglais
    "no longer accepting applications", "job is no longer available", "position is no longer available",
    "posting is no longer available", "job has expired", "this job has been filled",
    "position has been filled", "job posting has expired", "job is closed", "posting has been closed",
    "no longer open", "vacancy has been filled", "job you are looking for is no longer",
    "page you are looking for no longer exists",
    # Allemand (Suisse)
    "nicht mehr verfugbar", "nicht mehr aktiv", "stelle ist bereits besetzt", "stelle wurde besetzt",
    "inserat ist abgelaufen",
    # Italien
    "non e piu disponibile", "offerta scaduta", "annuncio scaduto", "posizione e stata chiusa",
    "offerta non e piu attiva", "candidature sono chiuse",
)]
_PROTECTION = ("just a moment", "attention required", "cf-chl", "captcha", "access denied",
               "verify you are human", "are you a robot")
_PAGES_LISTE = re.compile(
    r"/(jobs?|careers?|carrieres?|emplois?|offres?|search|search-page|recherche|stellen|lavora-con-noi"
    r"|opportunites?|join-us|nous-rejoindre)/?$", re.I)


def contient_marqueur_fermee(texte: str) -> str:
    """Renvoie la phrase « offre fermee » trouvee, ou une chaine vide."""
    plie = _fold(texte)
    return next((m for m in _MARQUEURS_FERMEE if m in plie), "")


def _jeton_offre(url: str) -> str:
    """Identifiant qui designe CE poste dans l'URL (numero long ou slug du poste).

    Si une redirection le perd, on n'est plus sur l'offre.
    Ex. : .../jobs/view/4473290869 -> « 4473290869 » ; .../Responsable-Logistique-VDJ_JR132609 -> « 132609 ».
    """
    parts = urlsplit(url)
    texte = unquote(f"{parts.path}?{parts.query}")
    nombres = re.findall(r"\d{5,}", texte)
    if nombres:
        return max(nombres, key=len)
    segments = [s for s in parts.path.split("/") if s]
    dernier = segments[-1] if segments else ""
    return _fold(dernier) if len(dernier) >= 12 else ""


def redirection_hors_offre(url_depart: str, url_finale: str) -> bool:
    """True si la redirection a quitte la fiche de poste (accueil, liste, recherche)."""
    if not url_finale or url_finale == url_depart:
        return False
    if "expired_jd_redir" in url_finale:  # LinkedIn le dit en toutes lettres
        return True
    jeton = _jeton_offre(url_depart)
    if jeton:
        # L'identifiant du poste a disparu de l'adresse : on n'est plus sur l'offre.
        return jeton not in _fold(unquote(url_finale))
    # Pas d'identifiant reconnaissable : on ne conclut que si l'on atterrit
    # clairement sur l'accueil ou sur une page liste (« /careers », « /emplois »...).
    depart = urlsplit(url_depart).path.rstrip("/")
    chemin = urlsplit(url_finale).path.rstrip("/")
    return chemin != depart and (chemin == "" or bool(_PAGES_LISTE.search(chemin + "/")))


def titre_present(titre: str, texte: str) -> bool:
    """Le poste annonce figure-t-il sur la page ? (au moins 60 % des mots porteurs)"""
    vides = {"h", "f", "hf", "fh", "m", "w", "de", "du", "des", "la", "le", "les", "et", "en",
             "the", "of", "and", "a", "di", "e", "cdi", "cdd", "x"}
    mots = [m for m in re.findall(r"[a-z0-9]+", _fold(titre)) if len(m) > 1 and m not in vides]
    if not mots:
        return True
    plie = _fold(texte)
    trouves = sum(1 for m in mots if m in plie)
    return trouves / len(mots) >= 0.6


# --- Ouverture d'une page, redirections suivies une a une -----------------------

def _ouvrir(session, url: str, max_redirects: int = 6):
    """GET avec controle anti-SSRF a chaque saut. Renvoie (code, url_finale, html) ou None."""
    courant = url
    for _ in range(max_redirects + 1):
        if not public_url(courant):
            return None
        resp = session.get(courant, headers=HEADERS, allow_redirects=False, timeout=TIMEOUT, stream=True)
        with resp:
            code = resp.status_code
            location = resp.headers.get("Location")
            if code in (301, 302, 303, 307, 308) and location:
                courant = urljoin(courant, location)
                continue
            corps = b""
            for morceau in resp.iter_content(65_536):
                corps += morceau
                if len(corps) >= MAX_BYTES:
                    break
            encodage = resp.encoding or "utf-8"
            try:
                html = corps.decode(encodage, errors="replace")
            except LookupError:
                html = corps.decode("utf-8", errors="replace")
            return code, courant, html
    return None


def _get_json(session, url: str):
    """Appel d'API publique. Renvoie (code, json ou None)."""
    # Pas de redirection suivie : l'API est sur un hôte connu, une redirection serait anormale.
    resp = session.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=TIMEOUT,
                       allow_redirects=False)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, None


# --- Plateformes avec API publique ---------------------------------------------

def _hote(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _verifier_linkedin(session, url: str) -> Verdict | None:
    m = re.search(r"/jobs/view/(?:[^/?#]*-)?(\d{6,})", url)
    if not m:
        return None
    page = _ouvrir(session, f"https://www.linkedin.com/jobs/view/{m.group(1)}/")
    if page is None:
        return Verdict(A_VERIFIER, "LinkedIn injoignable")
    code, finale, html = page
    if code in (429, 999):
        return Verdict(A_VERIFIER, "LinkedIn limite les vérifications : réessaie plus tard", finale, limite=True)
    if code in (404, 410):
        return Verdict(EXPIREE, "LinkedIn : l'offre n'existe plus", finale)
    if code != 200:
        return Verdict(A_VERIFIER, f"LinkedIn a répondu {code}", finale)
    if "/jobs/view/" not in urlsplit(finale).path or "expired_jd_redir" in finale:
        return Verdict(EXPIREE, "LinkedIn : offre fermée, renvoi vers une recherche", finale)
    if "closed-job" in html or contient_marqueur_fermee(_visible_text(html)):
        return Verdict(EXPIREE, "LinkedIn : les candidatures ne sont plus acceptées", finale)
    if "authwall" in finale or "/login" in finale:
        return Verdict(A_VERIFIER, "LinkedIn demande une connexion", finale)
    return Verdict(ACCESSIBLE, "LinkedIn : offre ouverte", finale)


def _verifier_workday(session, url: str) -> Verdict | None:
    """https://<tenant>.wdN.myworkdayjobs.com/[fr-FR/]<site>/job/<...> -> API CXS."""
    host = _hote(url)
    if not host.endswith(".myworkdayjobs.com"):
        return None
    segments = [s for s in urlsplit(url).path.split("/") if s]
    if "job" not in segments:
        return None
    i = segments.index("job")
    avant = segments[:i]
    if avant and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", avant[0]):
        avant = avant[1:]
    if len(avant) != 1:
        return None
    tenant, site = host.split(".")[0], avant[0]
    api = f"https://{host}/wday/cxs/{tenant}/{site}/" + "/".join(segments[i:])
    code, data = _get_json(session, api)
    if code in (404, 410):
        return Verdict(EXPIREE, "Workday : l'offre a été retirée du site carrière", url)
    if code != 200 or not isinstance(data, dict):
        return Verdict(A_VERIFIER, f"Workday a répondu {code}", url)
    info = data.get("jobPostingInfo") or {}
    if not info:
        return Verdict(EXPIREE, "Workday : offre introuvable", url)
    if info.get("canApply") is False:
        return Verdict(EXPIREE, "Workday : candidatures fermées", url)
    fin = str(info.get("endDate") or "")[:10]
    if fin and fin < date.today().isoformat():
        return Verdict(EXPIREE, f"Workday : date limite dépassée ({fin})", url)
    return Verdict(ACCESSIBLE, "Workday : offre ouverte", url)


def _verifier_smartrecruiters(session, url: str) -> Verdict | None:
    if _hote(url) not in ("jobs.smartrecruiters.com", "careers.smartrecruiters.com"):
        return None
    m = re.match(r"/([^/]+)/(\d{6,})", urlsplit(url).path)
    if not m:
        return None
    code, data = _get_json(session, f"https://api.smartrecruiters.com/v1/companies/{m.group(1)}/postings/{m.group(2)}")
    if code in (404, 410):
        return Verdict(EXPIREE, "SmartRecruiters : offre retirée", url)
    if code == 200 and isinstance(data, dict):
        if data.get("active") is False:
            return Verdict(EXPIREE, "SmartRecruiters : offre inactive", url)
        return Verdict(ACCESSIBLE, "SmartRecruiters : offre ouverte", url)
    return None  # 400 & co : on laisse la verification generique trancher


def _verifier_lever(session, url: str) -> Verdict | None:
    if not _hote(url).endswith("lever.co"):
        return None
    m = re.match(r"/([^/]+)/([0-9a-f-]{36})", urlsplit(url).path)
    if not m:
        return None
    api_host = "api.eu.lever.co" if ".eu." in _hote(url) else "api.lever.co"
    code, _ = _get_json(session, f"https://{api_host}/v0/postings/{m.group(1)}/{m.group(2)}")
    if code in (404, 410):
        return Verdict(EXPIREE, "Lever : offre retirée", url)
    if code == 200:
        return Verdict(ACCESSIBLE, "Lever : offre ouverte", url)
    return None


def _verifier_greenhouse(session, url: str) -> Verdict | None:
    if "greenhouse.io" not in _hote(url):
        return None
    m = re.match(r"/([^/]+)/jobs/(\d+)", urlsplit(url).path)
    if not m:
        return None
    code, _ = _get_json(session, f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}")
    if code in (404, 410):
        return Verdict(EXPIREE, "Greenhouse : offre retirée", url)
    if code == 200:
        return Verdict(ACCESSIBLE, "Greenhouse : offre ouverte", url)
    return None


_PLATEFORMES = (_verifier_linkedin, _verifier_workday, _verifier_smartrecruiters,
                _verifier_lever, _verifier_greenhouse)


# --- Verification generique ---------------------------------------------------

def _verifier_page(session, url: str, titre: str) -> Verdict:
    page = _ouvrir(session, url)
    if page is None:
        return Verdict(A_VERIFIER, "Adresse refusée ou redirections en boucle")
    code, finale, html = page
    if code in (404, 410):
        return Verdict(EXPIREE, f"Page supprimée (erreur {code})", finale)
    texte = _visible_text(html)
    plie = _fold(texte[:3000])
    if code in (401, 403, 429, 503) or any(p in plie for p in _PROTECTION):
        return Verdict(A_VERIFIER, "Site protégé contre les robots : ouvre le lien toi-même",
                       finale, limite=code == 429)
    if code >= 400:
        return Verdict(A_VERIFIER, f"Le site a répondu {code}", finale)
    marqueur = contient_marqueur_fermee(texte)
    if marqueur:
        return Verdict(EXPIREE, f"La page indique : « {marqueur} »", finale)
    if redirection_hors_offre(url, finale):
        chemin = urlsplit(finale).path.rstrip("/")
        if chemin and not _PAGES_LISTE.search(chemin + "/") and _jeton_offre(finale):
            # On atterrit sur UNE autre fiche (lien de suivi, nouvelle référence...) :
            # peut-être la même offre republiée. Papa tranche.
            return Verdict(A_VERIFIER, "Le lien mène vers une autre annonce : vérifie le poste", finale)
        return Verdict(REDIRIGE, "Le lien renvoie vers la page carrière, plus vers le poste", finale)
    if titre and len(texte) > 800 and not titre_present(titre, texte):
        # Page bien remplie mais sans le poste : sans doute un autre contenu.
        # Pas assez sur pour l'archiver : papa tranche.
        return Verdict(A_VERIFIER, "Le poste n'apparaît pas sur la page", finale)
    return Verdict(ACCESSIBLE, "Page de l'offre accessible", finale)


def verifier_offre(url: str, titre: str = "", session=None) -> Verdict:
    """Statut d'une offre : Accessible / Offre expiree / Lien redirige / A verifier."""
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")):
        return Verdict(A_VERIFIER, "Pas de lien web à vérifier")
    if not public_url(url):
        return Verdict(A_VERIFIER, "Adresse non publique : vérification refusée")
    propre = session is None
    session = session or requests.Session()
    try:
        for plateforme in _PLATEFORMES:
            verdict = plateforme(session, url)
            if verdict is not None:
                return verdict
        return _verifier_page(session, url, titre)
    except requests.RequestException as exc:
        return Verdict(A_VERIFIER, f"Site injoignable ({type(exc).__name__})")
    finally:
        if propre:
            session.close()


def check_link(url: str, titre: str = "") -> str:
    """Compatibilite avec l'ancien appel : renvoie seulement le statut."""
    return verifier_offre(url, titre).statut


# --- Verification par lot (scan et bouton « Verifier tous les liens ») ----------

def _famille(url: str) -> str:
    """Un fil par site : on ne martele jamais le meme serveur en parallele."""
    host = _hote(url)
    return "linkedin" if host == "linkedin.com" or host.endswith(".linkedin.com") else host


def _cle(url: str) -> str:
    """Une meme offre LinkedIn existe sous plusieurs adresses (fr., ch., www., avec slug) :
    on ne l'appelle qu'une fois."""
    m = re.search(r"linkedin\.com/jobs/view/(?:[^/?#]*-)?(\d{6,})", url)
    return f"linkedin:{m.group(1)}" if m else url


def verifier_lot(items, workers: int = 6, pause=(0.4, 1.0), pause_linkedin=(4.0, 7.0),
                 pause_limite=(20.0, 30.0), verifier=verifier_offre, sleep=time.sleep,
                 on_progress=None) -> dict:
    """items : iterable de (url, titre). Renvoie {url: Verdict}.

    Etape par etape :
      1. les adresses d'une meme offre sont fusionnees (une seule requete) ;
      2. les liens sont regroupes par site, chaque site dans son propre fil,
         lien apres lien, avec une pause (4 a 7 s pour LinkedIn, qui bloque vite) ;
      3. au premier refus 429, on attend 20 a 30 s et on retente UNE fois ;
         au second, les liens restants de ce site passent en « A verifier »
         sans etre appeles : on retentera au prochain scan.
    """
    par_cle: dict[str, tuple[str, str, list[str]]] = {}
    for url, titre in items:
        url = str(url or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        cle = _cle(url)
        if cle not in par_cle:
            par_cle[cle] = (url, str(titre or ""), [])
        par_cle[cle][2].append(url)
    groupes = defaultdict(list)
    for url, titre, alias in par_cle.values():
        groupes[_famille(url)].append((url, titre, alias))
    resultats: dict[str, Verdict] = {}
    total, verrou = len(par_cle), Lock()
    etat = {"fait": 0, "site": ""}

    def noter(alias, verdict, site):
        with verrou:
            for u in alias:
                resultats[u] = verdict
            etat["fait"] += 1
            etat["site"] = site

    def un_lien(url, titre, session):
        try:
            return verifier(url, titre, session=session)
        except Exception as exc:  # une page bizarre ne doit jamais casser tout le scan
            return Verdict(A_VERIFIER, f"Vérification impossible ({type(exc).__name__})")

    def traiter(famille, liens):
        attente = pause_linkedin if famille == "linkedin" else pause
        session, deja_freine = requests.Session(), False
        try:
            for index, (url, titre, alias) in enumerate(liens):
                if index:
                    sleep(random.uniform(*attente))
                verdict = un_lien(url, titre, session)
                if verdict.limite and not deja_freine:
                    deja_freine = True
                    sleep(random.uniform(*pause_limite))
                    verdict = un_lien(url, titre, session)
                noter(alias, verdict, famille)
                if verdict.limite:
                    for _, _, reste in liens[index + 1:]:
                        noter(reste, Verdict(A_VERIFIER, "Site saturé : vérification reportée"), famille)
                    break
        finally:
            session.close()

    if groupes:
        # La progression est rapportée par le fil principal : Streamlit refuse
        # qu'un fil secondaire touche à l'interface.
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(groupes)))) as pool:
            futures = [pool.submit(traiter, f, l) for f, l in groupes.items()]
            while True:
                _, en_cours = wait(futures, timeout=0.5)
                if on_progress:
                    on_progress(etat["fait"], total, etat["site"])
                if not en_cours:
                    break
            for f in futures:
                f.result()
    return resultats
