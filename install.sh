#!/usr/bin/env bash
# VPN Telegram bot installer.
# Usage (as root):
#   curl -fsSL https://raw.githubusercontent.com/ilyushinkirill2710-gif/VPNBoT/main/install.sh | sudo bash
# Optional environment variables (set before the pipe) to skip prompts:
#   BRANCH, INSTALL_DIR, BOT_TOKEN, ADMIN_IDS, DOMAIN,
#   REMNAWAVE_BASE_URL, REMNAWAVE_TOKEN, REMNAWAVE_SQUAD_UUIDS,
#   PLATEGA_MERCHANT_ID, PLATEGA_SECRET, PLATEGA_PAYMENT_METHOD,
#   SUPPORT_USERNAME, SETUP_CADDY (yes|no)

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/ilyushinkirill2710-gif/VPNBoT.git}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/vpnbot}"

C_RESET="\033[0m"; C_BOLD="\033[1m"; C_GREEN="\033[32m"; C_YELLOW="\033[33m"
C_RED="\033[31m"; C_CYAN="\033[36m"
log()  { printf "${C_CYAN}[i]${C_RESET} %s\n" "$*"; }
ok()   { printf "${C_GREEN}[+]${C_RESET} %s\n" "$*"; }
warn() { printf "${C_YELLOW}[!]${C_RESET} %s\n" "$*" >&2; }
die()  { printf "${C_RED}[x]${C_RESET} %s\n" "$*" >&2; exit 1; }

# ---------- sanity ----------
[[ $EUID -eq 0 ]] || die "Запустите скрипт от root: sudo bash install.sh"

# When piping from curl, stdin is not a TTY — try to reopen from /dev/tty.
if [[ ! -t 0 ]]; then
    if [[ -r /dev/tty ]]; then
        exec </dev/tty
    else
        warn "Интерактивный ввод недоступен — используйте переменные окружения или запустите скрипт напрямую: bash install.sh"
    fi
fi

ask() {
    # ask <var_name> <prompt> [default]
    local __var="$1" __prompt="$2" __default="${3:-}" __value=""
    __value="${!__var:-}"
    if [[ -n "$__value" ]]; then
        ok "$__var уже задан, использую значение из окружения"
        return 0
    fi
    local suffix=""
    [[ -n "$__default" ]] && suffix=" [${__default}]"
    while :; do
        printf "${C_BOLD}%s${C_RESET}%s: " "$__prompt" "$suffix"
        read -r __value || __value=""
        if [[ -z "$__value" && -n "$__default" ]]; then
            __value="$__default"
        fi
        if [[ -n "$__value" ]]; then
            break
        fi
        warn "Значение не может быть пустым."
    done
    printf -v "$__var" '%s' "$__value"
    export "$__var"
}

ask_yes_no() {
    local __var="$1" __prompt="$2" __default="${3:-yes}" __value="" __hint=""
    __value="${!__var:-}"
    if [[ -n "$__value" ]]; then
        ok "$__var уже задан (${__value})"
        return 0
    fi
    if [[ "$__default" == "yes" ]]; then __hint="[Y/n]"; else __hint="[y/N]"; fi
    while :; do
        printf "${C_BOLD}%s${C_RESET} %s: " "$__prompt" "$__hint"
        read -r __value || __value=""
        __value="${__value:-$__default}"
        case "${__value,,}" in
            y|yes) printf -v "$__var" '%s' "yes"; return 0 ;;
            n|no)  printf -v "$__var" '%s' "no";  return 0 ;;
            *) warn "Введите y или n" ;;
        esac
    done
}

# ---------- apt packages ----------
install_packages() {
    log "Обновляю apt и ставлю базовые пакеты…"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq git curl ca-certificates ufw >/dev/null
}

install_docker() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        ok "Docker уже установлен"
        return
    fi
    log "Устанавливаю Docker…"
    curl -fsSL https://get.docker.com | sh >/dev/null
    systemctl enable --now docker >/dev/null
    ok "Docker установлен"
}

install_caddy() {
    if command -v caddy >/dev/null 2>&1; then
        ok "Caddy уже установлен"
        return
    fi
    log "Устанавливаю Caddy…"
    apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https >/dev/null
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
    apt-get update -qq
    apt-get install -y -qq caddy >/dev/null
    ok "Caddy установлен"
}

# ---------- repo ----------
clone_or_update_repo() {
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        log "Обновляю существующий репо в $INSTALL_DIR…"
        git -C "$INSTALL_DIR" fetch --all --quiet
        git -C "$INSTALL_DIR" checkout --quiet "$BRANCH"
        git -C "$INSTALL_DIR" pull --quiet --ff-only
    else
        log "Клонирую репо в $INSTALL_DIR…"
        git clone --quiet --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    fi
    ok "Репо готов ($BRANCH)"
}

