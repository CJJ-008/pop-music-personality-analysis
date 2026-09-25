#!/usr/bin/env bash
# 把本项目推送到 GitHub，实现异地备份（需求 R6 / 决策 D4）。
#
# 使用前提：你已有 GitHub 账号，并在网页上新建了一个空仓库（不要勾选 README/.gitignore）。
#
# 用法（在项目根目录执行）：
#   bash scripts/setup_github.sh https://github.com/你的用户名/仓库名.git
#
# 脚本会：配置远程 origin -> 推送 main 分支 -> 设置上游跟踪。

set -euo pipefail

REPO_URL="${1:-}"

if [ -z "$REPO_URL" ]; then
    echo "用法: bash scripts/setup_github.sh <仓库地址>"
    echo "示例: bash scripts/setup_github.sh https://github.com/zhangsan/music-analysis.git"
    exit 1
fi

echo "[1/4] 检查当前分支与提交状态..."
git rev-parse --is-inside-work-tree >/dev/null
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "      当前分支: ${BRANCH}"

if [ -n "$(git status --porcelain)" ]; then
    echo "      提示: 工作区有未提交的改动，建议先 git add -A && git commit 再推送"
fi

echo "[2/4] 配置远程仓库 origin..."
if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$REPO_URL"
    echo "      已更新 origin -> ${REPO_URL}"
else
    git remote add origin "$REPO_URL"
    echo "      已添加 origin -> ${REPO_URL}"
fi

echo "[3/4] 推送 ${BRANCH} 分支（HTTPS 方式会弹出浏览器登录 GitHub）..."
# 国内网络若 SSH 22 端口不通，可改用 443 通道：
#   git remote set-url origin git@ssh.github.com:你的用户名/仓库名.git
#   GIT_SSH_COMMAND="ssh -p 443" git push -u origin main
git push -u origin "$BRANCH"

echo "[4/4] 完成。远程仓库:"
git remote -v
echo
echo "后续每次提交后用 git push 即可同步到 GitHub。"
