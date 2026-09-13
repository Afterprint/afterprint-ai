from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
Category = Literal['VERIFIED_FACT', 'CORROBORATED_CLAIM', 'INFERENCE', 'CONFLICT', 'UNKNOWN']
class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')
class Citation(Strict):
    evidenceId: str
    versionId: str
    span: str
    quote: str = ''
    page: int | None = None
    frameTimeMs: int | None = None
class Claim(Strict):
    id: str
    text: str
    category: Category
    citations: list[Citation]
class Span(Strict):
    ref: str
    text: str
    page: int | None = None
    frameTimeMs: int | None = None
class Source(Strict):
    evidenceId: str
    versionId: str
    sha256: str
    spans: list[Span]
    entities: list[dict] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)
    tool: str = 'afterprint-extract/0.1.0'
    authenticated: bool = False
class Request(Strict):
    caseId: str
    sources: list[Source] = Field(default_factory=list, max_length=1000)
    query: str = Field(default='', max_length=4000)
class ProcessRequest(Strict):
    caseId: str
    evidenceId: str
    versionId: str
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    url: str
    mimeType: str
class Answer(Strict):
    claims: list[Claim]
