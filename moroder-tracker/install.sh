#!/bin/bash
set -e

echo "=============================================="
echo "     УСТАНОВКА МАРОДЁР ТРЕКЕРА"
echo "=============================================="
echo ""

# --- Базовые зависимости ---
echo ">>> Устанавливаю системные пакеты..."
apt update -qq
apt install -y -qq python3 python3-pip

# --- Установка Python-зависимостей ---
echo ">>> Устанавливаю зависимости Python..."
cd /opt/moroder-tracker
pip3 install -r requirements.txt

# --- Копируем и запускаем сервис ---
echo ">>> Настраиваю автозапуск..."
cp marauder.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now marauder

# --- Файервол ---
if command -v ufw >/dev/null; then
    echo ">>> Открываю порт 5000..."
    ufw allow 5000/tcp
fi

# --- ОПЦИОНАЛЬНАЯ НАСТРОЙКА ДОМЕНА ---
echo ""
read -p "Хотите привязать свой домен и настроить Nginx? (y/n): " USE_DOMAIN

if [ "$USE_DOMAIN" = "y" ] || [ "$USE_DOMAIN" = "Y" ]; then
    read -p "Введите ваш домен (например, tracker.example.com): " DOMAIN

    echo ">>> Устанавливаю Nginx..."
    apt install -y -qq nginx

    echo ">>> Создаю конфигурацию для домена $DOMAIN..."
    cat << EOF > /etc/nginx/sites-available/tracker
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

    ln -sf /etc/nginx/sites-available/tracker /etc/nginx/sites-enabled/
    # Убираем default конфиг, чтобы не мешал
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl reload nginx
    echo ">>> Nginx настроен и запущен для домена $DOMAIN"
    echo ">>> Теперь ваш трекер доступен по http://$DOMAIN"
    echo ">>> Для SSL рекомендую подключить Cloudflare (режим Flexible) и создать A-запись с IP $(hostname -I | awk '{print $1}')"
else
    echo ">>> Nginx не настраивается. Трекер будет доступен по IP:"
fi

# --- Финальное сообщение ---
IP=$(hostname -I | awk '{print $1}')
echo ""
echo "=============================================="
echo "   ТРЕКЕР УСПЕШНО УСТАНОВЛЕН!"
echo ""
if [ "$USE_DOMAIN" = "y" ] || [ "$USE_DOMAIN" = "Y" ]; then
    echo "   Откройте для активации: http://$DOMAIN/activate"
else
    echo "   Откройте для активации: http://$IP:5000/activate"
fi
echo "   Логин: admin"
echo "   Пароль: admin (смените немедленно!)"
echo "=============================================="
