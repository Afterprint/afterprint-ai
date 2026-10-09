"""The HTTP surface: service-token authentication and how errors reach the caller."""

import pytest
from fastapi.testclient import TestClient

from afterprint_ai import app as app_module
from afterprint_ai.engine import extract
from afterprint_ai.schemas import Span

TOKEN = 't' * 40
GOOD = {'Authorization': f'Bearer {TOKEN}'}
PROCESS = {'caseId': 'c', 'evidenceId': 'e1', 'versionId': 'v1', 'sha256': 'a' * 64,
           'url': 'https://storage.example.com/o', 'mimeType': 'text/plain'}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('AI_SERVICE_TOKEN', TOKEN)
    return TestClient(app_module.app)


def test_every_route_needs_the_service_token(client):
    for method, path in [('get', '/internal/v1/health'), ('post', '/internal/v1/process-evidence'),
                         ('post', '/internal/v1/query'), ('post', '/internal/v1/detect-conflicts')]:
        assert getattr(client, method)(path).status_code == 401, path


@pytest.mark.parametrize('header', [
    '', 'Bearer', 'Bearer ', f'Bearer {TOKEN}x', f'Bearer {TOKEN[:-1]}', f'bearer {TOKEN}',
    f'Basic {TOKEN}', TOKEN, 'Bearer wrong',
])
def test_a_wrong_or_malformed_token_is_refused(client, header):
    assert client.get('/internal/v1/health', headers={'Authorization': header}).status_code == 401


def test_the_right_token_is_accepted(client):
    response = client.get('/internal/v1/health', headers=GOOD)
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_a_short_server_token_disables_the_service_even_if_it_matches(monkeypatch):
    """A weak configured secret must fail closed, never grant access."""
    monkeypatch.setenv('AI_SERVICE_TOKEN', 'short')
    client = TestClient(app_module.app)
    assert client.get('/internal/v1/health', headers={'Authorization': 'Bearer short'}).status_code == 401


def test_a_missing_server_token_refuses_everyone(monkeypatch):
    monkeypatch.delenv('AI_SERVICE_TOKEN', raising=False)
    client = TestClient(app_module.app)
    assert client.get('/internal/v1/health', headers={'Authorization': 'Bearer '}).status_code == 401
    assert client.get('/internal/v1/health').status_code == 401


def test_unknown_fields_are_rejected(client):
    response = client.post('/internal/v1/process-evidence', headers=GOOD, json={**PROCESS, 'extra': 1})
    assert response.status_code == 422


def test_a_malformed_hash_is_rejected_before_any_work(client, monkeypatch):
    called = []

    async def spy(_request):
        called.append(1)
        return []

    monkeypatch.setattr(app_module, 'process_media', spy)
    response = client.post('/internal/v1/process-evidence', headers=GOOD, json={**PROCESS, 'sha256': 'XYZ'})
    assert response.status_code == 422
    assert called == []


def test_a_validation_failure_in_processing_is_a_422_with_the_reason(client, monkeypatch):
    async def refuse(_request):
        raise ValueError('Unapproved storage endpoint')

    monkeypatch.setattr(app_module, 'process_media', refuse)
    response = client.post('/internal/v1/process-evidence', headers=GOOD, json=PROCESS)
    assert response.status_code == 422
    assert response.json()['detail'] == 'Unapproved storage endpoint'


def test_a_successful_process_returns_cited_source_data(client, monkeypatch):
    async def fake(_request):
        return [Span(ref='line 1', text='Vehicle X arrived at 20:54.')]

    monkeypatch.setattr(app_module, 'process_media', fake)
    response = client.post('/internal/v1/process-evidence', headers=GOOD, json=PROCESS)
    assert response.status_code == 200
    body = response.json()
    assert body['evidenceId'] == 'e1' and body['versionId'] == 'v1' and body['sha256'] == 'a' * 64
    assert body['spans'][0]['ref'] == 'line 1'


def test_query_with_no_sources_answers_unknown_instead_of_inventing(client):
    response = client.post('/internal/v1/query', headers=GOOD, json={'caseId': 'c', 'query': 'who did it'})
    assert response.status_code == 200
    claims = response.json()['claims']
    assert all(c['category'] == 'UNKNOWN' and c['citations'] == [] for c in claims)


def test_timeline_is_sorted_by_time(client):
    a = extract('e1', 'v1', 'a' * 64, [Span(ref='l1', text='Vehicle X arrived at 21:30.')]).model_dump()
    b = extract('e2', 'v2', 'b' * 64, [Span(ref='l1', text='Camera Y recorded at 08:15.')]).model_dump()
    response = client.post('/internal/v1/build-timeline', headers=GOOD, json={'caseId': 'c', 'sources': [a, b]})
    assert response.status_code == 200
    times = [e['time'] for e in response.json()]
    assert times == sorted(times) and len(times) == 2
