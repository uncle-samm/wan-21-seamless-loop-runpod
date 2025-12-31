"""
RunPod Serverless Handler for WAN 2.1 Seamless Loop Animation Generation
"""

import base64
import json
import os
import random
import subprocess
import sys
import threading
import time
import uuid
from io import BytesIO

import requests
import runpod

# Configuration
COMFYUI_PATH = "/workspace/ComfyUI"
WORKFLOW_PATH = "/workspace/workflow_api.json"
COMFYUI_PORT = 8188
INPUT_DIR = os.path.join(COMFYUI_PATH, "input")
OUTPUT_DIR = os.path.join(COMFYUI_PATH, "output")


def start_comfyui():
    """Start ComfyUI server in the background."""
    print("Starting ComfyUI server...")
    process = subprocess.Popen(
        [
            sys.executable,
            "main.py",
            "--listen",
            "127.0.0.1",
            "--port",
            str(COMFYUI_PORT),
        ],
        cwd=COMFYUI_PATH,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Wait for server to be ready
    max_wait = 120  # seconds
    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(
                f"http://127.0.0.1:{COMFYUI_PORT}/system_stats", timeout=2
            )
            if response.status_code == 200:
                print("ComfyUI server is ready!")
                return process
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)

    raise RuntimeError("ComfyUI server failed to start within timeout")


def save_input_image(image_data: str, filename: str) -> str:
    """Save base64 or URL image to ComfyUI input directory."""
    os.makedirs(INPUT_DIR, exist_ok=True)
    filepath = os.path.join(INPUT_DIR, filename)

    if image_data.startswith("http://") or image_data.startswith("https://"):
        # Download from URL
        response = requests.get(image_data)
        response.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(response.content)
    else:
        # Decode base64
        # Remove data URL prefix if present
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]
        image_bytes = base64.b64decode(image_data)
        with open(filepath, "wb") as f:
            f.write(image_bytes)

    return filename


def load_workflow() -> dict:
    """Load the workflow template."""
    with open(WORKFLOW_PATH, "r") as f:
        return json.load(f)


def modify_workflow(workflow: dict, params: dict) -> dict:
    """Modify workflow with input parameters."""
    # Set input image (same for both start and end frame for seamless loop)
    image_filename = params.get("image_filename", "input.png")
    workflow["52"]["inputs"]["image"] = image_filename
    workflow["102"]["inputs"]["image"] = image_filename

    # Set prompt
    prompt = params.get("prompt", "")
    workflow["6"]["inputs"]["text"] = prompt

    # Set seed
    seed = params.get("seed", random.randint(0, 2**32 - 1))
    workflow["3"]["inputs"]["seed"] = seed

    # Set frame count (default 21, will output 20 after removing last frame)
    frame_count = params.get("frame_count", 21)
    workflow["59"]["inputs"]["length"] = frame_count
    workflow["69"]["inputs"]["length"] = frame_count - 1  # Remove last frame for loop

    # Set temporal size for VAE decode (frame_count + 7)
    workflow["61"]["inputs"]["temporal_size"] = frame_count + 7

    # Set FPS
    fps = params.get("fps", 12)
    workflow["126"]["inputs"]["fps"] = fps

    # Set unique filename prefix to avoid conflicts
    workflow["126"]["inputs"]["filename_prefix"] = (
        f"seamless_loop_{uuid.uuid4().hex[:8]}"
    )

    return workflow


def queue_prompt(workflow: dict) -> str:
    """Queue a prompt to ComfyUI and return the prompt ID."""
    payload = {"prompt": workflow}
    response = requests.post(f"http://127.0.0.1:{COMFYUI_PORT}/prompt", json=payload)
    result = response.json()

    # Check for errors in the response
    if "error" in result:
        print(f"ComfyUI error: {result['error']}")
        if "node_errors" in result:
            print(f"Node errors: {json.dumps(result['node_errors'], indent=2)}")
        raise RuntimeError(f"ComfyUI rejected prompt: {result['error']}")

    if "prompt_id" not in result:
        print(f"Unexpected response: {result}")
        raise RuntimeError(f"No prompt_id in response: {result}")

    return result["prompt_id"]


