# Bundled face detector

`haarcascade_frontalface_default.xml` is OpenCV's published pretrained Haar face detector, retained with its embedded license comments.

Official source (tag 4.13.0): https://github.com/opencv/opencv/blob/4.13.0/data/haarcascades/haarcascade_frontalface_default.xml

Bundling this file avoids depending on whether a particular Python OpenCV wheel includes its optional `cv2/data` files. This detector locates a face; the attendance app trains a separate LBPH recognizer from consented student crops.
