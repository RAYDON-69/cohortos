# Undo the R57 merge safely

Never force-push `main`.

If merge commit SHA is `MERGE_SHA`:

```bash
git fetch origin
git checkout -b revert/r57-merge origin/main
git revert -m 1 MERGE_SHA
git push -u origin revert/r57-merge
# Open PR revert/r57-merge -> main and merge via GitHub UI
```

Safety refs created before merge:

- tag `pre-r57-main`
- branch `backup/main-before-r57`
