from __future__ import annotations

import html
import urllib.request

from .config import settings


VOICES = {
    "en": "en-US-JennyNeural",
    "es": "es-US-PalomaNeural",
    "vi": "vi-VN-HoaiMyNeural",
    "ko": "ko-KR-SunHiNeural",
    "fa": "fa-IR-DilaraNeural",
}


def synthesize(text: str, language: str) -> bytes:
    if not settings.speech_enabled:
        raise RuntimeError("Azure AI Speech is not configured")
    voice = VOICES.get(language, VOICES["en"])
    locale = voice[:5]
    ssml = (
        f"<speak version='1.0' xml:lang='{locale}'>"
        f"<voice name='{voice}'><prosody rate='-8%'>{html.escape(text)}</prosody></voice></speak>"
    )
    request = urllib.request.Request(
        f"https://{settings.speech_region}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=ssml.encode("utf-8"),
        headers={
            "Ocp-Apim-Subscription-Key": settings.speech_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
            "User-Agent": "LastMileNavigator",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()

