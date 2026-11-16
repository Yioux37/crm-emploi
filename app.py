import os
import sys
import base64
import subprocess
import requests
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Guillaume de Foucauld — CRM Direction Opérations",
    page_icon="⌚",
    layout="wide"
)

st.title("⌚ CRM Candidatures — Direction Opérations & Supply Chain")
st.markdown(
    "**Profil :** Guillaume de Foucauld | "
    "**Secteurs :** Luxe, Horlogerie, Joaillerie, Bijouterie, Textile / Couture | "
    "**Zones :** France, Suisse, Italie"
)

COLONNES_SCRAPER = [
    "Titre", "Entreprise", "Secteur", "Pays", "Source", "Lien",
    "Niveau estimé", "Date de détection"
]

COLONNES_CRM = [
    "Statut", "Priorité", "Contact / Chasseur", "Date dernière action", "Notes"
]

TOUTES_COLONNES = COLONNES_SCRAPER + COLONNES_CRM

STATUTS_DISPO = [
    "A analyser",
    "A postuler",
    "Candidature envoyee",
    "Reseau / Approche directe",
    "Entretien 1",
    "Entretien final / Shortlist",
    "Refuse / Sans suite",
    "Ecarte"
]

PRIORITES_DISPO = ["Haute", "Moyenne", "Veille"]


def load_data():
    if os.path.exists("offres_emploi.csv"):
        df = pd.read_csv("offres_emploi.csv", dtype=str)
        for col in TOUTES_COLONNES:
            if col not in df.columns:
                if col == "Source":
                    df[col] = "LinkedIn (Offres)"
                elif col == "Niveau estimé":
                    df[col] = "Management senior"
                elif col == "Date de détection":
                    df[col] = pd.Timestamp.today().strftime("%Y-%m-%d")
                elif col == "Statut":
                    df[col] = "A analyser"
                elif col == "Priorité":
                    df[col] = "Moyenne"
                else:
                    df[col] = ""

        df = df.fillna("")
        mapping_statuts = {
            "🆕 À analyser": "A analyser",
            "🎯 À postuler": "A postuler",
            "✉️ Candidature envoyée": "Candidature envoyee",
            "🤝 Réseau / Approche directe": "Reseau / Approche directe",
            "🗣️ Entretien 1": "Entretien 1",
            "🔥 Entretien final / Shortlist": "Entretien final / Shortlist",
            "❌ Refusé / Sans suite": "Refuse / Sans suite",
            "🗄️ Écarté": "Ecarte"
        }
        df["Statut"] = df["Statut"].replace(mapping_statuts)
        df.loc[~df["Statut"].isin(STATUTS_DISPO), "Statut"] = "A analyser"

        mapping_prio = {"🔴 Haute": "Haute", "🟠 Moyenne": "Moyenne", "🟢 Veille": "Veille"}
        df["Priorité"] = df["Priorité"].replace(mapping_prio)
        df.loc[~df["Priorité"].isin(PRIORITES_DISPO), "Priorité"] = "Moyenne"

        df = df[df["Pays"].isin(["France", "Suisse", "Italie"])]
        df = df.sort_values(by=["Date de détection", "Priorité"], ascending=[False, True])
        return df[TOUTES_COLONNES].reset_index(drop=True)

    return pd.DataFrame(columns=TOUTES_COLONNES)


def save_data(df_to_save):
    csv_content = df_to_save[TOUTES_COLONNES].to_csv(index=False)
    with open("offres_emploi.csv", "w", encoding="utf-8") as f:
        f.write(csv_content)

    # Synchronisation automatique vers GitHub si configuré sur Streamlit Cloud
    try:
        if "GITHUB_TOKEN" in st.secrets and "GITHUB_REPO" in st.secrets:
            token = st.secrets["GITHUB_TOKEN"]
            repo = st.secrets["GITHUB_REPO"]
            url = f"https://api.github.com/repos/{repo}/contents/offres_emploi.csv"
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json"
            }
            r_get = requests.get(url, headers=headers, timeout=10)
            sha = r_get.json().get("sha") if r_get.status_code == 200 else None

            payload = {
                "message": "Mise a jour CRM depuis l'interface web",
                "content": base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")
            }
            if sha:
                payload["sha"] = sha
            requests.put(url, json=payload, headers=headers, timeout=10)
    except Exception:
        pass


