# Maintainer: push notes

Staging package for public GitHub delivery. After `GH_TOKEN` / PAT is set:

```bash
export GH_TOKEN="<PAT>"
cd /tmp/hybridcut-github
gh auth status
gh repo create HybridCut --public --source=. --remote=origin --push
# if taken: Videoeditor-HybridCut or HybridCut-hevesi
gh repo view --json url -q .url
```

Do not commit tokens. Prefer classic PAT with `repo` scope.
