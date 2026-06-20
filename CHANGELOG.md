# Changelog

## 2026-06-20

### Added

- Automatic LinkedIn job discovery from a search query
- `--discover-only` mode to preview ranked jobs without applying
- `JOB_SEARCH_PORTAL` and `JOB_SEARCH_RESULT_LIMIT` configuration options
- Runtime controls for agent LLM timeout, step timeout, thinking mode, and vision mode
- Interview-prep-only generation mode
- Skip-document-generation mode for live apply flows

### Changed

- LinkedIn discovery now uses the guest job postings endpoint and broader URL extraction
- Batch mode can auto-discover, rank, and select the top verified jobs from a search query
- Documentation now includes search-based discovery and preview examples
- Local fallback model behavior is more configurable for slower or non-vision setups

### Fixed

- Browser agent runtime compatibility by initializing missing task timing state
- Explicit discovery and configuration error handling for search-driven runs