#!/usr/bin/env bash
# Commita e envia as mudanças do FundoLimpo para github.com/admirjuniorgit/FundoLimpo.
# Uso (Git Bash, na pasta do projeto):
#   ./commit.sh "o que mudou"      -> commita tudo e faz push
#   ./commit.sh                    -> pergunta a mensagem
#
# Lançar atualização para os usuários: mude VERSION em fundolimpo/app.py (ex.: 1.2.0 -> 1.3.0) e rode
# ./commit.sh "o que mudou". O GitHub Actions gera o instalador e publica a versão; quem tem o app
# instalado recebe a atualização ao abrir. A mensagem do commit vira a nota da versão.
set -e
cd "$(dirname "$0")"
REMOTE="https://github.com/admirjuniorgit/FundoLimpo.git"

# primeira vez neste PC: liga a pasta ao repositório do GitHub sem mexer nos arquivos
if [ ! -d .git ]; then
  echo "Ligando a pasta ao repositório $REMOTE..."
  git init -q -b main
  git remote add origin "$REMOTE"
  git fetch -q origin main
  git reset -q origin/main
  git checkout -q origin/main -- .github 2>/dev/null || true   # traz o workflow de publicação
  git branch -q --set-upstream-to=origin/main main
fi

if [ -z "$(git config user.name)" ]; then git config user.name "admirjuniorgit"; fi
if [ -z "$(git config user.email)" ]; then git config user.email "admir.junior2021@gmail.com"; fi

git pull -q --rebase --autostash origin main || true

if [ -z "$(git status --porcelain)" ]; then
  echo "Nada para commitar."
  exit 0
fi

git status --short
echo
MSG="$*"
if [ -z "$MSG" ]; then
  read -r -p "Mensagem do commit: " MSG
fi
[ -z "$MSG" ] && MSG="Atualizações $(date '+%Y-%m-%d %H:%M')"

OLD_VER=$(git show HEAD:fundolimpo/app.py 2>/dev/null | sed -n 's/^VERSION = "\(.*\)"/\1/p')
NEW_VER=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' fundolimpo/app.py)

git add -A
git commit -q -m "$MSG"
git push -q origin main

echo
echo "Enviado para https://github.com/admirjuniorgit/FundoLimpo"
if [ "$OLD_VER" != "$NEW_VER" ]; then
  echo "Versão mudou ($OLD_VER -> $NEW_VER): o GitHub vai gerar e publicar o instalador em ~10 min."
  echo "Acompanhe em https://github.com/admirjuniorgit/FundoLimpo/actions"
fi
