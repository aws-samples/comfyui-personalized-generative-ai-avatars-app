FROM nvidia/cuda:12.3.1-runtime-ubuntu22.04

# Set non-interactive mode for APT and the timezone environment variable
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Europe/Zurich \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

# Install dependencies
RUN apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y \
    python3.10 python3.10-dev python3.10-distutils python3.10-venv python3-pip \
    git \
    build-essential libssl-dev zlib1g-dev \
    libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm \
    libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev \
    libffi-dev liblzma-dev git-lfs \
    ffmpeg libsm6 libxext6 cmake libgl1-mesa-glx \
    libglib2.0-0 libsm6 libxrender1 libxext6 \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    git lfs install

# Ensure 'python3' points to 'python3.10'
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1

# Create and switch to a new user
RUN useradd -m -u 1010 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Set the working directory
WORKDIR /app/ComfyUI

# Upgrade pip and setuptools
RUN python3 -m pip install --upgrade pip setuptools wheel GitPython

# Install PyTorch with CUDA support
RUN python3 -m pip install --upgrade \
    xformers!=0.0.18 torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu121

# Install ONNX Runtime GPU
RUN python3 -m pip install onnxruntime-gpu

# Clone ComfyUI repository
RUN git clone https://github.com/comfyanonymous/ComfyUI .

# Copy the configuration file
COPY comfyui_config/extra_model_paths.yaml /app/ComfyUI/extra_model_paths.yaml

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
    transformers

# Include the custom nodes
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
    python3 -m pip install -r requirements.txt

# Copy the startup script
COPY startup.sh /app/startup.sh

USER root
RUN chmod +x /app/startup.sh && \
    chown user:user /app/startup.sh && \
    chown user:user /app/ComfyUI/extra_model_paths.yaml

USER user
CMD ["/app/startup.sh"]