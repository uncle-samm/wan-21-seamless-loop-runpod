"""
Test script for WAN 2.1 Seamless Loop RunPod Endpoint
"""

import base64
import os
import sys
import time
from pathlib import Path

import requests

# Configuration - UPDATE THESE
RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY", "YOUR_API_KEY_HERE")
ENDPOINT_ID = "01weny6a50wwur"

# API URLs
RUN_URL = f"https://api.runpod.ai/v2/{ENDPOINT_ID}/run"
STATUS_URL = f"https://api.runpod.ai/v2/{ENDPOINT_ID}/status"


def encode_image(image_path: str) -> str:
    """Read and base64 encode an image file."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def save_video(base64_data: str, output_path: str):
    """Decode base64 and save to file."""
    video_bytes = base64.b64decode(base64_data)
    with open(output_path, "wb") as f:
        f.write(video_bytes)
    print(f"Saved video to: {output_path}")


def run_generation(
    image_path: str, prompt: str, frame_count: int = 21, fps: int = 12, seed: int = None
):
    """Submit a generation job and wait for results."""

    headers = {
        "Authorization": f"Bearer {RUNPOD_API_KEY}",
        "Content-Type": "application/json",
    }

    # Prepare payload
    payload = {
        "input": {
            "image": encode_image(image_path),
            "prompt": prompt,
            "frame_count": frame_count,
            "fps": fps,
        }
    }

    if seed is not None:
        payload["input"]["seed"] = seed

    # Submit job
    print(f"Submitting job...")
    print(f"  Image: {image_path}")
    print(f"  Prompt: {prompt}")
    print(f"  Frames: {frame_count}, FPS: {fps}")

    response = requests.post(RUN_URL, json=payload, headers=headers)
    response.raise_for_status()

    job_data = response.json()
    job_id = job_data.get("id")
    print(f"  Job ID: {job_id}")

    # Poll for completion
    print("\nWaiting for generation...")
    start_time = time.time()

    while True:
        status_response = requests.get(f"{STATUS_URL}/{job_id}", headers=headers)
        status_data = status_response.json()
        status = status_data.get("status")

        elapsed = time.time() - start_time
        print(f"  Status: {status} ({elapsed:.1f}s)", end="\r")

        if status == "COMPLETED":
            print(f"\n\nCompleted in {elapsed:.1f}s!")
            return status_data.get("output")
        elif status == "FAILED":
            print(f"\n\nFailed!")
            print(f"Error: {status_data.get('error')}")
            return None
        elif status in ["IN_QUEUE", "IN_PROGRESS"]:
            time.sleep(2)
        else:
            print(f"\n\nUnknown status: {status}")
            print(status_data)
            return None


def main():
    # Default test image
    image_path = "Gemini_Generated_Image_lh33x5lh33x5lh33.png"

    # Check if image exists
    if not Path(image_path).exists():
        print(f"Error: Image not found: {image_path}")
        print("Usage: python test_endpoint.py [image_path] [prompt]")
        sys.exit(1)

    # Default prompt for idle animation
    prompt = "This animation shows the character standing in an idle pose. The character gently sways from side to side, shifting weight subtly. Chest rises and falls subtly, simulating breathing. The entire sequence loops smoothly, creating a continuous, gentle idle animation. Slow movements. Idle animation. Gray background."

    # Override with command line args if provided
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    if len(sys.argv) > 2:
        prompt = sys.argv[2]

    # Check endpoint ID
    if ENDPOINT_ID == "YOUR_ENDPOINT_ID_HERE":
        print("Error: Please update ENDPOINT_ID in the script!")
        print("Get it from the RunPod console after deployment.")
        sys.exit(1)

    # Run generation
    result = run_generation(image_path, prompt)

    if result:
        # Save the video
        video_data = result.get("video")
        seed = result.get("seed")

        if video_data:
            output_path = f"output_seed_{seed}.webp"
            save_video(video_data, output_path)
            print(f"Seed used: {seed}")
        else:
            print("No video in response!")
            print(result)


if __name__ == "__main__":
    main()
