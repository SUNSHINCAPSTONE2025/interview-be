import os
from google.cloud import speech_v1p1beta1 as speech

class STTService:
    @staticmethod
    def transcribe(audio_bytes: bytes, language: str = "ko-KR") -> str:
        if not audio_bytes:
            return ""
        
        key_path = os.getenv("GOOGLE_STT_KEY_PATH")
        if key_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path

        client = speech.SpeechClient()

        audio = speech.RecognitionAudio(content=audio_bytes)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED,
            language_code=language,
            enable_automatic_punctuation=True,
        )

        try:
            response = client.recognize(config=config, audio=audio)
        except Exception:
            return ""

        transcript = " ".join(
            [result.alternatives[0].transcript for result in response.results]
        ).strip()

        return transcript