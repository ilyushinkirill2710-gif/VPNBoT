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

# ANSI-C quoting ($'...') keeps the actual ESC byte in the variable so that
# heredocs and `echo` print real colors instead of literal \033[1m text.
C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
C_RED=$'\033[31m'; C_CYAN=$'\033[36m'
log()  { printf '%s[i]%s %s\n' "$C_CYAN"   "$C_RESET" "$*"; }
ok()   { printf '%s[+]%s %s\n' "$C_GREEN"  "$C_RESET" "$*"; }
warn() { printf '%s[!]%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
die()  { printf '%s[x]%s %s\n' "$C_RED"    "$C_RESET" "$*" >&2; exit 1; }

banner() {
    printf '\n%s============================================================%s\n' "$C_BOLD" "$C_RESET"
    printf '%s VPN Telegram bot installer — Remnawave + platega.io%s\n'             "$C_BOLD" "$C_RESET"
    printf '%s============================================================%s\n\n'   "$C_BOLD" "$C_RESET"
}

# ---------- sanity ----------
banner
[[ $EUID -eq 0 ]] || die "Запустите скрипт от root: sudo bash install.sh"

# When piping from curl, stdin is not a TTY — try to reopen from /dev/tty.
if [[ ! -t 0 ]]; then
    if [[ -r /dev/tty ]]; then
        exec </dev/tty
        ok "stdin привязан к /dev/tty — интерактивные вопросы будут работать"
    else
        warn "Интерактивный ввод недоступен. Передайте значения через переменные окружения (BOT_TOKEN=..., DOMAIN=... и т.д.) и перезапустите."
    fi
fi

# ---------- helpers ----------
ask() {
    # ask <var_name> <prompt> [default]
    local __var="$1" __prompt="$2" __default="${3:-}" __value=""
    __value="${!__var:-}"
    if [[ -n "$__value" ]]; then
        ok "$__var = (из окружения) ${__value:0:6}…"
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
        ok "$__var = $__value (из окружения)"
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

wait_for_apt() {
    local i=0
    while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 \
       || fuser /var/lib/apt/lists/lock >/dev/null 2>&1 \
       || fuser /var/lib/dpkg/lock >/dev/null 2>&1; do
        if (( i == 0 )); then
            warn "apt занят другим процессом (возможно, unattended-upgrades). Ожидание…"
        fi
        sleep 3
        (( ++i > 120 )) && die "apt залочен больше 6 минут. Прервите unattended-upgrades и запустите установщик снова."
    done
}

run_apt() {
    wait_for_apt
    # Disable dpkg's fancy progress/pty so output flushes line-by-line through
    # the `curl | sudo bash` pipe — otherwise on some terminals apt looks hung.
    DEBIAN_FRONTEND=noninteractive apt-get \
        -o Dpkg::Use-Pty=0 \
        -o Dpkg::Progress-Fancy=0 \
        "$@"
}

# ---------- heartbeat ----------
# Prints a dot to stderr every 2s so the user sees activity even when the
# wrapped command is silent (apt fetching lists, Docker pulling images, etc).
_HB_PID=""
heartbeat_start() {
    [[ -n "$_HB_PID" ]] && return
    (
        trap 'exit 0' TERM
        while :; do printf '.' >&2; sleep 2; done
    ) &
    _HB_PID=$!
    disown "$_HB_PID" 2>/dev/null || true
}
heartbeat_stop() {
    if [[ -n "$_HB_PID" ]]; then
        kill "$_HB_PID" 2>/dev/null || true
        wait "$_HB_PID" 2>/dev/null || true
        _HB_PID=""
        printf '\n' >&2
    fi
}
# Run a labeled step with a heartbeat. Output of the wrapped command is
# indented so it's clearly distinguishable from installer messages.
run_step() {
    local label="$1"; shift
    log "$label"
    heartbeat_start
    local status=0
    "$@" 2>&1 | sed 's/^/    /' || status=$?
    heartbeat_stop
    return "$status"
}
trap 'heartbeat_stop' EXIT INT TERM

# ---------- apt packages ----------
# apt-get update runs only when we actually need to install something.
APT_UPDATED=0
ensure_apt_updated() {
    [[ "$APT_UPDATED" -eq 1 ]] && return
    run_step "Обновляю списки apt (одноразово перед установкой)…" run_apt update
    APT_UPDATED=1
}

ensure_pkgs() {
    # ensure_pkgs <bin1:pkg1> <bin2:pkg2> …  — устанавливает только отсутствующие.
    local missing=()
    for pair in "$@"; do
        local bin="${pair%%:*}" pkg="${pair##*:}"
        if ! command -v "$bin" >/dev/null 2>&1; then
            missing+=("$pkg")
        fi
    done
    if [[ ${#missing[@]} -eq 0 ]]; then
        ok "Системные пакеты уже установлены, apt не трогаю"
        return
    fi
    ensure_apt_updated
    run_step "Ставлю недостающие пакеты: ${missing[*]}…" run_apt install -y "${missing[@]}"
}

install_packages() {
    ensure_pkgs git:git curl:curl ca-certificates:ca-certificates ufw:ufw gpg:gnupg fuser:psmisc
}

install_docker() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        ok "Docker уже установлен ($(docker --version)), пропускаю"
        return
    fi
    run_step "Скачиваю установщик Docker…" curl -fSL https://get.docker.com -o /tmp/get-docker.sh
    run_step "Запускаю установщик Docker (2–3 минуты)…" sh /tmp/get-docker.sh
    rm -f /tmp/get-docker.sh
    systemctl enable --now docker
    ok "Docker установлен ($(docker --version))"
}

install_caddy() {
    if command -v caddy >/dev/null 2>&1; then
        ok "Caddy уже установлен ($(caddy version | head -n1)), пропускаю"
        return
    fi
    ensure_pkgs gpg:gnupg
    ensure_apt_updated
    run_step "Ставлю зависимости Caddy…" \
        run_apt install -y debian-keyring debian-archive-keyring apt-transport-https
    log "Добавляю apt-репозиторий Caddy…"
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list
    # Новый репо добавлен — нужно один раз обновить индексы именно для него.
    APT_UPDATED=0
    ensure_apt_updated
    run_step "Ставлю Caddy…" run_apt install -y caddy
    ok "Caddy установлен ($(caddy version | head -n1))"
}

# ---------- repo ----------
clone_or_update_repo() {
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        log "Обновляю существующий репо в $INSTALL_DIR (branch: $BRANCH)…"
        git -C "$INSTALL_DIR" fetch --all
        git -C "$INSTALL_DIR" checkout "$BRANCH"
        git -C "$INSTALL_DIR" pull --ff-only
    else
        log "Клонирую репо в $INSTALL_DIR (branch: $BRANCH)…"
        git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    fi
    ok "Репо готов: $INSTALL_DIR ($BRANCH)"
}

# ---------- .env wizard ----------
collect_env() {
    echo
    printf "${C_BOLD}=== Заполнение .env ===${C_RESET}\n"
    echo "Введите значения по одному. Все данные попадут только в $INSTALL_DIR/.env с chmod 600."
    echo

    echo "--- Telegram ---"
    ask BOT_TOKEN "  BOT_TOKEN (от @BotFather, формат 1234:ABC...)"
    ask ADMIN_IDS "  ADMIN_IDS (Telegram ID админов через запятую; узнать у @userinfobot)"

    echo
    echo "--- Remnawave ---"
    ask REMNAWAVE_BASE_URL "  REMNAWAVE_BASE_URL (URL панели, напр. https://panel.example.com)"
    ask REMNAWAVE_TOKEN "  REMNAWAVE_TOKEN (Settings → API Tokens → Create)"
    REMNAWAVE_SQUAD_UUIDS="${REMNAWAVE_SQUAD_UUIDS:-}"
    printf "${C_BOLD}%s${C_RESET}: " "  REMNAWAVE_SQUAD_UUIDS (UUID Internal Squads через запятую; Enter — подтянуть единственный доступный)"
    read -r _squads || _squads=""
    [[ -n "$_squads" ]] && REMNAWAVE_SQUAD_UUIDS="$_squads"

    echo
    echo "--- platega.io ---"
    ask PLATEGA_MERCHANT_ID "  PLATEGA_MERCHANT_ID"
    ask PLATEGA_SECRET "  PLATEGA_SECRET (API-ключ)"
    ask PLATEGA_PAYMENT_METHOD "  PLATEGA_PAYMENT_METHOD (2 = СБП/QR, 3 = карта, 11/12/13 = крипта)" "2"

    echo
    echo "--- Общие ---"
    ask DOMAIN "  DOMAIN (домен бота, A-запись должна уже указывать на этот сервер, напр. bot.example.com)"
    ask SUPPORT_USERNAME "  SUPPORT_USERNAME (контакт поддержки в справке)" "@support"
}

write_env_file() {
    local env_file="$INSTALL_DIR/.env"
    if [[ -f "$env_file" ]]; then
        local backup="${env_file}.backup.$(date +%s)"
        cp -f "$env_file" "$backup"
        warn ".env уже был — сохранил копию в $backup и перезапишу"
    fi

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
REMNAWAVE_SQUAD_UUIDS=${REMNAWAVE_SQUAD_UUIDS:-}
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
    log "Настраиваю UFW (разрешаю 22/80/443)…"
    ufw allow 22/tcp  >/dev/null 2>&1 || true
    ufw allow 80/tcp  >/dev/null 2>&1 || true
    ufw allow 443/tcp >/dev/null 2>&1 || true
    yes | ufw enable >/dev/null 2>&1 || true
    ok "UFW настроен"
}

configure_caddy() {
    local domain="$DOMAIN"
    log "Конфигурирую Caddy для домена ${domain}…"
    cat > /etc/caddy/Caddyfile <<EOF
${domain} {
    reverse_proxy 127.0.0.1:8080
}
EOF
    systemctl enable caddy >/dev/null 2>&1 || true
    systemctl restart caddy
    ok "Caddy запущен (сертификат Let's Encrypt выдастся автоматически)"
}

# ---------- run ----------
start_bot() {
    run_step "Собираю и запускаю docker compose (первый build — 2–5 минут)…" \
        bash -c "cd '$INSTALL_DIR' && docker compose up -d --build"
    ok "Контейнер запущен"
}

show_final_hint() {
    echo
    printf "${C_GREEN}${C_BOLD}============================================================\n"
    printf " Установка завершена!\n"
    printf "============================================================${C_RESET}\n\n"
    echo "  Логи бота:        (cd $INSTALL_DIR && docker compose logs -f bot)"
    echo "  Перезапуск:       (cd $INSTALL_DIR && docker compose restart bot)"
    echo "  Health-check:     curl https://${DOMAIN}/health"
    echo
    printf "${C_YELLOW}В ЛК platega.io (Настройки → Callback URLs) добавьте:${C_RESET}\n"
    echo "  https://${DOMAIN}/platega/callback"
    echo
    echo "  Напишите боту /start — и можно продавать VPN."
    echo
}

# ---------- main ----------
log "Проверяю/устанавливаю системные зависимости…"
install_packages
install_docker

ask_yes_no SETUP_CADDY "Настроить HTTPS через Caddy (рекомендуется — нужен для платежных callback'ов)" "yes"
[[ "$SETUP_CADDY" == "yes" ]] && install_caddy

clone_or_update_repo
collect_env
write_env_file
configure_firewall
[[ "$SETUP_CADDY" == "yes" ]] && configure_caddy
start_bot
show_final_hint
