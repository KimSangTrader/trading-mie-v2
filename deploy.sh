#!/bin/bash

set -e  # 오류 발생 시 즉시 중단

echo "=================================================="
echo "🚀 MIE V2.0 Deployment Script"
echo "=================================================="

# 환경 변수
DEPLOY_DIR="/opt/mie-v2"
VENV_DIR="${DEPLOY_DIR}/venv"
LOG_DIR="/var/log/mie-v2"
SERVICE_NAME="mie-v2"

echo "📍 Deployment Directory: $DEPLOY_DIR"

# 1. 디렉토리 확인
if [ ! -d "$DEPLOY_DIR" ]; then
    echo "❌ Deployment directory does not exist: $DEPLOY_DIR"
    exit 1
fi

cd "$DEPLOY_DIR"

# 2. Git 최신 코드 가져오기
echo "📥 Pulling latest code from GitHub..."
git fetch origin
git pull origin main

# 3. 가상 환경 확인
if [ ! -d "$VENV_DIR" ]; then
    echo "🔧 Creating virtual environment..."
    python3.14 -m venv "$VENV_DIR"
fi

# 4. 가상 환경 활성화 및 의존성 설치
echo "📦 Installing dependencies..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

# 5. 테스트 실행
echo "🧪 Running tests..."
pytest tests/ -v --tb=short

if [ $? -ne 0 ]; then
    echo "❌ Tests failed. Aborting deployment."
    exit 1
fi

# 6. 통합 테스트 실행
echo "🔍 Running integration test..."
python main.py

if [ $? -ne 0 ]; then
    echo "❌ Integration test failed. Aborting deployment."
    exit 1
fi

# 7. systemd 서비스 재시작
echo "♻️  Restarting systemd service..."
sudo systemctl daemon-reload
sudo systemctl restart "$SERVICE_NAME"

# 8. 서비스 상태 확인
echo "📊 Checking service status..."
sudo systemctl status "$SERVICE_NAME" --no-pager

# 9. 배포 완료 메시지
echo "=================================================="
echo "✅ Deployment completed successfully!"
echo "=================================================="
echo "Service: $SERVICE_NAME"
echo "Status: $(sudo systemctl is-active $SERVICE_NAME)"
echo "Deployment Time: $(date)"
echo "=================================================="

# 10. 로그 기록
echo "[$(date)] Deployment successful" >> "$LOG_DIR/deployment.log"