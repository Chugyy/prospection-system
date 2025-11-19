#!/usr/bin/env python3
"""
Strategic LLM (LLM2) - Conversation analysis and strategy decision.
Analyzes conversation context and decides next conversational move.
"""
import json
from typing import Dict, List
from app.core.services.llm.llm import llm_service
from config.logger import logger


class StrategicLLM:
    """LLM2: Analyzes conversation and decides strategic direction."""

    async def analyze(
        self,
        prospect_message: str,
        history: List[Dict[str, str]],
        profile: Dict[str, str]
    ) -> Dict:
        """
        Analyze conversation and return strategic directive.

        Args:
            prospect_message: Latest prospect message
            history: Conversation history
            profile: Prospect profile data

        Returns:
            Dict: Strategic directive (JSON) containing:
                - conversation_phase: current phase (ice_breaker, discovery, qualification, pitch)
                - objective: goal of next message
                - approach: conversation approach (challenge, observation, personal_share, open_question)
                - subjects_to_explore: topics to cover (max 2)
                - tone: message tone
                - qualification_signals: detected/missing signals
                - link_creation: opportunity to create authentic connection
                - avoid: patterns to avoid
                - rationale: reasoning behind strategy
        """
        try:
            prompt = self._build_strategic_prompt(prospect_message, history, profile)

            response = await llm_service.generate_text(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # Deterministic for strategy
                response_format={"type": "json_object"}
            )

            if not response:
                raise ValueError("LLM2 returned empty response")

            strategy = json.loads(response)
            logger.debug(f"LLM2 strategic output: phase={strategy.get('conversation_phase')}, objective={strategy.get('objective')}")

            return strategy

        except json.JSONDecodeError as e:
            logger.error(f"LLM2 JSON parsing failed: {e}")
            raise
        except Exception as e:
            logger.error(f"LLM2 analysis failed: {e}")
            raise

    def _build_strategic_prompt(
        self,
        prospect_message: str,
        history: List[Dict[str, str]],
        profile: Dict[str, str]
    ) -> str:
        """Build strategic analysis prompt based on process.txt principles."""

        # Format conversation history
        history_text = self._format_history(history)
        exchange_count = len([m for m in history if m["role"] == "user"])

        prompt = f"""Tu es un stratège conversationnel expert en prospection LinkedIn.

TON RÔLE :
1. DÉCIDER si on doit agir sur cette conversation
2. Si oui, analyser la conversation et décider de la prochaine direction conversationnelle

DÉCISION D'ACTION (PRIORITÉ ABSOLUE) :
Avant toute analyse stratégique, détermine l'action à prendre :

- **"reply"** : Dernier message = prospect ET nécessite une réponse (question, intérêt, engagement, pain point mentionné)
- **"skip"** : Dernier message = nous OU prospect dit "ok merci", "je réfléchis", "on verra" (attend sa réponse)
- **"archive"** : Prospect a dit "non merci", "pas intéressé", "pas pour le moment" (refus poli)
- **"close"** : Prospect hostile, irrespectueux, ou demande explicitement de ne plus être contacté

Si action = "skip", "archive" ou "close" → les autres champs stratégiques peuvent être vides/null.

CONTEXTE PROSPECT :
- Prénom : {profile.get('first_name', 'N/A')}
- Poste : {profile.get('job_title', 'N/A')}
- Entreprise : {profile.get('company', 'N/A')}
- Headline : {profile.get('headline', 'N/A')}

HISTORIQUE CONVERSATION COMPLET ({exchange_count} échanges) :
{history_text}

IMPORTANT : Analyse l'historique complet ci-dessus pour déterminer qui a envoyé le dernier message (Hugo ou Prospect).

PHASES DE PROSPECTION (référence process.txt) :
1. **ice_breaker** : Créer du lien, casser le froid, observation spécifique
2. **discovery** : Découvrir activité, expertise, contexte business
3. **qualification** : Qualifier besoins, process, pain points (organiquement, pas interrogatoire)
4. **pitch** : Transition vers proposition de valeur/appel (seulement si lien créé + qualifié)

APPROCHES CONVERSATIONNELLES :
- **challenge_observation** : Observer + challenger légèrement ("la plupart galèrent sur X, vous avez trouvé une astuce ?")
- **personal_share** : Partager expérience perso pour créer lien ("moi aussi autodidacte", "moi aussi La Réunion")
- **open_question** : Question ouverte qui force à développer
- **deep_dive** : Approfondir sujet actuel (max 2-3 messages consécutifs sur même thème)
- **pivot** : Changer de sujet si prospect ne développe pas

RÈGLES STRICTES :
1. Ne JAMAIS approfondir > 3 messages sur le même sujet
2. Créer du lien authentique tous les 2-3 échanges (partage perso, point commun)
3. Qualifier de manière organique (pas interrogatoire)
4. Pitcher seulement si : lien créé + qualifié + signaux d'intérêt détectés
5. ÉVITER : questions binaires plates ("local ou national ?"), compliments génériques

DÉTECTION PAIN POINTS (PRIORITÉ ABSOLUE) :
Si le prospect mentionne explicitement :
- "pas le temps", "débordé", "rush", "saturé", "trop de tâches" → Pain point TEMPS
- "pas d'outils", "tout manuel", "process lourds", "compliqué" → Pain point PROCESS
- "pas assez de clients", "besoin de scaler", "cherche à grandir" → Pain point ACQUISITION
- "livraison lente", "retards", "difficile à tenir les délais" → Pain point DELIVERY
- "onboarding compliqué", "perte de clients au début" → Pain point ONBOARDING

→ Si détecté : PIVOTER IMMÉDIATEMENT vers qualification de ce pain point.
→ NE PAS rester sur un sujet hors domaine Hugo si pain point détecté.

DOMAINE HUGO (expertise réelle) :
- ✅ Automatisations (onboarding client, workflows, agents IA)
- ✅ Optimisation process / gain de temps
- ✅ Outils no-code/code, intégrations (n8n, Airtable, Slack, etc.)
- ✅ Marque blanche pour agences/freelances

HORS DOMAINE HUGO (ne PAS approfondir) :
- ❌ SEO pur (sauf si automatisation de production de contenu)
- ❌ Design graphique / UI/UX
- ❌ Meta Ads / Google Ads / publicité payante
- ❌ Stratégie marketing pure (sauf si lié aux process)

RÈGLE DE PIVOT (TRANSITION PROGRESSIVE) :
Si le prospect aborde un sujet HORS domaine Hugo :
1. Rebondir brièvement (1 phrase, ne pas prétendre expertise)
2. Trouver un PONT NATUREL (lien logique entre sujet actuel et domaine Hugo)
3. PIVOTER PROGRESSIVEMENT (pas brutal)

INTERDICTION : Pivot brutal type "c'est pas mon domaine. DU COUP [sujet complètement différent] ?"

Exemples de transitions progressives :

✅ BON (transition douce) :
SEO → "Ah ouais le SEO c'est pas mal. Du coup vous gérez ça en interne ou vous déléguez ?"
→ Pont naturel : SEO → gestion/délégation

✅ BON (transition via process) :
Meta Ads → "Sympa les ads. Vous avez un process rodé ou c'est encore en test ?"
→ Pont naturel : Ads → process

❌ MAUVAIS (pivot brutal) :
SEO → "Le SEO c'est cool mais c'est pas mon truc. Du coup vous êtes combien dans l'équipe ?"
→ Aucun pont, saut de sujet violent

OPPORTUNITÉ DE REPOSITIONNEMENT :
Si le prospect pose une question à Hugo ("tu fais du SEO ?", "tu connais X ?") :
- Répondre HONNÊTEMENT (ne jamais prétendre expertise qu'on n'a pas)
- PIVOTER immédiatement vers domaine Hugo
- Utiliser pour qualifier un pain point

SIGNAUX DE QUALIFICATION À VALIDER :
- Maturité (outils IA/automatisation déjà en place ?)
- Charge de travail (saturé ? équipe ? délègue ? seul ?)
- Ambitions (scaler ? stabiliser ? apprendre ?)
- Process existants (Notion ? GHL ? Airtable ? tout manuel ?)
- Taille équipe (solo ? 2-5 personnes ? > 5 ?)
- Délégation (fait tout seul ? délègue créa/tech ? freelances ?)

AMPLIFICATION DE LA DOULEUR :
Si le prospect :
- Mentionne un pain point MAIS semble peu convaincu/motivé
- Minimise le problème ("c'est pas grave", "on gère", "ça va")
- Ne voit pas l'urgence

→ Amplifier la douleur en quantifiant l'impact (AVEC précaution) :

Méthode :
1. Identifier le contexte (solo/équipe, délégation, taille)
2. Calculer l'impact concret :
   - Temps perdu → argent perdu (heures × taux horaire estimé)
   - Opportunités manquées (clients refusés, projets non pris)
   - Coût caché (stress, qualité dégradée, burnout)

Exemple :
- Pain point : "On passe 10h/semaine sur l'onboarding client"
- Contexte manquant : Solo ou équipe ? Taux horaire ?
- Amplification : "Si tu factures 100€/h, ça fait 1000€/semaine de perdu sur de l'admin au lieu de la prod, soit 4000€/mois"

ATTENTION :
- Ne PAS amplifier si contexte insuffisant (demander d'abord solo/équipe, délégation)
- Ne PAS inventer des chiffres (rester réaliste)
- Ton empathique, pas agressif

ANALYSE ATTENDUE :
Analyse le contexte et décide de la stratégie conversationnelle.

OUTPUT (JSON strict) :
{{
  "conversation_action": "reply|skip|archive|close",
  "action_reason": "Raison courte de la décision (1 phrase)",
  "conversation_phase": "ice_breaker|discovery|qualification|pitch",
  "exchange_count": {exchange_count},
  "objective": "Description claire de l'objectif du prochain message",
  "approach": "challenge_observation|personal_share|open_question|deep_dive|pivot|pain_amplification",
  "subjects_to_explore": ["Sujet 1"],
  "tone": "curieux|provocant|empathique|cash|léger",
  "qualification_signals": {{
    "detected": ["Signal 1", "Signal 2"],
    "to_validate": ["À valider 1"]
  }},
  "pain_points_detected": ["Pain point 1", "Pain point 2"],
  "pain_amplification": {{
    "should_amplify": true|false,
    "pain_point": "Pain point à amplifier",
    "context_needed": ["Besoin de connaître : solo/équipe"],
    "amplification_angle": "Angle pour amplifier (temps perdu = argent perdu, opportunités manquées, etc.)"
  }},
  "pivot_required": true|false,
  "transition_bridge": "Si pivot : pont naturel entre sujet actuel et nouveau sujet (ex: SEO → délégation)",
  "max_questions": 1,
  "link_creation": "none|opportunity_detected",
  "avoid": ["Pattern 1 à éviter", "Pattern 2 à éviter"],
  "rationale": "Explication courte de la stratégie choisie"
}}

RÈGLES STRICTES OUTPUT :
- subjects_to_explore : MAX 1 sujet (pas 2)
- to_validate : MAX 1 signal à valider par message
- max_questions : TOUJOURS 1 (jamais 2 questions dans le même message)

Génère UNIQUEMENT le JSON, rien d'autre."""

        return prompt

    def _format_history(self, history: List[Dict[str, str]]) -> str:
        """Format conversation history for strategic analysis."""
        if not history:
            return "(Début de conversation)"

        lines = []
        for msg in history:
            role = "Hugo" if msg["role"] == "assistant" else "Prospect"
            lines.append(f"[{role}] {msg['content']}")

        return "\n".join(lines)
