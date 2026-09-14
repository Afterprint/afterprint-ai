import hmac
import os

from fastapi import Depends, FastAPI, Header, HTTPException

from .engine import conflict_candidates, extract, query_sources, stable, verify
from .media import process_media
from .schemas import Answer, Claim, ProcessRequest, Request


async def authorize(authorization: str = Header(default='')) -> None:
    token = os.environ.get('AI_SERVICE_TOKEN', '')
    if len(token) < 32 or not hmac.compare_digest(authorization, 'Bearer '+token):
        raise HTTPException(401, 'Service authentication required')

app = FastAPI(title='Afterprint internal AI', version='1.0', dependencies=[Depends(authorize)])

@app.get('/internal/v1/health')
async def health():
    return {'status': 'ok', 'version': '0.1.0', 'mode': 'conservative-source-extraction'}

@app.post('/internal/v1/process-evidence')
async def process(request: ProcessRequest):
    try:
        spans = await process_media(request)
        return extract(request.evidenceId, request.versionId, request.sha256, spans)
    except (ValueError, OSError) as error:
        raise HTTPException(422, str(error)) from error

@app.post('/internal/v1/build-timeline')
async def timeline(request: Request):
    return sorted([event for s in request.sources for event in s.events], key=lambda e: e['time'])

@app.post('/internal/v1/build-graph')
async def graph(request: Request):
    nodes, edges = {}, []
    for s in request.sources:
        nodes[s.evidenceId] = {'id': s.evidenceId, 'label': s.evidenceId, 'evidenceId': s.evidenceId}
        for entity in s.entities:
            nodes[entity['id']] = entity
            edges.append({'from': s.evidenceId, 'to': entity['id'], 'relation': 'SOURCE_MENTIONS',
                          'versionId': s.versionId, 'span': entity['span']})
    return {'nodes': list(nodes.values()), 'edges': edges}

@app.post('/internal/v1/detect-conflicts')
async def conflicts(request: Request):
    return conflict_candidates(request.sources)

@app.post('/internal/v1/query', response_model=Answer)
async def query(request: Request):
    return Answer(claims=query_sources(request.query, request.sources))

@app.post('/internal/v1/reconstruct')
async def reconstruct(request: Request):
    claims = []
    for source in request.sources:
        for span in source.spans:
            claims.extend(query_sources(span.text, [source])[:1])
    claims = list({c.id: c for c in claims}.values())
    claims.append(Claim(id=stable(request.caseId+'unknown'), text='Periods and events not supported by the supplied sources remain unknown.', category='UNKNOWN', citations=[]))
    verify(claims, request.sources)
    return {'claims': [c.model_dump() for c in claims], 'verifiedFacts': [], 'corroboratedClaims': [],
            'conflicts': conflict_candidates(request.sources), 'unknownPeriods': [claims[-1].model_dump()],
            'hypotheses': [c.model_dump() for c in claims if c.category == 'INFERENCE'],
            'timeline': [e for s in request.sources for e in s.events],
            'sourceManifest': [{'versionId': s.versionId, 'sha256': s.sha256} for s in request.sources]}
