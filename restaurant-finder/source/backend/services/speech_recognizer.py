from pathlib import Path


class SpeechRecognitionUnavailable(RuntimeError):
    pass


class SpeechTranscriptionError(RuntimeError):
    pass


def transcribe_wav(path: Path, language: str = "en-IN") -> str:
    try:
        import speech_recognition as sr
    except ImportError as exc:
        raise SpeechRecognitionUnavailable(
            "Install SpeechRecognition to enable Python speech input."
        ) from exc

    recognizer = sr.Recognizer()

    try:
        with sr.AudioFile(str(path)) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.2)
            audio = recognizer.record(source)
    except Exception as exc:
        raise SpeechTranscriptionError("Could not read the recorded audio.") from exc

    try:
        return recognizer.recognize_google(audio, language=language).strip()
    except sr.UnknownValueError as exc:
        raise SpeechTranscriptionError("No clear speech was detected.") from exc
    except sr.RequestError as exc:
        raise SpeechTranscriptionError(
            "Speech recognition service is unavailable. Check your internet connection."
        ) from exc
