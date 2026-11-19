"""Réglages communs aux tests : jamais d'appel réseau réel vers LinkedIn."""
import os

# Le scan complet inclut la recherche LinkedIn du Ciblage : coupée pendant les tests.
os.environ.setdefault("LINKEDIN_CIBLAGE_PAGES", "0")
# Vérification des liens du flux : coupée aussi (elle ouvre chaque annonce).
os.environ.setdefault("LINK_CHECK", "0")
