# Changelog

## 0.2.0 — 2026-10-09

### Added
- 62 new tests (10 to 72). `tests/test_media.py` covers upload validation:
  approved hosts, credentials and scheme checks, SSRF targets such as the cloud
  metadata address, the HTTPS rule, the size limit while streaming, hash
  mismatch, redirects, and extraction for text, CSV, JSON, PDF, audio, and
  unsupported types. `tests/test_app.py` covers service-token authentication
  and how errors reach the caller.
- CI now lints `tests/` as well as `src/`.

### Fixed
- `EVIDENCE_STORAGE_HOSTS` entries were not trimmed, so `a.com, b.com` silently
  never matched `b.com`; they are now trimmed and lower-cased. An empty or unset
  list used to approve the empty string; it now approves nothing.
- A storage error (4xx, 5xx, or a redirect) raised an unhandled `httpx` error,
  returning 500, and its message contained the signed download URL. It is now a
  422 with a short message that omits the URL.
- The security contact address in the README and SECURITY.md was misspelled
  (`gmaill.com`).

### Changed
- URL validation moved into `validate_storage_url()` so it can be tested alone.
