#!/usr/bin/env python
# -*- coding: utf-8 -*-


import threading
import time
import socket
import urllib.request
import xmlrpc.client

import PyQt5.QtCore as QtCore
import PyQt5.QtGui as QtGui
import PyQt5.QtWidgets as QtWidgets

import numpy

from mjpeg_stream_client import get_array_from_mjpeg_stream


class RemoteImageGrabber(QtCore.QObject):
    sig_raw_image = QtCore.pyqtSignal('PyQt_PyObject')
    sig_jpg_image = QtCore.pyqtSignal('PyQt_PyObject')

    def __init__(self, single_image_loc, remote_server):
        super().__init__()
        self.server = xmlrpc.client.ServerProxy('http://'+remote_server+':5117/RPC2')
        start = False
        try:
            start = self.server.is_online()
        except socket.error:
            print("Error: Could not connect to "+remote_server+". Can you ping the rpi? Is the sever script running?")
        except:
            print("Error connecting - is the server script running on the rpi?")

        self.single_image = single_image_loc
        self.remote_server = remote_server
        self.stopping = False

    # This method is called after the thread has been started
    def run(self):
        if self.single_image:
            print("new RemoteImageGrabber starting in single_image mode...")
        else:
            #self.fetch_images()
            pass

    def stop(self):
        self.stopping = True

    @QtCore.pyqtSlot()
    def fetch_images(self):
        """ get images from the mjpeg_streamer"""
        mjpeg_available = self.server.activate_stream(True)
        if mjpeg_available:
            print("started mjpeg stream.")
        while not self.stopping:
            if mjpeg_available:
                print("opening url")
                proxies = {}
                opener = urllib.request.URLopener(proxies)
                stream = opener.open('http://'+self.remote_server+':8080/?action=stream')
                byte_array = b''
                # https://stackoverflow.com/questions/21702477/how-to-parse-mjpeg-http-stream-from-ip-camera
                while True:
                    print("attempting to get image from stream in {}".format(threading.current_thread()))
                    image = get_array_from_mjpeg_stream(stream)  # Todo #3
                    if image is not None:
                        print("emit refresh_preview image size {}".format(image.shape))
                        # PyQt does not copy objects - without explicit copy, this crashed when multithreading:
                        self.sig_jpg_image.emit(numpy.copy(image))
                    if self.stopping:
                        stream.close()
                        self.server.deactivate_stream()
                        break
            else:
                while True:
                    start = time.time()
                    jpeg_tuple = self.server.take_single_jpeg()
                    array = numpy.fromstring(str(jpeg_tuple), dtype=numpy.uint8)
                    w = 1024
                    h = 1024
                    image = numpy.multiply(array[:w * h].reshape((h, w)),2, dtype=numpy.uint8)
                    self.sig_jpg_image.emit(image)
                    print(time.time()-start)
                    if self.stopping:
                        break

    def order_single_bayer_image(self, shape=None):
        """Get 16-bit uncompressed image from rpi"""
        if shape is None:
            shape = (1024, 1024)
        print("getting bayer image in {}".format(threading.current_thread()))
        t0 = time.time()
        image_string = self.server.take_single_bayer(*shape).data
        t1 = time.time()
        print("Bayer image transferred in {:.1f} s".format(t1-t0))

        image = numpy.fromstring(image_string, numpy.uint16)
        assert(image.size == shape[0]*shape[1])

        self.sig_raw_image.emit(image.reshape(shape))
        return image.reshape(shape)

    def order_random_image(self, highest, shape):
        """Test 16-bit transmission without needing a camera: get random data from rpi"""
        image_string = self.server.take_random_16bit(highest, shape)
        image = numpy.fromstring(image_string.data, dtype=numpy.uint16)
        return image.reshape(shape)


class ImageGrabberUI(QtWidgets.QWidget):
    """minimal UI to test interoperability of RemoteImageGrabber with Qt"""
    sig_start_stream = QtCore.pyqtSignal()

    def __init__(self, server_address, *__args):
        super().__init__(*__args)

        self.grabber = RemoteImageGrabber(None, server_address)
        self._grabber_thread = QtCore.QThread()
        self.grabber.moveToThread(self._grabber_thread)
        self._grabber_thread.start()

        self.grabber.sig_raw_image.connect(self.display_image)
        self.grabber.sig_jpg_image.connect(self.display_image)

        # UI
        self.layout = QtWidgets.QHBoxLayout()
        self.setLayout(self.layout)
        self.label_for_image = QtWidgets.QLabel()
        self.layout.addWidget(self.label_for_image)
        self.button_bayer = QtWidgets.QPushButton("Bayer image")
        self.layout.addWidget(self.button_bayer)
        self.show()

        self.i = 0

        self.sig_start_stream.connect(self.grabber.fetch_images, QtCore.Qt.QueuedConnection)
        #self.sig_start_stream.emit()  # Does not work; slot is started in main thread.

        timer = QtCore.QTimer(self)
        timer.setInterval(500)
        timer.setSingleShot(True)
        timer.timeout.connect(self.grabber.fetch_images)
        timer.start()

        #self.grabber.order_single_bayer_image((512, 512))

    @QtCore.pyqtSlot('PyQt_PyObject')
    def display_image(self, ndarray):
        h, w = ndarray.shape
        image = QtGui.QImage(ndarray.data, w, h, QtGui.QImage.Format_Grayscale8)
        pixmap = QtGui.QPixmap.fromImage(image)
        print("displaying image in {}".format(threading.current_thread()))
        self.label_for_image.setPixmap(pixmap)



if __name__ == '__main__':
    import sys
    server_address = '10.82.202.30'
    request_shape = (128, 128)
    highest_in_16_bit = 1000

    app = QtWidgets.QApplication(sys.argv)
    gui = ImageGrabberUI(server_address)
    sys.exit(app.exec_())

    Grabber = RemoteImageGrabber(False, server_address)
    # Test with random data
    random_image = Grabber.order_random_image(highest_in_16_bit, request_shape)
    print("Random sata:", random_image.shape, "max:", numpy.max(random_image))

    # Test using Picamera
    cam_image_bayer = Grabber.order_single_bayer_image(request_shape)
    print("Camera image:", cam_image_bayer.shape, "max:", numpy.max(cam_image_bayer))



