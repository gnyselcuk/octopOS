#!/usr/bin/env bash
# scripts/test_fresh_install.sh
#
# Fresh install doğrulama scripti.
# Docker container içinde veya temiz bir VM'de çalıştırılır.
# Her adımı test eder, sonunda rapor üretir.
#
# Kullanım:
#   bash scripts/test_fresh_install.sh
#   bash scripts/test_fresh_install.sh --aws-test    # AWS bağlantısını da test et
#   bash scripts/test_fresh_install.sh --full        # Tüm testleri çalıştır

set -euo pipefail

# ── Renkler ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Bayraklar ────────────────────────────────────────────────────────────────
AWS_TEST=false
FULL_TEST=false
for arg in "$@"; do
    [[ "$arg" == "--aws-test" ]] && AWS_TEST=true
    [[ "$arg" == "--full"     ]] && FULL_TEST=true && AWS_TEST=true
done

# ── Yardımcılar ─────────────────────────────────────────────────────────────
PASS=0; FAIL=0; WARN=0
RESULTS=()

ok()   { echo -e "${GREEN}  ✅ $*${RESET}"; PASS=$((PASS + 1));  RESULTS+=("PASS: $*"); }
fail() { echo -e "${RED}  ❌ $*${RESET}"; FAIL=$((FAIL + 1));  RESULTS+=("FAIL: $*"); }
warn() { echo -e "${YELLOW}  ⚠️  $*${RESET}"; WARN=$((WARN + 1));  RESULTS+=("WARN: $*"); }

info() { echo -e "${CYAN}  ℹ  $*${RESET}"; }
section() { echo -e "\n${BOLD}━━━ $* ━━━${RESET}"; }

# ── Banner ───────────────────────────────────────────────────────────────────
echo -e "${BOLD}${CYAN}"
echo "  🐙 octopOS — Fresh Install Test"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo -e "${RESET}"

# ════════════════════════════════════════════════════════════════════════════
section "1. Python Ortamı"
# ════════════════════════════════════════════════════════════════════════════

PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [[ "$MAJOR" -ge 3 && "$MINOR" -ge 10 ]]; then
    ok "Python $PY_VERSION (>=3.10 gerekli)"
else
    fail "Python $PY_VERSION — 3.10+ gerekli!"
fi

# pip
if python3 -m pip --version &>/dev/null; then
    ok "pip mevcut: $(python3 -m pip --version | awk '{print $2}')"
else
    fail "pip bulunamadı"
fi

# ════════════════════════════════════════════════════════════════════════════
section "2. octopOS Kurulum"
# ════════════════════════════════════════════════════════════════════════════

# Core imports
CORE_PKGS=("boto3" "typer" "rich" "pydantic" "aiohttp" "yaml" "cryptography" "lancedb")
for pkg in "${CORE_PKGS[@]}"; do
    if python3 -c "import ${pkg//-/_}" 2>/dev/null; then
        ok "$pkg kurulu"
    else
        fail "$pkg KURULU DEĞİL"
    fi
done

# octo CLI erişilebilir mi?
if command -v octo &>/dev/null; then
    ok "'octo' CLI komutu PATH'te"
else
    fail "'octo' komutu bulunamadı — 'pip install -e .' çalıştırdın mı?"
fi

# octo --help
if octo --help &>/dev/null; then
    ok "octo --help çalışıyor"
else
    fail "octo --help hata verdi"
fi

# Tüm komutlar mevcut mu?
COMMANDS=("agent-status" "budget" "cache-stats" "dlq" "ask" "chat" "browse" "voice" "mcp")
for cmd in "${COMMANDS[@]}"; do
    if octo "$cmd" --help &>/dev/null; then
        ok "octo $cmd --help OK"
    else
        fail "octo $cmd bulunamadı veya hata veriyor"
    fi
done

# ════════════════════════════════════════════════════════════════════════════
section "3. Opsiyonel Bağımlılıklar"
# ════════════════════════════════════════════════════════════════════════════

# Playwright
if python3 -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); p.stop()" 2>/dev/null; then
    ok "Playwright kurulu ve çalışıyor"
