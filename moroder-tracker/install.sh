#!/bin/bash
set -e

echo ">>> Установка Мародёр Трекера..."

# Устанавливаем зависимости
apt update && apt install -y python3 python3-pip
pip3 install -r /opt/moroder-tracker/requirements.txt

# Копируем сервис и запускаем
cp /opt/moroder-tracker/marauder.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now marauder

echo ">>> Готово! Открой http://$(hostname -I | awk '{print $1}'):5000/activate"
echo "Логин: admin, пароль: admin (смените пароль!)"
