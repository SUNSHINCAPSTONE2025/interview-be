import os
import tempfile
import subprocess
from google.cloud import speech_v1p1beta1 as speech

class STTService:
    @staticmethod
    def transcribe(audio_bytes: bytes, language: str = "ko-KR") -> str:
        if not audio_bytes:
            raise ValueError("Audio bytes cannot be empty")

        # WebM을 WAV로 변환
        wav_bytes = STTService._convert_to_wav(audio_bytes)

        key_path = os.getenv("GOOGLE_STT_KEY_PATH")
        if key_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path

        client = speech.SpeechClient()

        audio = speech.RecognitionAudio(content=wav_bytes)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            language_code=language,
            enable_automatic_punctuation=True,
        )

        response = client.recognize(config=config, audio=audio)

        transcript = " ".join(
            [result.alternatives[0].transcript for result in response.results]
        ).strip()

        return transcript

    @staticmethod
    def _convert_to_wav(audio_bytes: bytes) -> bytes:
        """WebM/기타 형식을 WAV로 변환"""
        # ffmpeg 경로 설정 (Windows에서 PATH 인식 문제 해결)
        ffmpeg_cmd = r"C:\ffmpeg\bin\ffmpeg.exe"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as input_file:
            input_file.write(audio_bytes)
            input_path = input_file.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as output_file:
            output_path = output_file.name

        try:
            # ffmpeg로 WAV 변환 (mono, 16kHz)
            subprocess.run(
                [
                    ffmpeg_cmd,
                    "-i", input_path,
                    "-ar", "16000",  # 16kHz sample rate
                    "-ac", "1",       # mono
                    "-y",             # overwrite
                    output_path
                ],
                check=True,
                capture_output=True
            )

            # 변환된 WAV 읽기
            with open(output_path, "rb") as f:
                wav_bytes = f.read()

            return wav_bytes

        finally:
            # 임시 파일 삭제
            try:
                os.remove(input_path)
            except:
                pass
            try:
                os.remove(output_path)
            except:
                pass