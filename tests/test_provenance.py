import pytest
from afterprint_ai.schemas import Span, Claim, Citation
from afterprint_ai.engine import extract, query_sources, verify, conflict_candidates

def source(text='Vehicle X arrived at 20:54.'):
    return extract('e1', 'v1', 'a'*64, [Span(ref='line 1', text=text)])

def test_exact_location_and_time_precision():
    s = source()
    assert s.events[0]['precision'] == 'MINUTE'
    assert s.events[0]['timezone'] == 'UNKNOWN'
    answer = query_sources('Vehicle arrived', [s])
    assert answer[0].citations[0].span == 'line 1'
    assert answer[0].category == 'INFERENCE'

def test_unknown_does_not_fill_gap():
    assert query_sources('unmentioned elephant', [source()])[0].category == 'UNKNOWN'

def test_fabricated_citation_rejected():
    s = source()
    claim = Claim(id='c', text='Invented', category='INFERENCE', citations=[Citation(evidenceId='e1', versionId='v1', span='line 2', quote='Invented')])
    with pytest.raises(ValueError):
        verify([claim], [s])

def test_no_promotion_to_fact():
    s = source()
    c = query_sources('Vehicle', [s])[0]
    c.category = 'VERIFIED_FACT'
    with pytest.raises(ValueError):
        verify([c], [s])

def test_case_boundary():
    c = query_sources('Vehicle', [source()])[0]
    with pytest.raises(ValueError):
        verify([c], [])

def test_conflict_requires_linked_entity():
    a = source()
    b = extract('e2', 'v2', 'b'*64, [Span(ref='p1', text='Vehicle X arrived at 21:06.')])
    assert len(conflict_candidates([a,b])) == 1
    unrelated = extract('e3','v3','c'*64,[Span(ref='p1',text='Camera Y recorded 22:00.')])
    assert conflict_candidates([a,unrelated]) == []

def test_favorable_evidence_same_retrieval_threshold():
    a = source('Vehicle X was not at the depot; the dispatch entry was corrected.')
    assert 'not at the depot' in query_sources('Vehicle depot', [a])[0].text
