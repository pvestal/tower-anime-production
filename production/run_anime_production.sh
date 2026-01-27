#!/bin/bash
# Main entry point for anime production with LTX LoRAs

echo "🎬 Tower Anime Production System"
echo "================================"
echo ""

# Function to show menu
show_menu() {
    echo "Select operation:"
    echo "1) Train new character LoRA"
    echo "2) Train new action LoRA"
    echo "3) Generate character reference sheet"
    echo "4) Produce single scene"
    echo "5) Batch produce episode"
    echo "6) Manage LoRA database"
    echo "7) Test LoRA combination"
    echo "0) Exit"
    echo ""
}

# Function to train character LoRA
train_character() {
    echo "📚 Character LoRA Training"
    echo "-------------------------"
    read -p "Character name: " char_name
    read -p "Number of reference videos (1-5): " num_videos

    python3 << EOF
from anime_lora_pipeline import AnimeLoRAPipeline
from pathlib import Path

pipeline = AnimeLoRAPipeline()

# Find videos for character
videos = list(Path("/mnt/1TB-storage/ComfyUI/output").glob("*.mp4"))[:${num_videos}]
if videos:
    data_path = pipeline.prepare_character_training_data("${char_name}", videos)
    trigger_word = "${char_name}".lower().replace(' ', '_')
    result = pipeline.train_lora("${char_name}_lora", "character", trigger_word, data_path)
    print(f"Training result: {result}")
else:
    print("No videos found for training")
EOF
}

# Function to generate reference sheet
generate_references() {
    echo "🖼️ Character Reference Generation"
    echo "---------------------------------"
    read -p "Character name: " char_name

    python3 << EOF
import asyncio
from anime_production_manager import AnimeProductionManager

async def generate():
    manager = AnimeProductionManager()
    refs = await manager.generate_character_reference_sheet("${char_name}")
    print(f"Generated references: {refs}")

asyncio.run(generate())
EOF
}

# Function to produce scene
produce_scene() {
    echo "🎬 Scene Production"
    echo "------------------"
    read -p "Episode ID: " episode_id
    read -p "Scene number: " scene_num
    read -p "Scene type (action_fight/intimate_scene/dialogue/transformation): " scene_type
    read -p "Character name: " char_name
    read -p "Scene description: " description

    python3 << EOF
import asyncio
from anime_production_manager import AnimeProductionManager

async def produce():
    manager = AnimeProductionManager()
    result = await manager.produce_episode_scene(
        ${episode_id},
        ${scene_num},
        "${scene_type}",
        ["${char_name}"],
        "${description}"
    )
    print(f"Scene production result: {result}")

asyncio.run(produce())
EOF
}

# Function to test LoRA combination
test_loras() {
    echo "🧪 Test LoRA Combination"
    echo "------------------------"
    echo "Available LoRAs:"
    ls -1 /mnt/1TB-storage/ComfyUI/models/loras/*.safetensors | xargs -n1 basename | head -20
    echo ""

    read -p "Character LoRA (or 'none'): " char_lora
    read -p "Action LoRA (or 'none'): " action_lora
    read -p "NSFW LoRA (or 'none'): " nsfw_lora
    read -p "Test prompt: " prompt

    python3 << EOF
import requests
import json

workflow = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "ltxv-2b-fp8.safetensors"}},
    "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "t5xxl_fp16.safetensors", "type": "ltxv"}}
}

prev_model = ["1", 0]
prev_clip = ["2", 0]
node_num = 3

# Add LoRAs
for lora, strength in [("${char_lora}", 1.0), ("${action_lora}", 0.8), ("${nsfw_lora}", 0.6)]:
    if lora != "none" and lora != "":
        workflow[str(node_num)] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora,
                "strength_model": strength,
                "strength_clip": strength,
                "model": prev_model,
                "clip": prev_clip
            }
        }
        prev_model = [str(node_num), 0]
        prev_clip = [str(node_num), 1]
        node_num += 1

# Add generation nodes
workflow.update({
    str(node_num): {"class_type": "CLIPTextEncode", "inputs": {"text": "${prompt}", "clip": prev_clip}},
    str(node_num+1): {"class_type": "CLIPTextEncode", "inputs": {"text": "low quality", "clip": prev_clip}},
    str(node_num+2): {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": 512, "height": 384, "length": 25, "batch_size": 1}},
    str(node_num+3): {"class_type": "LTXVConditioning", "inputs": {"positive": [str(node_num), 0], "negative": [str(node_num+1), 0], "frame_rate": 24}},
    str(node_num+4): {"class_type": "KSampler", "inputs": {
        "seed": 42, "steps": 10, "cfg": 4.0, "sampler_name": "euler", "scheduler": "simple",
        "denoise": 1.0, "model": prev_model, "positive": [str(node_num+3), 0],
        "negative": [str(node_num+3), 1], "latent_image": [str(node_num+2), 0]
    }},
    str(node_num+5): {"class_type": "VAEDecode", "inputs": {"samples": [str(node_num+4), 0], "vae": ["1", 2]}},
    str(node_num+6): {"class_type": "VHS_VideoCombine", "inputs": {
        "images": [str(node_num+5), 0], "frame_rate": 12, "loop_count": 0,
        "filename_prefix": "lora_test", "format": "video/h264-mp4",
        "pingpong": False, "save_output": True
    }}
})

response = requests.post("http://localhost:8188/prompt", json={"prompt": workflow})
if response.status_code == 200:
    print(f"Test submitted: {response.json()['prompt_id']}")
    print("Check: /mnt/1TB-storage/ComfyUI/output/lora_test*.mp4")
else:
    print(f"Failed: {response.status_code}")
EOF
}

# Main loop
while true; do
    show_menu
    read -p "Choice: " choice

    case $choice in
        1) train_character ;;
        2) echo "Action LoRA training not yet implemented" ;;
        3) generate_references ;;
        4) produce_scene ;;
        5) echo "Batch production not yet implemented" ;;
        6) psql -h localhost -U patrick -d anime_production -c "SELECT id, name, type, trigger_word FROM lora_models;" ;;
        7) test_loras ;;
        0) echo "Exiting..."; exit 0 ;;
        *) echo "Invalid choice" ;;
    esac

    echo ""
    read -p "Press Enter to continue..."
    clear
done