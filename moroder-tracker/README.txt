# 1. Скопируйте файл в системную папку
sudo cp marauder.service /etc/systemd/system/

# 2. Примените изменения
sudo systemctl daemon-reload

# 3. Включите автозапуск при старте сервера
sudo systemctl enable marauder

# 4. Запустите трекер
sudo systemctl start marauder

# 5. Проверьте статус
sudo systemctl status marauder