df = load_data()

# ==============================================================================
# BARRE LATERALE
# ==============================================================================
st.sidebar.header("Synchronisation")
if st.sidebar.button("Rechercher de nouvelles offres"):
    with st.spinner("Scan des Maisons, Workday, LinkedIn et Cabinets..."):
        subprocess.run([sys.executable, "scraper.py"])
        df_nouveau = load_data()
        save_data(df_nouveau)
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("Filtres CRM")

if df.empty:
    st.info("Aucune offre dans la base. Clique sur 'Rechercher de nouvelles offres' à gauche pour démarrer.")
else:
    masquer_archives = st.sidebar.checkbox("Masquer 'Ecarte' et 'Refuse'", value=True)

    if masquer_archives:
        statuts_defaut = [s for s in STATUTS_DISPO if s not in ["Refuse / Sans suite", "Ecarte"]]
    else:
        statuts_defaut = STATUTS_DISPO

    filtre_statut = st.sidebar.multiselect("Statut CRM", options=STATUTS_DISPO, default=statuts_defaut)
    filtre_priorite = st.sidebar.multiselect("Priorite", options=PRIORITES_DISPO, default=PRIORITES_DISPO)

    pays_dispo = sorted(df["Pays"].unique().tolist())
    filtre_pays = st.sidebar.multiselect("Pays", options=pays_dispo, default=pays_dispo)

    filtre_secteur = st.sidebar.selectbox(
        "Secteur",
        options=["Tous", "Luxe", "Horlogerie", "Joaillerie / Bijouterie", "Textile / Couture"]
    )

    mot_cle = st.sidebar.text_input("Recherche rapide", placeholder="Maison, poste, contact, note...")

    masque = (
        (df["Statut"].isin(filtre_statut)) &
        (df["Priorité"].isin(filtre_priorite)) &
        (df["Pays"].isin(filtre_pays))
    )

    if filtre_secteur != "Tous":
        masque = masque & df["Secteur"].str.contains(filtre_secteur, case=False, na=False)

    if mot_cle:
        masque = masque & (
            df["Titre"].str.contains(mot_cle, case=False, na=False) |
            df["Entreprise"].str.contains(mot_cle, case=False, na=False) |
            df["Contact / Chasseur"].str.contains(mot_cle, case=False, na=False) |
            df["Notes"].str.contains(mot_cle, case=False, na=False)
        )

    df_filtre = df[masque].copy()

    # ==============================================================================
    # INDICATEURS CLES
    # ==============================================================================
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Offres affichees", len(df_filtre))
    c2.metric("A analyser", len(df[df["Statut"] == "A analyser"]))
    c3.metric("A postuler", len(df[df["Statut"] == "A postuler"]))
    c4.metric("Envoyees / Reseau", len(df[df["Statut"].isin(["Candidature envoyee", "Reseau / Approche directe"])]))
    c5.metric("Entretiens actifs", len(df[df["Statut"].isin(["Entretien 1", "Entretien final / Shortlist"])]))

    st.markdown("---")

    # ==============================================================================
    # TABLEAU PRINCIPAL
    # ==============================================================================
    st.subheader("Liste des opportunites")
    st.dataframe(
        df_filtre,
        column_config={
            "Lien": st.column_config.LinkColumn("Annonce", display_text="Ouvrir")
        },
        hide_index=True,
        height=450
    )

    csv_data = df_filtre.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="Exporter la selection en CSV (Excel)",
        data=csv_data,
        file_name=f"CRM_Candidatures_{pd.Timestamp.today().strftime('%Y-%m-%d')}.csv",
        mime="text/csv"
    )

    st.markdown("---")

    # ==============================================================================
    # FICHE DE SUIVI CRM
    # ==============================================================================
    st.subheader("Mettre a jour le suivi d'une candidature")
    if not df_filtre.empty:
        options_offres = [
            f"{idx} | {row['Entreprise']} - {row['Titre']} ({row['Pays']})"
            for idx, row in df_filtre.iterrows()
        ]
        choix_offre = st.selectbox("Selectionner l'offre a mettre a jour :", options_offres)
        idx_sel = int(choix_offre.split(" | ")[0])
        ligne_actuelle = df.loc[idx_sel]

        with st.form("form_maj_crm"):
            col_s1, col_s2, col_s3 = st.columns(3)
            new_statut = col_s1.selectbox("Statut", STATUTS_DISPO, index=STATUTS_DISPO.index(ligne_actuelle["Statut"]))
            new_prio = col_s2.selectbox("Priorite", PRIORITES_DISPO, index=PRIORITES_DISPO.index(ligne_actuelle["Priorité"]))
            new_date = col_s3.text_input("Date derniere action", value=ligne_actuelle["Date dernière action"] or pd.Timestamp.today().strftime("%Y-%m-%d"))

            new_contact = st.text_input("Contact / Chasseur de tetes", value=ligne_actuelle["Contact / Chasseur"])
            new_notes = st.text_area("Notes et prochaines etapes", value=ligne_actuelle["Notes"])

            if st.form_submit_button("Enregistrer le suivi"):
                df.at[idx_sel, "Statut"] = new_statut
                df.at[idx_sel, "Priorité"] = new_prio
                df.at[idx_sel, "Date dernière action"] = new_date
                df.at[idx_sel, "Contact / Chasseur"] = new_contact
                df.at[idx_sel, "Notes"] = new_notes
                save_data(df)
                st.success("Suivi mis a jour et sauvegarde !")
                st.rerun()

