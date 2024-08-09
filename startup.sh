#!/bin/bash

VENV_PATH="/home/user/opt/ComfyUI/.venv"

echo "START startup.sh"

# check if venv already exists
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating virtual environment..."
    python -m venv $VENV_PATH
fi

# activate venv
source $VENV_PATH/bin/activate

# ensure venv is in PATH
export PATH="$VENV_PATH/bin:$PATH"

# ensure pip is available
if [ ! -f "$VENV_PATH/bin/pip" ]; then
    echo "Installing pip..."
    python -m ensurepip
    ln -s $(which pip3) $VENV_PATH/bin/pip
fi

echo "## Python interpreter used: $(which python)"
echo "## Pip used: $(which pip)"
echo "## Virtual environment: $VIRTUAL_ENV"
echo "## Installed pip libraries:"
# pip list

echo "### check torch startup.sh"
# check if torch is installed, if not pip install the relevant packages
if ! python -c "import torch" &> /dev/null; then
    echo "Installing required Python packages..."
    pip install xformers!=0.0.18 -r /home/user/opt/ComfyUI/requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121
    pip install --upgrade GitPython
    pip install --upgrade torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu121
fi

echo "Check if library onnxruntime-gpu is missing"
# check if torch is installed, if not pip install the relevant packages
if ! python -c "import onnxruntime" &> /dev/null; then
    echo "Installing required Python package onnxruntime-gpu..."
    pip install onnxruntime-gpu
fi

# #####################################################################
# INSTALL CUSTOM NODES, MODELS, LORA FOR PERSONALIZED AVATARS WORKFLOW
# #####################################################################
echo "### check comfyui-manager"
if [ ! -d "/home/user/opt/ComfyUI/custom_nodes/ComfyUI-Manager" ]; then
    echo "custom_node ComfyUI-Manager does not exist. Cloning Repo from https://github.com/ltdrdata/ComfyUI-Manager"
    mkdir -p /home/user/opt/ComfyUI/custom_nodes/ComfyUI-Manager
    git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Manager /home/user/opt/ComfyUI/custom_nodes/ComfyUI-Manager
    cd /home/user/opt/ComfyUI/custom_nodes/ComfyUI-Manager
    git fetch origin 821fec5740291648de10e56c9bda0204eb696ab1
    git checkout 821fec5740291648de10e56c9bda0204eb696ab1
    pip install -r requirements.txt
    cd -
fi

echo "### check ComfyUI_IPAdapter_plus"
if [ ! -d "/home/user/opt/ComfyUI/custom_nodes/ComfyUI_IPAdapter_plus" ]; then
    echo "custom_node ComfyUI_IPAdapter_plus does not exist. Cloning Repo from https://github.com/cubiq/ComfyUI_IPAdapter_plus.git"
    mkdir -p /home/user/opt/ComfyUI/custom_nodes/ComfyUI_IPAdapter_plus
    git clone --depth 1 https://github.com/cubiq/ComfyUI_IPAdapter_plus.git /home/user/opt/ComfyUI/custom_nodes/ComfyUI_IPAdapter_plus
    cd /home/user/opt/ComfyUI/custom_nodes/ComfyUI_IPAdapter_plus
    git fetch origin 7d8adaec730bff243cc3026eed5111695cc5ed4e
    git checkout 7d8adaec730bff243cc3026eed5111695cc5ed4e
    pip install -r requirements.txt
    cd -
fi

echo "### check comfyui-reactor-node"
if [ ! -d "/home/user/opt/ComfyUI/custom_nodes/comfyui-reactor-node" ]; then
    echo "custom_node omfyui-reactor-node does not exist. Cloning Repo from https://github.com/Gourieff/comfyui-reactor-node"
    mkdir -p /home/user/opt/ComfyUI/custom_nodes/comfyui-reactor-node
    git clone --depth 1 https://github.com/Gourieff/comfyui-reactor-node /home/user/opt/ComfyUI/custom_nodes/comfyui-reactor-node
    cd /home/user/opt/ComfyUI/custom_nodes/comfyui-reactor-node
    git fetch origin 4beccb48f4b089f1201692b8d81016bdb850e0ca
    git checkout 4beccb48f4b089f1201692b8d81016bdb850e0ca
    pip install -r requirements.txt
    cd -
fi

echo "### check codeformer.pth"
if [ ! -s "/home/user/opt/ComfyUI/models/facerestore_models/codeformer.pth" ]; then
    echo "Codeformer.pth is missing. Installing it from https://github.com/sczhou/CodeFormer/releases/download/v0.1.0/codeformer.pth"
    mkdir -p /home/user/opt/ComfyUI/models/facerestore_models
    wget -O "/home/user/opt/ComfyUI/models/facerestore_models/codeformer.pth" "https://github.com/sczhou/CodeFormer/releases/download/v0.1.0/codeformer.pth"
