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
from storage import CRMStore, ConcurrentEditError, PRIORITIES, STATUSES

ROOT = Path(__file__).resolve().parent
PAGES = ["Accueil", "Opportunités", "Relances", "Statistiques", "Préférences"]

st.set_page_config(page_title="CRM Carrière | Direction & Supply Chain", page_icon="⌚", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 1.35rem; padding-bottom: 3rem; max-width: 1480px;}
[data-testid="stMetric"] {border: 1px solid rgba(128,128,128,.18); padding: 16px; border-radius: 14px;}
[data-testid="stSidebar"] {border-right: 1px solid rgba(128,128,128,.12);}
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
    st.title("🔐 Espace privé de recherche d'emploi")
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
    st.session_state["nav_target"] = "Opportunités"
    st.rerun()


st.sidebar.title("⌚ Mon espace carrière")
st.sidebar.caption("Direction Opérations & Supply Chain · Luxe")
if store.is_local:
    st.sidebar.caption("💾 SQLite local : pour un hébergement Cloud, configure une base PostgreSQL persistante.")
if "nav_target" in st.session_state:
    st.session_state["current_page"] = st.session_state.pop("nav_target")
st.sidebar.radio("Navigation", PAGES, key="current_page", label_visibility="collapsed")
st.sidebar.divider()
if st.sidebar.button("🔎 Rechercher de nouvelles offres", use_container_width=True):
    with st.spinner("Interrogation des portails et moteurs de recherche…"):
        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scraper.py"), "--output", str(ROOT / "offres_detectees.csv"),
                 "--report", str(ROOT / "scan_rapport.json")],
                cwd=ROOT, capture_output=True, text=True, timeout=900,
            )
            if result.returncode:
                st.sidebar.error("Le scan a échoué : aucune donnée existante n'a été effacée.")
                with st.sidebar.expander("Détails du scan"):
                    st.code((result.stderr + "\n" + result.stdout)[-5000:])
            else:
                new_count = store.import_csv(ROOT / "offres_detectees.csv")
                st.session_state["notice"] = f"Scan terminé : {new_count} nouvelle(s) opportunité(s) dans le CRM."
                st.rerun()
        except subprocess.TimeoutExpired:
            st.sidebar.error("Scan trop long : l'opération a été interrompue, sans suppression d'offre.")

if st.sidebar.button("↻ Actualiser le flux", use_container_width=True):
    try:
        count = store.import_csv(ROOT / "offres_detectees.csv")
        st.session_state["notice"] = f"Flux rechargé : {count} nouvelle(s) offre(s)."
        st.rerun()
    except Exception as exc:
        st.sidebar.error(f"Erreur d'import : {exc}")

st.sidebar.divider()
st.sidebar.subheader("Filtres")
selected_countries = st.sidebar.multiselect(
    "Pays", ["France", "Suisse", "Italie"], default=["France", "Suisse", "Italie"]
)
selected_statuses = st.sidebar.multiselect(
    "Statut", STATUSES, default=[x for x in STATUSES if x not in CLOSED]
)
selected_priorities = st.sidebar.multiselect("Priorité", PRIORITIES, default=PRIORITIES)
selected_sector = st.sidebar.selectbox(
    "Secteur", ["Tous", "Horlogerie", "Joaillerie / Bijouterie", "Textile / Couture", "Luxe"]
)
min_score = st.sidebar.slider("Score minimum", 0, 100, 0, step=5)
search = st.sidebar.text_input("Recherche", placeholder="Poste, maison, contact…")

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

st.title("⌚ CRM Candidatures")
st.caption("Un espace privé pour repérer les opportunités, préparer les candidatures et ne manquer aucune relance.")

if store.backup_error:
    st.warning("Une sauvegarde locale a échoué : " + store.backup_error)

