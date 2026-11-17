#!/bin/bash

set -e

# ============================================================
# CONFIGURATION
# ============================================================

VENV="/home/etpl/VISION/test-cell4/venv"

OPENCV_VERSION="4.10.0"

BUILD_DIR="/home/etpl/opencv_build"

OPENCV_DIR="$BUILD_DIR/opencv"

CONTRIB_DIR="$BUILD_DIR/opencv_contrib"

CPU_CORES=$(nproc)


# ============================================================
# HEADER
# ============================================================

echo ""
echo "============================================================"
echo "     OpenCV + GStreamer Installation"
echo "============================================================"
echo ""


# ============================================================
# CHECK VIRTUAL ENVIRONMENT
# ============================================================

if [ ! -f "$VENV/bin/activate" ]; then

    echo "ERROR: Virtual environment not found:"
    echo "$VENV"
    echo ""

    exit 1

fi


# ============================================================
# ACTIVATE VIRTUAL ENVIRONMENT
# ============================================================

echo "Activating virtual environment..."

source "$VENV/bin/activate"

echo ""

echo "Python:"
which python

echo ""

echo "Python version:"
python --version

echo ""

echo "Pip:"
which pip

echo ""


# ============================================================
# VERIFY PYTHON
# ============================================================

PYTHON_VERSION=$(python -c \
'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')

PYTHON_EXECUTABLE="$VENV/bin/python"

PYTHON_SITE_PACKAGES="$VENV/lib/python${PYTHON_VERSION}/site-packages"

PYTHON_INCLUDE_DIR="$VENV/include/python${PYTHON_VERSION}"


echo "============================================================"
echo "Python Configuration"
echo "============================================================"

echo ""
echo "Python executable:"
echo "$PYTHON_EXECUTABLE"

echo ""

echo "Python version:"
echo "$PYTHON_VERSION"

echo ""

echo "Python include:"
echo "$PYTHON_INCLUDE_DIR"

echo ""

echo "Python site-packages:"
echo "$PYTHON_SITE_PACKAGES"

echo ""


# ============================================================
# REMOVE EXISTING OPENCV
# ============================================================

echo "============================================================"
echo "Removing Existing OpenCV From VENV"
echo "============================================================"

pip uninstall -y opencv-python || true

pip uninstall -y opencv-python-headless || true

pip uninstall -y opencv-contrib-python || true

pip uninstall -y opencv-contrib-python-headless || true

echo ""

echo "Existing pip OpenCV packages removed."

echo ""


# ============================================================
# APT UPDATE
# ============================================================

echo "============================================================"
echo "Updating APT"
echo "============================================================"

sudo apt-get update

echo ""


# ============================================================
# INSTALL BUILD DEPENDENCIES
# ============================================================

echo "============================================================"
echo "Installing OpenCV Build Dependencies"
echo "============================================================"

sudo apt-get install -y \
    build-essential \
    cmake \
    git \
    pkg-config \
    wget \
    curl \
    unzip \
    yasm \
    nasm \
    libgtk-3-dev \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libtbb-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libwebp-dev \
    libopenexr-dev \
    libatlas-base-dev \
    gfortran \
    python3-dev \
    python3-numpy

echo ""


# ============================================================
# INSTALL GSTREAMER
# ============================================================

echo "============================================================"
echo "Installing GStreamer"
echo "============================================================"

sudo apt-get install -y \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-x \
    gstreamer1.0-gl \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev

echo ""


# ============================================================
# CHECK GSTREAMER
# ============================================================

echo "============================================================"
echo "Checking GStreamer"
echo "============================================================"

gst-launch-1.0 --version

echo ""


echo "Checking rtspsrc..."

if gst-inspect-1.0 rtspsrc >/dev/null 2>&1; then
    echo "rtspsrc: OK"
else
    echo "rtspsrc: FAILED"
fi


echo ""

echo "Checking rtph264depay..."

if gst-inspect-1.0 rtph264depay >/dev/null 2>&1; then
    echo "rtph264depay: OK"
else
    echo "rtph264depay: FAILED"
fi


echo ""

echo "Checking h264parse..."

if gst-inspect-1.0 h264parse >/dev/null 2>&1; then
    echo "h264parse: OK"
else
    echo "h264parse: FAILED"
fi


# ============================================================
# NVIDIA GSTREAMER CHECK
# ============================================================

