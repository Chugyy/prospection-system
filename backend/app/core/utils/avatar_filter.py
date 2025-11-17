#!/usr/bin/env python3
# app/core/utils/avatar_filter.py

import re
from typing import Tuple, Optional

# ============================
# BLACKLIST (rejet immédiat)
# ============================

BLACKLIST_SECTORS = [
    r'\bimmobilier\b',
    r'\bcomptabilit[ée]\b',
    r'\bfiscalit[ée]\b',
    r'\bnotaire\b',
    r'\bbtp\b',
    r'\bconstruction\b',
    r'\bautomation\b',
    r'\bartificial intelligence\b',
    r'\b(ia|ai)\s',  # IA/AI suivi d'un espace (ex: "Spécialiste IA ")
    r'\s(ia|ai)\b',  # IA/AI précédé d'un espace (ex: " IA Engineer")
    r'^(ia|ai)\s',   # IA/AI au début du texte
    r'\s(ia|ai)$',   # IA/AI à la fin du texte
]

BLACKLIST_TITLES = [
    r'\bnotaire\b',
    r'\bcomptable\b',
    r'\bexpert[- ]comptable\b',
    r'\bagent immobilier\b',
    r'\bhuissier\b',
    r'\bavocat fiscaliste\b',
]

BLACKLIST_KEYWORDS = [
    r"à l['\']écoute d['\']opportunit[ée]s",
    r'en recherche active',
    r'open to opportunities',
    r'actively looking',
]

# ============================
# WHITELIST (acceptation immédiate)
# ============================

WHITELIST_TITLES = [
    r'\bceo\b',
    r'\bfounder\b',
    r'\bfondateur\b',
    r'\bfondatrice\b',
    r'\bco[- ]founder\b',
    r'\bdirecteur\b',
    r'\bdirectrice\b',
    r'\bdirector\b',
    r'\bcommunity manager\b',
    r'\b[^a-z]cm[^a-z]\b',  # CM entouré de non-lettres
    r'\bchief\b',
    r'\bcto\b',
    r'\bcoo\b',
    r'\bcmo\b',
]

WHITELIST_SECTORS = [
    r'\bagence\b',
    r'\bagency\b',
    r'\bmarketing\b',
    r'\bweb\b',
    r'\bdesign\b',
    r'\bdigital\b',
    r'\bcommunication\b',
    r'\bmedia\b',
    r'\bcréatif\b',
    r'\bcreative\b',
    r'\bstudio\b',
]


def _matches_patterns(text: str, patterns: list) -> bool:
    """Vérifie si le texte match au moins un pattern de la liste."""
    if not text:
        return False

    text_lower = text.lower()

    for pattern in patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True

    return False


def quick_avatar_check(headline: str = '', job_title: str = '', company: str = '') -> Tuple[str, Optional[str]]:
    """
    Filtre rapide basé sur patterns avant d'appeler le LLM.

    Args:
        headline: Headline LinkedIn du prospect
        job_title: Job title du prospect
        company: Entreprise du prospect

    Returns:
        Tuple[decision, reason]:
        - decision: "accept", "reject", "llm_needed"
        - reason: explication de la décision
    """

    combined_text = f"{headline} {job_title} {company}".lower()

    # ============================
    # NIVEAU 1: BLACKLIST
    # ============================

    # Check secteurs blacklistés
    if _matches_patterns(combined_text, BLACKLIST_SECTORS):
        return ("reject", "blacklist_sector")

    # Check titres blacklistés
    if _matches_patterns(combined_text, BLACKLIST_TITLES):
        return ("reject", "blacklist_title")

    # Check keywords blacklistés
    if _matches_patterns(combined_text, BLACKLIST_KEYWORDS):
        return ("reject", "blacklist_keyword")

    # ============================
    # NIVEAU 2: WHITELIST
    # ============================

    # Check titres whitelistés
    title_match = _matches_patterns(combined_text, WHITELIST_TITLES)

    # Check secteurs whitelistés
    sector_match = _matches_patterns(combined_text, WHITELIST_SECTORS)

    # Si à la fois titre ET secteur matchent → acceptation immédiate
    if title_match and sector_match:
        return ("accept", "whitelist_title_and_sector")

    # Si seulement titre match (CEO, Founder, etc.) → acceptation
    if title_match:
        return ("accept", "whitelist_title")

    # Si seulement secteur match → LLM pour vérifier le titre
    if sector_match:
        return ("llm_needed", "sector_match_needs_title_validation")

    # ============================
    # NIVEAU 3: INCERTAIN
    # ============================

    return ("llm_needed", "no_clear_pattern")
