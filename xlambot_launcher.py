"""Точка входа собранной программы xlamBOT.

Задача этого файла - сделать так, чтобы в готовом .exe всё работало без
Python, терминала и настроек. Отсюда три вещи:

1. Каталог ресурсов. В собранной программе файлы лежат во временной папке
   PyInstaller, поэтому пути к моделям, картинкам и настройкам надо уметь
   находить и там. utils.PROJECT_ROOT настроен на это же, но проверяем ещё раз
   и предупреждаем, если что-то не так.

2. Мастер настройки при первом запуске. Если ADB не найден или устройство не
   видно, пользователь должен получить понятный список шагов, а не
   traceback. Запускаем мастер и ждём его завершения.

3. Панель. Поднимаем её на свободном порту, печатаем адрес и открываем браузер.
   На macOS и Linux окно открывает pywebview, на Windows - системный браузер.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser

APP_NAME = "xlamBOT"
VERSION = "0.8.22"
DEFAULT_PORT = 5195
WIZARD_MARKER = "setup_done.json"


def bundled_root() -> str:
    """Каталог ресурсов: временная папка PyInstaller или папка рядом."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return meipass
    return os.path.dirname(os.path.abspath(__file__))


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def free_port(preferred: int) -> int:
    for port in [preferred] + list(range(preferred + 1, preferred + 25)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred


def data_dir() -> str:
    """Куда складывать настройки пользователя, логи и состояние."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME)


def check_assets(root: str) -> list[str]:
    """Что из необходимого лежит рядом с программой."""
    problems = []
    required = [
        ("cfg", "папка настроек"),
        ("images", "шаблоны экрана"),
        ("models", "файлы моделей"),
        ("playstyles", "плейстайлы"),
        ("scrcpy", "связь с устройством"),
        ("static", "панель"),
        ("templates", "панель"),
    ]
    for name, what in required:
        if not os.path.isdir(os.path.join(root, name)):
            problems.append(f"нет папки {name} - {what}")
    for model in ("mainInGameModel.onnx", "tileDetector.onnx"):
        if not os.path.isfile(os.path.join(root, "models", model)):
            problems.append(f"нет модели {model}")
    return problems


def run_wizard() -> int:
    print("\nЗапускаю мастер настройки.\n")
    try:
        import setup_wizard

        return setup_wizard.main()
    except Exception as error:  # noqa: BLE001
        print(f"Мастер настройки не отработал: {error}")
        print("Разбираться можно в панели: статус устройства и логи.")
        return 1


def open_ui(url: str) -> None:
    time.sleep(1.5)
    try:
        webbrowser.open(url)
    except Exception:
        pass


# Имя мьютекса одинаковое для всех сборок, без версии: обновление должно
# узнавать запущенный экземпляр, иначе установщик не сможет его закрыть.
SINGLE_INSTANCE_MUTEX = "xlamBOT_single_instance"

_mutex_handle = None


def claim_single_instance() -> bool:
    """Занять мьютекс единственного запуска. False - программа уже открыта.

    Нужен по двум причинам. Установщик по этому мьютексу находит запущенный
    xlamBOT.exe и закрывает его сам вместо ошибки. И, что важнее, два
    экземпляра нельзя оставлять: они берут один и тот же порт и device
    профиль, из-за чего получается два бота на одном устройстве.
    """
    global _mutex_handle
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        handle = kernel32.CreateMutexW(None, True, SINGLE_INSTANCE_MUTEX)
        if not handle:
            # Не смогли создать - не блокируем запуск: отсутствие защиты
            # лучше, чем отказ работать.
            return True
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return False
        _mutex_handle = handle  # держим открытым до конца процесса
        return True
    except Exception:  # noqa: BLE001
        return True


def main() -> int:
    shell = None
    logs = None
    if os.name == 'nt' and is_frozen():
        from desktop_shell import LogBuffer
        logs = sys.stdout if isinstance(sys.stdout, LogBuffer) else LogBuffer(sys.stdout)
        sys.stdout = sys.stderr = logs
    if not claim_single_instance():
        print("xlamBOT уже запущен. Закройте окно программы и попробуйте снова.")
        print("Если окна нет, возможно программа запущена свёрнутым значком в трее.")
        return 3

    root = bundled_root()
    os.chdir(root)
    import update_client
    update_client.activate()

    print("=" * 64)
    print(f"  {APP_NAME} {VERSION}")
    print("=" * 64)

    problems = check_assets(root)
    if problems:
        print("\nПрограмма собрана неполно, часть файлов на месте:")
        for line in problems:
            print(f"  - {line}")
        print("\nЗапустите setup.py из исходников либо обратитесь в канал.")
        return 2

    # Мастер настройки: один раз, и только если есть повод
    marker = os.path.join(data_dir(), WIZARD_MARKER)
    needs_wizard = True
    if os.path.isfile(marker):
        try:
            import json

            with open(marker, encoding="utf-8") as handle:
                state = json.load(handle)
            needs_wizard = state.get("wizard_exit_code") != 0
        except Exception:
            needs_wizard = True

    if needs_wizard and not is_frozen() and os.environ.get("XLAMBOT_SKIP_WIZARD") != "1":
        code = run_wizard()
        try:
            import json

            os.makedirs(data_dir(), exist_ok=True)
            with open(marker, "w", encoding="utf-8") as handle:
                json.dump({"wizard_exit_code": code}, handle)
        except Exception:
            pass
        # Мастер не обязан пройти полностью: дальше панель покажет, что не так
        if code not in (0, 1):
            return code

    port = free_port(int(os.environ.get("XLAMBOT_PORT", DEFAULT_PORT)))
    url = f"http://127.0.0.1:{port}"

    print(f"\nПанель управления: {url}")
    print("Панель и консоль доступны через значок xlamBOT в системном трее.\n")

    threading.Thread(target=open_ui, args=(url,), daemon=True).start()

    try:
        from webui.app import create_app

        # None вместо main: панель сама поднимает ботов на найденных
        # устройствах и следит за их состоянием.
        app = create_app(None, start_discord_bot=False)
        update_client.mark_healthy()
        if is_frozen():
            threading.Thread(target=app.config['update_manager'].loop, daemon=True).start()
        from werkzeug.serving import make_server
        server = make_server('127.0.0.1', port, app, threaded=True)
        def stop_all():
            app.config['device_manager'].stop_all()
            app.config['runtime_manager'].stop()
        def shutdown():
            with app.config['update_manager'].lock:
                app.config['update_manager'].installing = True
            stop_all()
            server.shutdown()
        app.extensions['shutdown_server'] = shutdown
        if logs is not None:
            from desktop_shell import DesktopShell
            shell = DesktopShell(url, logs, stop_all, shutdown).start()
        try:
            server.serve_forever(poll_interval=.2)
        finally:
            stop_all()
            server.server_close()
            if shell:
                shell.close()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    except Exception as error:  # noqa: BLE001
        print(f"Панель не запустилась: {error}")
        return 3
    return 0


if __name__ == "__main__":
    if sys.stdout is None:
        from desktop_shell import LogBuffer
        sys.stdout = sys.stderr = LogBuffer()
    if '--tray-self-test' in sys.argv:
        import json
        import time
        from pathlib import Path
        from desktop_shell import DesktopShell, LogBuffer
        buffer = LogBuffer()
        shell = DesktopShell('http://127.0.0.1:5195', buffer, lambda:None, lambda:None).start()
        gui, c = shell.gui, shell.c
        try:
            gui.SendMessage(shell.hwnd, c.WM_COMMAND, 2, 0)
            buffer.write('tray self-test\n')
            gui.SendMessage(shell.hwnd, c.WM_APP+2, 0, 0)
            shown = bool(gui.IsWindowVisible(shell.console))
            gui.SendMessage(shell.console, c.WM_CLOSE, 0, 0)
            hidden = not gui.IsWindowVisible(shell.console)
            gui.SendMessage(shell.hwnd, c.WM_COMMAND, 2, 0)
            reopened = bool(gui.IsWindowVisible(shell.console))
            text = gui.GetWindowText(shell.edit)
            result = {'shown':shown,'close_hides':hidden,'reopened':reopened,'logs_visible':'tray self-test' in text}
        finally:
            shell.close()
        result['closed'] = shell.closed.is_set()
        Path(os.environ['XLAMBOT_SELF_TEST_OUTPUT']).write_text(json.dumps(result),encoding='utf-8')
        sys.exit(0 if all(result.values()) else 1)
    if '--restart-self-test' in sys.argv or '--restart-child-test' in sys.argv:
        import json
        import update_client
        if not claim_single_instance():
            sys.exit(3)
        if '--restart-child-test' in sys.argv:
            update_client.root().mkdir(parents=True, exist_ok=True)
            (update_client.root() / 'restart-child-test.json').write_text(
                json.dumps({'pid': os.getpid(), 'mutex_acquired': True}), encoding='utf-8')
            sys.exit(0)
        update_client.restart_application(['--restart-child-test'])
    if '--update-self-test' in sys.argv:
        import json
        import update_client
        os.chdir(bundled_root())
        overlay = update_client.activate()
        from webui.app import create_app
        import utils
        import webui.app
        app = create_app(None, start_discord_bot=False)
        client = app.test_client()
        headers = {'X-Xlam-UI-Token': app.config['UI_API_TOKEN']}
        response = client.get('/api/updates/status', headers=headers)
        update_client.mark_healthy()
        emulator_status = client.get('/api/emulators', headers=headers).status_code
        result = json.dumps({'overlay': str(overlay), 'utils': utils.__file__, 'app': webui.app.__file__,
                          'api_status': response.status_code, 'revision': update_client.read_state().get('revision'),
                          'emulators_status': client.get('/emulators').status_code,
                          'emulators_api_status': emulator_status,
                          'emulators_remote_status': client.get('/api/emulators', headers=headers, environ_overrides={'xlambot.remote':True}).status_code,
                          'panel_status': client.get('/panel').status_code}, ensure_ascii=True)
        if os.environ.get('XLAMBOT_SELF_TEST_OUTPUT'):
            from pathlib import Path
            Path(os.environ['XLAMBOT_SELF_TEST_OUTPUT']).write_text(result, encoding='utf-8')
        else:
            print(result)
        sys.exit(0 if response.status_code == 200 and emulator_status == 200 else 1)
    sys.exit(main())