def wait_for_completion(prompt_id: str, timeout: int = 600) -> dict:
    """Wait for the prompt to complete and return history."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = requests.get(
                f"http://127.0.0.1:{COMFYUI_PORT}/history/{prompt_id}"
            )
            if response.status_code == 200:
                history = response.json()
                if prompt_id in history:
                    return history[prompt_id]
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)

    raise TimeoutError(f"Prompt {prompt_id} did not complete within {timeout} seconds")


def get_output_file(history: dict) -> str:
    """Extract the output file path from history."""
    print(f"History keys: {history.keys()}")
    print(f"Full history: {json.dumps(history, indent=2, default=str)}")

    # Check for execution errors
    if "status" in history:
        status = history["status"]
        if status.get("status_str") == "error":
            error_msg = status.get("messages", [])
            print(f"Execution error: {error_msg}")
            raise RuntimeError(f"ComfyUI execution failed: {error_msg}")

    outputs = history.get("outputs", {})
    print(f"Outputs: {outputs}")

    # Look for SaveAnimatedWEBP output (node 126) - can be in "gifs" or "images"
    for node_id, node_output in outputs.items():
        print(
            f"Node {node_id} output keys: {node_output.keys() if isinstance(node_output, dict) else node_output}"
        )
        # Try "gifs" first (animated output)
        if "gifs" in node_output:
            for gif_info in node_output["gifs"]:
                filename = gif_info.get("filename")
                subfolder = gif_info.get("subfolder", "")
                if filename:
                    return os.path.join(OUTPUT_DIR, subfolder, filename)
        # Try "images" as fallback
        if "images" in node_output:
            for img_info in node_output["images"]:
                filename = img_info.get("filename")
                subfolder = img_info.get("subfolder", "")
                if filename:
                    return os.path.join(OUTPUT_DIR, subfolder, filename)

    raise ValueError("No output file found in history")


def encode_file_base64(filepath: str) -> str:
    """Read file and encode as base64."""
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# Global ComfyUI process
comfyui_process = None


def handler(job):
    """
    RunPod handler function.

    Expected input:
    {
        "image": "base64 encoded image or URL",
        "prompt": "animation description",
        "frame_count": 21,  # optional
        "fps": 12,  # optional
        "seed": 12345  # optional
    }

    Returns:
    {
        "video": "base64 encoded webp",
        "seed": used_seed
    }
    """
    global comfyui_process

    try:
        job_input = job["input"]

        # Validate input
        if "image" not in job_input:
            return {"error": "Missing required field: image"}

        # Start ComfyUI if not running
        if comfyui_process is None:
            comfyui_process = start_comfyui()

        # Save input image
        image_filename = f"input_{uuid.uuid4().hex[:8]}.png"
        save_input_image(job_input["image"], image_filename)

        # Prepare parameters
        seed = job_input.get("seed", random.randint(0, 2**32 - 1))
        params = {
            "image_filename": image_filename,
            "prompt": job_input.get("prompt", ""),
            "seed": seed,
            "frame_count": job_input.get("frame_count", 21),
            "fps": job_input.get("fps", 12),
        }

        # Load and modify workflow
        workflow = load_workflow()
        workflow = modify_workflow(workflow, params)

        # Queue prompt
        print(f"Queuing prompt with seed {seed}...")
        prompt_id = queue_prompt(workflow)
        print(f"Prompt ID: {prompt_id}")

        # Wait for completion
        print("Waiting for generation to complete...")
        history = wait_for_completion(prompt_id)

        # Get output file
        output_file = get_output_file(history)
        print(f"Output file: {output_file}")

        # Encode output
        video_base64 = encode_file_base64(output_file)

        # Cleanup input file
        try:
            os.remove(os.path.join(INPUT_DIR, image_filename))
        except OSError:
            pass

        return {"video": video_base64, "seed": seed}

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return {"error": str(e)}


# Start the serverless handler
if __name__ == "__main__":
    print("Starting WAN 2.1 Seamless Loop Handler...")
    runpod.serverless.start({"handler": handler})
