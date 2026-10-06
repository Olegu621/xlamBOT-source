# Telegram — подключение и управление / Setup and control

Интеграция входит в обычный жизненный цикл `webui.app.create_app`, которым пользуется `xlamBOT.exe`. При первом интерактивном запуске в консоли появляется выбор подключения. Ответ сохраняется отдельно от профилей устройств. При отказе Telegram не запускается. Без интерактивного stdin программа не задаёт вопросов: используется сохранённый выбор. Проверка обновления `--update-self-test` не подключает Telegram.

## Подключение через BotFather

Создайте бота у [BotFather](https://t.me/BotFather), запустите приложение в консоли и выберите подключение существующего токена. Ввод токена скрыт. Мастер проверяет `getMe`, предлагает персональную ссылку `/start` с одноразовым кодом на пять минут и открывает её в Telegram. Нажмите **Start**. Пока код не подтверждён, удалённое управление недоступно. `/start` не запускает автоигру.

Для повторной настройки:

```powershell
python xlambot_launcher.py --telegram-setup
# После выпуска обновления EXE:
.\xlamBOT.exe --telegram-setup
```

Если приложение уже открыто, закройте его перед повторной настройкой: один токен обслуживает один poller. Можно подключиться отдельным консольным процессом к уже работающей панели, когда встроенный Telegram отключён:

```powershell
python -m telegram_integration --telegram-setup --panel http://127.0.0.1:5195
```

Адрес должен быть loopback. Если панель выбрала другой порт, укажите фактический порт. Встроенная интеграция работает через те же защищённые обработчики приложения и не зависит от порта.

## Создание через бота-менеджера

Это отдельный сервис владельца проекта. Токен менеджера не входит в EXE или подписанный пакет. Создайте собственного менеджера через BotFather и включите **Bot Management Mode** в его настройках. Передайте токен сервису через секрет окружения `XLAMBOT_MANAGER_TOKEN`.

```bash
python -m telegram_integration.manager --directory /var/lib/xlam-telegram-manager --allowed-user 123456789
```

`--allowed-user` можно повторять для нескольких участников; без списка сервис принимает пользователей с действительной сессией создания. Собственный Telegram ID можно получить командой `/id` у менеджера. Рабочую директорию и файл окружения оставьте доступными только пользователю сервиса. На Linux токены защищены правами файлов; на Windows — пользовательским DPAPI. Не размещайте данные сервиса в рабочем дереве Git.

По умолчанию сервис слушает `127.0.0.1:8789`. Для удалённых установок поставьте перед ним HTTPS-прокси с ограничением частоты запросов и размера тела. Например, Caddy с DNS домена, направленным на сервер:

```caddyfile
manager.example.com {
    reverse_proxy 127.0.0.1:8789
}
```

Настройте запуск процесса при старте сервера средствами systemd или диспетчера служб. Не публикуйте порт backend напрямую. Клиент проверяет TLS и не следует перенаправлениям; HTTP допускается только на loopback для локальной настройки.

На клиенте задайте **несекретный** адрес менеджера:

```powershell
$env:XLAMBOT_TELEGRAM_MANAGER_URL = "https://manager.example.com"
python xlambot_launcher.py --telegram-setup
```

Действие «Создать бота» открывает менеджера с сессией этой установки. После **Start** менеджер узнаёт ваш Telegram ID и показывает зелёную кнопку создания. Она открывает официальный диалог `https://t.me/newbot/{manager}/{suggested_username}?name=xlamBOT`. Имя и username заполнены, но могут быть изменены. Telegram требует подтверждения пользователя.

Менеджер получает `managed_bot`, запрашивает токен через `getManagedBotToken` и передаёт его клиенту по HTTPS с помощью одноразового секретного подтверждения. Сессия действует десять минут, код привязки клиента — пять минут. Даже после выдачи токена нужно подтвердить код `/start` в созданном боте. Токены не выдаются для посторонних ботов без активной сессии владельца.

Один владелец может иметь только одну незавершённую сессию создания. После прерывания дождитесь её истечения либо используйте ручное подключение. Если ответ одноразовой выдачи потерян в сети, повторная выдача отклоняется; восстановите токен через BotFather и ручной мастер. Пока менеджер не развёрнут, работает вариант BotFather.

## Меню и уведомления

- `/menu` — управление; `/play` — запуск выбранного устройства; `/status` — сводка; `/devices` — выбор устройства; `/settings` — настройки; `/help` — справка.
- Зелёные кнопки запуска/продолжения, красная остановка, пауза, скриншот, диагностика. Перед командами показано выбранное устройство. Остановка всех требует отдельного подтверждения. Подписи и эмодзи остаются понятными в старых клиентах.
- Уведомления: жизненный цикл, ошибки, ADB, известные ошибки игрового экрана, завершение матчей, кубки аккаунта, боец, очередь, обновления и сводка. Категории включаются отдельно или пресетами; фильтр может ограничивать устройство.
- Тихие часы 23:00–08:00 можно включить в меню. Отдельно выбирается пропуск критических сообщений ночью. Интервал сводки: 15/30/60 минут. Пользовательское время задаётся через `python -m telegram_integration --quiet-start 22:00 --quiet-end 09:00` при отключённом встроенном poller.
- Для работающего устройства можно выбрать остановку через 30/60/120 минут или после 5/10/20 распознанных завершений матчей. Удаление лимита — в том же меню. Таймер считает реальное время, включая паузу. Остановка запрашивается ближайшим опросом, обычно в пределах пяти секунд; доступность API обязательна.
- Язык: русский, английский или общий язык панели. Неизвестные показатели отмечаются `—`. Счётчик матчей относится к текущему запуску игрового worker и считает распознанные итоговые экраны; он не является официальной статистикой сервера игры.

Наблюдение идёт раз в пять секунд. Нераспознанное событие не выдаётся за известное. Сводка показывает ADB, состояние worker, время работы, бойца, доступные кубки, счётчик и последнюю ошибку. Скриншот берётся из существующего захвата, новый поток ADB не создаётся. В меню есть тест, отключение Telegram и отвязка аккаунта. Они не останавливают игру.

## Хранение и надёжность

На Windows настройки: `%LOCALAPPDATA%\xlamBOT-Telegram\preferences.json`, токен: `secrets.bin`, защищённый DPAPI текущего пользователя. На Linux файлы имеют права 0600, папка — 0700. Папка отдельная от xlamBOT, поэтому не входит в его диагностические архивы/экспорт профилей. Привязка по коду хранит только SHA-256 кода.

Доступ разрешён только владельцу и его личному чату. Старые меню действуют десять минут и перестают действовать после смены выбранного устройства. Нажатие выполняется один раз. Offset Telegram сохраняется перед управлением: при аварийном завершении команда может остаться невыполненной, но не будет автоматически повторена после рестарта. Нажмите новую кнопку при необходимости.

Переподключение имеет таймауты и задержку до минуты; учитывается `retry_after`. Отправка с неясным результатом не повторяется автоматически. Очередь ограничена 50 сообщениями; события старше двух минут удаляются, одинаковые события объединяются в течение минуты. Telegram и наблюдение работают отдельными потоками. Ошибка Telegram не останавливает игровой worker. Неверный/отозванный токен отключает poller; конфликт двух poller тоже требует повторной настройки.

Локальная панель `127.0.0.1` доступна на компьютере с xlamBOT. Telegram не делает её доступной с телефона и не открывает её в интернет.

## Проверка и выпуск

```powershell
python -m pip install -r requirements-ci.txt
python -m unittest discover -s tests -v
```

Source CI проверяет модуль на Windows и Linux с Python 3.13. Тесты используют заглушки Telegram и локальный HTTP-сервис; реальные токены не нужны. Проверяются доступ, коды, дубликаты, устройства, фильтры, тихие часы, лимиты, OS-хранение, передача токена менеджером и обработка сети. Для приёмки с реальным Telegram владелец должен пройти оба мастера и проверить команды на своём эмуляторе.

После объединения исходников издатель запускает существующий `tools/publish.py` с новым номером ревизии и действующим закрытым ключом. Пакет включает `telegram_integration/*.pyc`; сохранение источников и тега обязательно. Новая сборка EXE учитывает пакет в PyInstaller. Подпись и загрузчик остаются прежними.

## English

Telegram is optional and starts through the normal `create_app` lifecycle, including the regular EXE. The first interactive console launch offers opt-in; headless startup never prompts and uses saved preferences. Use `--telegram-setup` to configure again. BotFather token entry is hidden, `getMe` is checked, and the owner must redeem a five-minute, single-use `/start` link. `/start` never starts gameplay.

One-button creation needs a separately deployed management bot with Bot Management Mode enabled. Run `python -m telegram_integration.manager --directory <private-directory>` with its token in the `XLAMBOT_MANAGER_TOKEN` secret; restrict owners with repeated `--allowed-user ID` options. Put HTTPS and rate limiting in front of the loopback backend. Set the non-secret `XLAMBOT_TELEGRAM_MANAGER_URL` on clients. The manager authenticates the Telegram owner, opens a prefilled official newbot dialog, receives `managed_bot`, calls `getManagedBotToken` and hands off the token through a ten-minute single-use capability. Final client pairing remains required. The manager token is never bundled. BotFather is the fallback when no manager is deployed.

Menus provide device selection, green start/resume, pause, red stop, confirmed stop-all, statistics, screenshots, diagnostics and notification settings. Categories, presets, device filters, quiet hours and 15/30/60-minute summaries persist. Limits stop an active device after 30/60/120 minutes or 5/10/20 recognized completed matches. The five-second observer requires the local API to be available; the timer includes pauses. Match totals represent recognized result screens in the current worker session, not official server statistics. Unknown data is shown as `—`. Language follows the panel or can be set to RU/EN.

Secrets are stored outside the xlamBOT export directory: Windows uses user DPAPI, POSIX uses 0700/0600 permissions. Owner ID and private chat are checked for every action. Buttons expire and are single-use. Persisting the update offset before control prevents replay after a crash but can lose an interrupted command. Network failures do not stop gameplay. Alerts are bounded, coalesced, expire after two minutes, and are not blindly resent after ambiguous delivery. Localhost panel links are never advertised as accessible from a phone.

Run the commands above for offline tests. Source CI covers Windows/Linux Python 3.13; real Telegram/emulator acceptance is still required. Merge source changes first, then use the existing publisher with the next unused revision and the original signing key; do not publish an unsigned or differently signed replacement.
