import adbutils
import os
import re
import socket
import subprocess
from collections import deque
import av
import kthread
import numpy as np
from subprocesskiller import kill_process_children_parents, kill_pid, kill_subprocs
from adbutils import Network
from kthread_sleep import sleep
from get_free_port import get_dynamic_ports
import atexit

startupinfo = subprocess.STARTUPINFO()
creationflags = 0 | subprocess.CREATE_NO_WINDOW
startupinfo.wShowWindow = subprocess.SW_HIDE
invisibledict = {
    "startupinfo": startupinfo,
    "creationflags": creationflags,
    "start_new_session": True,
}


@atexit.register
def kill_them_all():
    kill_subprocs(dontkill=())


def mainprocess(cmd):
    if isinstance(cmd, str):
        cmd = [cmd]
    exefile = cmd[0]
    exefile = exefile.strip().strip('"').strip()
    exefile = os.path.normpath(exefile)
    exefile = f'"{exefile}"'
    try:
        arguments = cmd[1:]
    except Exception:
        arguments = []

    args_command = " ".join(arguments).strip()
    wholecommand = f'start /min "" {exefile} {args_command}'
    p = subprocess.Popen(wholecommand, shell=True, **invisibledict)
    return p


def get_screen_height_width(adb_path, deviceserial):
    try:
        p = subprocess.run(
            rf"{adb_path} -s {deviceserial} shell dumpsys window",
            shell=True,
            capture_output=True,
            **invisibledict,
        )
        screenwidth, screenheight = [
            int(x)
            for x in re.findall(rb"cur=(\d{,4}x\d{,4}\b)", p.stdout)[0]
            .lower()
            .split(b"x")
        ]
        print(screenheight, screenwidth)

    except Exception:
        screenwidth, screenheight = (
            subprocess.run(
                rf'{adb_path} -s {deviceserial} shell dumpsys window | grep cur= |tr -s " " | cut -d " " -f 4|cut -d "=" -f 2',
                shell=True,
                capture_output=True,
                **invisibledict,
            )
            .stdout.decode("utf-8", "ignore")
            .strip()
            .split("x")
        )
        screenwidth, screenheight = int(screenwidth), int(screenheight)
    return screenwidth, screenheight


