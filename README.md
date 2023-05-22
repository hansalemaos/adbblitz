# ADB - Fastest screenshots - scrcpy raw stream directly to NumPy (without scrcpy.exe) - no root required!


### Tested against Windows 10 / Python 3.10 / Anaconda

### pip install adbblitz


### [with Google Pixel 6 - not rooted](https://github.com/hansalemaos/adbblitz/raw/main/google_pixel_6_2400x1080-no-root.mp4)


### [with Bluestacks 5 - not rooted ](https://github.com/hansalemaos/adbblitz/raw/main/adb_screenshot_test.mp4)



### TCP - Taking multiple screenshots 

If you want to take multiple screenshots using a TCP connection, you can use AdbShotTCP

Import the modules 

```python
from adbblitz import AdbShotUSB, AdbShotTCP
```

Use the with statement to create an instance of the AdbShotTCP class and specify the required parameters

Within the with block, you can iterate over the shosho object to capture screenshots
After everything is done, the socket connection will be closed, you don't have to take care about anything.


```python
from adbblitz import AdbShotUSB, AdbShotTCP
import numpy as np
from time import time
import cv2


with AdbShotTCP(
    device_serial="localhost:5555",
    adb_path=r"C:\ProgramData\chocolatey\lib\scrcpy\tools\scrcpy-win64-v2.0\adb.exe",
    ip="127.0.0.1",
    port=5555,
    max_frame_rate=60,
    max_video_width=960,
    scrcpy_server_version="2.0",
    forward_port=None,
    frame_buffer=24,
    byte_package_size=131072,
    sleep_after_exception=0.01,
    log_level="info",
    lock_video_orientation=0,
) as shosho:
framecounter = 0
stop_at_frame = None
fps = 0
start_time = time()
show_screenshot = True
# print(shosho)
for bi in shosho:
    if bi.dtype == np.uint16:
        continue
    cv2.imshow("title", bi)
    if cv2.waitKey(25) & 0xFF == ord("q"):
        # cv2.destroyAllWindows()
        # shosho.quit()
        break
    fps += 1
print(f"fast_ctypes_screenshots: {fps / (time() - start_time)}")
```


### TCP - Taking one screenshot at the time 

If you take only one screenshot, the connection will stay open until you call AdbShotTCP.quit()

```python
a = AdbShotTCP(
	device_serial="localhost:5555",
	adb_path=r"C:\ProgramData\chocolatey\lib\scrcpy\tools\scrcpy-win64-v2.0\adb.exe",
	ip="127.0.0.1",
	port=5037,
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
)

scr = a.get_one_screenshot()
scr.quit() # closes the connection
	
```

### USB - Taking multiple screenshots 

Same thing for USB 


```python

with AdbShotUSB(
    device_serial="xxxxx",
    adb_path=r"C:\ProgramData\chocolatey\lib\scrcpy\tools\scrcpy-win64-v2.0\adb.exe",
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
) as self:
    start_time, fps = time(), 0
    for bi in self:
        if bi.dtype == np.uint16:
            continue
        cv2.imshow("test", bi)
        fps += 1
        if cv2.waitKey(25) & 0xFF == ord("q"):
            cv2.destroyAllWindows()
            break
    print(f"FPS: {fps / (time() - start_time)}")
    cv2.destroyAllWindows()
```

### USB - Taking one screenshot at the time 
```python

su=AdbShotUSB(
            device_serial="xxxxxx",
            adb_path=r"C:\ProgramData\chocolatey\lib\scrcpy\tools\scrcpy-win64-v2.0\adb.exe",
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
        )
scr=su.get_one_screenshot()
scr.quit() # closes the connection

```
```

```





