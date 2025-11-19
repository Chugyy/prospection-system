"""
Audio and media transcription service using OpenAI Whisper API.
Supports: Audio files (.webm, .mp3, .wav, .m4a, .ogg).
"""

from pathlib import Path
from config.logger import logger


def extract_text_from_audio(file_path: Path, language: str = "fr") -> str:
    """
    Transcribe audio file using OpenAI Whisper API.

    Args:
        file_path: Path to the audio file
        language: ISO-639-1 language code (default: "fr")

    Returns:
        Transcribed text from audio
    """
    try:
        import openai
        from config.config import settings

        if not settings.OPENAI_API_KEY:
            logger.error("OpenAI API key not configured")
            return f"[Message vocal - transcription échouée: clé API manquante]"

        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

        with open(file_path, 'rb') as audio_file:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=language
            )

        transcribed_text = response.text
        logger.info(f"Audio transcribed: {file_path.name} ({len(transcribed_text)} chars)")
        return transcribed_text

    except ImportError:
        logger.error("openai package not installed")
        return "[Message vocal - transcription échouée: package openai manquant]"
    except Exception as e:
        logger.error(f"Audio transcription failed: {file_path.name} - {e}")
        return f"[Message vocal - transcription échouée: {str(e)}]"


def extract_text_from_media(file_path: Path) -> str:
    """
    Extract text from media files (currently audio only).

    Args:
        file_path: Path to media file

    Returns:
        Extracted/transcribed text content
    """
    suffix = file_path.suffix.lower()

    audio_formats = {'.webm', '.mp3', '.wav', '.m4a', '.ogg'}

    if suffix in audio_formats:
        return extract_text_from_audio(file_path)
    else:
        logger.warning(f"Unsupported media format: {suffix} ({file_path.name})")
        return f"[Format non supporté: {suffix}]"


def process_message_attachments(message: dict, account_id: str) -> str:
    """
    Process message attachments and enrich content with transcriptions.

    Args:
        message: Message dict from Unipile API
        account_id: Unipile account ID for downloading attachments

    Returns:
        Enriched content string (original text + transcriptions)
    """
    import tempfile
    from app.core.services.unipile.api.endpoints.messaging import get_message_attachment

    original_text = message.get('text', '').strip()
    attachments = message.get('attachments', [])

    if not attachments:
        return original_text

    transcriptions = []

    for att in attachments:
        att_type = att.get('type')
        att_id = att.get('id')
        is_voice_note = att.get('voice_note', False)

        # Skip non-audio attachments for now
        if att_type != 'audio' or not is_voice_note or not att_id:
            continue

        msg_id = message.get('id')
        if not msg_id:
            continue

        try:
            logger.info(f"Downloading audio attachment {att_id} from message {msg_id}")

            # Download attachment
            result = get_message_attachment(
                message_id=msg_id,
                attachment_id=att_id,
                account_id=account_id
            )

            if not result['success']:
                logger.error(f"Failed to download attachment: {result['error']}")
                transcriptions.append("[Message vocal - téléchargement échoué]")
                continue

            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as tmp:
                tmp.write(result['content'])
                tmp_path = Path(tmp.name)

            logger.info(f"Audio saved to temp file: {tmp_path} ({result['size']} bytes)")

            # Transcribe
            transcription = extract_text_from_audio(tmp_path)

            # Cleanup temp file
            tmp_path.unlink()

            transcriptions.append(transcription)
            logger.info(f"Transcription completed: {len(transcription)} chars")

        except Exception as e:
            logger.error(f"Error processing attachment {att_id}: {e}", exc_info=True)
            transcriptions.append("[Message vocal - erreur de traitement]")

    # Build final content
    parts = []
    if original_text:
        parts.append(original_text)

    for i, trans in enumerate(transcriptions, 1):
        if len(transcriptions) == 1:
            parts.append(f"[Transcription audio]: {trans}")
        else:
            parts.append(f"[Transcription audio {i}]: {trans}")

    return "\n\n".join(parts) if parts else ""
