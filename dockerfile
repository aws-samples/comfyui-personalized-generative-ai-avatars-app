FROM nvidia/cuda:12.3.1-runtime-ubuntu22.04

# Set non-interactive mode for APT and the timezone environment variable
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Europe/Zurich

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

# Install global Python packages
RUN python3 -m pip install --upgrade \
    xformers!=0.0.18 torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu121
    
RUN python3 -m pip install onnxruntime-gpu

# Clone ComfyUI repository
RUN git clone https://github.com/comfyanonymous/ComfyUI . 

# Copy the configuration file
COPY comfyui_config/extra_model_paths.yaml /app/ComfyUI/extra_model_paths.yaml

# Install requirements
RUN python3 -m pip install -r requirements.txt

# Include the custom nodes

RUN echo "### Install ComfyUI-Manager"
RUN mkdir -p custom_nodes/ComfyUI-Manager && \
    git clone https://github.com/ltdrdata/ComfyUI-Manager custom_nodes/ComfyUI-Manager && \
    cd custom_nodes/ComfyUI-Manager && \
    python3 -m pip install -r requirements.txt

RUN echo "### Install ComfyUI_IPAdapter_plus"
RUN mkdir -p custom_nodes/ComfyUI_IPAdapter_plus && \
    git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus.git custom_nodes/ComfyUI_IPAdapter_plus

RUN echo "### Install comfyui-reactor-node"
RUN mkdir -p custom_nodes/comfyui-reactor-node && \
    git clone https://github.com/Gourieff/comfyui-reactor-node custom_nodes/comfyui-reactor-node && \
    cd custom_nodes/comfyui-reactor-node && \
    python3 -m pip install -r requirements.txt

# Copy the startup script
COPY startup.sh /app/startup.sh
USER root
RUN chmod +x /app/startup.sh && \
    chown user:user /app/startup.sh && \
    chown user:user /app/ComfyUI/extra_model_paths.yaml
USER user

CMD ["/app/startup.sh"]