FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace

# Install system dependencies and uv
RUN apt-get update && apt-get install -y \
    git \
    wget \
    curl \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

# Add uv to PATH
ENV PATH="/root/.local/bin:$PATH"

# Clone ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /workspace/ComfyUI

WORKDIR /workspace/ComfyUI

# Install ComfyUI requirements with uv
RUN uv pip install --system -r requirements.txt

# Install custom nodes
WORKDIR /workspace/ComfyUI/custom_nodes

# ComfyUI-GGUF (for GGUF model loading)
RUN git clone https://github.com/city96/ComfyUI-GGUF.git && \
    cd ComfyUI-GGUF && uv pip install --system -r requirements.txt

# ComfyUI-WanStartEndFramesNative (for start/end frame conditioning)
# Using LunarECL's fix branch for clear_cache bug fix
RUN git clone -b fix/clear_cache-problem https://github.com/LunarECL/ComfyUI-WanStartEndFramesNative.git

# ComfyUI-Impact-Pack
RUN git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git && \
    cd ComfyUI-Impact-Pack && uv pip install --system -r requirements.txt || true

# comfyui_essentials
RUN git clone https://github.com/cubiq/ComfyUI_essentials.git && \
    cd ComfyUI_essentials && uv pip install --system -r requirements.txt || true

# ComfyUI-Custom-Scripts (for MathExpression)
RUN git clone https://github.com/pythongosssss/ComfyUI-Custom-Scripts.git

# rgthree-comfy (for Power Lora Loader)
RUN git clone https://github.com/rgthree/rgthree-comfy.git && \
    cd rgthree-comfy && uv pip install --system -r requirements.txt || true

# ComfyUI-VideoHelperSuite (for video output)
RUN git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    cd ComfyUI-VideoHelperSuite && uv pip install --system -r requirements.txt || true

# Install additional Python dependencies
RUN uv pip install --system \
    runpod \
    requests \
    pillow \
    websocket-client

# Download models
WORKDIR /workspace/ComfyUI/models

# GGUF Model (WAN 2.1 I2V 14B Q3_K_S - smallest for 24GB VRAM)
RUN mkdir -p unet && \
    wget -O unet/wan2.1-i2v-14b-480p-Q3_K_S.gguf \
    "https://huggingface.co/city96/Wan2.1-I2V-14B-480P-gguf/resolve/main/wan2.1-i2v-14b-480p-Q3_K_S.gguf"

# Text Encoder
RUN mkdir -p text_encoders && \
    wget -O text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors \
    "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"

# VAE
RUN mkdir -p vae && \
    wget -O vae/wan_2.1_vae.safetensors \
    "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors"

# CLIP Vision
RUN mkdir -p clip_vision && \
    wget -O clip_vision/clip_vision_h.safetensors \
    "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors"

# LoRAs
RUN mkdir -p loras/WAN2.1

# Style LoRA (birdman animation style)
RUN wget -O loras/WAN2.1/birdmanstyleanimationwanlora.safetensors \
    "https://civitai.com/api/download/models/1623701?type=Model&format=SafeTensor"

# Speed LoRA (LightX2V distillation - 4 steps instead of 20)
RUN wget -O loras/Wan21_T2V_14B_lightx2v_cfg_step_distill_lora_rank32.safetensors \
    "https://civitai.com/api/download/models/1909719?type=Model&format=SafeTensor"

WORKDIR /workspace

# Copy handler and workflow (at the end for faster rebuilds)
COPY src/handler.py /workspace/handler.py
COPY src/workflow_api.json /workspace/workflow_api.json

# Set up entry point
CMD ["python", "-u", "/workspace/handler.py"]
