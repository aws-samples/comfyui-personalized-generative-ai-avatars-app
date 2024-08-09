# 1. SSM into EC2
aws ssm start-session --target "$(aws ec2 describe-instances --filters "Name=tag:Name,Values=ComfyUIStack/ASG" "Name=instance-state-name,Values=running" --query 'Reservations[*].Instances[*].[InstanceId]' --output text)" --region $AWS_DEFAULT_REGION

# 2. SSH into Container
container_id=$(sudo docker container ls --format '{{.ID}} {{.Image}}' | grep 'comfyui:latest$' | awk '{print $1}')
sudo docker exec -it $container_id /bin/bash


# ###############################################
# models, loras, controlnets, etc.
# ###############################################
# SD 1.5 emaonly (Inference)
wget -c https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors?download=true -O ./models/checkpoints/v1-5-pruned-emaonly.safetensors

wget -c https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned.safetensors?download=true -O ./models/checkpoints/v1-5-pruned-fine-tuning.safetensors

# SDXL 1.0
wget -c https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors -P ./models/checkpoints/ 

# SDXL Video
wget -c https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt/resolve/main/svd_xt.safetensors -P ./models/checkpoints/

# SDXL Turbo
wget -c https://huggingface.co/stabilityai/sdxl-turbo/resolve/main/sd_xl_turbo_1.0.safetensors -P ./models/checkpoints/

# Blue Pencil XL
wget -c https://huggingface.co/bluepen5805/blue_pencil-XL/resolve/main/blue_pencil-XL-v2.0.0.safetensors -P ./models/checkpoints/ 
# Redmond V2 Lineart
wget -c https://huggingface.co/artificialguybr/LineAniRedmond-LinearMangaSDXL-V2/resolve/main/LineAniRedmondV2-Lineart-LineAniAF.safetensors -P ./models/checkpoints/ 

# LOGO Style
wget -c https://huggingface.co/artificialguybr/LogoRedmond-LogoLoraForSDXL-V2/resolve/main/LogoRedmondV2-Logo-LogoRedmAF.safetensors -P ./models/checkpoints/ 

# Sticker Style
wget -c https://huggingface.co/artificialguybr/StickersRedmond/resolve/main/StickersRedmond.safetensors -P ./models/checkpoints/ 

# T-shirt style
wget -c https://huggingface.co/artificialguybr/TshirtDesignRedmond-V2/resolve/main/TShirtDesignRedmondV2-Tshirtdesign-TshirtDesignAF.safetensors -P ./models/checkpoints/ 

# Negative Prompt Styles
wget -c https://civitai.com/api/download/models/245812 -P ./models/checkpoints/ 

# VAE
wget -c https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors -P ./models/checkpoints/ 

# Animatediff & custom nodes
wget -c https://huggingface.co/guoyww/animatediff/resolve/main/mm_sdxl_v10_beta.ckpt -P ./models/checkpoints/

# SDVN6-RealXL
wget -c https://civitai.com/api/download/models/134461 -O ./models/checkpoints/SDVN6-RealXL.safetensors

# DreamShaper XL
wget -c https://civitai.com/api/download/models/251662 -O ./models/checkpoints/DreamShaperXL.safetensors 

# FACE SWAP EXAMPLE Upscaler - https://huggingface.co/ai-forever/Real-ESRGAN
wget -c https://huggingface.co/ai-forever/Real-ESRGAN/blob/main/RealESRGAN_x2.pth -P ./models/upscale_models/


# Fantastic Characters
wget -c https://civitai.com/api/download/models/143722 -O ./models/checkpoints/fantastic_characters_sdxl.safetensors


wget -c https://civitai.com/api/download/models/355884 -O ./models/checkpoints/colossus_sdxl.safetensors


wget -c https://civitai.com/api/download/models/159987 -O ./animateDiffMotion_v15.ckpt

wget -c https://huggingface.co/navmesh/SDModels/raw/0eb9a8d60fcbcce7641e426028098441604300ad/artUniverse_v80.safetensors -O ./models/checkpoints/artUniverse_v80.safetensors

wget -c https://huggingface.co/navmesh/SDModels/resolve/0eb9a8d60fcbcce7641e426028098441604300ad/artUniverse_v80.safetensors  -O ./models/checkpoints/artUniverse_v80.safetensors

wget -c https://huggingface.co/teradakokoro/open/resolve/fb97d5a2f5a0736014cef426b1a153517ce34fa6/v2_lora_ZoomIn.ckpt -O ./v2_lora_ZoomIn.ckpt

wget -c https://civitai.com/api/download/models/375981 -O ./models/checkpoints/sdxl-turbo.safetensors

wget -c https://huggingface.co/stabilityai/sdxl-turbo/resolve/main/sd_xl_turbo_1.0.safetensors -O ./models/checkpoints/sd_xl_turbo_1.0.safetensors

wget -c https://huggingface.co/stabilityai/sdxl-turbo/resolve/main/sd_xl_turbo_1.0_fp16.safetensors -O ./models/checkpoints/sd_xl_turbo_1.0_fp16.safetensors

wget -c https://civitai.com/api/download/models/393500  -O ./models/checkpoints/lightning-fusion-XL.safetensors

wget -c https://civitai.com/api/download/models/214296 -O ./models/loras/harrlogos-text-xl.safetensors

wget -c https://civitai.com/api/download/models/351306 -O ./models/checkpoints/dreamshaper-XL.safetensors

wget -c https://civitai.com/api/download/models/357609 -O ./models/checkpoints/juggernaut-XL.safetensors

