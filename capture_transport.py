"""Safe transport extensions without replacing the installed scrcpy package.
Adapted from bsdedus/xlamBOT-TrioSafety 5f622fc, CC BY-NC 4.0.
Device ownership stays with WindowController; selftests acquire their own lease.
"""
import os
import re
import scrcpy as original
from scrcpy import core
from scrcpy.core import AdbConnection, SCRCPY_SERVER_VERSION
EVENT_FRAME = original.EVENT_FRAME
EVENT_DISCONNECT = original.EVENT_DISCONNECT
ACTION_UP = original.ACTION_UP
ACTION_DOWN = original.ACTION_DOWN
ACTION_MOVE = original.ACTION_MOVE

class _FullWriteSocket:
    def __init__(self, socket): self.socket = socket
    def send(self, data):
        self.socket.sendall(data)
        return len(data)
    def __getattr__(self, name): return getattr(self.socket, name)

class _CheckedControl:
    def __init__(self, sender, parent): self.sender, self.parent = sender, parent
    def __getattr__(self, name):
        method = getattr(self.sender, name)
        if not callable(method): return method
        def call(*args, **kwargs):
            if self.parent.control_socket is None:
                raise ConnectionError('scrcpy control socket is closed')
            return method(*args, **kwargs)
        return call

class Client(original.Client):
    def __init__(self, *args, encoder_name=None, **kwargs):
        if encoder_name is not None and not re.fullmatch(r'[A-Za-z0-9_.-]+', encoder_name):
            raise ValueError('Invalid video encoder component name')
        super().__init__(*args, encoder_name=None, **kwargs)
        self.encoder_name = encoder_name
        self.control = _CheckedControl(self.control, self)

    def _Client__stream_loop(self):
        try:
            super()._Client__stream_loop()
        except (ConnectionError, OSError):
            # Socket loss belongs to the owner's bounded capture recovery.
            # Other failures still reach the application's thread crash hook.
            self.stop()

    def _Client__init_server_connection(self):
        super()._Client__init_server_connection()
        if self.control_socket is not None:
            self.control_socket = _FullWriteSocket(self.control_socket)

    def __deploy_server(self) -> None:
        """
        Deploy server to android device
        """
        jar_name = "scrcpy-server.jar"
        server_file_path = os.path.join(
            os.path.abspath(os.path.dirname(core.__file__)), jar_name
        )
        self.device.sync.push(server_file_path, f"/data/local/tmp/{jar_name}")
        commands = [
            f"CLASSPATH=/data/local/tmp/{jar_name}",
            "app_process",
            "/",
            "com.genymobile.scrcpy.Server",
            # 2.7 is the newest server that still uses the host-initiated tunnel
            # this client speaks. 2.4 fails to negotiate a video stream on several
            # Android images (including software-rendered emulators).
            SCRCPY_SERVER_VERSION,
            "log_level=info",
            f"max_size={self.max_width}",
            f"max_fps={self.max_fps}",
            f"video_bit_rate={self.bitrate}",
            "tunnel_forward=true",
            "send_frame_meta=false",
            "control=true",
            "audio=false",
            "show_touches=false",
            "stay_awake=false",
            "power_off_on_close=false",
            "clipboard_autosync=false"
        ]
        if self.encoder_name:
            commands.append(f"video_encoder={self.encoder_name}")

        self.__server_stream: AdbConnection = self.device.shell(
            commands,
            stream=True,
        )

        # Wait for server to start
        self.__server_stream.read(10)

