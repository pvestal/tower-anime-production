## Summary

<!-- 1-3 sentences: what changed and why -->

## Changes

-

## Testing

- [ ] Backend syntax check passes (`find packages/ -name '*.py' -exec python -m py_compile {} +`)
- [ ] Frontend builds (`npm run build`)
- [ ] Tested in browser at `/anime-studio/` (if UI changes)
- [ ] Tested relevant API endpoints with curl (if backend changes)

## Review checklist

- [ ] No hardcoded secrets, tokens, or passwords
- [ ] No breaking changes to `/api/lora/*` response shapes
- [ ] Database changes are backwards-compatible (if any)
- [ ] New endpoints added to `src/api/*.ts` and `src/types/index.ts` (if applicable)
