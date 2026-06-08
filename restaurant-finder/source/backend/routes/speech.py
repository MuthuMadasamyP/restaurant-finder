import asyncio
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services.speech_recognizer import (
    SpeechRecognitionUnavailable,
    SpeechTranscriptionError,
    transcribe_wav,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/speech/transcribe",
    summary="Transcribe microphone input",
    description="Accepts a short WAV recording and returns Python speech recognition text.",
)
async def transcribe_speech_endpoint(
    audio: UploadFile = File(...),
    language: str = Form("en-IN"),
):
    if audio.content_type not in {"audio/wav", "audio/wave", "audio/x-wav"}:
        raise HTTPException(status_code=415, detail="Please upload a WAV audio recording.")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio recording is empty.")

    if len(audio_bytes) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio recording is too large.")

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            temp_file.write(audio_bytes)
            temp_path = Path(temp_file.name)

        transcript = await asyncio.to_thread(transcribe_wav, temp_path, language)
    except SpeechRecognitionUnavailable as exc:
        logger.warning("SpeechRecognition dependency is unavailable: %s", exc)
        raise HTTPException(status_code=501, detail=str(exc))
    except SpeechTranscriptionError as exc:
        logger.info("Speech transcription failed: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Unhandled speech transcription error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Speech transcription failed unexpectedly.")
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)

    return {"success": True, "transcript": transcript, "language": language}
