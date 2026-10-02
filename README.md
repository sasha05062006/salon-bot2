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


## Production notes

- Mini App uses separate roles: client (booking), master (own bookings/status result), admin (full booking/catalog/schedule management).
- Booking creation is disabled for admin/master accounts; clients create bookings only in the Mini App.
- In Telegram chat, booking is not exposed as a regular chat flow; the Mini App is the booking interface.
- Set `DB_PATH` to a persistent Railway Volume path (for example `/data/bookings.db`) so bookings survive redeploys.
- `WEBAPP_URL` should point to the public HTTPS Railway URL (or the Quick Tunnel URL in local development).
- Master permissions: a master cannot confirm, cancel, or reschedule. A master can mark a confirmed/in-progress booking as completed or no-show and add a comment.
