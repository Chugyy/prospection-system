# Plan de refactoring : Architecture unifiée des actions

## Objectif
Unifier l'architecture d'envoi des messages en créant des utils réutilisables et en rendant les workers autonomes.

---

## Architecture cible

```
app/core/
├── job/
│   ├── reply.py          # Génère + envoie réponses IMMÉDIATEMENT
│   ├── connection.py      # Gère connexions + envoie IMMÉDIATEMENT
│   ├── followup.py        # Crée les relances A/B/C planifiées
│   └── queue.py           # Exécute les actions planifiées
├── utils/
│   ├── actions.py         # Fonctions send_* réutilisables
│   ├── scheduler.py
│   └── quota.py
```

---

## Changements clés

### ✅ Nouveau comportement
- **reply.py** : Envoie **immédiatement** (plus de délai 2-10 min)
- **connection.py** : Utilise `actions.py` au lieu de code dupliqué
- **followup.py** : Renommé, focus sur création des relances
- **queue.py** : Nouveau fichier pour exécuter les actions planifiées

---

## Étapes de migration

### 1. Créer `utils/actions.py`
Extraire les fonctions d'exécution depuis `followup.py` :

```python
async def execute_send_reply(prospect_id, account_id, content):
    """Envoie immédiatement une réponse générée"""
    result = await send_message_via_unipile(...)
    await crud.create_log(action='send_reply', status='success', ...)
    return result

async def execute_send_first_contact(prospect_id, account_id):
    """Envoie immédiatement le premier contact"""
    content = await message_composer.generate_welcome_message(...)
    result = await send_message_via_unipile(...)
    await crud.create_log(action='send_first_contact', status='success', ...)
    return result

async def execute_send_followup(action_type, prospect_id, account_id, payload):
    """Envoie immédiatement un followup"""
    content = ... (selon action_type)
    result = await send_message_via_unipile(...)
    await crud.create_log(action=action_type, status='success', ...)
    return result
```

---

### 2. Modifier `reply.py`
**AVANT** :
```python
# Créer action pending
await crud.create_log(
    action='send_reply',
    status='pending',
    scheduled_at=datetime.now() + timedelta(minutes=random.randint(2, 10)),
    ...
)
```

**APRÈS** :
```python
from app.core.utils.actions import execute_send_reply

# Envoyer immédiatement
result = await execute_send_reply(
    prospect_id=prospect_id,
    account_id=account_id,
    content=response
)

if result['success']:
    replies_generated += 1
    logger.info(f"✅ Reply sent immediately to prospect {prospect_id}")
else:
    failed += 1
    logger.error(f"❌ Failed to send reply to prospect {prospect_id}")
```

---

### 3. Modifier `connection.py`
**AVANT** :
```python
# Code dupliqué d'envoi
content = await message_composer.generate_welcome_message(...)
result = await send_message_via_unipile(...)
```

**APRÈS** :
```python
from app.core.utils.actions import execute_send_first_contact

# Utiliser la fonction centralisée
result = await execute_send_first_contact(
    prospect_id=prospect_id,
    account_id=account_id
)
```

---

### 4. Renommer et refactorer `followup.py`
**Garder** uniquement la logique de création des relances planifiées :
```python
async def schedule_followup_actions():
    """
    Analyse les prospects et CRÉE les actions de relance si nécessaire
    (Followup A1/A2/A3, B, C)
    """
    prospects = await crud.get_prospects_needing_followup()

    for prospect in prospects:
        followup_type = determine_followup_type(prospect)
        scheduled_at = calculate_scheduled_time(...)

        await crud.create_log(
            action=f'send_followup_{followup_type}',
            status='pending',
            scheduled_at=scheduled_at,
            ...
        )
```

---

### 5. Créer `queue.py`
**Nouveau fichier** pour exécuter les actions planifiées :
```python
from app.core.utils.actions import (
    execute_send_reply,
    execute_send_first_contact,
    execute_send_followup
)

async def process_pending_actions():
    """Exécute toutes les actions pending dans logs"""

    pending_actions = await crud.get_pending_actions(limit=10)

    for action in pending_actions:
        # Vérifier quota
        if not await should_process_today(action['action']):
            continue

        # Exécuter selon le type
        if action['action'] == 'send_reply':
            result = await execute_send_reply(...)
        elif action['action'] == 'send_first_contact':
            result = await execute_send_first_contact(...)
        elif action['action'].startswith('send_followup'):
            result = await execute_send_followup(...)

        # Marquer comme exécuté
        await crud.mark_log_executed(action['id'])
```

---

## Résumé des bénéfices

| Avant | Après |
|-------|-------|
| reply crée action pending → followup exécute | reply envoie immédiatement |
| Délai 2-10 min (risque doublon) | Envoi immédiat (pas de risque) |
| Code dupliqué dans connection.py | Code réutilisé via actions.py |
| followup.py = tout-en-un | Séparation: followup.py + queue.py |
| 2 workers nécessaires (reply + followup) | Chaque worker autonome |

---

## Ordre d'implémentation

1. ✅ Créer `utils/actions.py`
2. ✅ Modifier `reply.py` (envoi immédiat)
3. ✅ Modifier `connection.py` (utiliser actions.py)
4. ✅ Créer `queue.py` (exécuteur)
5. ✅ Refactorer `followup.py` (création relances uniquement)
6. ✅ Tester avec les 7 chats existants

---

## Tests de validation

- [ ] Reply worker envoie immédiatement sans créer log pending
- [ ] Connection worker utilise actions.py
- [ ] Followup worker crée actions planifiées
- [ ] Queue worker exécute les actions planifiées
- [ ] Pas de doublon de messages
- [ ] Logs créés avec status='success' après envoi
