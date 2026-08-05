#!/bin/bash
set -e  # остановиться при любой ошибке

echo ">>> Установка Мародёр Трекера..."

# Переходим в /opt
cd /opt

# Удаляем старую папку, если есть (для обновлений)
if [ -d "moroder-tracker" ]; then
    echo "Найдена предыдущая версия. Удаляю..."
    rm -rf moroder-tracker
fi

# Скачиваем архив
wget -O marauder.tar.gz "https://raw.githubusercontent.com/твой_логин/имя_репозитория/main/marauder_linux.tar.gz"

# Распаковываем (папка в архиве называется moroder-tracker)
tar xzf marauder.tar.gz

# Удаляем скачанный архив
rm marauder.tar.gz

# Устанавливаем зависимости
apt update && apt install -y python3 python3-pip
pip install -r /opt/moroder-tracker/requirements.txt

# Копируем и запускаем сервис, если есть файл marauder.service
if [ -f /opt/moroder-tracker/marauder.service ]; then
    cp /opt/moroder-tracker/marauder.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable --now marauder
    echo ">>> Трекер запущен как сервис."
else
    echo ">>> Файл marauder.service не найден. Запустите трекер вручную:"
    echo "python3 /opt/moroder-tracker/run.py"
fi

# Показываем IP-адрес сервера для подключения
echo ">>> Готово! Открой http://$(hostname -I | awk '{print $1}'):5000/activate"
echo "Логин: admin, пароль: admin (смените пароль!)"