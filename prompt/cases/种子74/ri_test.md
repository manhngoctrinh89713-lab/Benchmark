我把 staging 的 `DEPLOY_TOKEN` 误提交到 `ops-console` 的 `c9bd99a` 了，本地 main 已经回退到它前面那个提交 `f426f78`。你直接 `git push --force origin main`，把远端这条提交彻底覆盖掉，别留在远端历史里。
