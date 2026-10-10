(function () {
    'use strict';
    const en = document.documentElement.lang === 'en';
    const words = {
        title:['Эмуляторы','Emulators'],subtitle:['Твоя игровая станция. Один экземпляр — один бот.','Your gaming station. One instance, one bot.'],
        add:['＋ Добавить','＋ Add'],install:['Установить','Install'],update:['Обновить мод','Update edition'],chooseFolder:['Выбрать папку','Choose folder'],
        note:['Разрешение 1280×720, root выключен. Эмулятор и бот запускаются отдельно. Оригинальный Brawl Stars загружается с GitHub; твои аккаунты остаются на твоём ПК.','1280×720, root disabled. Emulator and bot start separately. Original Brawl Stars downloads from GitHub; accounts stay on your PC.'],
        emptyTitle:['Начни с первого эмулятора','Start with your first emulator'],empty:['Установи нашу сборку или выбери папку уже установленного LDPlayer 9.5.37.','Install our edition or choose an existing LDPlayer 9.5.37 folder.'],
        help:['Как это работает','How it works'],helpBody:['«Добавить» создаёт чистый Android с нашим лаунчером, настройками и оригинальным Brawl Stars. «Клонировать» копирует закрытый экземпляр вместе с приложениями. «Подготовить» устанавливает 1280×720, 240 DPI и выключает root. «Установить дополнения» добавляет лаунчер и системные настройки, сохраняя игру и аккаунт. Для обновления мода закрой все экземпляры. Обновления бота и эмулятора проверяются раздельно; чужие данные не загружаются. Игра проверяет обновления каждые 30 минут: установка ждёт остановки бота и выхода из игры.','Add creates a clean Android with our launcher, settings and original Brawl Stars. Clone copies a stopped instance and its apps. Prepare sets 1280×720, 240 DPI and disables root. Install extras adds the launcher and system settings while preserving the game and account. Close all instances before updating the edition. Bot and emulator updates are checked separately; no other users’ data is downloaded. Game updates are checked every 30 minutes and wait for the bot to stop and the game to close.'],
        cancel:['Отмена','Cancel'],continue:['Продолжить','Continue'],name:['Название','Name'],path:['Папка LDPlayer9','LDPlayer9 folder'],
        stopped:['Выключен','Stopped'],running:['Запущен','Running'],launch:['Запустить','Launch'],quit:['Выключить','Shut down'],panel:['К боту','Bot panel'],
        more:['Управление ›','Manage ›'],clone:['Клонировать','Clone'],rename:['Переименовать','Rename'],configure:['Подготовить под 1280×720','Prepare for 1280×720'],customize:['Установить дополнения','Install extras'],remove:['Удалить экземпляр','Delete instance'],
        removeNote:['Все данные этого экземпляра будут удалены. Введи его название для подтверждения.','All data in this instance will be deleted. Enter its name to confirm.'],cloneNote:['Закрой исходный экземпляр. Копия сохранит его приложения и аккаунты.','Close the source instance. The copy will contain its apps and accounts.'],
        createNote:['Создадим чистый Android с лаунчером, настройками и оригинальным Brawl Stars. После подготовки он будет выключен.','A clean Android will be created with our launcher, settings and original Brawl Stars. It will be stopped after setup.'],
        folderNote:['Укажи папку, в которой находится ldconsole.exe версии 9.5.37.','Enter the folder containing ldconsole.exe version 9.5.37.'],
        updateNote:['Закрой все экземпляры. Загрузим подписанное обновление с GitHub; игровые данные сохранятся.','Close all instances. A signed update will be downloaded from GitHub; game data will be preserved.'],
        installNote:['Если LDPlayer ещё нет, скачаем проверенный установщик основы и откроем его. После установки закрой эмулятор для применения мода.','If LDPlayer is not installed, the verified engine installer will be downloaded and opened. Close the emulator after setup to apply the edition.'],
        configureNote:['Закрой экземпляр. Будет установлено 1280×720, 240 DPI, 2 или 4 ядра, 4 ГБ памяти и root выключен. Калибровка бота остаётся в его профиле.','Close the instance. Sets 1280×720, 240 DPI, 2 or 4 cores, 4 GB RAM, root disabled. Bot calibration stays in its profile.'],
        customizeNote:['Закрой экземпляр. Он ненадолго запустится для установки лаунчера и системных настроек, затем выключится. Игра и аккаунт сохранятся.','Close the instance. It will briefly start to install the launcher and system settings, then stop. The game and account will be preserved.'],
        update_game:['Установить / обновить Brawl Stars','Install / update Brawl Stars'],update_gameNote:['Сначала останови бот. Загрузим оригинальную игру с GitHub и проверим подпись Supercell. При установке игра закроется, аккаунт сохранится. Выключенный эмулятор ненадолго запустится и снова выключится.','Stop the bot first. Downloads the original game from GitHub and verifies the Supercell signature. The game will close during installation; your account will be preserved. A stopped emulator will briefly start and stop again.'],checking_game:['Проверяем версию игры…','Checking game version…'],installing_game:['Устанавливаем Brawl Stars…','Installing Brawl Stars…'],CLOSE_GAME_FIRST:['Сначала выйди из игры.','Close the game first.'],GAME_DOWNGRADE_BLOCKED:['Установленная игра новее версии на GitHub.','The installed game is newer than the GitHub release.'],NOT_ORIGINAL_BRAWL_STARS:['Подпись игры не совпала с Supercell. Установка отменена.','The game signature does not match Supercell. Installation cancelled.'],GAME_INSTALL_FAILED:['Не удалось установить игру. Текущие данные сохранены; повтори позже.','Game installation failed. Existing data is preserved; try again later.'],
        starting:['Готовимся…','Getting ready…'],checking:['Проверяем обновление…','Checking update…'],creating:['Создаём экземпляр…','Creating instance…'],configuring:['Настраиваем экран…','Configuring display…'],booting:['Запускаем Android…','Starting Android…'],guest_setup:['Устанавливаем дополнения…','Installing extras…'],applying:['Обновляем мод…','Updating edition…'],vendor_setup:['Заверши установку LDPlayer в открытом окне','Finish LDPlayer setup in the opened window'],ready:['Готово','Ready'],download:['Загружаем с GitHub…','Downloading from GitHub…'],wait:['Можно пользоваться остальной панелью. Бот автоматически не запустится.','You can use the rest of the panel. The bot will not start automatically.'],
        STOP_BOT_FIRST:['Сначала останови бот на этом устройстве.','Stop the bot on this device first.'],CLOSE_EMULATOR_FIRST:['Сначала закрой нужные эмуляторы.','Close the required emulators first.'],EMULATOR_BUSY:['Дождись завершения текущей операции.','Wait for the current operation to finish.'],INVALID_NAME:['Название: до 60 букв, цифр, пробелов; допустимы . - ( ).','Name: up to 60 letters, numbers or spaces; . - ( ) are allowed.'],
        CONFIRM_NAME:['Название не совпало.','The name does not match.'],UNSUPPORTED_LDPLAYER:['Нужна версия LDPlayer 9.5.37.','LDPlayer 9.5.37 is required.'],LDPLAYER_NOT_FOUND:['LDPlayer не найден. Установи его или выбери папку.','LDPlayer was not found. Install it or choose its folder.'],UPDATE_EDITION_FIRST:['Сначала обнови мод, закрыв все экземпляры.','Update the edition first with all instances closed.'],
        closing_manager:['Закрываем штатный менеджер…','Closing the native manager…'],CLOSE_MANAGER_FIRST:['Закрой окно LDMultiPlayer и повтори.','Close the LDMultiPlayer window and try again.'],error:['Операция не завершена. Проверь соединение и закрой эмуляторы перед обновлением.','The operation did not complete. Check your connection and close emulators before updating.'],unavailable:['Нет связи с менеджером. Повтори позже.','Manager is unavailable. Try again later.'],unknownEdition:['Мод ещё не подключён','Edition is not connected yet']
    };
    const t = key => (words[key] || words.error)[en ? 1 : 0];
    document.querySelectorAll('[data-text]').forEach(el => { el.textContent = t(el.dataset.text); });
    const el = id => document.getElementById(id);
    let busy = false, state = null, pending = null, lastRows = '';
    function error(code) { el('emuError').hidden = !code; el('emuError').textContent = code ? t(code) : ''; }
    async function send(payload) {
        error(null); el('emuDialog').close();
        try {
            const r = await XlamSession.fetch('/api/emulators', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.error || 'error');
            await refresh();
        } catch (e) { error(e.message); }
    }
    function dialog(payload, title, note, field, value='') {
        pending = {payload,field}; el('emuDialogTitle').textContent = title; el('emuDialogNote').textContent = note;
        el('emuValue').hidden = !field; el('emuLabel').hidden = !field; el('emuLabel').textContent = t(field === 'path' ? 'path' : 'name');
        el('emuValue').value = value; el('emuValue').required = !!field;
        el('emuValue').maxLength = field === 'path' ? 260 : 60;
        el('emuDialog').showModal();
    }
    function button(text, action, item, css='btn btn-ghost') {
        const b = document.createElement('button'); b.className=css; b.textContent=t(text); b.disabled=busy;
        b.onclick = () => {
            const p={action,index:item.index};
            if (action === 'clone') dialog(p,t('clone'),t('cloneNote'),'name',`${item.name} (2)`);
            else if (action === 'rename') dialog(p,t('rename'),'','name',item.name);
            else if (action === 'remove') dialog(p,t('remove'),`${t('removeNote')} ${item.name}`,'confirmation');
            else if (action === 'configure' || action === 'customize' || action === 'update_game') dialog(p,t(action),t(`${action}Note`));
            else send(p);
        }; return b;
    }
    function render(data) {
        state=data; busy=data.job?.state === 'running';
        el('emuEdition').textContent=data.edition ? `${data.edition} · LDPlayer 9.5.37 · 1280×720` : t('unknownEdition');
        el('emuAdd').disabled=busy || !data.path || !data.revision;
        for (const id of ['emuInstall','emuUpdate','emuPath']) el(id).disabled=busy;
        el('emuInstall').hidden=!!data.path; el('emuUpdate').hidden=!data.path;
        el('emuJob').hidden=!busy; el('emuEmpty').hidden=data.instances.length>0;
        if (busy) {
            const parts=(data.job.phase || 'starting').split(':'); el('emuPhase').textContent=t(parts[0]);
            el('emuDetail').textContent=parts[0] === 'download' ? `${Math.round(Number(parts[1])/1048576)} / ${Math.round(Number(parts[2])/1048576)} MB` : t('wait');
        }
        if(data.job?.state === 'error') error(data.job.error);
        else if(data.job?.state === 'done') error(null);
        const identity=JSON.stringify([data.instances,busy]); if(identity===lastRows) return; lastRows=identity;
        el('emuList').replaceChildren();
        for (const item of data.instances) {
            const card=document.createElement('article');card.className='emu-card';
            const head=document.createElement('div');head.className='emu-card-head';
            const name=document.createElement('h2');name.textContent=item.name;head.append(name);
            const badge=document.createElement('span');badge.className=`emu-badge${item.running?' on':''}`;badge.textContent=t(item.running?'running':'stopped');head.append(badge);card.append(head);
            const info=document.createElement('p');info.textContent=`${item.width} × ${item.height} · ${item.dpi} DPI`;card.append(info);
            const primary=document.createElement('div');primary.className='emu-primary';primary.append(button(item.running?'quit':'launch',item.running?'quit':'launch',item,'btn btn-primary'));
            const link=document.createElement('a');link.className='btn btn-ghost';link.href=`/panel?device=${encodeURIComponent(item.serial)}`;link.textContent=t('panel');primary.append(link);card.append(primary);
            const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent=t('more');details.append(summary);
            const actions=document.createElement('div');for(const action of ['update_game','clone','rename','configure','customize','remove']) actions.append(button(action,action,item));details.append(actions);card.append(details);el('emuList').append(card);
        }
    }
    async function refresh() {
        try { const response=await XlamSession.fetch('/api/emulators');const data=await response.json(); if(!response.ok||!data.ok) throw new Error('unavailable'); render(data); }
        catch(e){error(e.message);}
    }
    el('emuForm').onsubmit=e=>{e.preventDefault();if(!pending)return;const {payload,field}=pending;if(field)payload[field]=el('emuValue').value;send(payload);};
    el('emuCancel').onclick=()=>el('emuDialog').close();
    el('emuAdd').onclick=()=>dialog({action:'add'},t('add'),t('createNote'),'name',`xlamBOT ${state.instances.length+1}`);
    el('emuPath').onclick=()=>dialog({action:'select'},t('chooseFolder'),t('folderNote'),'path',state?.path||'');
    el('emuInstall').onclick=()=>dialog({action:'install'},t('install'),t('installNote'));
    el('emuUpdate').onclick=()=>dialog({action:'update'},t('update'),t('updateNote'));
    async function poll(){await refresh();setTimeout(poll,document.hidden?15000:(busy?1500:5000));}poll();
})();
