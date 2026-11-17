"""Alertes e-mail optionnelles (SMTP); alertes dans l'app toujours actives."""
from __future__ import annotations

import argparse
import os
import smtplib
from datetime import date, timedelta
from email.message import EmailMessage

from scoring import calculate_score
from storage import CRMStore

CLOSED = {"Refuse / Sans suite", "Ecarte"}


def collect_alerts(store: CRMStore, now: date | None = None) -> dict:
    now = now or date.today()
    prefs = store.preferences()
    df = store.list_offers()
    high = []
    due = []
    for offer in df.to_dict("records"):
        if offer["status"] in CLOSED:
            continue
        score, _ = calculate_score(offer, prefs, today=now)
        try:
            days_old = (now - date.fromisoformat(offer["detected_on"])).days
        except ValueError:
            days_old = 365
        if 0 <= days_old <= 7 and score >= int(prefs.get("alert_threshold", 85)):
            high.append({**offer, "score": score})
        next_date = offer.get("next_action", "")
        if next_date and next_date <= now.isoformat():
            due.append(offer)
    return {"high": sorted(high, key=lambda r: -r["score"]),
            "due": sorted(due, key=lambda r: r["next_action"])}


def compose(store: CRMStore, mode: str, now: date | None = None) -> tuple[str, str, list[tuple[str, str]]]:
    now = now or date.today()
    alerts = collect_alerts(store, now)
    lines = [f"Point CRM emploi du {now.isoformat()}", ""]
    sent_keys: list[tuple[str, str]] = []
    if mode == "weekly":
        all_offers = store.list_offers()
        active = all_offers[~all_offers["status"].isin(CLOSED)] if not all_offers.empty else all_offers
        lines.extend([f"Opportunités suivies : {len(all_offers)}",
                      f"Opportunités actives : {len(active)}",
                      f"Actions en retard ou aujourd'hui : {len(alerts['due'])}", ""])
        week_key = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
        sent_keys.append(("weekly", week_key))
        subject = f"Bilan hebdomadaire CRM emploi - {week_key}"
    else:
        subject = f"CRM emploi : offres & relances - {now.isoformat()}"

    high = [a for a in alerts["high"] if not store.is_notified("high", a["id"])]
    lines.append(f"Nouvelles opportunités bien notées ({len(high)}) :")
    for o in high[:20]:
        lines.append(f"- {o['score']}/100 | {o['title']} - {o['company']} ({o['country']})")
        if o["link"].startswith(("https://", "http://")):
            lines.append(f"  {o['link']}")
        sent_keys.append(("high", o["id"]))
    if not high:
        lines.append("- Aucune nouvelle alerte")
    lines.extend(["", f"Relances dues ({len(alerts['due'])}) :"])
    for o in alerts["due"][:30]:
        lines.append(f"- {o['next_action']} | {o['company']} - {o['title']} ({o['status']})")
    if not alerts["due"]:
        lines.append("- Aucune relance")
    lines.append("\nConfigurer le calendrier des relances dans le CRM.")
    if mode == "daily":
        # Les rappels peuvent revenir chaque jour tant que l'action reste a faire.
        sent_keys.append(("daily", now.isoformat()))
    return subject, "\n".join(lines), sent_keys


def send_email(subject: str, content: str) -> None:
    required = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "ALERT_TO")
    absent = [k for k in required if not os.getenv(k)]
    if absent:
        raise RuntimeError("SMTP non configuré : " + ", ".join(absent))
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT") or "587")
    user = os.environ["SMTP_USER"]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.getenv("ALERT_FROM", user)
    msg["To"] = os.environ["ALERT_TO"]
    msg.set_content(content)
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20) as client:
            client.login(user, os.environ["SMTP_PASSWORD"])
            client.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as client:
            client.starttls()
            client.login(user, os.environ["SMTP_PASSWORD"])
            client.send_message(msg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Alertes CRM optionnelles")
    parser.add_argument("--mode", choices=("daily", "weekly"), default="daily")
    parser.add_argument("--dry-run", action="store_true", help="Affiche sans envoyer ni marquer comme notifié")
    args = parser.parse_args()
    store = CRMStore()
    store.bootstrap()
    now = date.today()
    existing_key = ("weekly", f"{now.isocalendar().year}-W{now.isocalendar().week:02d}") if args.mode == "weekly" else ("daily", now.isoformat())
    if store.is_notified(*existing_key) and not args.dry_run:
        print("Résumé déjà envoyé pour cette période.")
        return
    subject, content, keys = compose(store, args.mode, now)
    if args.dry_run:
        print("Objet :", subject, "\n", content)
        return
    send_email(subject, content)
    for kind, key in keys:
        store.mark_notified(kind, key)
    print("E-mail envoyé ; suivi des notifications enregistré.")


if __name__ == "__main__":
    main()
