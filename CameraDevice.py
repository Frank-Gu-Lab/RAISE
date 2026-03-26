# Camera Class
from PIL import Image, ImageTk
from time import sleep
from threading import Lock, Thread
from typing import Generator
import numpy as np
import tkinter as tk
import cv2

class ImageCaptureError(Exception):
    """
    Error caused by failure to read data from camera device.
    """
    pass

class CameraDevice():
    """
    A class for representing a camera device that can read RGB image data.
    """

    num_devices: int = 0
    def __init__(self, cam_idx: int = 0, name: str = None) -> None:
        # Increase the device counter
        # Useful if instantiating multiple cameras
        CameraDevice.num_devices += 1
        if name is None:
            self.name = f'Camera {CameraDevice.num_devices}'
        else:
            self.name = name
        
        self.camera = None

        # Attempt to open the camera device
        try:
            self.open(cam_idx)
        except:
            SystemExit(1)
        
        # Instantiate a multi-threading lock to prevent race condition while reading image data
        self.lock = Lock()

        # Instantiate generator that produces image frames
        self.feed = self.get_feed()

        # Confirm that the camera device opened properly by setting 
        # the frame height, frame width, and capture speed
        if self.camera is not None:
            self.fps = self.camera.get(cv2.CAP_PROP_FPS)
            self.width = self.camera.get(cv2.CAP_PROP_FRAME_WIDTH)
            self.height = self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT)
        
        # Create a separate thread for viewing a live feed preview in a separate window
        self.live_feed_thread = Thread(target=self.live_feed_wrapper, daemon=True)
    
    def open(self, cam_idx):
        super().open()
        # Instantiate a camera attribute with a VideoCapture object
        self.camera = cv2.VideoCapture(cam_idx)
        self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT, 1200)
        self.camera.get(cv2.CAP_PROP_FRAME_WIDTH, 1600)
        self.device_id = CameraDevice.num_devices

        # Open the VideoCapture object if it is not already open
        if not self.camera.isOpened():
            if not self.camera.open(cam_idx):
                raise IOError(f'Failed to Connect with Camera #{cam_idx}')
    
    def __repr__(self) -> str:
        return f'Capture Device {self.device_id}'

    def get_width(self) -> int:
        """
        Returns the width of the capture frame
        """
        return int(self.width)

    def get_height(self) -> int:
        """
        Returns the height of the capture frame
        """
        return int(self.height)
    
    def get_fps(self) -> int:
        """
        Returns the capture speed of the camera device
        """
        return int(self.fps)

    def get_name(self) -> str:
        """
        Returns the name of the camera device
        """
        return self.name
    
    def get_feed(self) -> Generator[np.ndarray, None, None]:
        """
        A generator for producing image frames
        """
        while True:
            ret, frame = self.camera.read()
            if not ret:
                return None
            yield frame

    def live_feed_wrapper(self):
        try:
            self.live_feed()
        except Exception as e:
            print(f'Exception in live_feed thread {e}, terminating live feed')
            self.destroy_preview()
    
    def live_feed(self):
        cv2.namedWindow(self.name, cv2.WINDOW_AUTOSIZE)
        while True:
            self.lock.acquire()

            try:
                img: np.ndarray = next(self.feed)
            except:
                self.lock.release()
                break
            img = cv2.resize(src=img, dsize=(640, 480), interpolation=cv2.INTER_LINEAR)
            cv2.imshow(self.name, img)

            key = cv2.waitKey(1)
            if key == ord('\u001b'): # Release camera live-feed after pressing ECS key
                self.lock.release()
                self.close()
                break

            self.lock.release()
    
    def start_preview(self):
        self.live_feed_thread.start()
    
    def stop_preview(self):
        self.live_feed_thread.join()

    def destroy_preview(self):
        cv2.destroyWindow(self.name)
        print('Preview window closed')

    def read(self, fname: str | None = None, nt: int = 64):
        if nt < 1:
            raise ValueError
        
        self.lock.acquire()

        img_array: np.ndarray = np.ndarray((nt, self.get_height(), self.get_width(), 3), dtype=np.uint8)
        for i in range(nt):
            try:
                img_array[i] = next(self.feed)
            except:
                return
        
        img_avg: np.ndarray = np.ndarray((self.get_height(), self.get_width(), 3), dtype=np.uint8)
        img_avg[: ,: , 0] = np.mean(img_array[:, :, :, 0], axis=0)
        img_avg[: ,: , 1] = np.mean(img_array[:, :, :, 1], axis=0)
        img_avg[: ,: , 2] = np.mean(img_array[:, :, :, 2], axis=0)
        assert img_array.dtype == 'uint8'

        if fname is not None:
            img_avg_resized = cv2.resize(src=img_avg, dsize=(640, 480), interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(fname, img_avg_resized)

        self.lock.release()

        return img_avg


    def close(self):
        self.camera.release()
        cv2.destroyWindow(self.name)

class Camera:
    def __init__(self, cam_idx: int = 0, name: str = None) -> None:
        self.lock = Lock()
        self.camera = CameraDevice(cam_idx, name)
        self.camera_feed = self.camera.camera_feed()
        #self.preview = Thread(target=self.launch_preview, name=self.get_camera_name(), daemon=True)
        #self.preview.start()
    
    def get_camera_name(self) -> str:
        return self.camera.get_name()

    def get_camera_width(self) -> int:
        return self.camera.get_width()
    
    def get_camera_height(self) -> int:
        return self.camera.get_height()
    
    def launch_preview(self) -> None:
        def update(root: tk.Tk, display: tk.Label) -> None:
            self.lock.acquire()

            try:
                frame = next(self.camera_feed)
            except StopIteration:
                return
            img = ImageTk.PhotoImage(Image.fromarray(frame))
            display.image = img
            display.config(image=img)
            self.lock.release()

            root.after(30, update, root, display)

        root = tk.Tk()
        root.title(self.get_camera_name())
        img = ImageTk.PhotoImage(Image.fromarray(np.zeros((self.get_camera_height(), self.get_camera_width(), 3), dtype=np.uint8)))
        display = tk.Label(root, image=img)
        display.config(image=img)
        display.pack()

        root.bind('<Escape>', lambda e: root.quit())
        
        update(root, display)

        root.mainloop()

    def capture_image(self, fname: str = '') -> None | np.ndarray:
        self.lock.acquire()
        frame = next(self.camera_feed)
        self.lock.release()

        if frame is not None:
            img = Image.fromarray(frame)
            if fname == '':
                return img
            img.save(fname)
            print(f'Saved Image: {fname}')
    
    def close(self) -> None:
        self.camera.close()
        del(self.camera_feed)


if __name__ == '__main__':
    cam = CameraDevice()

    cam.start_preview()
    try:
        while True:
            pass
    except:
        pass
    finally:
        cam.stop_preview()
