# Legacy Code

This directory contains code refactored out of the main execution path.

## `ai_a/`
- Originally `app/services/ai_a`.
- Contains old versions of pipeline steps or unused utility scripts.
- The active pipeline logic has been moved to `app/services/rag/` and `app/services/rag/steps/`.
- **Do not import from here** in new code.
