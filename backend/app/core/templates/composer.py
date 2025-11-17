#!/usr/bin/env python3
"""
Message composer for LinkedIn prospection with AI generation and template validation.
"""
import random
import logging
from typing import Dict, Any, Optional

from app.core.services.llm.llm import llm_service

logger = logging.getLogger(__name__)

# Salutations aléatoires
GREETINGS = ["Salut", "Hey", "Hello", "Bonjour", "Hola"]


class MessageComposer:
    """Générateur de messages de prospection avec IA + templates"""

    def __init__(self):
        self.llm = llm_service

    async def generate_welcome_message(self, profile: Dict[str, Any]) -> str:
        """
        Génère un message de bienvenue personnalisé via IA

        Args:
            profile: Dict contenant les infos du profil

        Returns:
            Message personnalisé ou fallback si l'IA échoue
        """
        # Toujours utiliser l'IA pour le message de bienvenue
        ai_message = await self._generate_ai_message(profile, 'welcome')
        if ai_message:
            return ai_message

        # Fallback basique si l'IA échoue
        context = self._extract_profile_context(profile)
        first_name = context['first_name'] or "l'équipe"
        company = context['company'] or 'votre entreprise'

        greeting = random.choice(GREETINGS)
        return f"{greeting} {first_name}, merci pour la connexion ! Comment ça se passe chez {company} ?"

    def generate_followup_message(self, profile: Dict[str, Any], step: int) -> str:
        """
        Génère un follow-up avec templates

        Args:
            profile: Dict contenant les infos du profil
            step: Numéro du followup (1, 2, ou 3)

        Returns:
            Message de followup formaté
        """
        # Limiter à 3 follow-ups max
        step = min(step, 3)

        # Templates depuis TRI-LINKEDIN
        templates = {
            1: "{greeting} {first_name}, j'imagine que tu n'as pas vu mon message alors je me permets de te relancer. Belle journée à toi !",
            2: "{first_name} ?",
            3: """{greeting} {first_name},

Je suis Hugo, spécialiste en automatisation back-end et agents IA. J'aide freelances et agences à créer des systèmes qui leur font gagner temps et performance.

J'ai déjà aidé +10 agences comme la tienne et en aucun cas elles regrettent les solutions implémentées.

Tu serais dispo pour un call d'ici 1-2 jours dans l'après-midi ? On pourrait échanger 15-20 min pour voir concrètement ce que je peux t'apporter.

Qu'est-ce que tu en penses ?"""
        }

        template = templates.get(step, templates[1])

        # Choisir une salutation aléatoire
        greeting = random.choice(GREETINGS)

        context = self._extract_profile_context(profile)

        return self._format_template(template, greeting, context)

    async def _generate_ai_message(
        self,
        profile: Dict[str, Any],
        message_type: str
    ) -> Optional[str]:
        """Génère un message via IA avec prompt contextualisé"""

        if message_type != 'welcome':
            return None

        prompt = self._build_welcome_prompt(profile)

        try:
            result = await self.llm.generate_text(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            return result.strip() if result else None

        except Exception as e:
            logger.error(f"AI generation failed: {e}")
            return None

    def _build_welcome_prompt(self, profile: Dict[str, Any]) -> str:
        """Prompt pour message de bienvenue après connexion"""

        context = self._extract_profile_context(profile)

        prompt = f"""Tu es Hugo, développeur spécialisé en automatisations back-end et agents IA. Tu aides freelances et agences à optimiser leurs process.

PROFIL :
- Nom: {context['name']}
- Titre: {context['headline']}
- Entreprise: {context['company']}
- Localisation: {context['location']}
- Description: {context['about']}

STRUCTURE DU MESSAGE (OBLIGATOIRE) :
1. Salutation : Salut/Hey/Hello/Bonjour/Hola [prénom]
2. **Hook émotionnel** : "je suis tombé sur...", "j'aime bien...", "j'ai vu que..."
3. **Compliment spécifique** : Montre que tu as vraiment lu (positionnement, mention précise, différenciation)
4. **UNE question ouverte mais cadrée** : Sur son activité, pas sur la géographie

EXEMPLES RÉELS (RESPECTE CETTE STRUCTURE) :
✅ "Hey Lucas, je vois que tu gères les Facebook Ads pour l'e-com, **pas mal du tout**, tu bosses plutôt avec des structures déjà rodées ou t'accompagnes aussi des shops en lancement ?"
→ Hook + compliment léger + question intéressante

✅ "Hello Lucie, **je suis tombé sur ton profil** et **j'aime beaucoup** ta mention "visual storytelling" qui **sort du classique** "graphic design". Tu te concentres plutôt sur quel type de projets en ce moment en tant que freelance ?"
→ Hook émotionnel + compliment précis + différenciation + question

✅ "Hello Mathias, j'ai vu que tu connectais les freelances IA avec les entreprises via Skillize, **ça m'intéresse pas mal** car je bosse justement sur des projets d'automatisation. Tu as lancé la plateforme il y a combien de temps ?"
→ Observation + hook émotionnel + lien personnel + question temporelle

TYPES DE QUESTIONS (privilégier les intéressantes) :
✅ **Activité/Expertise** : "tu te concentres plutôt sur quel type de projets ?", "tu bosses surtout sur quels leviers ?"
✅ **Profil clients** : "tu accompagnes plutôt quel type de structures ?", "tu bosses avec quel profil de clients ?"
✅ **Temporelle** : "ça fait longtemps que tu as lancé ?", "tu as démarré il y a combien de temps ?"
❌ **Géographie** : ÉVITER "local ou national ?" (trop basique, pas engageant)

HOOKS ÉMOTIONNELS À UTILISER :
- "je suis tombé sur..."
- "j'aime bien/beaucoup..."
- "ça m'intéresse..."
- "j'ai remarqué..."

COMPLIMENTS SPÉCIFIQUES (exemples) :
- "ton positionnement X qui sort du classique Y"
- "ta mention X, ça parle direct"
- "pas mal du tout"
- "c'est un positionnement qui parle"
- Citer un élément précis de sa bio

RÈGLES STRICTES :
- TOUJOURS inclure un hook émotionnel + compliment spécifique
- Question sur l'ACTIVITÉ, pas sur la géographie
- 1-2 phrases MAX avant la question
- UNE SEULE question
- Ne JAMAIS mentionner IA/automatisation/tech sauf si c'est dans sa bio
- Pas d'emojis
- Ton direct, pas corporate
- INTERDIT : "Il est important", "essentiel", "tu as raison", formules corporate

OBJECTIF : Donner ENVIE de répondre par un compliment sincère + question intéressante

Génère UNIQUEMENT le message, rien d'autre."""

        return prompt

    def _extract_profile_context(self, profile: Dict[str, Any]) -> Dict[str, str]:
        """Extrait et nettoie le contexte du profil avec fallbacks"""

        first_name = profile.get('first_name', '')
        last_name = profile.get('last_name', '')

        # Construire le nom complet
        name = f"{first_name} {last_name}".strip()
        if not name:
            name = first_name or last_name or ''

        # Extraire les autres champs
        company = profile.get('company', '')
        headline = profile.get('headline', '') or profile.get('job_title', '')
        location = profile.get('location', '')
        about = profile.get('about', '')

        # Tronquer about à 300 caractères
        if about and len(about) > 300:
            about = about[:300]

        return {
            'name': name,
            'first_name': first_name,
            'headline': headline,
            'company': company,
            'location': location,
            'about': about
        }

    def _format_template(
        self,
        template: str,
        greeting: str,
        context: Dict[str, str]
    ) -> str:
        """
        Formate un template avec validation des variables

        Args:
            template: Template avec {placeholders}
            greeting: Salutation sélectionnée
            context: Contexte du profil

        Returns:
            Template formaté avec fallbacks
        """
        # Variables avec fallbacks intelligents
        variables = {
            'greeting': greeting,
            'name': context['name'],
            'first_name': context['first_name'] or (
                f"l'équipe {context['company']}" if context['company'] else "votre équipe"
            ),
            'company': context['company'] or 'votre entreprise',
            'title': context['headline'],
            'location': context['location']
        }

        try:
            return template.format(**variables)
        except KeyError as e:
            logger.warning(f"Missing template variable {e} - using template as-is")
            # Retourner le template tel quel si variable manquante
            return template


# Instance globale réutilisable
message_composer = MessageComposer()
