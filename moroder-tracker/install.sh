#!/bin/bash
set -e

# Проверка root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Запустите скрипт от root (sudo ./install.sh)"
    exit 1
fi

echo "=============================================="
echo "     УСТАНОВКА МАРОДЁР ТРЕКЕРА"
echo "=============================================="
echo ""

# --- Базовые зависимости ---
echo ">>> Устанавливаю системные пакеты..."
apt update -qq
apt install -y -qq python3 python3-pip

# --- Переходим в папку приложения ---
mkdir -p /opt/moroder-tracker
cd /opt/moroder-tracker

# Проверка наличия requirements.txt
if [ ! -f requirements.txt ]; then
    echo "❌ Ошибка: requirements.txt не найден в /opt/moroder-tracker"
    echo "Убедитесь, что файлы приложения скопированы в эту папку"
    exit 1
fi

# Проверка наличия точки входа (run.py или app.py)
if [ ! -f run.py ] && [ ! -f app.py ]; then
    echo "❌ Ошибка: не найден run.py или app.py"
    exit 1
fi

# --- Установка Python-зависимостей ---
echo ">>> Устанавливаю зависимости Python..."
pip3 install --upgrade pip
pip3 install -r requirements.txt

# --- Освобождаем порт 5000, если занят ---
echo ">>> Проверяю порт 5000..."
if ss -tulpn | grep -q ':5000 '; then
    echo "⚠️ Порт 5000 уже используется. Останавливаю старый процесс..."
    fuser -k 5000/tcp 2>/dev/null || true
    sleep 2
fi

# Определяем точку входа
ENTRY_POINT="run.py"
[ ! -f "$ENTRY_POINT" ] && ENTRY_POINT="app.py"

# --- Создание systemd unit (если есть права) ---
if [ -f marauder.service ]; then
    echo ">>> Настраиваю автозапуск..."
    cat > /etc/systemd/system/marauder.service <<EOF
[Unit]
Description=Marauder Tracker
After=network.target

[Service]
WorkingDirectory=/opt/moroder-tracker
ExecStart=/usr/bin/python3 /opt/moroder-tracker/$ENTRY_POINT
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload 2>/dev/null || true
    systemctl enable marauder 2>/dev/null || true
    systemctl start marauder 2>/dev/null || {
        echo "⚠️ systemd не работает, запускаю вручную..."
        nohup python3 "$ENTRY_POINT" > /var/log/marauder.log 2>&1 &
    }
else
    echo "⚠️ marauder.service не найден, запускаю Flask вручную..."
    nohup python3 "$ENTRY_POINT" > /var/log/marauder.log 2>&1 &
fi

# --- Файервол ---
if command -v ufw >/dev/null; then
    echo ">>> Открываю порты 80 и 5000..."
    ufw allow 80/tcp
    ufw allow 5000/tcp
fi

# --- Проверка и освобождение порта 80 ---
echo ">>> Проверяю порт 80..."
if ss -tulpn | grep -q ':80 '; then
    echo "⚠️ Порт 80 уже используется. Пытаюсь остановить конфликтующий процесс..."
    for pkg in apache2 nginx lighttpd; do
        if command -v $pkg >/dev/null; then
            service $pkg stop 2>/dev/null || systemctl stop $pkg 2>/dev/null || true
        fi
    done
    if ss -tulpn | grep -q ':80 '; then
        echo "❌ Не удалось освободить порт 80. Освободите его вручную и перезапустите установку."
        exit 1
    fi
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
    rm -f /etc/nginx/sites-enabled/default

    echo ">>> Проверяю конфигурацию Nginx..."
    nginx -t

    echo ">>> Запускаю Nginx..."
    if systemctl enable nginx 2>/dev/null; then
        systemctl start nginx 2>/dev/null || service nginx start
    else
        service nginx enable 2>/dev/null || true
        service nginx start
    fi
    if ! ss -tulpn | grep -q ':80 '; then
        echo "⚠️ Nginx не запустился через сервис, пробую запустить вручную..."
        nginx
    fi
    echo ">>> Nginx настроен для домена $DOMAIN"
    echo ">>> Не забудьте создать A-запись $DOMAIN -> $(hostname -I | awk '{print $1}')"
else
    echo ">>> Nginx не настраивается. Трекер будет доступен по IP:"
    echo ">>> Проверьте, что порт 5000 открыт в файерволе."
fi

# --- Проверки после установки ---
IP=$(hostname -I | awk '{print $1}')
echo ""
echo "=============================================="
echo "   РЕЗУЛЬТАТ УСТАНОВКИ"
echo ""
if ss -tulpn | grep -q ':5000 '; then
    echo "✅ Marauder слушает порт 5000"
else
    echo "❌ Marauder не запустился. Смотрите лог: /var/log/marauder.log"
fi
if [ "$USE_DOMAIN" = "y" ] || [ "$USE_DOMAIN" = "Y" ]; then
    if ss -tulpn | grep -q ':80 '; then
        echo "✅ Nginx слушает порт 80"
    else
        echo "❌ Nginx не запустился. Проверьте конфигурацию или логи."
    fi
    echo "   Откройте для активации: http://$DOMAIN/activate"
else
    echo "   Откройте для активации: http://$IP:5000/activate"
fi
echo "   Логин: admin"
echo "   Пароль: admin (смените немедленно!)"
echo "=============================================="
