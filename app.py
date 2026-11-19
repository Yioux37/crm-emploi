"""CRM carrière luxe / opérations - interface Streamlit.

Données personnelles en base, jamais dans le flux GitHub du scanner.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from link_health import check_link
from matching import canonical_url
from notifications import CLOSED, collect_alerts
from scoring import DEFAULT_PREFERENCES, calculate_score
from source_catalog import SEARCH_SITES, NEWS_SITES, MANUAL_OR_RESTRICTED, catalog_totals
from sources_plus import read_sources_config
from market_signals import signal_guidance
from storage import (CRMStore, ConcurrentEditError, CONTACT_KINDS, MANUAL_SOURCES,
                     PRIORITIES, STATUSES, TARGET_STATUSES)

ROOT = Path(__file__).resolve().parent
STATUS_LABELS = {
    "A analyser": "À analyser", "A postuler": "À postuler", "Candidature envoyee": "Candidature envoyée",
    "Reseau / Approche directe": "Réseau / Approche directe", "Entretien 1": "Entretien 1",
    "Entretien final / Shortlist": "Entretien final / Shortlist",
    "Refuse / Sans suite": "Refusé / Sans suite", "Ecarte": "Écarté",
}
PAGES = ["Tableau de bord", "Pipeline", "Relances", "Signaux marché", "Coulisses", "Réglages"]

st.set_page_config(page_title="CRM Carrière | Direction & Supply Chain", page_icon="◆", layout="wide")
st.markdown("""
<style>
/* Typographie : serif éditorial pour les titres, sans lisible pour le corps. */
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=Inter:wght@300;400;500;600&display=swap');

:root{
  --ink:#15201B; --sage:#6E7A72; --line:#E4E8E5; --green:#1F4D3A; --green-700:#173A2B;
  --card:#FBFCFB; --alert:#9A3B34;
}

