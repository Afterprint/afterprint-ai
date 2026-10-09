"""Upload validation: which hosts evidence may come from, size limits, integrity checks,
and what the service must never leak. These paths are security relevant."""

import asyncio
import hashlib
import sys

import httpx
import pytest
from pypdf import PdfWriter

from afterprint_ai import media
from afterprint_ai.media import approved_storage_hosts, command, process_media, validate_storage_url
from afterprint_ai.schemas import ProcessRequest

HOST = 'storage.example.com'
SIGNED_URL = f'https://{HOST}/originals/abc?X-Amz-Signature=TOP-SECRET-SIGNATURE'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request(data: bytes, url: str = SIGNED_URL, mime: str = 'text/plain', digest: str | None = None):
    return ProcessRequest(caseId='case', evidenceId='e1', versionId='v1',
                          sha256=digest or sha(data), url=url, mimeType=mime)


def storage(monkeypatch, handler):
    """Route every httpx.AsyncClient to an in-memory fake instead of the network."""
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs['transport'] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(media.httpx, 'AsyncClient', factory)


def serves(data: bytes, status: int = 200, chunk: int = 4):
    def handler(_request: httpx.Request) -> httpx.Response:
        stream = httpx.ByteStream(data)
        return httpx.Response(status, stream=stream)

    return handler


def run(data: bytes, **kwargs):
    return asyncio.run(process_media(request(data, **kwargs)))


@pytest.fixture(autouse=True)
def approved_host(monkeypatch):
    monkeypatch.setenv('EVIDENCE_STORAGE_HOSTS', HOST)
    monkeypatch.delenv('ALLOW_LOCAL_STORAGE', raising=False)
    monkeypatch.delenv('MAX_UPLOAD_BYTES', raising=False)


# --- Which hosts are approved --------------------------------------------------------------

def test_hosts_are_trimmed_lowercased_and_blanks_dropped(monkeypatch):
    monkeypatch.setenv('EVIDENCE_STORAGE_HOSTS', ' A.example.com ,b.example.com,, ')
    assert approved_storage_hosts() == {'a.example.com', 'b.example.com'}


def test_an_unset_or_empty_allowlist_approves_nothing(monkeypatch):
    monkeypatch.delenv('EVIDENCE_STORAGE_HOSTS', raising=False)
    assert approved_storage_hosts() == set()
    for url in ['https://storage.example.com/x', 'https:///x', 'https://localhost/x']:
        with pytest.raises(ValueError, match='Unapproved storage endpoint'):
            validate_storage_url(url)
    monkeypatch.setenv('EVIDENCE_STORAGE_HOSTS', '')
    with pytest.raises(ValueError, match='Unapproved storage endpoint'):
        validate_storage_url('https://storage.example.com/x')


def test_a_host_with_a_space_after_the_comma_still_matches(monkeypatch):
    monkeypatch.setenv('EVIDENCE_STORAGE_HOSTS', 'one.example.com, two.example.com')
    validate_storage_url('https://two.example.com/obj')


def test_the_approved_host_is_accepted_regardless_of_case():
    validate_storage_url(f'https://{HOST.upper()}/obj')


@pytest.mark.parametrize('url', [
    'https://evil.example.com/obj',            # not approved
    f'https://{HOST}.evil.com/obj',            # approved name as a prefix
    f'https://evil{HOST}/obj',                 # approved name as a suffix
    f'https://user:pass@{HOST}/obj',           # credentials in the URL
    f'https://{HOST}@evil.example.com/obj',    # userinfo trick: real host is evil.example.com
    f'ftp://{HOST}/obj',
    f'file://{HOST}/obj',
    f'gopher://{HOST}/obj',
    'https://169.254.169.254/latest/meta-data',  # cloud metadata address
    'https://127.0.0.1/obj',
    'https://[::1]/obj',
    '',
])
def test_unapproved_destinations_are_refused(url):
    with pytest.raises(ValueError, match='Unapproved storage endpoint'):
        validate_storage_url(url)


def test_plain_http_needs_an_explicit_opt_in(monkeypatch):
    with pytest.raises(ValueError, match='HTTPS required'):
        validate_storage_url(f'http://{HOST}/obj')
    monkeypatch.setenv('ALLOW_LOCAL_STORAGE', 'true')
    validate_storage_url(f'http://{HOST}/obj')
    monkeypatch.setenv('ALLOW_LOCAL_STORAGE', 'yes')   # only the exact value "true" counts
    with pytest.raises(ValueError, match='HTTPS required'):
        validate_storage_url(f'http://{HOST}/obj')


def test_a_refused_url_never_triggers_a_request(monkeypatch):
    calls = []
    storage(monkeypatch, lambda r: calls.append(r) or httpx.Response(200, content=b'x'))
    with pytest.raises(ValueError, match='Unapproved storage endpoint'):
        run(b'x', url='https://evil.example.com/obj')
    assert calls == []


# --- Size limit ---------------------------------------------------------------------------

def test_evidence_over_the_limit_is_rejected(monkeypatch):
    monkeypatch.setenv('MAX_UPLOAD_BYTES', '10')
    data = b'x' * 11
    storage(monkeypatch, serves(data))
    with pytest.raises(ValueError, match='exceeds size limit'):
        run(data)