else
    echo "File /home/user/opt/ComfyUI/models/facerestore_models/codeformer.pth already exists."
fi

echo "### check dreamshaper-xl.safetensors"
if [ ! -s "/home/user/opt/ComfyUI/models/checkpoints/dreamshaper-XL.safetensors" ]; then
    echo "dreamshaper-XL.safetensors. Installing it from https://civitai.com/api/download/models/354657"
    mkdir -p /home/user/opt/ComfyUI/models/checkpoints
    wget -O "/home/user/opt/ComfyUI/models/checkpoints/dreamshaper-XL.safetensors" "https://civitai.com/api/download/models/354657"
else
    echo "File /home/user/opt/ComfyUI/models/checkpoints/dreamshaper-XL.safetensors already exists."
fi

echo "### check other models"
declare -A files_to_download=(
    ["/home/user/opt/ComfyUI/models/insightface/inswapper_128.onnx"]="https://huggingface.co/ezioruan/inswapper_128.onnx/resolve/main/inswapper_128.onnx"
    ["/home/user/opt/ComfyUI/models/facerestore_models/codeformer.pth"]="https://github.com/sczhou/CodeFormer/releases/download/v0.1.0/codeformer.pth"
    ["/home/user/opt/ComfyUI/models/clip_vision/model.safetensors"]="https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors"
    ["/home/user/opt/ComfyUI/models/clip_vision/model_sdxl.safetensors"]="https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/image_encoder/model.safetensors"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter_sd15.safetensors"]="https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15.safetensors"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter_sd15_light_v11.bin"]="https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15_light_v11.bin"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter-plus_sd15.safetensors"]="https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus_sd15.safetensors"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter-plus-face_sd15.safetensors"]="https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus-face_sd15.safetensors"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter-full-face_sd15.safetensors"]="https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-full-face_sd15.safetensors"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter_sd15_vit-G.safetensors"]="https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15_vit-G.safetensors"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter_sdxl_vit-h.safetensors"]="https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter_sdxl_vit-h.safetensors"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter-plus_sdxl_vit-h.safetensors"]="https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter-plus-face_sdxl_vit-h.safetensors"]="https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter_sdxl.safetensors"]="https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter_sdxl.safetensors"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter-faceid_sd15.bin"]="https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid_sd15.bin"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter-faceid-plusv2_sd15.bin"]="https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sd15.bin"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter-faceid-portrait-v11_sd15.bin"]="https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-portrait-v11_sd15.bin"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter-faceid_sdxl.bin"]="https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid_sdxl.bin"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter-faceid-plusv2_sdxl.bin"]="https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sdxl.bin"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter-faceid-portrait_sdxl.bin"]="https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-portrait_sdxl.bin"
    ["/home/user/opt/ComfyUI/models/ipadapter/ip-adapter-faceid-portrait_sdxl_unnorm.bin"]="https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-portrait_sdxl_unnorm.bin"
    ["/home/user/opt/ComfyUI/models/loras/ip-adapter-faceid_sd15_lora.safetensors"]="https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid_sd15_lora.safetensors"
    ["/home/user/opt/ComfyUI/models/loras/ip-adapter-faceid-plusv2_sd15_lora.safetensors"]="https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sd15_lora.safetensors"
    ["/home/user/opt/ComfyUI/models/loras/ip-adapter-faceid_sdxl_lora.safetensors"]="https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid_sdxl_lora.safetensors"
    ["/home/user/opt/ComfyUI/models/loras/ip-adapter-faceid-plusv2_sdxl_lora.safetensors"]="https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sdxl_lora.safetensors"
    ["/home/user/opt/ComfyUI/models/clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K-sd15.safetensors"]="https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors"
    ["/home/user/opt/ComfyUI/models/clip_vision/CLIP-ViT-bigG-14-laion2B-39B-b160k-sdxl.safetensors"]="https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/image_encoder/model.safetensors"
)

for path in "${!files_to_download[@]}"; do
    url=${files_to_download[$path]}
    if [ ! -s "$path" ]; then
        echo "File $path is missing. Downloading it from $url"
        mkdir -p "$(dirname "$path")"
        if wget -O "$path" "$url"; then
            echo "Downloaded $path successfully."
        else
            echo "Failed to download $path from $url" >&2
        fi
    else
        echo "File $path already exists."
    fi
done

# Start ComfyUI
exec $VENV_PATH/bin/python /home/user/opt/ComfyUI/main.py --listen 0.0.0.0 --port 8181 --output-directory /home/user/opt/ComfyUI/output/