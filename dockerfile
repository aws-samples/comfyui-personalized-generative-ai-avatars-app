# Stage 1: Builder stage with all build dependencies
FROM nvidia/cuda:12.6.0-runtime-ubuntu24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Europe/Zurich \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1

# Install build dependencies and security updates
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y \
    python3 python3-dev python3-venv python3-pip \
    git \
    build-essential libssl-dev zlib1g-dev \
    libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm \
    libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev \
    libffi-dev liblzma-dev \
    cmake && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    # Install git-lfs from official GitHub release (patched version)
    curl -L https://github.com/git-lfs/git-lfs/releases/download/v3.7.1/git-lfs-linux-amd64-v3.7.1.tar.gz -o /tmp/git-lfs.tar.gz && \
    tar -xzf /tmp/git-lfs.tar.gz -C /tmp && \
    /tmp/git-lfs-3.7.1/install.sh && \
    rm -rf /tmp/git-lfs* && \
    git lfs install

# Create user for building
RUN useradd -m -u 1010 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PIP_BREAK_SYSTEM_PACKAGES=1

WORKDIR /app/ComfyUI

# Upgrade pip and setuptools
RUN python3 -m pip install --upgrade pip setuptools wheel GitPython

# Install PyTorch with CUDA support
RUN python3 -m pip install --upgrade \
    xformers!=0.0.18 torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu121

# Install ONNX Runtime GPU
RUN python3 -m pip install onnxruntime-gpu

# Clone ComfyUI repository (keeping .git)
RUN git clone https://github.com/comfyanonymous/ComfyUI .

# Install ComfyUI requirements
RUN python3 -m pip install -r requirements.txt

# Install custom requirements
RUN python3 -m pip install \
    aliyun-python-sdk-core-v3==2.13.10 \
    opencv-python \
    tensorflow[gpu] \
    onnx \
    modelscope \
    scikit-image \
    matplotlib \
    insightface \
    diffusers==0.18.2 \
    sentencepiece \
    python-slugify==8.0.1 \
    timm \
    controlnet_aux==0.0.6 \
    mmdet==2.26.0 \
    mediapipe \
    transformers \
    tf-keras

# Install custom nodes
RUN echo "### Install ComfyUI-Manager" && \
    mkdir -p custom_nodes/ComfyUI-Manager && \
    git clone https://github.com/ltdrdata/ComfyUI-Manager custom_nodes/ComfyUI-Manager && \
    cd custom_nodes/ComfyUI-Manager && \
    python3 -m pip install -r requirements.txt

RUN echo "### Install ComfyUI_IPAdapter_plus" && \
    mkdir -p custom_nodes/ComfyUI_IPAdapter_plus && \
    git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus.git custom_nodes/ComfyUI_IPAdapter_plus
    
RUN echo "### Install ComfyUI-ReActor Node" && \
    mkdir -p custom_nodes/ComfyUI-ReActor && \
    git clone https://github.com/Gourieff/ComfyUI-ReActor.git custom_nodes/ComfyUI-ReActor && \
    cd custom_nodes/ComfyUI-ReActor && \
    python3 -m pip install -r requirements.txt && \
    echo "import tensorflow" | cat - __init__.py > temp && mv temp __init__.py

# Stage 2: Runtime stage with minimal dependencies
FROM nvidia/cuda:12.6.0-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Europe/Zurich \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

# Install runtime dependencies WITHOUT vulnerable ffmpeg/cjson packages
# FFmpeg will be built from source to avoid CVE-2024-35368, CVE-2024-35367, CVE-2024-35366, CVE-2023-49528
# cJSON excluded to avoid CVE-2025-57052
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    python3 python3-venv \
    git \
    curl wget ca-certificates \
    libsm6 libxext6 libgl1 \
    libglib2.0-0 libxrender1 \
    libgomp1 \
    libgfortran5 \
    # FFmpeg build dependencies (temporary)
    build-essential \
    nasm yasm \
    libx264-dev libx265-dev \
    libvpx-dev libfdk-aac-dev \
    libmp3lame-dev libopus-dev \
    libass-dev libfreetype6-dev \
    pkg-config && \
    # Install git-lfs from official GitHub release (patched version)
    curl -L https://github.com/git-lfs/git-lfs/releases/download/v3.7.1/git-lfs-linux-amd64-v3.7.1.tar.gz -o /tmp/git-lfs.tar.gz && \
    tar -xzf /tmp/git-lfs.tar.gz -C /tmp && \
    /tmp/git-lfs-3.7.1/install.sh && \
    rm -rf /tmp/git-lfs* && \
    git lfs install && \
    # Build FFmpeg 7.1 from source (patched version)
    cd /tmp && \
    wget -q https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz && \
    tar xf ffmpeg-7.1.tar.xz && \
    cd ffmpeg-7.1 && \
    ./configure \
        --prefix=/usr/local \
        --enable-gpl \
        --enable-nonfree \
        --enable-libx264 \
        --enable-libx265 \
        --enable-libvpx \
        --enable-libfdk-aac \
        --enable-libmp3lame \
        --enable-libopus \
        --enable-libass \
        --enable-libfreetype \
        --disable-doc \
        --disable-debug \
        --disable-static \
        --enable-shared && \
    make -j$(nproc) && \
    make install && \
    ldconfig && \
    # Cleanup build dependencies to reduce image size (keep curl, wget, ca-certificates)
    cd / && rm -rf /tmp/ffmpeg* && \
    apt-get purge -y build-essential nasm yasm \
        libx264-dev libx265-dev libvpx-dev libfdk-aac-dev \
        libmp3lame-dev libopus-dev libass-dev libfreetype6-dev pkg-config && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Create and switch to user
RUN useradd -m -u 1010 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR /app/ComfyUI

# Copy Python packages from builder
COPY --from=builder --chown=user:user /home/user/.local /home/user/.local

# Copy ComfyUI installation from builder (including .git directories)
COPY --from=builder --chown=user:user /app/ComfyUI /app/ComfyUI

# Copy the configuration file
COPY --chown=user:user comfyui_config/extra_model_paths.yaml /app/ComfyUI/extra_model_paths.yaml

# Copy the startup script
COPY startup.sh /app/startup.sh

USER root
RUN chmod +x /app/startup.sh && \
    chown user:user /app/startup.sh

USER user
CMD ["/app/startup.sh"]