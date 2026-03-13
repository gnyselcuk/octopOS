#!/bin/bash
#
# octopOS EC2 Deployment Script
# Amazon Linux 2 üzerinde Docker Compose ile deployment
#

set -e

# Renk kodları
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Banner
echo -e "
╔═══════════════════════════════════════════════════════════════╗
║                    🐙 octopOS Deployment                      ║
║                  Agentic Operating System                     ║
╚═══════════════════════════════════════════════════════════════╝
"

# -----------------------------------------------------------------------------
# 1. Sistem Güncelleme ve Docker Kurulumu
# -----------------------------------------------------------------------------
install_docker() {
    log_info "Docker kurulumu başlıyor..."

    # Sistem güncelleme (Amazon Linux 2)
    log_info "Sistem güncelleniyor..."
    sudo yum update -y

    # Docker kurulumu
    log_info "Docker yükleniyor..."
    sudo yum install -y docker

    # Docker Compose v2 kurulumu
    log_info "Docker Compose v2 yükleniyor..."
    sudo curl -SL https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-linux-x86_64 -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    sudo ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose

    # Docker servisini başlatma
    log_info "Docker servisi başlatılıyor..."
    sudo service docker start
    sudo systemctl enable docker

    # Docker user grubu
    log_info "Kullanıcı izinleri ayarlanıyor..."
    sudo usermod -aG docker $USER

    log_success "Docker kurulumu tamamlandı!"
}

# -----------------------------------------------------------------------------
# 2. Port Kontrolü ve Firewall
# -----------------------------------------------------------------------------
configure_firewall() {
    log_info "Güvenlik duvarı yapılandırılıyor..."

    # Gerekli portları açma
    sudo firewall-cmd --permanent --add-port=22/tcp     # SSH
    sudo firewall-cmd --permanent --add-port=80/tcp     # HTTP
    sudo firewall-cmd --permanent --add-port=443/tcp    # HTTPS
    sudo firewall-cmd --permanent --add-port=8080/tcp   # octopOS CLI port
    sudo firewall-cmd --reload

    log_success "Portlar yapılandırıldı (22, 80, 443, 8080)"
}

# -----------------------------------------------------------------------------
# 3. Proje Klonlama
# -----------------------------------------------------------------------------
clone_project() {
    log_info "Proje klonlanıyor..."

    # Dizin oluşturma
    mkdir -p ~/octopos
    cd ~/octopos

    # Git clone (burada repo URL'sini değiştirin)
    if [ -d ".git" ]; then
        log_warning "Proje zaten mevcut, güncelleniyor..."
        git pull
    else
        log_info "Lütfen GitHub repo URL'nizi girin:"
        read -r REPO_URL
        git clone "$REPO_URL" .
    fi

    log_success "Proje klonlandı!"
}

# -----------------------------------------------------------------------------
# 4. Environment Yapılandırma
# -----------------------------------------------------------------------------
setup_environment() {
    log_info "Environment yapılandırılıyor..."

    # .env dosyası oluşturma
    if [ ! -f .env ]; then
        cat > .env << 'EOF'
# AWS Configuration
AWS_REGION=us-east-1
AWS_PROFILE=default

# Agent Configuration
AGENT_NAME=octo
AGENT_PERSONA=technical
AGENT_LANGUAGE=tr

# User Configuration
USER_NAME=admin
USER_WORKSPACE_PATH=/home/ec2-user/workspace

# Paths
LANCEDB_PATH=/home/ec2-user/octopos/data/lancedb
TASK_DB_PATH=/home/ec2-user/octopos/data/tasks.db

# Security
AUTO_APPROVE_SAFE_OPERATIONS=false
REQUIRE_APPROVAL_FOR_CODE=true

# Logging
LOG_LEVEL=INFO
LOG_DESTINATION=cloudwatch

# Debug
DEBUG=false
EOF
        log_warning ".env dosyası oluşturuldu - AWS kimlik bilgilerinizi ekleyin!"
    fi

    # Workspace dizini
    mkdir -p ~/workspace
    mkdir -p ~/octopos/data/lancedb

    log_success "Environment yapılandırıldı!"
}

# -----------------------------------------------------------------------------
# 5. Docker Build ve Çalıştırma
# -----------------------------------------------------------------------------
deploy_application() {
    log_info "Uygulama deploy ediliyor..."

    cd ~/octopos

    # Production docker-compose ile çalıştırma
    docker-compose -f docker-compose.prod.yml up -d --build

    log_success "Uygulama deploy edildi!"
}

# -----------------------------------------------------------------------------
# 6. Health Check
# -----------------------------------------------------------------------------
health_check() {
    log_info "Sağlık kontrolü yapılıyor..."

    sleep 5

    # Container durumu
    echo ""
    log_info "Container durumu:"
    docker ps --filter "label=app=octopos"

    # Log kontrolü
    echo ""
    log_info "Son loglar:"
    docker logs octopos-app --tail 20 || true

    log_success "Health check tamamlandı!"
}

# -----------------------------------------------------------------------------
# Ana Menu
# -----------------------------------------------------------------------------
main() {
    echo "Lütfen bir işlem seçin:"
    echo ""
    echo "  1) Docker Kurulumu (Amazon Linux 2)"
    echo "  2) Proje Klonlama ve Environment"
    echo "  3) Tam Deployment (1+2+Build)"
    echo "  4) Sadece Uygulama Çalıştırma"
    echo "  5) Durum Kontrolü ve Loglar"
    echo "  6) Temizleme (Stop & Remove)"
    echo ""
    echo -n "Seçiminiz [1-6]: "

    read -r choice

    case $choice in
        1)
            install_docker
            ;;
        2)
            clone_project
            setup_environment
            ;;
        3)
            install_docker
            clone_project
            setup_environment
            deploy_application
            health_check
            ;;
        4)
            deploy_application
            health_check
            ;;
        5)
            health_check
            ;;
        6)
            log_warning "Tüm container'lar durduruluyor ve siliniyor..."
            cd ~/octopos
            docker-compose -f docker-compose.prod.yml down -v
            log_success "Temizleme tamamlandı!"
            ;;
        *)
            log_error "Geçersiz seçim!"
            exit 1
            ;;
    esac
}

# Script çalıştırma
main "$@"