if imported["legacy"]:
    st.info(f"{imported['legacy']} offre(s) importée(s) depuis l'ancien CSV. Tes notes et statuts sont conservés.")


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
        ui, hide_index=True, use_container_width=True,
        column_config={
            "Score": st.column_config.ProgressColumn("Score /100", min_value=0, max_value=100, format="%d"),
            "Lien": st.column_config.LinkColumn("Annonce", display_text="Ouvrir"),
        },
    )


def inline_offer_buttons(offers_subset: pd.DataFrame, prefix: str, limit: int = 5):
    for _, r in offers_subset.head(limit).iterrows():
        with st.container(border=True):
            a, b, c = st.columns([6, 1.2, 1.5], vertical_alignment="center")
            with a:
                st.markdown(f"**{r['title']}**")
                st.caption(f"{r['company']} · {r['country']} · {r['status']}")
            b.metric("Score", f"{r['score']}/100", label_visibility="visible")
            if c.button("Ouvrir la fiche", key=f"{prefix}_{r['id']}", use_container_width=True):
                go_to_offer(r["id"])


page = st.session_state.get("current_page", "Accueil")

if page == "Accueil":
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

    col_main, col_side = st.columns([1.7, 1], gap="large")
    with col_main:
        st.subheader("🎯 Opportunités prioritaires")
        ranked = visible[~visible["is_closed"]].sort_values(["score", "detected_on"], ascending=False)
        inline_offer_buttons(ranked, "home")
        if ranked.empty:
            st.info("Aucune offre visible. Ajuste les filtres ou lance une recherche.")
    with col_side:
        st.subheader("📅 Actions à venir")
        todo = df[(df["next_action"] != "") & (~df["is_closed"])].sort_values("next_action") if not df.empty else df
        if todo.empty:
            st.info("Renseigne une date de prochaine action dans les fiches pour recevoir tes rappels.")
        else:
            for _, r in todo.head(7).iterrows():
                overdue = r["next_action"] <= today
                st.markdown(f"{'🔴' if overdue else '🗓️'} **{r['next_action']}** — {r['company']}")
                st.caption(r["title"])
        st.divider()
        st.subheader("📥 Flux récent")
        st.caption(f"{len(df)} opportunité(s) conservée(s) dans le CRM, dont {len(visible)} affichée(s) après filtrage.")
        if (ROOT / "scan_rapport.json").exists():
            import json
            try:
                report = json.loads((ROOT / "scan_rapport.json").read_text(encoding="utf-8"))
                st.caption(f"Dernier scan enregistré : {report.get('date_scan', '—')} · {report.get('statut', 'inconnu')}")
            except (ValueError, OSError):
                pass