echo ""
echo "============================================================"
echo "Checking NVIDIA GStreamer Plugins"
echo "============================================================"

echo ""

echo "Checking nvv4l2decoder..."

if gst-inspect-1.0 nvv4l2decoder >/dev/null 2>&1; then
    echo "nvv4l2decoder: AVAILABLE"
else
    echo "nvv4l2decoder: NOT AVAILABLE"
fi


echo ""

echo "Checking nvvidconv..."

if gst-inspect-1.0 nvvidconv >/dev/null 2>&1; then
    echo "nvvidconv: AVAILABLE"
else
    echo "nvvidconv: NOT AVAILABLE"
fi


# ============================================================
# CREATE BUILD DIRECTORY
# ============================================================

echo ""
echo "============================================================"
echo "Preparing OpenCV Build Directory"
echo "============================================================"

mkdir -p "$BUILD_DIR"

rm -rf "$OPENCV_DIR"

rm -rf "$CONTRIB_DIR"

cd "$BUILD_DIR"


# ============================================================
# DOWNLOAD OPENCV
# ============================================================

echo ""
echo "============================================================"
echo "Downloading OpenCV $OPENCV_VERSION"
echo "============================================================"

wget \
    "https://github.com/opencv/opencv/archive/refs/tags/${OPENCV_VERSION}.zip" \
    -O opencv.zip

unzip -q opencv.zip

mv "opencv-${OPENCV_VERSION}" opencv

rm opencv.zip


# ============================================================
# DOWNLOAD OPENCV CONTRIB
# ============================================================

echo ""
echo "============================================================"
echo "Downloading OpenCV Contrib $OPENCV_VERSION"
echo "============================================================"

wget \
    "https://github.com/opencv/opencv_contrib/archive/refs/tags/${OPENCV_VERSION}.zip" \
    -O opencv_contrib.zip

unzip -q opencv_contrib.zip

mv "opencv_contrib-${OPENCV_VERSION}" opencv_contrib

rm opencv_contrib.zip


# ============================================================
# CREATE BUILD DIRECTORY
# ============================================================

echo ""
echo "============================================================"
echo "Creating OpenCV Build Directory"
echo "============================================================"

cd "$OPENCV_DIR"

mkdir -p build

cd build


# ============================================================
# CMAKE CONFIGURATION
# ============================================================

echo ""
echo "============================================================"
echo "Configuring OpenCV"
echo "============================================================"

echo ""

echo "Using Python:"
echo "$PYTHON_EXECUTABLE"

echo ""

echo "Using site-packages:"
echo "$PYTHON_SITE_PACKAGES"

echo ""


cmake .. \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -DOPENCV_EXTRA_MODULES_PATH="$CONTRIB_DIR/modules" \
    -DWITH_GSTREAMER=ON \
    -DWITH_FFMPEG=ON \
    -DWITH_V4L=ON \
    -DWITH_LIBV4L=ON \
    -DWITH_GTK=ON \
    -DWITH_TBB=ON \
    -DBUILD_opencv_python3=ON \
    -DBUILD_TESTS=OFF \
    -DBUILD_PERF_TESTS=OFF \
    -DBUILD_EXAMPLES=OFF \
    -DBUILD_opencv_apps=OFF \
    -DBUILD_JAVA=OFF \
    -DBUILD_FREETYPE=OFF \
    -DBUILD_OPENEXR=ON \
    -DPYTHON3_EXECUTABLE="$PYTHON_EXECUTABLE" \
    -DPYTHON3_INCLUDE_DIR="$PYTHON_INCLUDE_DIR" \
    -DPYTHON3_PACKAGES_PATH="$PYTHON_SITE_PACKAGES"


# ============================================================
# VERIFY CMAKE CONFIGURATION
# ============================================================

echo ""
echo "============================================================"
echo "Checking CMake Configuration"
echo "============================================================"

echo ""

echo "GStreamer configuration:"

grep -i "GStreamer" CMakeCache.txt || true

echo ""


# ============================================================
# CHECK GSTREAMER
# ============================================================

if grep -q "WITH_GSTREAMER:BOOL=ON" CMakeCache.txt; then

    echo "GStreamer option: ENABLED"

else

    echo "WARNING: GStreamer option was not detected."

fi


# ============================================================
# BUILD OPENCV
# ============================================================

echo ""
echo "============================================================"
echo "Building OpenCV"
echo "============================================================"

