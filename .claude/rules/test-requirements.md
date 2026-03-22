# Test Requirements — Every Change Needs a Test

*Auto-generated: 2026-03-22 12:45*

## What Needs a Test

| Change Type | Test Type | Location |
|-------------|-----------|----------|
| New API endpoint | pytest integration test | `apps/api/tests/test_<feature>.py` |
| Service/business logic | pytest unit test | `apps/api/tests/test_<service>.py` |
| New React component | Vitest render test | `apps/web/__tests__/<dir>/<name>.test.tsx` |
| Hook/logic change | Vitest unit test | `apps/web/__tests__/<dir>/<name>.test.tsx` |
| Bug fix | Regression test (fails without fix) | Same as above |