elif page == "Opportunités":
    st.subheader("🎯 Explorer et mettre à jour les opportunités")
    st.caption("Les statuts et priorités sont éditables dans le tableau. Les autres informations se modifient dans la fiche.")
    if visible.empty:
        st.info("Aucune offre ne correspond aux filtres sélectionnés.")
    else:
        editor_data = visible.set_index("id")[["title", "company", "country", "score", "status",
                                               "priority", "next_action", "link"]].rename(columns={
            "title": "Poste", "company": "Maison", "country": "Pays", "score": "Score",
            "status": "Statut", "priority": "Priorité", "next_action": "Prochaine action", "link": "Lien"
        })
        edited = st.data_editor(
            editor_data, key="main_table_editor", hide_index=True,
            use_container_width=True, height=min(700, max(245, 46 * (len(editor_data) + 1))),
            column_config={
                "Statut": st.column_config.SelectboxColumn("Statut", options=STATUSES, required=True),
                "Priorité": st.column_config.SelectboxColumn("Priorité", options=PRIORITIES, required=True),
                "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
                "Lien": st.column_config.LinkColumn("Annonce", display_text="Ouvrir")
            },
            disabled=["Poste", "Maison", "Pays", "Score", "Prochaine action", "Lien"],
        )
        a, b = st.columns([1, 2])
        with a:
            if st.button("💾 Enregistrer les modifications du tableau", type="primary"):
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
        with b:
            export_cols = ["title", "company", "sector", "country", "source", "link", "level",
                           "detected_on", "score", "status", "priority", "contact", "last_action",
                           "next_action", "notes", "link_status"]
            download = visible[export_cols].to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ Exporter la sélection (CSV)", data=download,
                               file_name=f"candidatures_{today}.csv", mime="text/csv")

        st.divider()
        st.subheader("🗂️ Fiche de candidature")
        ids = visible["id"].tolist()
        labels = {r["id"]: offer_label(r) for r in visible.to_dict("records")}
        preselected = st.session_state.get("chosen_offer_id")
        idx = ids.index(preselected) if preselected in ids else 0
        chosen = st.selectbox("Sélectionne une opportunité", ids, index=idx, format_func=lambda x: labels.get(x, x))
        st.session_state["chosen_offer_id"] = chosen
        current = store.offer(chosen)
        with st.container(border=True):
            details_l, details_r = st.columns([3, 1])
            with details_l:
                st.markdown(f"### {current['title']}")
                st.caption(f"{current['company']} · {current['country']} · {current['sector']}")
            with details_r:
                score, reasons = calculate_score(current, prefs)
                st.metric("Compatibilité estimée", f"{score}/100")
            with st.expander("Comprendre le score", expanded=False):
                st.write(" · ".join(reasons))
                st.caption("Score heuristique personnalisable, pas une probabilité de recrutement.")
            links = store.links_for(chosen)
            if links:
                st.markdown("**Annonces et sources**")
                for alternate in links:
                    st.markdown(f"- [{alternate['source']}]({alternate['url']})")
            if current["link"].startswith(("https://", "http://")):
                x, y = st.columns([1, 3])
                with x:
                    if st.button("🔎 Vérifier le lien", key=f"check_{chosen}"):
                        with st.spinner("Vérification du lien…"):
                            status = check_link(current["link"])
                            store.record_link_check(chosen, status)
                        st.session_state["notice"] = f"Lien : {status}. Un blocage d'accès n'est pas considéré comme une annonce expirée."
                        st.rerun()
                with y:
                    st.caption(f"État du lien : {current['link_status']}" +
                               (f" · Vérifié le {current['link_checked_at'][:10]}" if current['link_checked_at'] else ""))
            with st.form(f"edit_{chosen}"):
                c1, c2, c3 = st.columns([2, 1, 1])
                status = c1.selectbox("Statut", STATUSES, index=STATUSES.index(current["status"]))
                priority = c2.selectbox("Priorité", PRIORITIES, index=PRIORITIES.index(current["priority"]))
                contact = c3.text_input("Contact / Chasseur", value=current["contact"])
                d1, d2 = st.columns(2)
                last_action = d1.text_input("Dernière action (AAAA-MM-JJ)", value=current["last_action"], placeholder="2026-11-17")
                next_action = d2.text_input("Prochaine action (AAAA-MM-JJ)", value=current["next_action"], placeholder="2026-11-24")
                notes = st.text_area("Notes et prochaines étapes", value=current["notes"], height=130)
                submitted = st.form_submit_button("Enregistrer la fiche", type="primary")
            if submitted:
                try:
                    store.update_offer(chosen, {
                        "status": status, "priority": priority, "contact": contact,
                        "last_action": last_action, "next_action": next_action, "notes": notes,
                    }, expected_updated_at=current["updated_at"])
                    st.session_state["notice"] = "Fiche enregistrée. Historique mis à jour."
                    st.rerun()
                except (ValueError, ConcurrentEditError) as exc:
                    st.error(str(exc))
            with st.expander("🕒 Historique des actions"):
                events = store.timeline(chosen)
                for event in events:
                    st.markdown(f"**{event['when_at'][:16].replace('T', ' ')} UTC** — {event['action']}")

    with st.expander("➕ Ajouter une opportunité réseau / chasseur de têtes"):
        with st.form("add_manual", clear_on_submit=True):
            a, b = st.columns(2)
            company = a.text_input("Maison / Entreprise *")
            title = b.text_input("Intitulé du poste *")
            c, d, e = st.columns(3)
            country = c.selectbox("Pays", ["France", "Suisse", "Italie"])
            sector = d.selectbox("Secteur", ["Horlogerie", "Joaillerie / Bijouterie", "Textile / Couture", "Luxe"])
            priority = e.selectbox("Priorité", PRIORITIES, index=1)
            status = st.selectbox("Statut initial", STATUSES, index=1)
            contact = st.text_input("Contact / Chasseur")
            url = st.text_input("Lien vers l'offre (facultatif)")
            next_action = st.text_input("Prochaine action (AAAA-MM-JJ, facultatif)")
            notes = st.text_area("Notes")
            if st.form_submit_button("Ajouter au CRM"):
                if not title.strip() or not company.strip():
                    st.error("Le poste et l'entreprise sont requis.")
                elif url and not canonical_url(url):
                    st.error("Le lien doit être une URL http(s) valide ou rester vide.")
                else:
                    try:
                        if next_action:
                            date.fromisoformat(next_action)
                        added = store.add_manual({
                            "title": title, "company": company, "sector": sector, "country": country,
                            "priority": priority, "status": status, "contact": contact, "link": url,
                            "next_action": next_action, "notes": notes, "last_action": today,
                        })
                        st.session_state["notice"] = "Opportunité créée." if added else "Cette opportunité existe déjà."
                        st.rerun()
                    except ValueError:
                        st.error("Date incorrecte, utilise le format AAAA-MM-JJ.")