wget -c https://huggingface.co/wangfuyun/AnimateLCM/resolve/main/AnimateLCM_sd15_t2v.ckpt?download=true -O ./models/animatediff_models/AnimateLCM_sd15_t2v.ckpt

wget -c https://huggingface.co/wangfuyun/AnimateLCM/resolve/main/AnimateLCM_sd15_t2v_lora.safetensors?download=true -O ./models/loras/AnimateLCM_sd15_t2v_lora.safetensors

wget -c https://huggingface.co/monster-labs/control_v1p_sd15_qrcode_monster/resolve/main/control_v1p_sd15_qrcode_monster.safetensors?download=true -O ./models/controlnet/control_v1p_sd15_qrcode_monster.safetensors

wget -c https://civitai.com/api/download/models/252914 -O ./models/checkpoints/dreamshaper-8-sd15-lcm.safetensors

wget -c https://civitai.com/api/download/models/128713 -O ./models/checkpoints/dreamshaper-8-sd15.safetensors

wget -c https://civitai.com/api/download/models/395827 -O ./models/checkpoints/jib-mix-realistic-xl.safetensors

wget -c https://huggingface.co/ByteDance/AnimateDiff-Lightning/resolve/main/animatediff_lightning_8step_comfyui.safetensors?download=true -O ./models/loras/animatediff_lightning_8step_comfyui.safetensors

wget -c https://huggingface.co/ByteDance/AnimateDiff-Lightning/resolve/main/animatediff_lightning_4step_comfyui.safetensors?download=true -O ./models/loras/animatediff_lightning_4step_comfyui.safetensors

wget -c https://huggingface.co/InstantX/InstantID/resolve/main/ControlNetModel/diffusion_pytorch_model.safetensors?download=true -O ./models/controlnet/InstantID_controlnet_diffusion_model.safetensors

wget -c https://huggingface.co/MonsterMMORPG/tools/resolve/main/antelopev2.zip -O ./antelope.zip

wget -c https://huggingface.co/huchenlei/ipadapter_pulid/resolve/main/ip-adapter_pulid_sdxl_fp16.safetensors?download=true -O ./models/pulid/ip-adapter_pulid_sdxl_fp16.safetensors

wget -c https://civitai.com/api/download/models/361593 -O ./models/checkpoints/realistic-vision-xl-4-lightning.safetensors


wget -c https://civitai.com/api/download/models/344398 -O ./models/checkpoints/photon_lcm.safetensors

wget -c https://civitai.com/api/download/models/350715 -O ./custom_nodes/ComfyUI-AnimateDiff-Evolved/motion_lora/pxlpshr_shatter_400.safetensors




# Juggernaut XL Hyper
# Res: 832*1216 (Any SDXL Res will work fine)

# Sampler: DPM++ SDE Karras

# Steps: 4-6

# CFG: 1-2 (recommend 2 for a bit negative prompt affection)
# Negative: Only working slightly on CFG 2

# HiRes: 4xNMKD-Siax_200k with 3 Steps and 0.35 Denoise + 1.5 Upscale
wget -c https://civitai.com/api/download/models/471120 -O ./models/checkpoints/juggernaut-xl-hyper.safetensors

# DPM SDE++ Karras / 4-6+ Steps$
# CFG scale 1.5-2
wget -c https://civitai.com/api/download/models/245598 -O ./models/checkpoints/realistic-vision-v60-sd15.safetensors

wget -c https://huggingface.co/DIAMONIK7777/antelopev2/resolve/main/1k3d68.onnx?download=true -O ./1k3d68.onnx
wget -c https://huggingface.co/DIAMONIK7777/antelopev2/resolve/main/2d106det.onnx?download=true -O ./2d106det.onnx
wget -c https://huggingface.co/DIAMONIK7777/antelopev2/resolve/main/genderage.onnx?download=true -O ./genderage.onnx
wget -c https://huggingface.co/DIAMONIK7777/antelopev2/resolve/main/glintr100.onnx?download=true -O ./glintr100.onnx
wget -c https://huggingface.co/DIAMONIK7777/antelopev2/resolve/main/scrfd_10g_bnkps.onnx?download=true -O ./scrfd_10g_bnkps.onnx

# LahMysterious_SDXL_Lightning.safetensors - CFG 1.0 / 4-8 steps / euler & SGM_Uniform
wget -c https://civitai.com/api/download/models/387984 -O ./models/checkpoints/mysterious_sdxl_lightning.safetensors


# #################################
# some handy commands
# ################################

# sudo yum install -y awscli
# sudo su
# cd /var/lib/docker/plugins/<id>/propagated-mounts/volumes/ComfyUIVolume/data

# copy complete S3 path to current dir
aws s3 cp s3://<your-bucket>/<your-prefix> . --recursive

# copy single file
aws s3 cp s3://<your-bucket>/Juggernaut_X_RunDiffusion_Hyper.safetensors /models/checkpoints/Juggernaut_X_RunDiffusion_Hyper.safetensors

# copy all .safetensors files from data dir
aws s3 cp data s3://<your-bucket>/ --recursive --exclude "*" --include "*.safetensors"

# delete all .jpeg files
find . -type f -name "*.jpeg" -delete

# yum install ImageMagick
# convert jpg to png
for file in *.jpg; do convert "$file" "${file%.jpg}.png"; done

# convert jpeg to png
for file in *.jpeg; do convert "$file" "${file%.jpg}.png"; done

# helper scripts
for file in *.txt; do
    sed -i "s/\./,/g; s/'//g" "$file"    # Replace . with , and remove '.
    sed -i '1s/^/lora_triggerword_sdxl, /' "$file"         # Add 'XYZ, ' to the beginning of the file.
done
