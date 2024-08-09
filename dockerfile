FROM nvidia/cuda:12.3.1-runtime-ubuntu22.04

# Set non-interactive mode for APT and the timezone environment variable
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Europe/Zurich

# Install dependencies
RUN apt-get update && apt-get install -y \
    git \
    make build-essential libssl-dev zlib1g-dev \
    libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm \
    libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev git git-lfs  \
    ffmpeg libsm6 libxext6 cmake libgl1-mesa-glx \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && git lfs install

# Create and switch to a new user
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Pyenv and Python setup
RUN curl https://pyenv.run | bash
ENV PATH=$HOME/.pyenv/shims:$HOME/.pyenv/bin:$PATH
ARG PYTHON_VERSION=3.10.12
RUN pyenv install $PYTHON_VERSION && \
    pyenv global $PYTHON_VERSION && \
    pyenv rehash && \
    pip install --no-cache-dir --upgrade pip setuptools wheel 

# Set the working directory
WORKDIR /home/user/opt/ComfyUI

# Clone fixed commit ID of ComfyUI directly into /home/user/opt/ComfyUI
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI . && \
    git fetch origin 887a6341ed14c9904230cf55a0eabe95cd0218d3 && \
    git checkout 887a6341ed14c9904230cf55a0eabe95cd0218d3 && \
    pip install --user --no-cache-dir -r requirements.txt

# Clone ComfyUI-Manager and install its requirements
RUN mkdir -p custom_nodes/ComfyUI-Manager && \
    git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Manager custom_nodes/ComfyUI-Manager && \
    cd custom_nodes/ComfyUI-Manager && \
    git fetch origin 821fec5740291648de10e56c9bda0204eb696ab1 && \
    git checkout 821fec5740291648de10e56c9bda0204eb696ab1 && \
    pip install --user --no-cache-dir -r requirements.txt

# Copy the configuration file
COPY comfyui_config/extra_model_paths.yaml /home/user/config/extra_model_paths.yaml

# Copy the startup script to a different location
COPY startup.sh /home/user/startup.sh
USER root
RUN chmod +x /home/user/startup.sh
RUN chown user:user /home/user/startup.sh
USER user

CMD ["/home/user/startup.sh"]