echo ""

echo "CPU cores:"
echo "$CPU_CORES"

echo ""

make -j"$CPU_CORES"


# ============================================================
# INSTALL OPENCV SYSTEM LIBRARIES
# ============================================================

echo ""
echo "============================================================"
echo "Installing OpenCV System Libraries"
echo "============================================================"

sudo make install

sudo ldconfig


# ============================================================
# FIND PYTHON CV2
# ============================================================

echo ""
echo "============================================================"
echo "Finding Compiled Python cv2"
echo "============================================================"

CV2_FILE=$(find "$OPENCV_DIR/build" \
    -type f \
    \( \
        -name "cv2*.so" \
        -o -name "cv2.*.so" \
    \) \
    | head -n 1)


if [ -z "$CV2_FILE" ]; then

    echo ""
    echo "ERROR: Compiled cv2 module was not found."
    echo ""

    find "$OPENCV_DIR/build" \
        -type f \
        -name "*.so" \
        | grep cv2 || true

    exit 1

fi


echo ""

echo "Compiled cv2 found:"
echo "$CV2_FILE"


# ============================================================
# INSTALL CV2 INTO VENV
# ============================================================

echo ""
echo "============================================================"
echo "Installing cv2 Into Virtual Environment"
echo "============================================================"

mkdir -p "$PYTHON_SITE_PACKAGES"

cp "$CV2_FILE" "$PYTHON_SITE_PACKAGES/"


echo ""

echo "cv2 installed into:"
echo "$PYTHON_SITE_PACKAGES"


# ============================================================
# TEST OPENCV
# ============================================================

echo ""
echo "============================================================"
echo "Testing Python OpenCV"
echo "============================================================"

python - <<'PY'

import cv2
import sys

print("")
print("Python executable:")
print(sys.executable)

print("")
print("OpenCV version:")
print(cv2.__version__)

print("")
print("GStreamer:")
print("")

info = cv2.getBuildInformation()

for line in info.splitlines():

    if "GStreamer" in line:
        print(line)

print("")
print("OpenCV import: SUCCESS")

PY


# ============================================================
# VERIFY GSTREAMER
# ============================================================

echo ""
echo "============================================================"
echo "FINAL GSTREAMER CHECK"
echo "============================================================"

python -c "import cv2; print(cv2.getBuildInformation())" \
    | grep -i gstreamer


# ============================================================
# VERIFY VIDEOIO BACKENDS
# ============================================================

echo ""
echo "============================================================"
echo "VIDEO BACKEND CHECK"
echo "============================================================"

python - <<'PY'

import cv2

print("Available OpenCV video backends:")

try:

    backends = cv2.videoio_registry.getBackends()

    for backend in backends:
        print(" ", backend)

except Exception as e:

    print("Could not list backends:")
    print(e)

PY


# ============================================================
# NVIDIA GSTREAMER FINAL CHECK
# ============================================================

echo ""
echo "============================================================"
echo "NVIDIA GSTREAMER FINAL CHECK"
echo "============================================================"

echo ""

if gst-inspect-1.0 nvv4l2decoder >/dev/null 2>&1; then

    echo "nvv4l2decoder : AVAILABLE"

else

    echo "nvv4l2decoder : NOT AVAILABLE"

fi


if gst-inspect-1.0 nvvidconv >/dev/null 2>&1; then

    echo "nvvidconv     : AVAILABLE"

else

    echo "nvvidconv     : NOT AVAILABLE"

fi


# ============================================================
# FINAL RESULT
# ============================================================

echo ""
echo "============================================================"
echo "INSTALLATION COMPLETE"
echo "============================================================"

echo ""

echo "Virtual environment:"
echo "$VENV"

echo ""

echo "Python:"
which python

echo ""

echo "OpenCV:"
python -c "import cv2; print(cv2.__version__)"

echo ""

echo "GStreamer support:"
python -c "import cv2; print(cv2.getBuildInformation())" \
    | grep -i gstreamer

echo ""

echo "============================================================"
echo "Expected:"
echo "    GStreamer: YES"
echo "============================================================"

echo ""

echo "For your NVIDIA RTSP pipeline also verify:"
echo ""
echo "    gst-inspect-1.0 nvv4l2decoder"
echo "    gst-inspect-1.0 nvvidconv"
echo ""

echo "============================================================"