class AdbShotUSB:
    """
    A class for capturing screenshots using ADB (Android Debug Bridge) over USB.

    Args:
        device_serial (str): The serial number of the target Android device.
        adb_path (str): The path to the ADB executable.
        adb_host_address (str, optional): The IP address of the ADB server (default: "127.0.0.1").
        adb_host_port (int, optional): The port of the ADB server (default: 5037).
        sleep_after_exception (float, optional): Sleep duration in seconds after an exception (default: 0.05).
        frame_buffer (int, optional): The size of the frame buffer (default: 4) - creates a deque with the len of 4.
        lock_video_orientation (int, optional): Video orientation lock value (default: 0).
        max_frame_rate (int, optional): Maximum video frame rate (default: 0).
        byte_package_size (int, optional): Size of the byte package for data retrieval (default: 131072).
        scrcpy_server_version (str, optional): Version of the scrcpy server (default: "2.0").
        log_level (str, optional): Logging level (default: "info").
        max_video_width (int, optional): Maximum width of the video (default: 0).
        start_server (bool, optional): Whether to start the ADB server (default: True). adb start-server
        connect_to_device (bool, optional): Whether to connect to the device (default: True). adb connect XXXX

    Attributes:
        lastframes (deque): A deque to store the last frames captured.
        loop_finished (bool): Indicates whether the frame capturing loop has finished.
        adb_path (str): The path to the ADB executable.
        device_serial (str): The serial number of the target Android device.
        host (str): The IP address of the ADB server.
        port (int): The port of the ADB server.
        folder_here (str): The absolute path to the current folder.
        scrcpy_path (str): The absolute path to the scrcpy-server.jar file.
        codec (av.CodecContext): The codec context for video decoding.
        getting_screenshot (bool): Indicates whether a screenshot is being retrieved.
        serverstream: The ADB shell stream for the scrcpy server.
        video_socket: The socket connection for video transmission.
        pause_capturing (bool): Indicates whether capturing is paused.
        stop_capturing (bool): Indicates whether capturing should be stopped.
        byte_size (int): Size of the byte package for data retrieval.
        sleep_after_exception (float): Sleep duration in seconds after an exception.
        all_raw_data264 (list): A list to store all the raw video data in H.264 format.
        real_height (int): The actual height of the captured frames.
        real_width (int): The actual width of the captured frames.
        adb_host (adbutils.AdbClient): The ADB client for connecting to the ADB host.
        device (adbutils.AdbDevice): The ADB device to which the class is connected.
        lock_video_orientation (int): Video orientation lock value.
        max_frame_rate (int): Maximum video frame rate.
        scrcpy_server_version (str): Version of the scrcpy server.
        log_level (str): Logging level.
        max_video_width (int): Maximum width of the video.
        video_bitrate (int): The video bitrate (ignored).
        cmdservercommand (list): The command list for starting the scrcpy server.
        screenwidth (int): screen width
        screenheight (int): screen height
    """
    def __init__(
        self,
        device_serial,
        adb_path,
        adb_host_address="127.0.0.1",
        adb_host_port=5037,
        sleep_after_exception=0.05,
        frame_buffer=4,
        lock_video_orientation=0,
        max_frame_rate=0,
        byte_package_size=131072,
        scrcpy_server_version="2.0",
        log_level="info",
        max_video_width=0,
        start_server=True,
        connect_to_device=True,
        *args,
        **kwargs,
    ):

        self.lastframes = deque([], frame_buffer)
        self.loop_finished = True
        if "/" in adb_path or "\\" in adb_path:
            adb_path = os.path.normpath(adb_path)
        self.adb_path = adb_path
        self.device_serial = device_serial
        self.host = adb_host_address
        self.port = adb_host_port
        if start_server:
            mainprocess([adb_path, "start-server"])
        if connect_to_device:
            self.connect_to_device()
        self.folder_here = os.path.normpath(os.path.abspath(os.path.dirname(__file__)))
        self.scrcpy_path = os.path.normpath(
            os.path.join(self.folder_here, "scrcpy-server.jar")
        )
        self.codec = av.CodecContext.create("h264", "r")
        self.getting_screenshot = False
        self.serverstream = None
        self.video_socket = None
        self.pause_capturing = True
        self.stop_capturing = False
        self.byte_size = byte_package_size
        self.sleep_after_exception = sleep_after_exception
        self.all_raw_data264 = []
        self.real_height, self.real_width = 0, 0
        self.adb_host = adbutils.AdbClient(host="127.0.0.1", port=self.port)
        self.device = [
            x for x in self.adb_host.device_list() if x.serial == self.device_serial
        ][0]

        #self.device.sync.push(self.scrcpy_path, r"/data/local/tmp/scrcpy-server.jar")
        self._copy_scrcpy()
        self.lock_video_orientation = lock_video_orientation
        self.max_frame_rate = max_frame_rate
        self.byte_package_size = byte_package_size
        self.scrcpy_server_version = scrcpy_server_version
        self.log_level = log_level
        self.max_video_width = max_video_width
        self.video_bitrate = 8000000  # ignored with raw video
        self.cmdservercommand = [
           # self.adb_path,
           # "-s",
           # self.device_serial,
           # "shell",
            "CLASSPATH=/data/local/tmp/scrcpy-server.jar",
            "app_process",
            "/",
            "com.genymobile.scrcpy.Server",
            str(self.scrcpy_server_version),
            "tunnel_forward=true",
            "control=false",
            "cleanup=true",
            "clipboard_autosync=false",
            f"video_bit_rate={self.video_bitrate}",
            "audio=false",
            f"log_level={self.log_level}",
            f"lock_video_orientation={self.lock_video_orientation}",
            "downsize_on_error=false",
            # "send_device_meta=true",
            # "send_frame_meta=true",
            "send_dummy_byte=true",
            "raw_video_stream=true",
        ]
        self.screenwidth, self.screenheight = 0, 0
        if max_video_width > 0:
            self.cmdservercommand.append(f"max_size={self.max_video_width}")
        else:
            try:
                self.screenwidth, self.screenheight = get_screen_height_width(
                    self.adb_path, self.device_serial
                )
                self.max_video_width = self.screenwidth
                self.cmdservercommand.append(f"max_size={self.max_video_width}")
            except Exception as fe:
                print(fe)

        if max_frame_rate > 0:
            self.cmdservercommand.append(f"max_fps={self.max_frame_rate}")
        self.start_server()
        self._start_capturing()

    def _copy_scrcpy(self):
        adb_push = subprocess.run(
            [
                self.adb_path,
                "-s",
                self.device_serial,
                "push",
                self.scrcpy_path,
                "/data/local/tmp/",
            ],
            capture_output=True,
            cwd=self.folder_here,
            **invisibledict,
        )
        print(adb_push.stdout)

    def __enter__(self):
        self.stop_capturing = False
        self.pause_capturing = False
        while self.real_width == 0 or self.real_height == 0:
            try:
                _x = self.get_one_screenshot(copy_ndarray=False)

                self.real_height, self.real_width, *_ = _x.shape
            except Exception:
                continue
        self.stop_capturing = False
        self.pause_capturing = False
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.quit()

    def __iter__(self):
        self.pause_capturing = False
        self.stop_capturing = False
        return self

    def __next__(self):
        return self._iter_frames()

    def _iter_frames(self):
        try:
            return self.lastframes[-1].copy()
        except Exception:
            return np.array([], dtype=np.uint16)

    def quit(self):
        self.stop_capturing = True
        # self.pause_capturing = True
        while self.t.is_alive() or self.t2.is_alive():
            try:
                if self.t.is_alive:
                    self.t.kill()
            except Exception:
                pass
            try:
                if self.t2.is_alive:
                    self.t2.kill()
            except Exception:
                pass
            # sleep(.01)
        try:
            self.video_socket.close()
        except Exception as fe:
            print(fe)

    def start_server(self):
        self.serverstream = self.device.shell(
            self.cmdservercommand,
            stream=True,
        )
        cont = 0
        while True:
            cont += 1
            print(f"Connecting to server - {cont}", end="\r")

            try:
                self.video_socket = self.device.create_connection(
                    Network.LOCAL_ABSTRACT, "scrcpy"
                )
                self.video_socket.setblocking(False)
                self.video_socket.settimeout(1)
                dummy_byte = self.video_socket.recv(1)
                if len(dummy_byte) > 0:
                    break
            except Exception as fe:
                #print(fe)
                sleep(.1)
                #pass

    def connect_to_device(self):
        pa = subprocess.run(
            [self.adb_path, "connect", self.device_serial],
            capture_output=True,
            **invisibledict,
        )
        print(pa.stdout.decode("utf-8", "ignore"))

    def _start_capturing(self):
        self.t = kthread.KThread(
            target=self.get_all_raw_data, name="get_all_raw_data_thread"
        )
        self.t.start()

        self.t2 = kthread.KThread(target=self._parse_frames, name="parse_frames_thread")
        self.t2.start()

    def get_all_raw_data(self):
        self.pause_capturing = True
        self.stop_capturing = False
        while not self.stop_capturing:
            if not self.pause_capturing:
                try:
                    ra = self.video_socket.recv(self.byte_size)
                    self.all_raw_data264.append(ra)
                except Exception as fe:
                    sleep(self.sleep_after_exception)
                    # print(fe)
                    continue
            else:
                try:
                    ra = self.video_socket.recv(self.byte_size)
                    self.all_raw_data264.append(ra)
                    sleep(0.01)
                    continue
                except Exception as fe:
                    sleep(0.1)
                    continue

    def get_one_screenshot(self, copy_ndarray:bool=False):
        """
          Retrieves a single screenshot from the captured frames.

          Args:
              copy_ndarray (bool, optional): Whether to return a copy of the screenshot ndarray (default: False).

          Returns:
              ndarray: The captured screenshot as a NumPy ndarray.

          Raises:
              None

          Note:
              If `copy_ndarray` is True, a copy of the ndarray is returned to prevent modifications to the original data.
              If `copy_ndarray` is False, the original ndarray is returned, which may be modified externally.

          """
        onescreenshot = []
        try:
            thelastframe = self.lastframes[-1]
        except Exception:
            thelastframe = np.array([], dtype=np.uint16)
        self.lastframes.clear()
        self.getting_screenshot = True
        self.pause_capturing = False
        self.loop_finished = False
        while len(onescreenshot) == 0:
            while not self.loop_finished:
                sleep(0.001)
                continue
            try:
                if not copy_ndarray:
                    onescreenshot = self.lastframes[-1]
                else:
                    onescreenshot = self.lastframes[-1].copy()

            except Exception as ba:
                if len(thelastframe) > 0:
                    self.lastframes.append(thelastframe)
                    onescreenshot = thelastframe
                    break
                else:
                    continue
        self.getting_screenshot = False

        self.pause_capturing = True
        return onescreenshot

    def _parse_frames(self):
        self.pause_capturing = False
        self.stop_capturing = False
        while not self.stop_capturing:
            if self.pause_capturing:
                sleep(0.01)
                continue
            packets = None
            try:
                thistime = len(self.all_raw_data264)
                joinedall = b"".join(self.all_raw_data264[:thistime])
                packets = self.codec.parse(joinedall)
                _ = [self.all_raw_data264.pop(0) for _ in range(thistime)]
            except Exception as fa:
                sleep(self.sleep_after_exception)
            try:
                packlen = len(packets)
                for ini, pack in enumerate(packets):
                    try:
                        frames = self.codec.decode(pack)
                        if self.getting_screenshot:
                            if packlen - ini > 3:
                                continue
                        for frame in frames:
                            new_frame = frame.to_rgb().reformat(
                                width=frame.width, height=frame.height, format="bgr24"
                            )
                            self.lastframes.append(new_frame.to_ndarray())
                    except Exception as fa:
                        continue
                self.loop_finished = True
            except Exception as fe:
                sleep(self.sleep_after_exception)


