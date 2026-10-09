import asyncio
import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pypdf import PdfReader

from .schemas import ProcessRequest, Span


async def command(*args: str) -> str:
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.PIPE)
    try:
        out, _ = await asyncio.wait_for(process.communicate(), timeout=120)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise ValueError('Media processing exceeded time limit')
    if process.returncode:
        raise ValueError('Media tool failed')
    return out.decode('utf-8', errors='replace')

def approved_storage_hosts() -> set[str]:
    """Hosts evidence may be fetched from, from EVIDENCE_STORAGE_HOSTS (comma separated).

    Entries are trimmed and lower-cased, and blanks are ignored, so an unset variable
    approves nothing instead of matching an empty host.
    """
    raw = os.environ.get('EVIDENCE_STORAGE_HOSTS', '')
    return {host.strip().lower() for host in raw.split(',') if host.strip()}


def validate_storage_url(url: str) -> None:
    """Refuse any URL that is not an approved evidence store. Raises ValueError."""
    parsed = urlparse(url)
    if parsed.hostname not in approved_storage_hosts() or parsed.scheme not in ('https', 'http') or parsed.username:
        raise ValueError('Unapproved storage endpoint')
    if parsed.scheme == 'http' and os.environ.get('ALLOW_LOCAL_STORAGE') != 'true':
        raise ValueError('HTTPS required')


async def process_media(request: ProcessRequest) -> list[Span]:
    validate_storage_url(request.url)
    maximum = int(os.environ.get('MAX_UPLOAD_BYTES', '104857600'))
    with tempfile.TemporaryDirectory(prefix='afterprint-') as folder:
        path = Path(folder)/'original'
        digest = hashlib.sha256()
        size = 0
        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=60) as client, client.stream('GET', request.url) as response:
                if response.status_code != 200:
                    # Never echo the URL: it is a signed link that grants read access.
                    raise ValueError(f'Evidence download failed (HTTP {response.status_code})')
                with path.open('wb') as file:
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > maximum:
                            raise ValueError('Evidence exceeds size limit')
                        digest.update(chunk)
                        file.write(chunk)
        except httpx.HTTPError as error:
            raise ValueError(f'Evidence download failed ({type(error).__name__})') from error
        if digest.hexdigest() != request.sha256:
            raise ValueError('Evidence hash mismatch')
        mime = request.mimeType
        if mime in ('text/plain', 'text/csv', 'application/json'):
            text = path.read_text(encoding='utf-8')
            return [Span(ref=f'line {i+1}', text=line) for i, line in enumerate(text.splitlines()) if line.strip()]
        if mime == 'application/pdf':
            pages = await asyncio.to_thread(lambda: list(PdfReader(path).pages))
            spans = [Span(ref=f'page {i+1}', page=i+1, text=p.extract_text() or '') for i, p in enumerate(pages)]
            if not any(s.text.strip() for s in spans):
                raise ValueError('Scanned PDF requires an OCR adapter; no native text found')
            return [s for s in spans if s.text.strip()]
        if mime.startswith('image/'):
            text = await command(os.environ.get('TESSERACT_PATH', 'tesseract'), str(path), 'stdout')
            return [Span(ref='image OCR', text=text)] if text.strip() else []
        if mime.startswith(('audio/', 'video/')):
            endpoint = os.environ.get('SPEECH_API_URL')
            if not endpoint:
                raise ValueError('Speech provider is not configured')
            audio = Path(folder)/'audio.wav'
            await command(os.environ.get('FFMPEG_PATH', 'ffmpeg'), '-nostdin', '-i', str(path),
                          '-vn', '-ac', '1', '-ar', '16000', str(audio))
            async with httpx.AsyncClient(timeout=120) as client:
                with audio.open('rb') as file:
                    response = await client.post(endpoint, headers={'Authorization': 'Bearer '+os.environ.get('SPEECH_API_KEY', '')},
                        data={'model': os.environ.get('SPEECH_MODEL', 'whisper-1'), 'response_format': 'verbose_json'},
                        files={'file': ('audio.wav', file, 'audio/wav')})
                response.raise_for_status()
                segments = response.json().get('segments', [])
            return [Span(ref=f'segment {i+1}', frameTimeMs=int(s['start']*1000), text=s['text']) for i, s in enumerate(segments)]
        raise ValueError('Unsupported media type')