elif page == "Relances":
    st.subheader("📅 Relances et prochaines actions")
    due = df[(df["next_action"] != "") & (df["next_action"] <= today) & (~df["is_closed"])].sort_values("next_action") if not df.empty else df
    upcoming = df[(df["next_action"] > today) & (~df["is_closed"])].sort_values("next_action") if not df.empty else df
    p1, p2 = st.columns(2)
    p1.metric("À traiter aujourd'hui ou en retard", len(due))
    p2.metric("Programmées à venir", len(upcoming))
    st.markdown("#### 🔴 À traiter")
    inline_offer_buttons(due, "due", limit=25)
    if due.empty:
        st.success("Aucune relance en retard.")
    st.markdown("#### 🗓️ Planifiées")
    short_table(upcoming)
    st.caption("Après une relance, mets à jour la dernière action et fixe une nouvelle date sur la fiche.")

elif page == "Statistiques":
    st.subheader("📈 Pilotage de la recherche")
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
        st.caption("Les totaux par statut représentent l'état actuel des dossiers. "
                   "Un taux de réponse fiable nécessiterait de tracer chaque candidature envoyée et ses réponses.")

elif page == "Préférences":
    st.subheader("⚙️ Profil de pertinence et sécurité")
    st.markdown("Les scores sont calculés à partir de critères transparents, sans IA externe et sans analyser de CV.")
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
    st.markdown("**Données et alertes**")
    st.write("Les offres publiques sont dans `offres_detectees.csv`. Les contacts et notes sont uniquement en base de données.")
    st.write("Les alertes de relance sont toujours visibles dans l'accueil et l'onglet Relances. "
             "Les e-mails quotidiens et hebdomadaires nécessitent une configuration SMTP facultative (voir README).")
    st.download_button("⬇️ Sauvegarde de mes données (CSV)",
                       data=df.drop(columns=["is_closed", "why_score", "score"], errors="ignore")
                       .to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"sauvegarde_crm_{today}.csv", mime="text/csv")
    if st.button("🔒 Se déconnecter"):
        st.session_state["authenticated"] = False
        st.rerun()