class AdbShotTCP:
    def __init__(
        self,
        device_serial,
        adb_path,
        ip="127.0.0.1",
        port=5555,
        max_frame_rate=0,
        max_video_width=0,
        scrcpy_server_version="2.0",
        forward_port=None,
        frame_buffer=4,
        byte_package_size=131072,
        sleep_after_exception=0.005,
        log_level="info",
        lock_video_orientation=0,
        start_server=True,
        connect_to_device=True,
        *args,
        **kwargs,
    ):
        r"""Class for capturing screenshots from an Android device over TCP/IP using ADB.

        Args:
            device_serial (str): Serial number or IP address of the target device.
            adb_path (str): Path to the ADB executable.
            ip (str, optional): IP address of the device. Defaults to "127.0.0.1".
            port (int, optional): Port number to connect to the device. Defaults to 5555.
            max_frame_rate (int, optional): Maximum frame rate of the captured screenshots. Defaults to 0 (unlimited).
            max_video_width (int, optional): Maximum width of the captured screenshots. Defaults to 0 (unlimited).
            scrcpy_server_version (str, optional): Version of the scrcpy server to use. Defaults to "2.0".
            forward_port (int, optional): Port number to forward to the scrcpy server. Defaults to None.
            frame_buffer (int, optional): Number of frames to keep in the buffer. Defaults to 4.
            byte_package_size (int, optional): Size of each byte package to receive from the server. Defaults to 131072.
            sleep_after_exception (float, optional): Sleep time after encountering an exception. Defaults to 0.005.
            log_level (str, optional): Log level for the scrcpy server. Defaults to "info".
            lock_video_orientation (int, optional): Orientation of the video to lock. Defaults to 0 (unlocked).
            start_server (bool, optional): Whether to start the scrcpy server. Defaults to True.
            connect_to_device (bool, optional): Whether to connect to the device. Defaults to True.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Raises:
            Exception: If connection to the device fails.

        Methods:
            connect_to_device(): Connects to the Android device using ADB.
            quit(): Stops capturing and closes the connection to the device.
            get_one_screenshot(copy_ndarray=False): Retrieves a single screenshot from the device.
            __enter__(): Context manager entry point.
            __exit__(exc_type, exc_value, traceback): Context manager exit point.
            __iter__(): Returns the iterator object.
            __next__(): Returns the next frame in the iteration.

        """
        if not forward_port:
            forward_port = get_dynamic_ports(qty=1)[0]
        if "/" in adb_path or "\\" in adb_path:
            adb_path = os.path.normpath(adb_path)
        if start_server:
            mainprocess([adb_path, "start-server"])
        self.video_bitrate = 8000000  # ignored
        self.loop_finished = True
        self.getting_screenshot = False
        self.sleep_after_exception = sleep_after_exception
        self.stop_capturing = False
        self.pause_capturing = False
        self.byte_size = byte_package_size
        self.ip = ip
        self.port = port
        self.device_serial = device_serial

        self.adb_path = adb_path
        self.max_frame_rate = max_frame_rate
        self.max_video_width = int(max_video_width)
        self.scrcpy_server_version = scrcpy_server_version
        self.forward_port = forward_port
        self.folder_here = os.path.normpath(os.path.abspath(os.path.dirname(__file__)))
        self.scrcpy_path = os.path.normpath(
            os.path.join(self.folder_here, "scrcpy-server.jar")
        )
        self.all_raw_data264 = []
        self.log_level = log_level
        self.lock_video_orientation = lock_video_orientation
        self.real_width, self.real_height = 0, 0

        if connect_to_device:
            self.connect_to_device()
        self.cmdservercommand = [
            self.adb_path,
            "-s",
            self.device_serial,
            "shell",
            "CLASSPATH=/data/local/tmp/scrcpy-server.jar",
            "app_process",
            "/",
            "com.genymobile.scrcpy.Server",
            self.scrcpy_server_version,
            "tunnel_forward=true",
            "control=false",
            "cleanup=true",
            "clipboard_autosync=false",
            f"video_bit_rate={self.video_bitrate}",
            "audio=false",
            f"log_level={self.log_level}",
            f"lock_video_orientation={self.lock_video_orientation}",
            "downsize_on_error=false",
            # "send_device_meta=true",
            # "send_frame_meta=true",
            "send_dummy_byte=true",
            "raw_video_stream=true",
        ]
        self.screenwidth, self.screenheight = 0, 0
        if max_video_width > 0:
            self.cmdservercommand.append(f"max_size={self.max_video_width}")
        else:
            try:
                self.screenwidth, self.screenheight = get_screen_height_width(
                    self.adb_path, self.device_serial
                )
                self.max_video_width = self.screenwidth
                self.cmdservercommand.append(f"max_size={self.max_video_width}")
            except Exception as fe:
                print(fe)

        if max_frame_rate > 0:
            self.cmdservercommand.append(f"max_fps={self.max_frame_rate}")

        self.video_socket = None
        self.t = None
        self.t2 = None
        self.t3 = None
        self.lastframes = deque([], frame_buffer)
        self.codec = av.codec.CodecContext.create("h264", "r")

        self._copy_scrcpy()
        self._forward_port()

        self.scrcpy_proc = None
        self._start_scrcpy()
        self._connect_to_server()
        self._start_capturing()
        # self.pause_capturing = True

    def __enter__(self):
        self.stop_capturing = False
        self.pause_capturing = False
        while self.real_width == 0 or self.real_height == 0:
            _x = self.get_one_screenshot(copy_ndarray=False)
            try:
                self.real_height, self.real_width, *_ = _x.shape
            except Exception:
                continue
        self.stop_capturing = False
        self.pause_capturing = False
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.quit()

    def __iter__(self):
        self.pause_capturing = False
        self.stop_capturing = False
        return self

    def __next__(self):
        return self._iter_frames()

    def connect_to_device(self):
        pa = subprocess.run(
            [self.adb_path, "connect", self.device_serial],
            capture_output=True,
            **invisibledict,
        )
        print(pa.stdout.decode("utf-8", "ignore"))

    def quit(self):
        self.stop_capturing = True
        while self.t.is_alive() or self.t2.is_alive():
            try:
                if self.t.is_alive:
                    self.t.kill()
            except Exception:
                pass
            try:
                if self.t2.is_alive:
                    self.t2.kill()
            except Exception:
                pass
        self.video_socket.close()

        try:
            self.scrcpy_proc.stdout.close()
        except Exception:
            pass
        try:
            self.scrcpy_proc.stdin.close()
        except Exception:
            pass
        try:
            self.scrcpy_proc.stderr.close()
        except Exception:
            pass
        try:
            self.scrcpy_proc.wait(timeout=2)
        except Exception:
            pass
        try:
            self.scrcpy_proc.kill()
        except Exception:
            pass

        try:
            kill_process_children_parents(
                pid=self.scrcpy_proc.pid, max_parent_exe="adb.exe", dontkill=()
            )
            sleep(2)
        except Exception as fe:
            print(fe)
        try:
            kill_pid(pid=self.scrcpy_proc.pid)
        except Exception as fe:
            print(fe)

    def _copy_scrcpy(self):
        adb_push = subprocess.run(
            [
                self.adb_path,
                "-s",
                self.device_serial,
                "push",
                self.scrcpy_path,
                "/data/local/tmp/",
            ],
            capture_output=True,
            cwd=self.folder_here,
            **invisibledict,
        )
        print("Copying scrcpy-server.jar ... to /data/local/tmp/")
        print(adb_push.stdout.decode("utf-8", "ignore"))

    def _start_scrcpy(self):
        self.scrcpy_proc = subprocess.Popen(
            self.cmdservercommand,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            cwd=self.folder_here,
            **invisibledict,
        )

    def _forward_port(self):
        fw = subprocess.run(
            [
                self.adb_path,
                "-s",
                self.device_serial,
                "forward",
                f"tcp:{self.forward_port}",
                "localabstract:scrcpy",
            ],
            cwd=self.folder_here,
            capture_output=True,
            **invisibledict,
        )
        print(f"Forwarding {self.forward_port} ... localabstract:scrcpy")
        print(fw.stdout.decode("utf-8", "ignore"))

    def _connect_to_server(self):
        dummy_byte = b""
        cont = 0
        while not dummy_byte:
            try:
                cont += 1
                print(f"Connecting to server - {cont}", end="\r")
                if self.stop_capturing:
                    break
                self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.video_socket.connect((self.ip, self.forward_port))

                self.video_socket.setblocking(False)
                self.video_socket.settimeout(1)
                dummy_byte = self.video_socket.recv(1)
                if len(dummy_byte) == 0:
                    try:
                        self.video_socket.close()
                    except Exception:
                        continue
            except Exception as fe:
                print(fe)

        print(f"\n\nConnected to server {self.video_socket}")

    def _start_capturing(self):
        self.t = kthread.KThread(target=self._all_raw_data, name="all_raw_data_thread")
        self.t.start()

        self.t2 = kthread.KThread(target=self._parse_frames, name="parse_frames_thread")
        self.t2.start()
        # sleep(1)
        # self.t3 = kthread.KThread(target=self._get_infos2, name="_get_infos2d")
        # self.t3.start()

    def _get_infos2(self):
        while True:
            try:
                self.real_height, self.real_width, *_ = self.lastframes[-1].shape
                print(self.real_width, self.real_height)
                break
            except Exception as fa:
                sleep(0.1)
                continue

    def get_one_screenshot(self, copy_ndarray=False):
        onescreenshot = []
        try:
            thelastframe = self.lastframes[-1]
        except Exception:
            thelastframe = np.array([], dtype=np.uint16)
        self.lastframes.clear()
        self.getting_screenshot = True
        self.pause_capturing = False
        self.loop_finished = False
        while len(onescreenshot) == 0:
            while not self.loop_finished:
                sleep(0.001)
                continue
            try:
                if not copy_ndarray:
                    onescreenshot = self.lastframes[-1]
                else:
                    onescreenshot = self.lastframes[-1].copy()

            except Exception as ba:
                if len(thelastframe) > 0:
                    self.lastframes.append(thelastframe)
                    onescreenshot = thelastframe
                    break
                else:
                    continue
        self.getting_screenshot = False

        self.pause_capturing = True
        return onescreenshot

    def _iter_frames(self):
        try:
            return self.lastframes[-1].copy()
        except Exception:
            return np.array([], dtype=np.uint16)

    def _all_raw_data(self):
        self.pause_capturing = True
        self.stop_capturing = False
        while not self.stop_capturing:
            if not self.pause_capturing:
                try:
                    ra = self.video_socket.recv(self.byte_size)
                    self.all_raw_data264.append(ra)
                except Exception as fe:
                    sleep(self.sleep_after_exception)
                    # print(fe)
                    continue
            else:
                try:
                    ra = self.video_socket.recv(self.byte_size)
                    self.all_raw_data264.append(ra)
                    sleep(0.01)
                    continue
                except Exception as fe:
                    sleep(0.1)
                    continue

    def _parse_frames(self):
        self.pause_capturing = True
        self.stop_capturing = False
        while not self.stop_capturing:
            if self.pause_capturing:
                sleep(0.01)
                continue
            packets = None
            try:
                thistime = len(self.all_raw_data264)
                joinedall = b"".join(self.all_raw_data264[:thistime])
                packets = self.codec.parse(joinedall)
                _ = [self.all_raw_data264.pop(0) for _ in range(thistime)]
            except Exception as fa:
                sleep(self.sleep_after_exception)
            try:
                packlen = len(packets)
                for ini, pack in enumerate(packets):
                    try:
                        frames = self.codec.decode(pack)
                        if self.getting_screenshot:
                            if packlen - ini > 3:
                                continue
                        for frame in frames:
                            new_frame = frame.to_rgb().reformat(
                                width=frame.width, height=frame.height, format="bgr24"
                            )
                            self.lastframes.append(new_frame.to_ndarray())
                    except Exception as fa:
                        print(fa)
                        continue
                self.loop_finished = True
            except Exception as fe:
                print(fe, end="\r")
                sleep(self.sleep_after_exception)
