import pytest
from afterprint_ai.schemas import Span, Claim, Citation
from afterprint_ai.engine import extract, query_sources, verify, conflict_candidates

def source(evidence_id='e1', version_id='v1', text='Vehicle X arrived at 20:54.', ref='line 1'):
    return extract(evidence_id, version_id, 'a'*64, [Span(ref=ref, text=text)])

def test_verified_fact_without_citations_raises():
    with pytest.raises(ValueError):
        verify([Claim(id='c', text='x', category='VERIFIED_FACT', citations=[])], [])

def test_inference_without_citations_is_accepted():
    claim = Claim(id='c', text='x', category='INFERENCE', citations=[])
    assert verify([claim], []) == [claim]

def test_query_sources_returns_unknown_when_nothing_matches():
    assert query_sources('unrelated elephant parade', [source()])[0].category == 'UNKNOWN'

def test_conflict_candidates_finds_shared_entity_with_different_times():
    a = source('e1', 'v1', 'Vehicle X arrived at 20:54.')
    b = extract('e2', 'v2', 'b'*64, [Span(ref='p1', text='Vehicle X arrived at 21:06.')])
    conflicts = conflict_candidates([a, b])
    assert len(conflicts) == 1
    assert conflicts[0]['type'] == 'TIMESTAMP_CONFLICT'

def test_corroborated_claim_accepted_with_two_distinct_versions():
    a = source('e1', 'v1', 'Vehicle X arrived at 20:54.')
    b = source('e2', 'v2', 'Vehicle X arrived at 20:54.', ref='line 1')
    claim = Claim(id='c', text='Corroborated arrival', category='CORROBORATED_CLAIM', citations=[
        Citation(evidenceId='e1', versionId='v1', span='line 1', quote=a.spans[0].text),
        Citation(evidenceId='e2', versionId='v2', span='line 1', quote=b.spans[0].text),
    ])
    assert verify([claim], [a, b]) == [claim]