else
    warn "Playwright eksik — 'octo browse' çalışmaz. Kur: playwright install chromium"
fi

# sounddevice (Nova Sonic için)
if python3 -c "import sounddevice" 2>/dev/null; then
    ok "sounddevice kurulu (Nova Sonic ses girişi çalışır)"
else
    warn "sounddevice eksik — 'octo voice' sadece TTS modunda çalışır. Kur: pip install sounddevice"
fi

# pyaudio (fallback)
if python3 -c "import pyaudio" 2>/dev/null; then
    ok "pyaudio kurulu (ses fallback)"
else
    info "pyaudio yok (opsiyonel fallback)"
fi

# Docker
if docker info &>/dev/null 2>&1; then
    ok "Docker erişilebilir — EphemeralContainer sandbox tam çalışır"
else
    warn "Docker erişilemiyor — sandbox subprocess moduna düşer (daha az izole)"
fi

# ════════════════════════════════════════════════════════════════════════════
section "4. Konfigürasyon"
# ════════════════════════════════════════════════════════════════════════════

PROFILE="$HOME/.octopos/profile.yaml"
if [[ -f "$PROFILE" ]]; then
    ok "Profil dosyası mevcut: $PROFILE"
else
    warn "Profil yok — ilk çalıştırmada 'octo setup' çalıştırılmalı"
fi

# Data dizinleri
DATA_DIRS=("data" "logs" "data/lancedb")
for d in "${DATA_DIRS[@]}"; do
    if [[ -d "$d" ]]; then
        ok "Dizin mevcut: $d"
    else
        warn "Dizin yok: $d — ilk çalıştırmada otomatik oluşturulur"
    fi
done

# ════════════════════════════════════════════════════════════════════════════
section "5. AWS Bağlantısı"
# ════════════════════════════════════════════════════════════════════════════

if [[ "$AWS_TEST" == "true" ]]; then
    # AWS credentials
    if [[ -n "${AWS_ACCESS_KEY_ID:-}" ]] || [[ -n "${AWS_PROFILE:-}" ]] || \
       [[ -f "$HOME/.aws/credentials" ]]; then
        info "AWS credential kaynağı tespit edildi"
        
        # STS GetCallerIdentity
        if python3 -c "
import boto3, sys
try:
    sts = boto3.client('sts')
    identity = sts.get_caller_identity()
    print(f'Account: {identity[\"Account\"]} | ARN: {identity[\"Arn\"]}')
    sys.exit(0)