st.markdown("---")

# ==============================================================================
# AJOUT MANUEL (RESEAU / CHASSEURS)
# ==============================================================================
with st.expander("Ajouter manuellement une opportunite (Reseau / Chasseur de tetes)"):
    with st.form("form_ajout_manuel", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        new_entreprise = col_a.text_input("Maison / Entreprise *")
        new_titre = col_b.text_input("Intitule du poste *")

        col_c, col_d, col_e = st.columns(3)
        new_pays = col_c.selectbox("Pays", ["France", "Suisse", "Italie"])
        new_secteur = col_d.selectbox("Secteur", ["Horlogerie", "Joaillerie / Bijouterie", "Textile / Couture", "Luxe"])
        new_priorite = col_e.selectbox("Priorite", PRIORITES_DISPO)

        col_f, col_g = st.columns(2)
        new_statut = col_f.selectbox("Statut initial", STATUTS_DISPO, index=1)
        new_contact = col_g.text_input("Contact / Chasseur")

        new_lien = st.text_input("Lien (optionnel)")
        new_notes = st.text_area("Notes initiales")

        if st.form_submit_button("Ajouter au CRM"):
            if new_entreprise and new_titre:
                nouvelle_ligne = pd.DataFrame([{
                    "Titre": new_titre,
                    "Entreprise": new_entreprise,
                    "Secteur": new_secteur,
                    "Pays": new_pays,
                    "Source": "Approche directe / Reseau",
                    "Lien": new_lien if new_lien else f"manuel://{pd.Timestamp.now().timestamp()}",
                    "Niveau estimé": "Direction fonctionnelle",
                    "Date de détection": pd.Timestamp.today().strftime("%Y-%m-%d"),
                    "Statut": new_statut,
                    "Priorité": new_priorite,
                    "Contact / Chasseur": new_contact,
                    "Date dernière action": pd.Timestamp.today().strftime("%Y-%m-%d"),
                    "Notes": new_notes
                }])
                df_maj = pd.concat([nouvelle_ligne, df], ignore_index=True)
                save_data(df_maj)
                st.success("Opportunite ajoutee et sauvegardee !")
                st.rerun()
            else:
                st.error("Renseigne la Maison et le poste.")