def test_evidence_exactly_at_the_limit_is_accepted(monkeypatch):
    monkeypatch.setenv('MAX_UPLOAD_BYTES', '11')
    data = b'hello world'
    storage(monkeypatch, serves(data))
    assert run(data)[0].text == 'hello world'


def test_the_limit_is_enforced_while_streaming_not_after(monkeypatch):
    """A server that never stops must be cut off, not buffered to the end."""
    monkeypatch.setenv('MAX_UPLOAD_BYTES', '1000')
    produced = []

    class Endless(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(10_000):
                produced.append(1)
                yield b'x' * 500

    storage(monkeypatch, lambda r: httpx.Response(200, stream=Endless()))
    with pytest.raises(ValueError, match='exceeds size limit'):
        run(b'ignored')
    assert len(produced) < 10, f'read {len(produced)} chunks before stopping'


# --- Integrity ------------------------------------------------------------------------------

def test_a_hash_mismatch_is_rejected(monkeypatch):
    storage(monkeypatch, serves(b'the real bytes'))
    with pytest.raises(ValueError, match='hash mismatch'):
        run(b'the real bytes', digest=sha(b'different bytes'))


def test_a_single_flipped_byte_is_caught(monkeypatch):
    original = b'witness statement 0001'
    tampered = b'witness statement 0002'
    storage(monkeypatch, serves(tampered))
    with pytest.raises(ValueError, match='hash mismatch'):
        run(original)


# --- Download failures never leak the signed URL -------------------------------------------

@pytest.mark.parametrize('status', [301, 302, 307, 400, 403, 404, 500, 503])
def test_non_200_responses_become_a_clean_error_without_the_url(monkeypatch, status):
    storage(monkeypatch, lambda r: httpx.Response(status, headers={'Location': 'https://evil.example.com/'}))
    with pytest.raises(ValueError) as caught:
        run(b'x')
    assert f'HTTP {status}' in str(caught.value)
    assert 'TOP-SECRET-SIGNATURE' not in str(caught.value)
    assert HOST not in str(caught.value)


def test_redirects_are_never_followed(monkeypatch):
    seen = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append(str(r.url))
        if r.url.host == HOST:
            return httpx.Response(302, headers={'Location': 'https://evil.example.com/steal'})
        return httpx.Response(200, content=b'x')

    storage(monkeypatch, handler)
    with pytest.raises(ValueError, match='HTTP 302'):
        run(b'x')
    assert seen == [SIGNED_URL], 'must not have contacted the redirect target'


def test_network_errors_become_a_clean_error_without_the_url(monkeypatch):
    def boom(_request):
        raise httpx.ConnectError('connection refused for ' + SIGNED_URL)

    storage(monkeypatch, boom)
    with pytest.raises(ValueError) as caught:
        run(b'x')
    assert 'ConnectError' in str(caught.value)
    assert 'TOP-SECRET-SIGNATURE' not in str(caught.value)


# --- What gets extracted --------------------------------------------------------------------

def test_text_is_split_into_numbered_lines_and_blank_lines_are_skipped(monkeypatch):
    data = b'first\n\n   \nsecond\nthird\n'
    storage(monkeypatch, serves(data))
    spans = run(data)
    assert [(s.ref, s.text) for s in spans] == [('line 1', 'first'), ('line 4', 'second'), ('line 5', 'third')]


@pytest.mark.parametrize('mime', ['text/csv', 'application/json'])
def test_csv_and_json_are_read_as_text(monkeypatch, mime):
    data = b'a,b\n1,2\n'
    storage(monkeypatch, serves(data))
    assert [s.text for s in run(data, mime=mime)] == ['a,b', '1,2']


def test_an_unsupported_media_type_is_refused(monkeypatch):
    data = b'MZ\x90\x00'
    storage(monkeypatch, serves(data))
    with pytest.raises(ValueError, match='Unsupported media type'):
        run(data, mime='application/x-msdownload')


def test_audio_needs_a_configured_speech_provider(monkeypatch):
    monkeypatch.delenv('SPEECH_API_URL', raising=False)
    data = b'RIFF....WAVE'
    storage(monkeypatch, serves(data))
    with pytest.raises(ValueError, match='Speech provider is not configured'):
        run(data, mime='audio/wav')


def test_a_pdf_with_no_text_is_not_silently_accepted(monkeypatch, tmp_path):
    path = tmp_path / 'blank.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open('wb') as file:
        writer.write(file)
    data = path.read_bytes()
    storage(monkeypatch, serves(data))
    with pytest.raises(ValueError, match='Scanned PDF requires an OCR adapter'):
        run(data, mime='application/pdf')


# --- Running external tools ---------------------------------------------------------------

def test_a_media_tool_that_fails_is_reported():
    with pytest.raises(ValueError, match='Media tool failed'):
        asyncio.run(command(sys.executable, '-c', 'import sys; sys.exit(3)'))


def test_a_media_tool_output_is_returned():
    assert asyncio.run(command(sys.executable, '-c', 'print("ok")')).strip() == 'ok'
