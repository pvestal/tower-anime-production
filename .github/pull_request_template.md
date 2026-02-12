## Summary

<!-- 1-3 sentences: what changed and why -->

## Changes

-

## Testing

- [ ] Backend tests pass (`cd training/lora-studio && venv/bin/python -m pytest tests/ -v`)
- [ ] Frontend tests pass (`cd training/lora-studio && npx vitest run`)
- [ ] Tested in browser at `/lora-studio/` (if UI changes)
- [ ] Tested relevant API endpoints with curl (if backend changes)

## Review checklist

- [ ] No hardcoded secrets, tokens, or passwords
- [ ] No breaking changes to `/api/lora/*` response shapes (check `test_response_contracts.py`)
- [ ] Database changes are backwards-compatible (if any)
- [ ] New endpoints added to `src/api/client.ts` and `src/types/index.ts` (if applicable)