except Exception as e:
    print(f'Hata: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/tmp/sts_err; then
            ok "AWS credentials geçerli ($(python3 -c "import boto3; print(boto3.client('sts').get_caller_identity()['Account'])"))"
        else
            fail "AWS credentials geçersiz: $(cat /tmp/sts_err)"
        fi

        # Bedrock erişimi
        if python3 -c "
import boto3, json, sys
try:
    client = boto3.client('bedrock-runtime', region_name='${AWS_DEFAULT_REGION:-us-east-1}')
    resp = client.invoke_model(
        modelId='amazon.nova-lite-v1:0',
        body=json.dumps({'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'ping'}]}]})
    )
    sys.exit(0)
except Exception as e:
    print(f'Bedrock hata: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/tmp/bedrock_err; then
            ok "Bedrock (nova-lite) erişilebilir"
        else
            fail "Bedrock erişimi başarısız: $(cat /tmp/bedrock_err | head -1)"
        fi

    else
        warn "AWS credentials bulunamadı — AWS testleri atlandı"
        info "Kur: 'aws configure' veya 'octo setup'"
    fi
else
    info "AWS testi atlandı (--aws-test flag'ı ile etkinleştir)"
fi

# ════════════════════════════════════════════════════════════════════════════
section "6. İç Modül Import Testleri"
# ════════════════════════════════════════════════════════════════════════════

MODULES=(
    "src.utils.config:get_config"
    "src.utils.aws_sts:get_auth_manager"
    "src.engine.orchestrator:Orchestrator"
    "src.engine.supervisor:Supervisor"
    "src.engine.dead_letter_queue:DeadLetterQueue"
    "src.specialist.coder_agent:CoderAgent"
    "src.specialist.self_healing_agent:SelfHealingAgent"
    "src.primitives.cloud_aws.s3_manager:S3Manager"
    "src.primitives.cloud_aws.dynamodb_client:DynamoDBClient"
    "src.interfaces.cli.commands:browse,voice,chat"
    "src.interfaces.telegram.bot:TelegramBot"
    "src.interfaces.voice.nova_sonic:NovaSonicClient"
    "src.utils.file_delivery:FileDeliveryService"
    "src.utils.aws_eventbridge:EventBridgeScheduler"
    "src.utils.bedrock_guardrails:BedrockGuardrails"
    "src.utils.cloudwatch_logger:CloudWatchLogger"
)

for entry in "${MODULES[@]}"; do
    module="${entry%%:*}"
    symbols="${entry##*:}"
    
    test_code="from ${module} import ${symbols}"
    if python3 -c "$test_code" 2>/tmp/import_err; then
        ok "$module OK"
    else
        fail "$module IMPORT HATASI: $(cat /tmp/import_err | tail -1)"
    fi
done

# ════════════════════════════════════════════════════════════════════════════
if [[ "$FULL_TEST" == "true" ]]; then
section "7. Unit Test Paketi"
# ════════════════════════════════════════════════════════════════════════════
    info "pytest çalıştırılıyor (unit testler)…"
    if python3 -m pytest tests/unit/ -x -q --tb=short --no-header 2>&1 | tee /tmp/pytest_out.txt; then
        ok "Tüm unit testler geçti"
    else
        FAILED_COUNT=$(grep -c "FAILED" /tmp/pytest_out.txt 2>/dev/null || echo "?")
        fail "$FAILED_COUNT unit test başarısız"
    fi
fi

# ════════════════════════════════════════════════════════════════════════════
section "📊 SONUÇ RAPORU"
# ════════════════════════════════════════════════════════════════════════════

echo ""
echo -e "${BOLD}Toplam: ${GREEN}$PASS geçti${RESET} | ${RED}$FAIL başarısız${RESET} | ${YELLOW}$WARN uyarı${RESET}"
echo ""

if [[ $FAIL -gt 0 ]]; then
    echo -e "${RED}${BOLD}Kritik hatalar (kurulum tamamlanmadan önce düzeltilmeli):${RESET}"
    for r in "${RESULTS[@]}"; do
        [[ "$r" == FAIL:* ]] && echo -e "  ${RED}• ${r#FAIL: }${RESET}"
    done
    echo ""
fi

if [[ $WARN -gt 0 ]]; then
    echo -e "${YELLOW}${BOLD}Uyarılar (opsiyonel özellikler etkilenir):${RESET}"
    for r in "${RESULTS[@]}"; do
        [[ "$r" == WARN:* ]] && echo -e "  ${YELLOW}• ${r#WARN: }${RESET}"
    done
    echo ""
fi

# JSON rapor
REPORT_FILE="/tmp/octopos_install_report_$(date +%Y%m%d_%H%M%S).json"
python3 -c "
import json, sys
data = {
    'timestamp': '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
    'python_version': '$(python3 --version 2>&1)',
    'platform': '$(uname -a)',
    'passed': $PASS,
    'failed': $FAIL,
    'warnings': $WARN,
    'results': []
}
print(json.dumps(data, indent=2))
" > "$REPORT_FILE"

echo -e "${CYAN}📄 Rapor kaydedildi: $REPORT_FILE${RESET}"
echo ""

if [[ $FAIL -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}🎉 Kurulum başarılı! octopOS çalışmaya hazır.${RESET}"
    echo -e "${CYAN}   Sonraki adım: octo setup${RESET}"
    exit 0
else
    echo -e "${RED}${BOLD}💥 $FAIL kritik hata bulundu. Lütfen yukarıdaki hataları düzelt.${RESET}"
    exit 1
fi
