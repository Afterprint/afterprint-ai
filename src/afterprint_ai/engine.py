import hashlib
import re

from .schemas import Citation, Claim, Source, Span


def stable(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]

def citation(source: Source, span: Span) -> Citation:
    return Citation(evidenceId=source.evidenceId, versionId=source.versionId, span=span.ref,
                    quote=span.text, page=span.page, frameTimeMs=span.frameTimeMs)

def verify(claims: list[Claim], sources: list[Source]) -> list[Claim]:
    indexed = {s.versionId: s for s in sources}
    for claim in claims:
        if claim.category in ('VERIFIED_FACT', 'CORROBORATED_CLAIM', 'CONFLICT') and not claim.citations:
            raise ValueError('A grounded claim needs citations')
        for c in claim.citations:
            source = indexed.get(c.versionId)
            if not source or source.evidenceId != c.evidenceId:
                raise ValueError('Citation outside authorized source set')
            span = next((s for s in source.spans if s.ref == c.span), None)
            if not span or not c.quote or c.quote not in span.text:
                raise ValueError('Citation quote does not match its source span')
            if c.page != span.page or c.frameTimeMs != span.frameTimeMs:
                raise ValueError('Citation location mismatch')
            if claim.category == 'VERIFIED_FACT' and not source.authenticated:
                raise ValueError('Unauthenticated source cannot establish verified fact')
        if claim.category == 'CORROBORATED_CLAIM':
            distinct = {c.versionId for c in claim.citations}
            if len(distinct) < 2:
                raise ValueError('Corroboration requires citations from at least two distinct evidence versions')
    return claims

def extract(evidence_id: str, version_id: str, digest: str, spans: list[Span]) -> Source:
    events, entities = [], {}
    for span in spans:
        for match in re.finditer(r'\b([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\b', span.text):
            h, m, s = match.groups()
            events.append({'id': stable(version_id+span.ref+str(match.start())),
                           'time': f'{int(h):02}:{m}:{s or "00"}',
                           'description': f'The source contains the time claim “{match.group()}”.',
                           'precision': 'EXACT' if s else 'MINUTE', 'basis': 'STATEMENT',
                           'timezone': 'UNKNOWN', 'category': 'INFERENCE',
                           'citations': [Citation(evidenceId=evidence_id, versionId=version_id,
                                                span=span.ref, quote=span.text, page=span.page,
                                                frameTimeMs=span.frameTimeMs).model_dump()]})
        for match in re.finditer(r'\b(?:Vehicle|Gate|Camera|Device|Depot)\s+[A-Za-z0-9-]+', span.text):
            label = match.group()
            entities[label] = {'id': stable(label.casefold()), 'label': label, 'type': 'SOURCE_LABEL',
                               'evidenceId': evidence_id, 'span': span.ref}
    return Source(evidenceId=evidence_id, versionId=version_id, sha256=digest, spans=spans,
                  events=events, entities=list(entities.values()))

def query_sources(query: str, sources: list[Source]) -> list[Claim]:
    words = {w.casefold() for w in re.findall(r'\w+', query) if len(w) > 2}
    candidates = []
    for source in sources:
        for span in source.spans:
            score = len(words & set(re.findall(r'\w+', span.text.casefold())))
            if score:
                candidates.append((score, source, span))
    candidates.sort(key=lambda x: (-x[0], x[1].versionId, x[2].ref))
    claims = [Claim(id=stable(source.versionId+span.ref), category='INFERENCE',
                    text=f'Source excerpt (not independently authenticated): {span.text}',
                    citations=[citation(source, span)]) for _, source, span in candidates[:8]]
    if not claims:
        claims = [Claim(id=stable(query), text='The authorized evidence does not provide enough support to answer this question.',
                        category='UNKNOWN', citations=[])]
    return verify(claims, sources)

def conflict_candidates(sources: list[Source]) -> list[dict]:
    result = []
    # Candidate contradictions only where matching extracted labels link the records.
    for i, a in enumerate(sources):
        for b in sources[i+1:]:
            common = {e['label'].casefold() for e in a.entities} & {e['label'].casefold() for e in b.entities}
            if not common:
                continue
            for ea in a.events:
                for eb in b.events:
                    if ea['time'] == eb['time']:
                        continue
                    result.append({'id': stable(ea['id']+eb['id']), 'type': 'TIMESTAMP_CONFLICT',
                                   'description': 'Potential differing time claims for a shared source label; event identity needs human review.',
                                   'status': 'OPEN', 'left': {'id': ea['id'], 'text': ea['description'],
                                   'category': 'INFERENCE', 'citations': ea['citations']},
                                   'right': {'id': eb['id'], 'text': eb['description'],
                                   'category': 'INFERENCE', 'citations': eb['citations']}})
    return result
