#!/usr/bin/env python3
# app/core/services/avatar/filter.py

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
    r'\bconsultant\b',
    r'\bexpert\b',
    r'\bspécialiste\b',
    r'\bspecialist\b',
    r'\bmedia buyer\b',
    r'\bcopywriter\b',
    r'\brédacteur\b',
    r'\bredacteur\b',
    r'\btraffic manager\b',
    r'\bgrowth hacker\b',
    r'\bgrowth\b',
    r'\bproduct manager\b',
    r'\bchef de projet\b',
    r'\bproject manager\b',
    r'\bsocial media manager\b',
    r'\bstratège\b',
    r'\bstratégiste\b',
    r'\bstrategist\b',
]

WHITELIST_SECTORS = [
    r'\bagence\b',
    r'agency',  # Match "agency" même collé à d'autres mots (ex: actiris-agency)
    r'\bmarketing\b',
    r'\bweb\b',
    r'\bdesign\b',
    r'\bdigital\b',
    r'\bcommunication\b',
    r'\bmedia\b',
    r'\bcréatif\b',
    r'\bcreative\b',
    r'\bstudio\b',
    r'\bseo\b',
    r'\bsem\b',
    r'\bcontent\b',
    r'\bréférencement\b',
    r'\bmotion\b',
    r'\banimation\b',
    r'\bvideo\b',
    r'\bvidéo\b',
    r'\bgraphic\b',
    r'\bgraphique\b',
    r'\bsaas\b',
    r'\btech\b',
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


async def analyze_prospect_with_llm(headline: str, job_title: str, company: str) -> Tuple[str, str]:
    """
    Analyse approfondie d'un prospect avec LLM pour les cas ambigus.

    Utilisé quand quick_avatar_check() retourne "llm_needed".

    Args:
        headline: Headline LinkedIn
        job_title: Job title
        company: Entreprise

    Returns:
        Tuple[decision, reason]:
        - decision: "accept" ou "reject"
        - reason: explication courte
    """
    from app.core.services.llm.llm import llm_service
    import json
    from config.logger import logger

    system_prompt = """Tu es un expert en qualification de prospects B2B pour Hugo, développeur spécialisé en automatisations et agents IA.

PROFIL CLIENT IDÉAL:
- CEO, Founder, Directeur, Consultant, Expert, Media Buyer, Copywriter, Traffic Manager, Growth Hacker, Product Manager, Chef de projet
- Secteurs: agences (marketing, web, design), SaaS, tech, digital, communication, media
- Besoin potentiel: automatisations, workflows, onboarding client, agents IA

PROFILS À REJETER:
- Immobilier, comptabilité, fiscalité, notaire, BTP, construction
- Spécialistes IA/automation (concurrents directs)
- En recherche d'emploi ("à l'écoute d'opportunités", "open to work")
- Secteurs sans besoin d'automatisation évident

Ta mission: analyser le profil et décider si c'est un bon prospect."""

    user_prompt = f"""Analyse ce profil LinkedIn:

Headline: {headline or 'N/A'}
Job Title: {job_title or 'N/A'}
Company: {company or 'N/A'}

Réponds UNIQUEMENT par un JSON avec ce format exact:
{{
  "decision": "accept" ou "reject",
  "reason": "explication courte (max 15 mots)"
}}

Exemples:
- CEO d'une agence marketing → {{"decision": "accept", "reason": "CEO agence marketing, profil idéal"}}
- Développeur IA chez Google → {{"decision": "reject", "reason": "concurrent IA, pas client potentiel"}}
- Consultant RH freelance → {{"decision": "accept", "reason": "consultant indépendant, peut automatiser"}}
- Agent immobilier → {{"decision": "reject", "reason": "secteur blacklisté immobilier"}}"""

    try:
        response = await llm_service.generate_text(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2
        )

        if not response:
            logger.warning("LLM returned empty response for prospect analysis")
            return ("reject", "llm_error_empty_response")

        result = json.loads(response)
        decision = result.get("decision", "reject")
        reason = result.get("reason", "llm_decision")

        # Validation
        if decision not in ["accept", "reject"]:
            logger.warning(f"Invalid LLM decision: {decision}")
            return ("reject", "llm_error_invalid_decision")

        logger.info(f"🤖 LLM avatar analysis: decision={decision}, reason={reason}")
        return (decision, f"llm_{reason}")

    except Exception as e:
        logger.error(f"LLM avatar analysis failed: {e}")
        # En cas d'erreur LLM, on rejette par sécurité
        return ("reject", f"llm_error_{str(e)[:30]}")
