# Salon Bot 2

Telegram salon booking bot + Telegram Mini App.

## Бесплатный запуск Mini App без домена

Проект умеет запускать Mini App через бесплатный Cloudflare Quick Tunnel. Покупать домен не нужно. Cloudflare выдаёт HTTPS-адрес вида `https://....trycloudflare.com`.

Важно: Quick Tunnel работает, пока запущен твой компьютер и `run_free.bat`. После перезапуска URL может измениться.

### Первый запуск

1. Установи Cloudflare Tunnel:
   `winget install Cloudflare.cloudflared`
2. Создай `.env` на основе `.env.example`.
3. Заполни `BOT_TOKEN` и `ADMIN_ID`.
4. Запусти `run_free.bat`.
5. Скрипт сам получит HTTPS-адрес и передаст его боту как `WEBAPP_URL`.

После этого кнопка Mini App появляется в меню бота.

### Что работает в Mini App

- RU / UZ
- услуги
- мастер
- дата
- время
- имя и телефон
- создание записи
- раздел «Записи» для разрешённого `ADMIN_ID`
- серверная проверка Telegram initData

### Важно

Это бесплатный режим для разработки/первого запуска. Если компьютер выключен, Mini App недоступен. Для постоянной работы позже можно перенести backend на бесплатный/платный облачный хостинг.