# ---------- .env wizard ----------
write_env() {
    local env_file="$INSTALL_DIR/.env"
    if [[ -f "$env_file" ]]; then
        warn ".env уже существует, оставляю как есть (сохранил копию в .env.backup)"
        cp -f "$env_file" "$env_file.backup.$(date +%s)"
        return
    fi

    echo
    printf "${C_BOLD}=== Настройка бота ===${C_RESET}\n"
    echo "Введите значения по одному. Где не знаете — смотрите ссылки в комментариях."
    echo

    echo "Telegram:"
    ask BOT_TOKEN "  BOT_TOKEN (от @BotFather)"
    ask ADMIN_IDS "  ADMIN_IDS (Telegram ID админов через запятую; узнать у @userinfobot)"

    echo
    echo "Remnawave:"
    ask REMNAWAVE_BASE_URL "  REMNAWAVE_BASE_URL (например https://panel.example.com)"
    ask REMNAWAVE_TOKEN "  REMNAWAVE_TOKEN (Settings → API Tokens)"
    REMNAWAVE_SQUAD_UUIDS="${REMNAWAVE_SQUAD_UUIDS:-}"
    printf "${C_BOLD}%s${C_RESET}: " "  REMNAWAVE_SQUAD_UUIDS (список UUID Internal Squads через запятую; Enter — подтянуть единственный доступный)"
    read -r _squads || _squads=""
    [[ -n "$_squads" ]] && REMNAWAVE_SQUAD_UUIDS="$_squads"

    echo
    echo "platega.io:"
    ask PLATEGA_MERCHANT_ID "  PLATEGA_MERCHANT_ID"
    ask PLATEGA_SECRET "  PLATEGA_SECRET"
    ask PLATEGA_PAYMENT_METHOD "  PLATEGA_PAYMENT_METHOD (2 = СБП/QR, 3 = карта, 11/12/13 = крипта)" "2"

    echo
    ask DOMAIN "Домен для бота (A-запись должна указывать на этот сервер, например bot.example.com)"
    ask SUPPORT_USERNAME "Контакт поддержки в справке (например @support)" "@support"

    local bot_username
    bot_username="$(curl -fsS --max-time 5 "https://api.telegram.org/bot${BOT_TOKEN}/getMe" \
        | grep -oE '"username":"[^"]+"' | head -n1 | sed 's/"username":"//;s/"//' || true)"
    local return_url="https://t.me/${bot_username:-your_bot}"

    cat > "$env_file" <<EOF
# Generated by install.sh on $(date -Iseconds)
BOT_TOKEN=${BOT_TOKEN}
ADMIN_IDS=${ADMIN_IDS}
SUPPORT_USERNAME=${SUPPORT_USERNAME}

DATABASE_URL=sqlite+aiosqlite:///./data/vpnbot.sqlite3

REMNAWAVE_BASE_URL=${REMNAWAVE_BASE_URL}
REMNAWAVE_TOKEN=${REMNAWAVE_TOKEN}
REMNAWAVE_SQUAD_UUIDS=${REMNAWAVE_SQUAD_UUIDS}
REMNAWAVE_TRAFFIC_LIMIT_GB=0

PLATEGA_MERCHANT_ID=${PLATEGA_MERCHANT_ID}
PLATEGA_SECRET=${PLATEGA_SECRET}
PLATEGA_BASE_URL=https://app.platega.io
PLATEGA_PAYMENT_METHOD=${PLATEGA_PAYMENT_METHOD}
PLATEGA_CALLBACK_URL=https://${DOMAIN}/platega/callback
PLATEGA_RETURN_URL=${return_url}
PLATEGA_FAIL_URL=${return_url}

WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8080
LOG_LEVEL=INFO
EOF
    chmod 600 "$env_file"
    ok ".env создан: $env_file"
}

# ---------- firewall + caddy ----------
configure_firewall() {
    if ! command -v ufw >/dev/null 2>&1; then
        return
    fi
    ufw allow 22/tcp  >/dev/null 2>&1 || true
    ufw allow 80/tcp  >/dev/null 2>&1 || true
    ufw allow 443/tcp >/dev/null 2>&1 || true
    echo "y" | ufw enable >/dev/null 2>&1 || true
    ok "UFW: 22/80/443 разрешены"
}

configure_caddy() {
    local domain="$DOMAIN"
    cat > /etc/caddy/Caddyfile <<EOF
${domain} {
    reverse_proxy 127.0.0.1:8080
}
EOF
    systemctl enable caddy >/dev/null 2>&1 || true
    systemctl restart caddy
    ok "Caddy настроен на ${domain} (HTTPS выдастся автоматически)"
}

# ---------- run ----------
start_bot() {
    log "Собираю и запускаю docker compose…"
    (cd "$INSTALL_DIR" && docker compose up -d --build)
    ok "Контейнер запущен"
}

# ---------- main ----------
install_packages
install_docker

ask_yes_no SETUP_CADDY "Настроить HTTPS через Caddy (рекомендуется — нужен для платежных callback'ов)" "yes"
[[ "$SETUP_CADDY" == "yes" ]] && install_caddy

clone_or_update_repo
write_env
configure_firewall
[[ "$SETUP_CADDY" == "yes" ]] && configure_caddy
start_bot

echo
printf "${C_GREEN}${C_BOLD}Готово!${C_RESET}\n"
echo "  Логи бота:            (cd $INSTALL_DIR && docker compose logs -f bot)"
echo "  Перезапуск:           (cd $INSTALL_DIR && docker compose restart bot)"
echo "  Health-check:         curl https://${DOMAIN:-<домен>}/health"
echo "  В ЛК platega.io добавьте Callback URL:  https://${DOMAIN:-<домен>}/platega/callback"
echo "  Напишите боту /start — и можно продавать VPN."
