# Contributing to KruschBiz

Thank you for contributing to KruschBiz!

## Development Guidelines

1. **Air-Gap Compliance**: Never introduce dependencies or code that make network requests to external public APIs, cloud analytics, or cloud telemetry.
2. **Citation Preservation**: When adding parsers or chunking logic, always preserve page-true and section-true locators via KruschNexus.
3. **Assertion Grounding Integrity**: All changes to the RAG synthesis engine must undergo evaluation against `tests/eval/test_golden_eval_gate.py` to prevent regression below the 90% threshold.
4. **Code Quality**: Ensure all code passes `ruff check .` and unit tests pass with `pytest tests` (100 tests).
