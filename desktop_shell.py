"""Windows tray and an application-owned console that closes without killing workers."""
import collections
import os
import re
import sys
import threading
import time
import webbrowser


class LogBuffer:
    encoding = 'utf-8'
    def __init__(self, forward=None, limit=120000):
        self.forward, self.limit = forward, limit
        self.parts = collections.deque()
        self.size = self.version = 0
        self.lock = threading.Lock()

    def write(self, value):
        value = str(value)
        if self.forward:
            try:
                self.forward.write(value)
            except (OSError, ValueError):
                pass
        plain = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', value)
        with self.lock:
            self.parts.append(plain[-self.limit:])
            self.size += len(self.parts[-1])
            while self.size > self.limit and len(self.parts) > 1:
                self.size -= len(self.parts.popleft())
            self.version += 1
        return len(value)

    def snapshot(self):
        with self.lock:
            return self.version, ''.join(self.parts)

    def flush(self):
        if self.forward:
            try:
                self.forward.flush()
            except (OSError, ValueError):
                pass

    def isatty(self):
        return False


class DesktopShell:
    def __init__(self, url, logs, stop_all, exit_app):
        self.url, self.logs = url, logs
        self.stop_all, self.exit_app = stop_all, exit_app
        self.ready, self.closed = threading.Event(), threading.Event()
        self.hwnd = self.console = self.edit = None
        self.error = None
        self.seen = -1
        self.exiting = False

    def start(self):
        self.thread = threading.Thread(target=self._run, name='xlambot-tray', daemon=True)
        self.thread.start()
        if not self.ready.wait(8) or self.error:
            raise RuntimeError('Could not initialize Windows tray') from self.error
        return self

    def _run(self):
        import win32api as api
        import win32con as c
        import win32gui as gui
        self.gui, self.c = gui, c
        try:
            instance = api.GetModuleHandle(None)
            self.taskbar_created = gui.RegisterWindowMessage('TaskbarCreated')
            name = 'xlamBOT.Tray.' + str(os.getpid())
            klass = gui.WNDCLASS()
            klass.hInstance, klass.lpszClassName, klass.lpfnWndProc = instance, name, self._window_proc
            klass.hCursor = gui.LoadCursor(0, c.IDC_ARROW)
            klass.hbrBackground = c.COLOR_WINDOW + 1
            gui.RegisterClass(klass)
            self.hwnd = gui.CreateWindowEx(0, name, 'xlamBOT', 0, 0, 0, 0, 0, 0, 0, instance, None)
            icon_path = sys.executable if getattr(sys, 'frozen', False) else os.path.join(os.path.dirname(__file__), 'build_assets', 'xlambot.ico')
            self.owned_icon = not getattr(sys, 'frozen', False)
            if self.owned_icon:
                self.icon = gui.LoadImage(0, icon_path, c.IMAGE_ICON, 32, 32, c.LR_LOADFROMFILE)
            else:
                icons, small = gui.ExtractIconEx(icon_path, 0)
                self.icon = small[0] if small else icons[0]
                for extra in icons + small:
                    if extra != self.icon:
                        gui.DestroyIcon(extra)
                self.owned_icon = True
            self.console = gui.CreateWindowEx(0, name, 'xlamBOT · Console', c.WS_OVERLAPPEDWINDOW,
                                             c.CW_USEDEFAULT, c.CW_USEDEFAULT, 950, 560, 0, 0, instance, None)
            # Consume the process startup ShowWindow override before commands.
            gui.ShowWindow(self.console, c.SW_HIDE)
            self.edit = gui.CreateWindowEx(c.WS_EX_CLIENTEDGE, 'EDIT', '', c.WS_CHILD | c.WS_VISIBLE |
                c.WS_VSCROLL | c.WS_HSCROLL | c.ES_MULTILINE | c.ES_READONLY | c.ES_AUTOVSCROLL,
                0, 0, 930, 520, self.console, 0, instance, None)
            gui.SendMessage(self.edit, c.EM_SETLIMITTEXT, self.logs.limit + 10000, 0)
            font = gui.LOGFONT()
            font.lfFaceName, font.lfHeight = 'Consolas', -15
            self.font = gui.CreateFontIndirect(font)
            gui.SendMessage(self.edit, c.WM_SETFONT, self.font, True)
            self._icon(gui.NIM_ADD)
            self.ready.set()
            threading.Thread(target=self._refresh_loop, daemon=True, name='xlambot-console-refresh').start()
            gui.PumpMessages()
        except Exception as error:
            self.error = error
            self.ready.set()
        finally:
            self.closed.set()
            if self.hwnd:
                try:
                    self._icon(gui.NIM_DELETE)
                    if self.console:
                        gui.DestroyWindow(self.console)
                    gui.DestroyWindow(self.hwnd)
                    gui.UnregisterClass(name, instance)
                except Exception:
                    pass
            if getattr(self, 'owned_icon', False) and getattr(self, 'icon', None):
                gui.DestroyIcon(self.icon)
            if getattr(self, 'font', None):
                gui.DeleteObject(self.font)

    def _icon(self, action):
        self.gui.Shell_NotifyIcon(action, (self.hwnd, 1, self.gui.NIF_ICON | self.gui.NIF_MESSAGE |
            self.gui.NIF_TIP, self.c.WM_APP + 1, self.icon, 'xlamBOT'))

    def _refresh_loop(self):
        while not self.closed.wait(.5):
            if self.console and self.gui.IsWindowVisible(self.console):
                try:
                    self.gui.PostMessage(self.hwnd, self.c.WM_APP + 2, 0, 0)
                except Exception:
                    return

    def _refresh(self):
        version, text = self.logs.snapshot()
        if version == self.seen:
            return
        self.seen = version
        self.gui.SetWindowText(self.edit, text.replace('\r\n', '\n').replace('\n', '\r\n'))
        self.gui.SendMessage(self.edit, self.c.EM_SETSEL, -1, -1)
        self.gui.SendMessage(self.edit, self.c.EM_SCROLLCARET, 0, 0)

    def _command(self, command):
        if self.exiting:
            return
        if command == 1:
            threading.Thread(target=webbrowser.open, args=(self.url+'/panel',), daemon=True).start()
        elif command in (2, 3):
            self.gui.ShowWindow(self.console, self.c.SW_SHOW if command == 2 else self.c.SW_HIDE)
            if command == 2:
                self.gui.ShowWindow(self.console, self.c.SW_RESTORE)
                self._refresh()
                try:
                    self.gui.SetForegroundWindow(self.console)
                except Exception:
                    pass
        elif command == 4:
            threading.Thread(target=self.stop_all, daemon=True, name='xlambot-tray-stop').start()
        elif command == 5:
            self.exiting = True
            threading.Thread(target=self.exit_app, daemon=True, name='xlambot-tray-exit').start()

    def _window_proc(self, hwnd, message, wparam, lparam):
        gui, c = self.gui, self.c
        if message == getattr(self, 'taskbar_created', -1) and self.hwnd:
            self._icon(gui.NIM_ADD)
            return 0
        if message == c.WM_CLOSE and hwnd == self.console:
            gui.ShowWindow(hwnd, c.SW_HIDE)
            return 0
        if message == c.WM_SIZE and hwnd == self.console and self.edit:
            _, _, width, height = gui.GetClientRect(hwnd)
            gui.MoveWindow(self.edit, 0, 0, width, height, True)
            return 0
        if message == c.WM_APP + 2:
            self._refresh()
            return 0
        if message == c.WM_APP + 3:
            gui.PostQuitMessage(0)
            return 0
        if message == c.WM_COMMAND:
            self._command(wparam & 0xffff)
            return 0
        if message == c.WM_APP + 1:
            if lparam == c.WM_LBUTTONDBLCLK:
                self._command(1)
            elif lparam == c.WM_RBUTTONUP:
                from presentation_preferences import read
                ru = read()['language'] == 'ru'
                menu = gui.CreatePopupMenu()
                labels = [('Открыть панель','Open panel'), ('Показать консоль','Show console'),
                          ('Скрыть консоль','Hide console'), ('Остановить все устройства','Stop all devices'),
                          ('Выйти из xlamBOT','Exit xlamBOT')]
                try:
                    for index, label in enumerate(labels, 1):
                        gui.AppendMenu(menu, c.MF_STRING | (c.MF_GRAYED if self.exiting else 0), index, label[0 if ru else 1])
                    try:
                        gui.SetForegroundWindow(hwnd)
                    except Exception:
                        pass
                    x, y = gui.GetCursorPos()
                    gui.TrackPopupMenu(menu, c.TPM_LEFTALIGN | c.TPM_RIGHTBUTTON, x, y, 0, hwnd, None)
                    gui.PostMessage(hwnd, c.WM_NULL, 0, 0)
                finally:
                    gui.DestroyMenu(menu)
            return 0
        return gui.DefWindowProc(hwnd, message, wparam, lparam)

    def close(self):
        if self.hwnd and not self.closed.is_set():
            self.gui.PostMessage(self.hwnd, self.c.WM_APP + 3, 0, 0)
            self.thread.join(timeout=3)