html, body, .stApp, [class*="css"]{
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}
.stApp{ background:#FFFFFF; color:var(--ink); }
.block-container{ padding-top:2.1rem; padding-bottom:4rem; max-width:1320px; }

/* Titres en serif */
h1,h2,h3,h4,
[data-testid="stHeading"] h1,[data-testid="stHeading"] h2,[data-testid="stHeading"] h3{
  font-family:'Cormorant Garamond',Georgia,serif !important;
  font-weight:500 !important; letter-spacing:.3px; color:var(--ink);
}
h1,[data-testid="stHeading"] h1{ font-size:2.5rem !important; line-height:1.12; }
h2{ font-size:2rem !important; }
h3{ font-size:1.55rem !important; }

/* Texte secondaire */
[data-testid="stCaptionContainer"], small{ color:var(--sage) !important; }

/* Cartes de chiffres */
[data-testid="stMetric"]{
  background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px 20px;
}
[data-testid="stMetricLabel"] p{
  text-transform:uppercase; letter-spacing:1.4px; font-size:.68rem !important;
  color:var(--sage) !important; font-weight:600;
}
[data-testid="stMetricValue"]{
  font-family:'Cormorant Garamond',Georgia,serif; font-weight:500;
  font-size:2.2rem !important; color:var(--ink);
}

/* Barre latérale */
[data-testid="stSidebar"]{ background:#F7F9F7; border-right:1px solid var(--line); }
[data-testid="stSidebar"] [data-testid="stHeading"] h1{ font-size:1.6rem !important; }

/* Boutons */
.stButton>button, .stDownloadButton>button, .stFormSubmitButton>button{
  border-radius:8px; border:1px solid var(--line); font-weight:500; letter-spacing:.2px;
  transition:all .15s ease;
}
.stButton>button:hover, .stDownloadButton>button:hover{ border-color:var(--green); color:var(--green); }
.stButton>button[kind="primary"], .stFormSubmitButton>button[kind="primary"]{
  background:var(--green); border-color:var(--green); color:#fff;
}
.stButton>button[kind="primary"]:hover, .stFormSubmitButton>button[kind="primary"]:hover{
  background:var(--green-700); border-color:var(--green-700); color:#fff;
}

a, a:visited{ color:var(--green); }

/* Onglets : libellés en petites capitales, soulignement vert */
.stTabs [data-baseweb="tab-list"]{ gap:26px; border-bottom:1px solid var(--line); }
.stTabs [data-baseweb="tab"]{
  padding:8px 2px; font-size:.78rem; text-transform:uppercase; letter-spacing:1.3px; color:var(--sage);
}
.stTabs [aria-selected="true"]{ color:var(--green) !important; }
.stTabs [data-baseweb="tab-highlight"]{ background:var(--green); }

/* Conteneurs encadrés et tableaux */
[data-testid="stVerticalBlockBorderWrapper"]{ border-radius:12px; }
[data-testid="stDataFrame"]{ border:1px solid var(--line); border-radius:10px; }
hr{ border-color:var(--line); }

/* Badge de score : rond, lisible en entier, couleur selon le niveau */
.score-badge{ width:58px; height:58px; border-radius:50%; display:flex; flex-direction:column;
  align-items:center; justify-content:center; font-family:'Cormorant Garamond',Georgia,serif;
  font-size:1.55rem; font-weight:600; line-height:1; border:2px solid; }
.score-badge small{ font-family:'Inter',sans-serif; font-size:.55rem; letter-spacing:.8px;
  color:inherit !important; opacity:.75; margin-top:2px; }
.tier-high{ color:#1F4D3A; border-color:#1F4D3A; background:#EEF4F0; }
.tier-mid{ color:#8A6A1F; border-color:#C9A54A; background:#FBF6E9; }
.tier-low{ color:#6E7A72; border-color:#C9D1CC; background:#F6F8F7; }

/* Ligne d'offre compacte */
.offer-title{ font-weight:600; font-size:1rem; color:var(--ink); line-height:1.3; }
.offer-meta{ color:var(--sage); font-size:.83rem; margin-top:4px; }
.pill{ display:inline-block; padding:2px 9px; border-radius:999px; font-size:.72rem;
  border:1px solid var(--line); background:#fff; color:var(--ink); margin-right:6px; }
.pill-new{ background:#1F4D3A; border-color:#1F4D3A; color:#fff; }

/* Frise d'avancement : une case par étape */
.funnel{ display:flex; gap:8px; margin:6px 0 22px 0; flex-wrap:wrap; }
.funnel-step{ flex:1 1 110px; border:1px solid var(--line); border-radius:10px; padding:10px 12px;
  background:var(--card); }
.funnel-step .n{ font-family:'Cormorant Garamond',Georgia,serif; font-size:1.7rem; line-height:1; }
.funnel-step .l{ font-size:.66rem; text-transform:uppercase; letter-spacing:1px; color:var(--sage); margin-top:4px; }
.funnel-step.closed{ background:#F6F3F2; border-style:dashed; }
.funnel-step.active{ border-color:var(--green); }

/* En-tête de section d'étape dans le Pipeline */
.stage-head{ display:flex; align-items:baseline; gap:10px; margin:18px 0 6px 0; }
.stage-head .t{ font-family:'Cormorant Garamond',Georgia,serif; font-size:1.35rem; }
.stage-head .c{ color:var(--sage); font-size:.85rem; }

/* Épure : on masque le pied de page Streamlit */
footer{ visibility:hidden; height:0; }
</style>
""", unsafe_allow_html=True)


def secret(key: str) -> str:
    if os.getenv(key):
        return os.environ[key]
    try:
        return str(st.secrets.get(key, "") or "")
    except (FileNotFoundError, AttributeError):
        return ""


def require_password():
    pwd = secret("APP_PASSWORD")
    if not pwd:
        st.error("Accès fermé : configure **APP_PASSWORD** pour protéger tes candidatures.")
        st.code('APP_PASSWORD="mot-de-passe-personnel" streamlit run app.py', language="bash")
        st.caption("Dans Streamlit Cloud, ajoute APP_PASSWORD dans les Secrets de l'application.")
        st.stop()
    if st.session_state.get("authenticated"):
        return
    st.title("Espace privé de recherche d'emploi")
    st.write("Connecte-toi pour accéder aux annonces, contacts et notes de candidature.")
    with st.form("login"):
        entered = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Accéder au CRM", type="primary")
    if submitted:
        import hmac
        if hmac.compare_digest(entered.encode(), pwd.encode()):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    st.stop()


require_password()


@st.cache_resource(show_spinner=False)
def get_store() -> CRMStore:
    # Les identifiants Postgres restent exclusivement dans les secrets de l'hôte.
    return CRMStore(db_url=secret("DATABASE_URL") or None)


try:
    store = get_store()
    imported = store.bootstrap(ROOT)
except Exception as exc:
    st.error(f"Base de données inaccessible : {exc}")
    st.stop()

if "notice" in st.session_state:
    st.success(st.session_state.pop("notice"))

prefs = store.preferences()
df = store.list_offers()
if not df.empty:
    scored = [calculate_score(r, prefs) for r in df.to_dict("records")]
    df["score"] = [v[0] for v in scored]
    df["why_score"] = [" • ".join(v[1]) for v in scored]
    df["is_closed"] = df["status"].isin(CLOSED)
else:
    df["score"] = pd.Series(dtype=int)
    df["why_score"] = pd.Series(dtype=str)
    df["is_closed"] = pd.Series(dtype=bool)
alerts = collect_alerts(store)
today = date.today().isoformat()


def go_to_offer(offer_id: str):
    st.session_state["chosen_offer_id"] = offer_id
    st.session_state["nav_target"] = "Pipeline"
    st.rerun()


st.sidebar.title("Mon espace carrière")
st.sidebar.caption("Direction Opérations & Supply Chain · Luxe")
if store.is_local:
    st.sidebar.caption("SQLite local : pour un hébergement Cloud, configure une base PostgreSQL persistante.")
if "nav_target" in st.session_state:
    st.session_state["current_page"] = st.session_state.pop("nav_target")
st.sidebar.radio("Navigation", PAGES, key="current_page", label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.caption("Collecte automatique : GitHub Actions met a jour "
                   "les annonces publiques du depot.")
def run_scan_with_progress(timeout_s: int = 900):
    """Lance scraper.py et anime une barre de progression pendant le scan.

    Etape par etape :
      1. SCAN_PROGRESS=json demande au scraper d'ecrire des lignes "@@PROGRESS {...}".
      2. subprocess.Popen (et non subprocess.run) permet de lire ces lignes
         EN DIRECT, au lieu d'attendre la fin du scan.
      3. Chaque ligne met a jour st.progress (barre) et un texte d'etape.
    Renvoie (code de sortie, 5000 derniers caracteres du journal).
    """
    import json as _json, os as _os, time as _time
    env = dict(_os.environ, SCAN_PROGRESS="json", PYTHONUNBUFFERED="1")
    bar = st.sidebar.progress(0.0, text="Démarrage du scan…")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "scraper.py"), "--output", str(ROOT / "offres_detectees.csv"),
         "--report", str(ROOT / "scan_rapport.json")],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, bufsize=1,
    )
    started, log = _time.monotonic(), []
    for line in proc.stdout:
        if _time.monotonic() - started > timeout_s:
            proc.kill()
            raise subprocess.TimeoutExpired(proc.args, timeout_s)
        if line.startswith("@@PROGRESS "):
            info = _json.loads(line[len("@@PROGRESS "):])
            if info.get("done_all"):
                bar.progress(1.0, text="Scan terminé")
                continue
            detail = f" · {info['done']}/{info['total']}" if info.get("total") else ""
            label = f" · {info['label']}" if info.get("label") else ""
            eta = f" · {info['eta']}" if info.get("eta") else ""
            bar.progress(float(info.get("overall", 0)),
                         text=f"Étape {info['step']}/{info['steps']} : {info['name']}{detail}{label}{eta}")
        else:
            log.append(line)
    code = proc.wait()
    return code, "".join(log)[-5000:]


if st.sidebar.button("Rechercher de nouvelles offres", width="stretch"):
    try:
        code, journal = run_scan_with_progress()
        if code:
            st.sidebar.error("Le scan a échoué : aucune donnée existante n'a été effacée.")
            with st.sidebar.expander("Détails du scan"):
                st.code(journal)
        else:
            new_count = store.import_csv(ROOT / "offres_detectees.csv")
            st.session_state["notice"] = f"Scan terminé : {new_count} nouvelle(s) opportunité(s) dans le CRM."
            st.rerun()
    except subprocess.TimeoutExpired:
        st.sidebar.error("Scan trop long : l'opération a été interrompue, sans suppression d'offre.")

if st.sidebar.button("Actualiser le flux", width="stretch"):
    try:
        count = store.import_csv(ROOT / "offres_detectees.csv")
        st.session_state["notice"] = f"Flux rechargé : {count} nouvelle(s) offre(s)."
        st.rerun()
    except Exception as exc:
        st.sidebar.error(f"Erreur d'import : {exc}")

st.sidebar.divider()
st.sidebar.subheader("Filtres")
FILTER_KEYS = ("f_countries", "f_statuses", "f_priorities", "f_sector", "f_min_score", "f_search")


def reset_filters():
    """Callback : vide l'état des filtres AVANT que les widgets soient redessinés."""
    for key in FILTER_KEYS:
        st.session_state.pop(key, None)


# Toutes les étapes sont affichées par défaut : les offres refusées ont
# désormais leur propre tableau dans le Pipeline, elles ne polluent plus la liste.
selected_countries = st.sidebar.multiselect(
    "Pays", ["France", "Suisse", "Italie"], default=["France", "Suisse", "Italie"], key="f_countries"
)
selected_statuses = st.sidebar.multiselect(
    "Statut", STATUSES, default=STATUSES, key="f_statuses", format_func=lambda s: STATUS_LABELS.get(s, s)
)
selected_priorities = st.sidebar.multiselect("Priorité", PRIORITIES, default=PRIORITIES, key="f_priorities")
selected_sector = st.sidebar.selectbox(
    "Secteur", ["Tous", "Horlogerie", "Joaillerie / Bijouterie", "Textile / Couture", "Luxe"], key="f_sector"
)
min_score = st.sidebar.slider("Score minimum", 0, 100, 0, step=5, key="f_min_score")
search = st.sidebar.text_input("Recherche", placeholder="Poste, maison, contact…", key="f_search")
st.sidebar.button("Réinitialiser les filtres", on_click=reset_filters, width="stretch")

visible = df.copy()
if not visible.empty:
    mask = (visible["country"].isin(selected_countries) & visible["status"].isin(selected_statuses)
            & visible["priority"].isin(selected_priorities) & (visible["score"] >= min_score))
    if selected_sector != "Tous":
        mask &= visible["sector"].str.contains(selected_sector, case=False, regex=False, na=False)
    if search:
        cols = ["title", "company", "sector", "contact", "notes", "country"]
        search_match = pd.Series(False, index=visible.index)
        for col in cols:
            search_match |= visible[col].astype(str).str.contains(search, case=False, regex=False, na=False)
        mask &= search_match
    visible = visible[mask].sort_values(["score", "detected_on"], ascending=[False, False])

n_hidden = len(df) - len(visible)

st.title("CRM Candidatures")
st.caption("Un espace privé pour repérer les opportunités, préparer les candidatures et ne manquer aucune relance.")

if store.backup_error:
    st.warning("Une sauvegarde locale a échoué : " + store.backup_error)

if n_hidden:
    fc1, fc2 = st.columns([4, 1], vertical_alignment="center")
    fc1.warning(f"**{n_hidden} offre(s) masquée(s)** par les filtres de la barre latérale "
                f"({len(visible)} affichée(s) sur {len(df)}).")
    fc2.button("Tout afficher", on_click=reset_filters, width="stretch", key="reset_top")

if imported["legacy"]:
    st.info(f"{imported['legacy']} offre(s) importée(s) depuis l'ancien CSV. Tes notes et statuts sont conservés.")


def table_height(n_rows: int) -> int:
    """Hauteur qui affiche TOUTES les lignes (35 px par ligne + en-tête).

    Avant : plafond à 640 px, donc ~15 lignes visibles et le reste caché
    dans un défilement interne au tableau, peu visible.
    """
    return 35 * (max(n_rows, 1) + 1) + 3


def offer_label(r) -> str:
    return f"{r['company']} · {r['title']} ({r['country']})"


def short_table(rows: pd.DataFrame, *, show_status: bool = True):
    if rows.empty:
        st.info("Aucune offre pour cette sélection.")
        return
    cols = ["title", "company", "country", "score", "status", "priority", "next_action", "link"]
    if not show_status:
        cols.remove("priority")
    ui = rows[cols].rename(columns={
        "title": "Poste", "company": "Maison", "country": "Pays", "score": "Score",
        "status": "Statut", "priority": "Priorité", "next_action": "Prochaine action", "link": "Lien"
    })
    st.dataframe(
        ui, hide_index=True, width="stretch",
        column_config={
            "Score": st.column_config.ProgressColumn("Score /100", min_value=0, max_value=100, format="%d"),
            "Lien": st.column_config.LinkColumn("Annonce", display_text="Ouvrir"),
        },
    )


def score_badge(score: int) -> str:
    """Badge rond : le score s'affiche EN ENTIER (st.metric le tronquait en « 9… »)."""
    score = int(score)
    tier = "tier-high" if score >= 85 else "tier-mid" if score >= 70 else "tier-low"
    return f"<div class='score-badge {tier}'>{score}<small>/100</small></div>"


def _esc(text: object) -> str:
    """Échappe le HTML : un titre d'annonce ne doit jamais casser la page."""
    import html
    return html.escape(str(text or ""))


def inline_offer_buttons(offers_subset: pd.DataFrame, prefix: str, limit: int = 5):
    """Liste d'offres compacte : badge de score | poste + infos | bouton."""
    new_cutoff = (date.today() - timedelta(days=3)).isoformat()
    for _, r in offers_subset.head(limit).iterrows():
        with st.container(border=True):
            a, b, c = st.columns([0.9, 6, 1.4], vertical_alignment="center")
            a.markdown(score_badge(r["score"]), unsafe_allow_html=True)
            pills = f"<span class='pill'>{_esc(STATUS_LABELS.get(r['status'], r['status']))}</span>"
            if r["detected_on"] >= new_cutoff:
                pills = "<span class='pill pill-new'>Nouveau</span>" + pills
            b.markdown(
                f"<div class='offer-title'>{_esc(r['title'])}</div>"
                f"<div class='offer-meta'>{pills}{_esc(r['company'])} · {_esc(r['country'])}"
                f" · détectée le {_esc(r['detected_on'])}</div>",
                unsafe_allow_html=True)
            if c.button("Ouvrir", key=f"{prefix}_{r['id']}", width="stretch"):
                go_to_offer(r["id"])


# ============================================================================
#  Vues et éditeurs du Pipeline (définis avant le routage ; ils utilisent les
#  variables globales store, df, visible, prefs, today, alerts ci-dessus).
# ============================================================================

FUNNEL = ["A analyser", "A postuler", "Candidature envoyee",
          "Reseau / Approche directe", "Entretien 1", "Entretien final / Shortlist"]


CLOSED_STAGES = [x for x in STATUSES if x in CLOSED]


def stage_editor(rows: pd.DataFrame, key: str):
    """Un tableau éditable (statut, priorité) pour UNE étape, avec son bouton d'enregistrement.

    Changer le statut puis enregistrer fait passer la ligne dans le tableau de l'étape choisie.
    """
    editor_data = rows.set_index("id")[["title", "company", "country", "score", "status",
                                        "priority", "next_action", "link"]].rename(columns={
        "title": "Poste", "company": "Maison", "country": "Pays", "score": "Score",
        "status": "Statut", "priority": "Priorité", "next_action": "Prochaine action", "link": "Lien"})
    edited = st.data_editor(
        editor_data, key=f"tbl_{key}", hide_index=True, width="stretch",
        height=table_height(len(editor_data)),
        column_config={
            "Poste": st.column_config.TextColumn("Poste", width="large"),
            "Statut": st.column_config.SelectboxColumn("Statut", options=STATUSES, required=True),
            "Priorité": st.column_config.SelectboxColumn("Priorité", options=PRIORITIES, required=True),
            "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
            "Lien": st.column_config.LinkColumn("Annonce", display_text="Ouvrir")},
        disabled=["Poste", "Maison", "Pays", "Score", "Prochaine action", "Lien"])
    if st.button("Enregistrer", type="primary", key=f"save_{key}"):
        changed = 0
        try:
            for offer_id in editor_data.index:
                delta = {}
                for col, field in (("Statut", "status"), ("Priorité", "priority")):
                    if edited.loc[offer_id, col] != editor_data.loc[offer_id, col]:
                        delta[field] = edited.loc[offer_id, col]
                if delta:
                    old = df[df["id"] == offer_id].iloc[0]
                    changed += int(store.update_offer(offer_id, delta, expected_updated_at=old["updated_at"]))
            st.session_state["notice"] = f"{changed} fiche(s) mise(s) à jour."
            st.rerun()
        except (ConcurrentEditError, ValueError) as exc:
            st.error(str(exc))


def stage_header(status: str, count: int):
    st.markdown(f"<div class='stage-head'><span class='t'>{_esc(STATUS_LABELS.get(status, status))}</span>"
                f"<span class='c'>{count} offre(s)</span></div>", unsafe_allow_html=True)


def offers_table_view(rows):
    """Vue Table : un tableau par étape d'avancement.

    Les étapes en cours s'affichent dans l'ordre du parcours. Les offres refusées
    ou écartées sont regroupées plus bas, chacune dans son tableau : visibles,
    mais séparées des candidatures actives.
    """
    active = [s_ for s_ in STATUSES if s_ not in CLOSED]
    shown = 0
    for status in active:
        subset = rows[rows["status"] == status]
        if subset.empty:
            continue
        stage_header(status, len(subset))
        stage_editor(subset, key=status)
        shown += len(subset)
    if not shown:
        st.info("Aucune candidature en cours pour cette sélection.")

    closed_rows = rows[rows["status"].isin(CLOSED)]
    st.divider()
    st.markdown(f"#### Refusées et écartées · {len(closed_rows)}")
    if closed_rows.empty:
        st.caption("Aucune offre refusée ou écartée. Pour en classer une, choisis "
                   "« Refuse / Sans suite » ou « Ecarte » dans sa colonne Statut puis enregistre.")
    for status in CLOSED_STAGES:
        subset = closed_rows[closed_rows["status"] == status]
        if subset.empty:
            continue
        with st.expander(f"{STATUS_LABELS.get(status, status)} · {len(subset)}", expanded=True):
            stage_editor(subset, key=status)

    export_cols = ["title", "company", "sector", "country", "source", "link", "level",
                   "detected_on", "score", "status", "priority", "contact", "last_action",
                   "next_action", "notes", "link_status"]
    st.download_button("Exporter la sélection (CSV)",
                       data=rows[export_cols].to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"candidatures_{today}.csv", mime="text/csv")


def offers_board_view(rows):
    """Vue Board (kanban) : une colonne par étape, cartes déplaçables par menu."""
    st.caption("Fais avancer une carte avec le menu « Déplacer vers ». "
               "Les offres refusées et écartées sont dans la vue Table, en bas.")
    columns = st.columns(len(FUNNEL))
    for col, status in zip(columns, FUNNEL):
        subset = rows[rows["status"] == status]
        with col:
            st.markdown(f"<div style='font-size:.68rem;letter-spacing:1px;text-transform:uppercase;"
                        f"color:#6E7A72;padding-bottom:6px'>{STATUS_LABELS.get(status, status)} · {len(subset)}</div>",
                        unsafe_allow_html=True)
            for _, r in subset.head(25).iterrows():
                with st.container(border=True):
                    st.markdown(f"**{r['title'][:42]}**")
                    st.caption(f"{r['company']} · {r['country']} · {r['score']}/100")
                    moved = st.selectbox("Déplacer vers", STATUSES, index=STATUSES.index(status),
                                         key=f"board_{r['id']}", label_visibility="collapsed")
                    if moved != status:
                        try:
                            store.update_offer(r["id"], {"status": moved}, expected_updated_at=r["updated_at"])
                            st.rerun()
                        except (ConcurrentEditError, ValueError) as exc:
                            st.error(str(exc))


def offers_grouped_view(rows):
    """Vue Groupée : la base repliée par statut, pays, maison ou priorité."""
    field_label = st.selectbox("Regrouper par", ["Statut", "Pays", "Maison", "Priorité"], key="group_by")
    field = {"Statut": "status", "Pays": "country", "Maison": "company", "Priorité": "priority"}[field_label]
    for value, grp in rows.groupby(field):
        st.markdown(f"**{value or '—'}** · {len(grp)}")
        short_table(grp)


def offer_detail_and_add():
    """Fiche de candidature détaillée + ajout manuel (réseau, chasseur, lien LinkedIn)."""
    st.divider()
    st.subheader("Fiche de candidature")
    ids = visible["id"].tolist()
    if ids:
        labels = {r["id"]: offer_label(r) for r in visible.to_dict("records")}
        preselected = st.session_state.get("chosen_offer_id")
        idx = ids.index(preselected) if preselected in ids else 0
        chosen = st.selectbox("Sélectionne une opportunité", ids, index=idx,
                              format_func=lambda x: labels.get(x, x), key="fiche_sel")
        st.session_state["chosen_offer_id"] = chosen
        current = store.offer(chosen)
        with st.container(border=True):
            dl, dr = st.columns([3, 1])
            with dl:
                st.markdown(f"### {current['title']}")
                st.caption(f"{current['company']} · {current['country']} · {current['sector']}")
            with dr:
                score, reasons = calculate_score(current, prefs)
                st.caption("Compatibilité")
                st.markdown(score_badge(score), unsafe_allow_html=True)
            with st.expander("Comprendre le score", expanded=False):
                st.write(" · ".join(reasons))
                st.caption("Score heuristique personnalisable, pas une probabilité de recrutement.")
            offer_links = store.links_for(chosen)
            if offer_links:
                st.markdown("**Annonces et sources**")
                for alternate in offer_links:
                    st.markdown(f"- [{alternate['source']}]({alternate['url']})")
            if current["link"].startswith(("https://", "http://")):
                x, y = st.columns([1, 3])
                with x:
                    if st.button("Vérifier le lien", key=f"check_{chosen}"):
                        with st.spinner("Vérification du lien…"):
                            link_state = check_link(current["link"])
                            store.record_link_check(chosen, link_state)
                        st.session_state["notice"] = f"Lien : {link_state}. Un blocage d'accès n'est pas une annonce expirée."
                        st.rerun()
                with y:
                    st.caption(f"État du lien : {current['link_status']}" +
                               (f" · Vérifié le {current['link_checked_at'][:10]}" if current['link_checked_at'] else ""))
            with st.form(f"edit_{chosen}"):
                c1, c2, c3 = st.columns([2, 1, 1])
                f_status = c1.selectbox("Statut", STATUSES, index=STATUSES.index(current["status"]))
                f_priority = c2.selectbox("Priorité", PRIORITIES, index=PRIORITIES.index(current["priority"]))
                f_contact = c3.text_input("Contact / Chasseur", value=current["contact"])
                d1, d2 = st.columns(2)
                f_last = d1.text_input("Dernière action (AAAA-MM-JJ)", value=current["last_action"], placeholder="2026-11-17")
                f_next = d2.text_input("Prochaine action (AAAA-MM-JJ)", value=current["next_action"], placeholder="2026-11-24")
                f_notes = st.text_area("Notes et prochaines étapes", value=current["notes"], height=130)
                submitted = st.form_submit_button("Enregistrer la fiche", type="primary")
            if submitted:
                try:
                    store.update_offer(chosen, {"status": f_status, "priority": f_priority, "contact": f_contact,
                                                "last_action": f_last, "next_action": f_next,
                                                "notes": f_notes}, expected_updated_at=current["updated_at"])
                    st.session_state["notice"] = "Fiche enregistrée. Historique mis à jour."
                    st.rerun()
                except (ValueError, ConcurrentEditError) as exc:
                    st.error(str(exc))
            with st.expander("Historique des actions"):
                for event in store.timeline(chosen):
                    st.markdown(f"**{event['when_at'][:16].replace('T', ' ')} UTC** — {event['action']}")

    with st.expander("Ajouter une opportunité (réseau, chasseur, post ou offre LinkedIn)"):
        st.caption("Vu un post « je recrute » ou une offre sur LinkedIn ? Colle son lien : "
                   "l'origine est détectée automatiquement.")
        with st.form("add_manual", clear_on_submit=True):
            a, b = st.columns(2)
            m_company = a.text_input("Maison / Entreprise *")
            m_title = b.text_input("Intitulé du poste *")
            c, d, e = st.columns(3)
            m_country = c.selectbox("Pays", ["France", "Suisse", "Italie"])
            m_sector = d.selectbox("Secteur", ["Horlogerie", "Joaillerie / Bijouterie", "Textile / Couture", "Luxe"])
            m_priority = e.selectbox("Priorité", PRIORITIES, index=1)
            m_status = st.selectbox("Statut initial", STATUSES, index=1)
            m_contact = st.text_input("Contact / Chasseur")
            m_url = st.text_input("Lien vers l'offre ou le post LinkedIn (facultatif)")
            m_origin = st.selectbox("Origine (si pas de lien LinkedIn)", MANUAL_SOURCES)
            m_next = st.text_input("Prochaine action (AAAA-MM-JJ, facultatif)")
            m_notes = st.text_area("Notes")
            if st.form_submit_button("Ajouter au CRM"):
                if not m_title.strip() or not m_company.strip():
                    st.error("Le poste et l'entreprise sont requis.")
                elif m_url and not canonical_url(m_url):
                    st.error("Le lien doit être une URL http(s) valide ou rester vide.")
                else:
                    try:
                        if m_next:
                            date.fromisoformat(m_next)
                        added = store.add_manual({"title": m_title, "company": m_company, "sector": m_sector,
                                                  "country": m_country, "priority": m_priority, "status": m_status,
                                                  "contact": m_contact, "link": m_url, "source": m_origin,
                                                  "next_action": m_next, "notes": m_notes, "last_action": today})
                        st.session_state["notice"] = "Opportunité créée." if added else "Cette opportunité existe déjà."
                        st.rerun()
                    except ValueError:
                        st.error("Date incorrecte, utilise le format AAAA-MM-JJ.")


def pipeline_offers_tab():
    if visible.empty:
        st.info("Aucune offre ne correspond aux filtres. Ajuste-les dans la barre latérale.")
    else:
        view = st.radio("Vue", ["Table", "Board", "Groupé"], horizontal=True,
                        key="offers_view", label_visibility="collapsed")
        hidden = len(df) - len(visible)
        st.caption(f"**{len(visible)} offre(s) affichée(s)** sur {len(df)} en base"
                   + (f" · {hidden} masquée(s) par les filtres de la barre latérale" if hidden else ""))
        if view == "Table":
            offers_table_view(visible)
        elif view == "Board":
            offers_board_view(visible[~visible["is_closed"]])
        else:
            offers_grouped_view(visible)
    offer_detail_and_add()


def reseau_tab():
    st.caption("Chasseurs, DRH et contacts réseau : le moteur d'une recherche de dirigeant. "
               "Une date de prochaine relance les fait remonter dans l'onglet Relances.")
    cdf = store.list_contacts()
    due = cdf[(cdf["next_contact"] != "") & (cdf["next_contact"] <= today)] if not cdf.empty else cdf
    m1, m2, m3 = st.columns(3)
    m1.metric("Contacts", len(cdf))
    m2.metric("À relancer", len(due))
    m3.metric("Chasseurs", int((cdf["kind"] == "Chasseur de têtes").sum()) if not cdf.empty else 0)
    if not cdf.empty:
        order = cdf.copy()
        order["_k"] = order["next_contact"].replace("", "9999-99-99")
        view = order.sort_values("_k")[["name", "kind", "company", "role", "last_contact", "next_contact"]].rename(
            columns={"name": "Nom", "kind": "Type", "company": "Maison", "role": "Fonction",
                     "last_contact": "Dernier contact", "next_contact": "Prochaine relance"})
        st.dataframe(view, hide_index=True, width="stretch")
    st.markdown("#### Ajouter ou modifier un contact")
    ids = [""] + (cdf["id"].tolist() if not cdf.empty else [])
    labels = {"": "— Nouveau contact —"}
    if not cdf.empty:
        labels.update({r["id"]: f"{r['name']} · {r['company']}" for r in cdf.to_dict("records")})
    sel = st.selectbox("Fiche", ids, format_func=lambda x: labels.get(x, x), key="contact_sel")
    cur = cdf[cdf["id"] == sel].iloc[0].to_dict() if sel else {}
    with st.form("contact_form"):
        a, b = st.columns(2)
        name = a.text_input("Nom *", value=cur.get("name", ""))
        kind = b.selectbox("Type", CONTACT_KINDS,
                           index=CONTACT_KINDS.index(cur["kind"]) if cur.get("kind") in CONTACT_KINDS else 3)
        c, d = st.columns(2)
        company = c.text_input("Maison / Cabinet", value=cur.get("company", ""))
        role = d.text_input("Fonction", value=cur.get("role", ""))
        e, f = st.columns(2)
        email = e.text_input("Email", value=cur.get("email", ""))
        phone = f.text_input("Téléphone", value=cur.get("phone", ""))
        g, h = st.columns(2)
        last_c = g.text_input("Dernier contact (AAAA-MM-JJ)", value=cur.get("last_contact", ""))
        next_c = h.text_input("Prochaine relance (AAAA-MM-JJ)", value=cur.get("next_contact", ""))
        notes = st.text_area("Notes", value=cur.get("notes", ""), height=110)
        s1, s2 = st.columns(2)
        save = s1.form_submit_button("Enregistrer", type="primary")
        remove = s2.form_submit_button("Supprimer") if sel else False
    if save:
        try:
            payload = {"name": name, "kind": kind, "company": company, "role": role, "email": email,
                       "phone": phone, "last_contact": last_c, "next_contact": next_c, "notes": notes}
            if sel:
                store.update_contact(sel, payload)
                st.session_state["notice"] = "Contact mis à jour."
            else:
                store.add_contact(payload)
                st.session_state["notice"] = "Contact ajouté."
            st.rerun()
        except (ValueError, KeyError) as exc:
            st.error(str(exc))
    if remove:
        store.delete_contact(sel)
        st.session_state["notice"] = "Contact supprimé."
        st.rerun()


def cibles_tab():
    st.caption("Les maisons que tu vises, même sans offre ouverte. "
               "Quand le radar en détecte une, tu sais déjà pourquoi elle compte.")
    tdf = store.list_targets()
    m1, m2 = st.columns(2)
    m1.metric("Sociétés suivies", len(tdf))
    m2.metric("En discussion", int((tdf["status"] == "En discussion").sum()) if not tdf.empty else 0)
    if not tdf.empty:
        view = tdf[["name", "country", "sector", "priority", "status"]].rename(
            columns={"name": "Société", "country": "Pays", "sector": "Secteur",
                     "priority": "Priorité", "status": "Statut"})
        st.dataframe(view, hide_index=True, width="stretch")
    st.markdown("#### Ajouter ou modifier une société")
    ids = [""] + (tdf["id"].tolist() if not tdf.empty else [])
    labels = {"": "— Nouvelle société —"}
    if not tdf.empty:
        labels.update({r["id"]: r["name"] for r in tdf.to_dict("records")})
    sel = st.selectbox("Fiche", ids, format_func=lambda x: labels.get(x, x), key="target_sel")
    cur = tdf[tdf["id"] == sel].iloc[0].to_dict() if sel else {}
    pays_opts = ["", "France", "Suisse", "Italie"]
    with st.form("target_form"):
        a, b = st.columns(2)
        name = a.text_input("Société *", value=cur.get("name", ""))
        country = b.selectbox("Pays", pays_opts,
                              index=pays_opts.index(cur["country"]) if cur.get("country") in pays_opts else 0)
        c, d = st.columns(2)
        sector = c.text_input("Secteur", value=cur.get("sector", ""))
        priority = d.selectbox("Priorité", PRIORITIES,
                               index=PRIORITIES.index(cur["priority"]) if cur.get("priority") in PRIORITIES else 1)
        status = st.selectbox("Statut", TARGET_STATUSES,
                              index=TARGET_STATUSES.index(cur["status"]) if cur.get("status") in TARGET_STATUSES else 0)
        notes = st.text_area("Notes", value=cur.get("notes", ""), height=110)
        s1, s2 = st.columns(2)
        save = s1.form_submit_button("Enregistrer", type="primary")
        remove = s2.form_submit_button("Supprimer") if sel else False
    if save:
        try:
            payload = {"name": name, "country": country, "sector": sector, "priority": priority,
                       "status": status, "notes": notes}
            if sel:
                store.update_target(sel, payload)
                st.session_state["notice"] = "Société mise à jour."
            else:
                store.add_target(payload)
                st.session_state["notice"] = "Société ajoutée."
            st.rerun()
        except (ValueError, KeyError) as exc:
            st.error(str(exc))
    if remove:
        store.delete_target(sel)
        st.session_state["notice"] = "Société supprimée."
        st.rerun()


def entretiens_tab():
    st.caption("Une fiche de préparation par entretien : recherche sur la maison, "
               "questions à poser, points clés. Pour ne pas repartir de zéro à chaque rendez-vous.")
    pdf = store.list_prep()
    upcoming = pdf[(pdf["interview_date"] != "") & (pdf["interview_date"] >= today)] if not pdf.empty else pdf
    m1, m2 = st.columns(2)
    m1.metric("Préparations", len(pdf))
    m2.metric("Entretiens à venir", len(upcoming))
    if not pdf.empty:
        view = pdf[["company", "role", "interview_date"]].rename(
            columns={"company": "Maison", "role": "Poste", "interview_date": "Date"}).sort_values("Date")
        st.dataframe(view, hide_index=True, width="stretch")
    st.markdown("#### Préparer un entretien")
    ids = [""] + (pdf["id"].tolist() if not pdf.empty else [])
    labels = {"": "— Nouvelle préparation —"}
    if not pdf.empty:
        labels.update({r["id"]: f"{r['company']} · {r['interview_date'] or 'sans date'}"
                       for r in pdf.to_dict("records")})
    sel = st.selectbox("Fiche", ids, format_func=lambda x: labels.get(x, x), key="prep_sel")
    cur = pdf[pdf["id"] == sel].iloc[0].to_dict() if sel else {}
    with st.form("prep_form"):
        a, b, c = st.columns([2, 2, 1])
        company = a.text_input("Maison *", value=cur.get("company", ""))
        role = b.text_input("Poste visé", value=cur.get("role", ""))
        idate = c.text_input("Date (AAAA-MM-JJ)", value=cur.get("interview_date", ""))
        research = st.text_area("Recherche sur la maison (sites, actualités, dirigeants)",
                                value=cur.get("research", ""), height=120)
        questions = st.text_area("Questions à poser", value=cur.get("questions", ""), height=120)
        notes = st.text_area("Points clés / notes", value=cur.get("notes", ""), height=100)
        s1, s2 = st.columns(2)
        save = s1.form_submit_button("Enregistrer", type="primary")
        remove = s2.form_submit_button("Supprimer") if sel else False
    if save:
        try:
            payload = {"company": company, "role": role, "interview_date": idate,
                       "research": research, "questions": questions, "notes": notes}
            if sel:
                store.update_prep(sel, payload)
                st.session_state["notice"] = "Préparation mise à jour."
            else:
                store.add_prep(payload)
                st.session_state["notice"] = "Préparation créée."
            st.rerun()
        except (ValueError, KeyError) as exc:
            st.error(str(exc))
    if remove:
        store.delete_prep(sel)
        st.session_state["notice"] = "Préparation supprimée."
        st.rerun()


# ============================================================================
#  Routage des pages
# ============================================================================
page = st.session_state.get("current_page", "Tableau de bord")

if page == "Tableau de bord":
    new_cutoff = (date.today() - timedelta(days=7)).isoformat()
    count_new = int((df["detected_on"] >= new_cutoff).sum()) if not df.empty else 0
    count_high = len(alerts["high"])
    count_due = len(alerts["due"])
    interviews = int(df["status"].isin(["Entretien 1", "Entretien final / Shortlist"]).sum()) if not df.empty else 0
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Détectées ces 7 jours", count_new)
    m2.metric(f"Scores ≥ {prefs['alert_threshold']}", count_high)
    m3.metric("Relances à traiter", count_due)
    m4.metric("Entretiens en cours", interviews)

    # Frise d'avancement : où en est chaque offre, refusées comprises (à part, en pointillés).
    counts = df["status"].value_counts().to_dict() if not df.empty else {}
    steps = "".join(
        f"<div class='funnel-step{' closed' if s_ in CLOSED else ''}{' active' if counts.get(s_) and s_ not in CLOSED else ''}'>"
        f"<div class='n'>{counts.get(s_, 0)}</div><div class='l'>{_esc(STATUS_LABELS.get(s_, s_))}</div></div>"
        for s_ in STATUSES)
    st.markdown(f"<div class='funnel'>{steps}</div>", unsafe_allow_html=True)

    col_main, col_side = st.columns([1.8, 1], gap="large")
    with col_main:
        ranked = visible[~visible["is_closed"]].sort_values(["score", "detected_on"], ascending=False)
        h1, h2 = st.columns([3, 1.3], vertical_alignment="bottom")
        h1.subheader("Opportunités prioritaires")
        top_n = h2.selectbox("Afficher", [8, 15, 30, "Toutes"], index=0, key="home_top_n",
                             format_func=lambda v: f"Top {v}" if v != "Toutes" else "Toutes")
        limit = len(ranked) if top_n == "Toutes" else int(top_n)
        st.caption(f"{min(limit, len(ranked))} sur {len(ranked)} offre(s) en cours, classées par score.")
        inline_offer_buttons(ranked, "home", limit=limit)
        if ranked.empty:
            st.info("Aucune offre en cours. Ajuste les filtres ou lance une recherche.")
        elif limit < len(ranked):
            if st.button(f"Voir les {len(ranked)} offres dans le Pipeline", width="stretch"):
                st.session_state["nav_target"] = "Pipeline"
                st.rerun()
    with col_side:
        st.subheader("Actions à venir")
        todo = df[(df["next_action"] != "") & (~df["is_closed"])].sort_values("next_action") if not df.empty else df
        if todo.empty:
            st.info("Renseigne une date de prochaine action dans les fiches pour recevoir tes rappels.")
        else:
            for _, r in todo.head(7).iterrows():
                overdue = r["next_action"] <= today
                tag = "· en retard" if overdue else ""
                st.markdown(f"**{r['next_action']}** — {r['company']} {tag}")
                st.caption(r["title"])
        st.divider()
        st.subheader("Répartition")
        if not df.empty:
            open_df = df[~df["is_closed"]]
            for label, col in (("Par pays", "country"), ("Par niveau de score", None)):
                st.caption(label)
                if col:
                    data = open_df[col].value_counts()
                else:
                    tiers = pd.cut(open_df["score"], [-1, 69, 84, 100], labels=["< 70", "70–84", "85+"])
                    data = tiers.value_counts().reindex(["85+", "70–84", "< 70"])
                st.bar_chart(data, horizontal=True, height=130, color="#1F4D3A")
        st.divider()
        st.subheader("Flux récent")
        st.caption(f"{len(df)} opportunité(s) dans le CRM · {len(visible)} affichée(s) avec les filtres actuels.")
        if (ROOT / "scan_rapport.json").exists():
            import json
            try:
                report = json.loads((ROOT / "scan_rapport.json").read_text(encoding="utf-8"))
                st.caption(f"Dernier scan enregistré : {report.get('date_scan', '—')} · "
                           f"{report.get('annonces_nouvelles', 0)} nouvelle(s) offre(s)")
                if report.get('statut') in ('degrade', 'partiel'):
                    st.warning("Certaines sources n'ont pas répondu au dernier scan. "
                               "Les annonces déjà trouvées sont conservées. Voir Coulisses → Santé du radar.")
            except (ValueError, OSError):
                pass

elif page == "Pipeline":
    st.subheader("Pipeline")
    st.caption("Ta base de candidatures, à la manière d'un tableau Notion. "
               "Les onglets regroupent offres, réseau, sociétés cibles et préparation d'entretiens.")
    tab_offres, tab_reseau, tab_cibles, tab_prep = st.tabs(
        ["Offres", "Réseau", "Sociétés cibles", "Entretiens"])
    with tab_offres:
        pipeline_offers_tab()
    with tab_reseau:
        reseau_tab()
    with tab_cibles:
        cibles_tab()
    with tab_prep:
        entretiens_tab()

elif page == "Relances":
    st.subheader("Relances et prochaines actions")
    tab_off, tab_res = st.tabs(["Offres", "Réseau"])
    with tab_off:
        due = df[(df["next_action"] != "") & (df["next_action"] <= today) & (~df["is_closed"])].sort_values("next_action") if not df.empty else df
        upcoming = df[(df["next_action"] > today) & (~df["is_closed"])].sort_values("next_action") if not df.empty else df
        p1, p2 = st.columns(2)
        p1.metric("À traiter aujourd'hui ou en retard", len(due))
        p2.metric("Programmées à venir", len(upcoming))
        st.markdown("#### À traiter")
        inline_offer_buttons(due, "due", limit=25)
        if due.empty:
            st.success("Aucune relance d'offre en retard.")
        st.markdown("#### Planifiées")
        short_table(upcoming)
    with tab_res:
        cdf = store.list_contacts()
        if cdf.empty:
            st.info("Aucun contact. Ajoute tes chasseurs et ton réseau dans Pipeline → Réseau.")
        else:
            cdue = cdf[(cdf["next_contact"] != "") & (cdf["next_contact"] <= today)].sort_values("next_contact")
            clater = cdf[cdf["next_contact"] > today].sort_values("next_contact")
            st.markdown("#### Contacts à relancer")
            if cdue.empty:
                st.success("Aucune relance réseau en retard.")
            else:
                for _, r in cdue.iterrows():
                    st.markdown(f"**{r['next_contact']}** — {r['name']} · {r['company']} · {r['kind']}")
                    if r["notes"]:
                        st.caption(r["notes"][:120])
            st.markdown("#### Relances planifiées")
            if clater.empty:
                st.caption("Aucune relance réseau programmée.")
            else:
                st.dataframe(clater[["next_contact", "name", "company", "kind"]].rename(
                    columns={"next_contact": "Date", "name": "Nom", "company": "Maison", "kind": "Type"}),
                    hide_index=True, width="stretch")
    st.caption("Après une relance, mets à jour la date dans la fiche (offre ou contact).")

elif page == "Signaux marché":
    st.subheader("Radar d'entreprises : signaux de recrutement potentiels")
    st.write(
        "Les investissements, ouvertures de manufactures, acquisitions et nominations peuvent "
        "justifier une prise de contact ciblée. **Ces articles ne sont pas des offres d'emploi** "
        "et ne prouvent pas qu'un poste est ouvert."
    )
    signals_file = ROOT / "signaux_marche.csv"
    if signals_file.exists():
        try:
            signals = pd.read_csv(signals_file, dtype=str, keep_default_na=False)
            expected = ["Date de détection", "Actualité", "Entreprise", "Catégorie",
                        "Pays", "Source", "Lien"]
            if not set(expected).issubset(signals.columns):
                st.warning("Le fichier de signaux n'a pas les colonnes attendues.")
            elif signals.empty:
                st.info("Aucun signal enregistré. Le prochain scan alimentera cet onglet.")
            else:
                signals = signals.sort_values("Date de détection", ascending=False)
                cols = st.columns(3)
                cols[0].metric("Signaux visibles", len(signals))
                cols[1].metric("Maisons repérées", signals["Entreprise"].nunique())
                cols[2].metric("Pays identifiés", int(signals["Pays"].ne("Non précisé").sum()))
                st.dataframe(
                    signals[expected], hide_index=True, width="stretch",
                    column_config={"Lien": st.column_config.LinkColumn("Lire l'article", display_text="Ouvrir")},
                )
                st.caption("Date = découverte par le radar, pas date de publication de l'article. "
                           "Vérifier l'information et la date dans la source avant de contacter une entreprise.")
                with st.expander("Transformer une actualité en prise de contact (facultatif)"):
                    records = signals.to_dict("records")
                    signal_ix = st.selectbox("Actualité à examiner", range(len(records)),
                        format_func=lambda i: f"{records[i]['Entreprise']} : {records[i]['Actualité'][:90]}",
                        key="market_signal_selection")
                    selected = records[signal_ix]
                    hypothesis, next_step = signal_guidance(selected["Catégorie"])
                    st.markdown(f"**Piste à explorer :** {hypothesis}")
                    st.write(next_step)
                    st.caption("Vérifie la date et le contenu de l'article original. "
                               "Aucun poste ouvert ni contact identifié n'est présumé.")
                    draft = (f"Bonjour,\n\nJ'ai lu une actualité concernant "
                             f"{selected['Entreprise']} et je m'intéresse aux enjeux "
                             "de direction des opérations, de manufacture et de supply chain. "
                             "Si le sujet est pertinent pour votre équipe, je serais heureux "
                             "d'échanger à ce propos.\n\nBien cordialement")
                    st.text_area("Brouillon personnalisable (jamais envoyé automatiquement)",
                                 value=draft, height=150, key=f"market_draft_{signal_ix}")
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            st.warning(f"Impossible de lire les signaux : {exc}")
    else:
        st.info("La première collecte de presse créera `signaux_marche.csv` dans le dépôt.")
    st.markdown("**Actions conseillées** : repérer la maison, identifier le besoin métier possible, "
                "puis préparer une approche personnalisée (sans collecte automatisée de contacts privés).")

elif page == "Coulisses":
    st.subheader("Coulisses du radar")
    st.caption("Où le radar cherche, ce qui a répondu, et le bilan chiffré de ta recherche.")
    totals = catalog_totals()
    c1, c2, c3 = st.columns(3)
    c1.metric("Sites recherchés", totals["index_targets"])
    c2.metric("Prioritaires chaque jour", totals["priority_daily"])
    c3.metric("Sources presse", totals["news_targets"])
    st.info("**Surveillé** ne veut pas dire **scrapé en direct**. "
            "Pour la plupart des sites, le radar cherche seulement des annonces "
            "déjà publiques dans un moteur de recherche. "
            "Les autres sites tournent entre les jours pour limiter les requêtes.")
    tab_jobs, tab_news, tab_direct, tab_health, tab_stats, tab_limits = st.tabs([
        "Emploi et chasse", "Presse et tendances", "Flux directs",
        "Santé du radar", "Statistiques", "Limites et accès"])
    with tab_jobs:
        sites = pd.DataFrame([
            {"Site": name, "Famille": kind, "Lien": "https://" + domain,
             "Fréquence": "Quotidienne" if priority else "En rotation"}
            for name, domain, kind, lang, priority in SEARCH_SITES
        ])
        choice = st.selectbox("Afficher", ["Tous"] + sorted(sites["Famille"].unique().tolist()),
                              key="source_family")
        if choice != "Tous":
            sites = sites[sites["Famille"] == choice]
        st.dataframe(sites, hide_index=True, width="stretch",
                     column_config={"Lien": st.column_config.LinkColumn("Site public")})
    with tab_news:
        st.write("Ces articles aident à comprendre les entreprises, "
                 "mais **ne correspondent pas à des postes vacants**.")
        news = pd.DataFrame([{"Média": name, "Lien": "https://" + domain,
                              "Fréquence": "En rotation"}
                             for name, domain in NEWS_SITES])
        st.dataframe(news, hide_index=True, width="stretch",
                     column_config={"Lien": st.column_config.LinkColumn("Site public")})
    with tab_direct:
        st.write("Les flux publics (Lever, Ashby, Greenhouse, SmartRecruiters, SuccessFactors, "
                 "Oracle, RSS) sont plus précis quand une maison dispose d'un identifiant "
                 "confirmé. Ils ne nécessitent ni connexion candidat ni scraping des pages.")
        try:
            cfg = read_sources_config()
            rows = []
            for provider, key in [("Lever", "lever"), ("Ashby", "ashby"),
                                  ("Greenhouse", "greenhouse"),
                                  ("SmartRecruiters", "smartrecruiters"),
                                  ("SuccessFactors", "successfactors"),
                                  ("Oracle Recruiting", "oracle"),
                                  ("Workable", "workable"),
                                  ("Recruitee", "recruitee"),
                                  ("RSS/Atom", "rss")]:
                for board in cfg.get(key, []):
                    rows.append({"Fournisseur": provider, "Maison": board.get("company", ""),
                                 "Configuration": board.get("site") or board.get("board") or
                                                   board.get("company_id") or board.get("host") or
                                                   board.get("account") or board.get("url") or
                                                   board.get("index")})
            st.dataframe(pd.DataFrame(rows, columns=["Fournisseur", "Maison", "Configuration"]),
                         hide_index=True, width="stretch")
            st.caption("Les identifiants de flux doivent être vérifiés à leur source "
                       "(script verifier_sources.py).")
        except (OSError, ValueError, TypeError) as exc:
            st.warning("Configuration non disponible : " + str(exc))
    with tab_health:
        st.write("Ici on voit les **sites qui ont répondu**, ceux qui n'ont renvoyé "
                 "aucune annonce et ceux dont la collecte a échoué. "
                 "Un site en erreur n'est pas un site sans emploi.")
        report_file = ROOT / "scan_rapport.json"
        if not report_file.exists():
            st.info("Aucun rapport disponible : lance un scan depuis le Mac.")
        else:
            try:
                import json
                report = json.loads(report_file.read_text(encoding="utf-8"))
                h1, h2, h3, h4 = st.columns(4)
                h1.metric("Résultats publics", report.get("resultats_sources", "—"))
                h2.metric("Offres retenues", report.get("annonces_retenues", "—"))
                h3.metric("Nouvelles offres", report.get("annonces_nouvelles", 0))
                h4.metric("Sources en erreur / reportées", report.get("sources_en_erreur", "—"))
                st.caption(f"Dernier scan : {report.get('date_scan', 'inconnue')} · "
                           f"État général : {report.get('statut', 'inconnu')}")
                if report.get("statut") in ("degrade", "partiel"):
                    st.warning("Certains connecteurs n'ont pas répondu. "
                               "Les offres déjà enregistrées sont préservées.")
                diagnostics = report.get("etat_sources", {})
                if diagnostics:
                    table_rows = []
                    for source, detail in sorted(diagnostics.items()):
                        table_rows.append({
                            "Source": source,
                            "État": detail.get("etat", "inconnu"),
                            "Annonces accessibles": int(detail.get("brutes", 0)),
                            "Pertinentes": int(detail.get("retenues", 0)),
                            "Précision": detail.get("detail", ""),
                        })
                    table = pd.DataFrame(table_rows)
                    choices = ["Toutes", "En erreur", "Avec résultats", "Sans résultat"]
                    selected = st.selectbox("Afficher les sources", choices, key="health_filter")
                    if selected == "En erreur":
                        table = table[table["État"].isin(["erreur", "indisponible", "non_interroge"])]
                    elif selected == "Avec résultats":
                        table = table[table["Annonces accessibles"] > 0]
                    elif selected == "Sans résultat":
                        table = table[table["État"] == "vide"]
                    st.dataframe(table, hide_index=True, width="stretch")
                    st.caption("Annonces accessibles = résultats techniques de la source. "
                               "Pertinentes = annonces qui passent nos critères métier, luxe et pays.")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                st.warning("Impossible de lire le rapport du scan : " + str(exc))
    with tab_stats:
        if df.empty:
            st.info("Aucune donnée à analyser.")
        else:
            a, b, c = st.columns(3)
            a.metric("Offres détectées et réseau", len(df))
            b.metric("Candidatures envoyées / en entretien", int(df["status"].isin(
                ["Candidature envoyee", "Entretien 1", "Entretien final / Shortlist"]).sum()))
            c.metric("Entretiens actuellement actifs", int(df["status"].isin(
                ["Entretien 1", "Entretien final / Shortlist"]).sum()))
            l, r = st.columns(2)
            with l:
                st.markdown("**Par statut**")
                st.bar_chart(df["status"].value_counts().rename_axis("Statut"), horizontal=True)
                st.markdown("**Par source principale**")
                st.bar_chart(df["source"].value_counts().rename_axis("Source"), horizontal=True)
            with r:
                st.markdown("**Par pays**")
                st.bar_chart(df["country"].value_counts().rename_axis("Pays"))
                st.markdown("**Offres détectées par mois**")
                by_month = df.assign(mois=df["detected_on"].str[:7]).groupby("mois").size().rename("Offres")
                st.bar_chart(by_month)
            st.caption("Les totaux par statut représentent l'état actuel des dossiers.")
    with tab_limits:
        for name, why in MANUAL_OR_RESTRICTED:
            st.markdown(f"**{name}** : {why}")
        st.caption("Les offres confidentielles exigent une démarche humaine, "
                   "les APIs privées exigent une autorisation, et les pages "
                   "protégées ne sont pas contournées.")

elif page == "Réglages":
    st.subheader("Réglages")
    with st.expander("Comment utiliser le radar (guide rapide)", expanded=False):
        st.markdown("**1. Tableau de bord** — les meilleures offres et les actions du jour.\n\n"
                    "**2. Pipeline** — toutes tes candidatures, ton réseau, tes sociétés cibles "
                    "et tes préparations d'entretien, en onglets.\n\n"
                    "**3. Relances** — qui et quoi recontacter aujourd'hui, côté offres et côté réseau.\n\n"
                    "**4. Signaux marché** — les mouvements d'entreprises à exploiter en approche réseau.\n\n"
                    "Le score mesure la ressemblance avec tes critères, **pas une probabilité de recrutement**. "
                    "Aucune candidature n'est jamais envoyée automatiquement.")
    st.markdown("#### Profil de pertinence")
    st.caption("Les scores sont calculés à partir de critères transparents, sans IA externe et sans analyser de CV.")
    with st.form("preferences"):
        countries = st.multiselect("Pays prioritaires", ["France", "Suisse", "Italie"],
                                   default=prefs.get("preferred_countries", []))
        sectors = st.multiselect("Secteurs prioritaires", DEFAULT_PREFERENCES["preferred_sectors"],
                                 default=prefs.get("preferred_sectors", []))
        keywords = st.text_area("Mots-clés métier (séparés par des virgules)",
                                value=prefs.get("priority_keywords", ""))
        brands = st.text_area("Maisons favorites (séparées par des virgules)",
                              value=prefs.get("preferred_brands", ""))
        threshold = st.slider("Seuil pour une alerte 'offre prioritaire'", 50, 100,
                              int(prefs.get("alert_threshold", 85)), step=5)
        if st.form_submit_button("Enregistrer les préférences", type="primary"):
            store.save_preferences({
                "preferred_countries": countries, "preferred_sectors": sectors,
                "priority_keywords": keywords, "preferred_brands": brands,
                "alert_threshold": threshold,
            })
            st.session_state["notice"] = "Préférences enregistrées ; scores recalculés."
            st.rerun()
    st.divider()
    st.markdown("#### Données et sécurité")
    st.write("Les offres publiques sont dans `offres_detectees.csv`. Les contacts, notes, "
             "sociétés cibles et préparations sont uniquement en base de données.")
    st.download_button("Sauvegarde de mes données (CSV)",
                       data=df.drop(columns=["is_closed", "why_score", "score"], errors="ignore")
                       .to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"sauvegarde_crm_{today}.csv", mime="text/csv")
    if st.button("Se déconnecter"):
        st.session_state["authenticated"] = False
        st.rerun()
