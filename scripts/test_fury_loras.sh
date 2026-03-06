#!/bin/bash
# Test all new Fury-related LoRAs against nova_animal_xl checkpoint
# Run after training completes and GPU is free
# Usage: ./scripts/test_fury_loras.sh

set -e

API="http://127.0.0.1:8188"
CHECKPOINT="nova_animal_xl_v11.safetensors"
OUTPUT_PREFIX="fury_lora_test"

# Wait for GPU to be free
echo "Checking GPU availability..."
while true; do
    gpu_used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
    if [ "$gpu_used" -lt 2000 ]; then
        echo "GPU free ($gpu_used MB used). Starting tests."
        break
    fi
    echo "GPU busy ($gpu_used MB). Waiting 60s..."
    sleep 60
done

# Free ComfyUI VRAM
curl -s -X POST "$API/free" -H "Content-Type: application/json" -d '{"unload_models": true, "free_memory": true}'
sleep 5

python3 << 'PYEOF'
import json, requests, random, time, sys

SERVER = "http://127.0.0.1:8188"
CHECKPOINT = "nova_animal_xl_v11.safetensors"

tests = [
    {
        "name": "furry_enhancer",
        "lora": "furry_enhancer_v8.2.safetensors",
        "strength": 0.7,
        "prompt": "masterpiece, best quality, anthro, furry, 1girl, fox girl, orange fur, fluffy tail, green eyes, neon city, rain, leather jacket, detailed fur, full body",
    },
    {
        "name": "furry_realism",
        "lora": "furry_realism_illus.safetensors",
        "strength": 0.7,
        "prompt": "masterpiece, best quality, anthro, 1girl, furry, furry female, orange fur, medium hair, pink hair, large breasts, lidded eyes, green sclera, green iris, fox tail, furry body, detailed fur, fox, fluffy fur, detailed eyes, realistic lighting",
    },
    {
        "name": "ma_tianba_horse",
        "lora": "ma_tianba_horse_anthro.safetensors",
        "strength": 0.8,
        "prompt": "masterpiece, best quality, Anthro, horse, ma tianba, gray skin, muscular male, tall male, white mane, black eyes, standing, full body, dark background",
    },
    {
        "name": "succubus_lilith",
        "lora": "succubus_sakura_dungeon.safetensors",
        "strength": 0.8,
        "prompt": "masterpiece, best quality, succubus_(sakura_dungeon), 1girl, demon girl, purple skin, large curved ram horns, long white hair, glowing purple eyes, demon wings, demon tail, voluptuous, dark atmosphere, dramatic lighting",
    },
    {
        "name": "human_anthro_pov",
        "lora": "human_on_anthro_male_pov_il.safetensors",
        "strength": 0.6,
        "prompt": "masterpiece, best quality, pov_sex, 1girl, anthro, furry female, fox girl, orange fur, green eyes, bedroom, intimate",
    },
    {
        "name": "fantasy_forge",
        "lora": "fantasy_forge_v3_il.safetensors",
        "strength": 0.7,
        "prompt": "masterpiece, best quality, FantasyForge . 1girl, demon succubus, purple skin, horns, wings, dark temple, magical energy, fantasy, mystical atmosphere",
    },
    {
        "name": "human_female_furry_male",
        "lora": "human_female_on_furry_male_concept.safetensors",
        "strength": 0.6,
        "prompt": "masterpiece, best quality, 1girl, 1boy, human girl, anthro male, furry male, horse, muscular, intimate, bedroom",
    },
    {
        "name": "human_male_furry_female",
        "lora": "human_male_on_furry_female_concept.safetensors",
        "strength": 0.6,
        "prompt": "masterpiece, best quality, 1boy, 1girl, human male, anthro female, furry female, fox girl, orange fur, intimate, bedroom",
    },
]

results = []
for t in tests:
    print(f"\nTesting: {t['name']} ({t['lora']})")
    seed = random.randint(0, 2**63)
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CHECKPOINT}},
        "2": {"class_type": "LoraLoader", "inputs": {"model": ["1", 0], "clip": ["1", 1], "lora_name": t["lora"], "strength_model": t["strength"], "strength_clip": t["strength"]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": t["prompt"], "clip": ["2", 1]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "bad quality, worst quality, blurry, deformed, human, realistic photo", "clip": ["2", 1]}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 832, "height": 1216, "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {"model": ["2", 0], "positive": ["3", 0], "negative": ["4", 0], "latent_image": ["5", 0], "seed": seed, "steps": 25, "cfg": 5.0, "sampler_name": "euler_ancestral", "scheduler": "normal", "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": f"fury_test_{t['name']}"}}
    }

    resp = requests.post(f"{SERVER}/prompt", json={"prompt": workflow})
    d = resp.json()
    if "prompt_id" not in d:
        print(f"  QUEUE FAIL: {json.dumps(d)[:200]}")
        results.append({"name": t["name"], "status": "queue_fail"})
        continue

    pid = d["prompt_id"]
    print(f"  Queued: {pid}")

    # Wait for completion
    for _ in range(120):  # 10 min max
        time.sleep(5)
        h = requests.get(f"{SERVER}/history/{pid}").json()
        if h:
            st = h[pid].get("status", {}).get("status_str", "unknown")
            if st == "success":
                out = ""
                for nid, o in h[pid].get("outputs", {}).items():
                    if "images" in o:
                        out = o["images"][0]["filename"]
                print(f"  SUCCESS: {out}")
                results.append({"name": t["name"], "status": "success", "file": out})
                break
            elif st != "success" and "execution_error" in str(h[pid].get("status", {}).get("messages", [])):
                msgs = h[pid].get("status", {}).get("messages", [])
                err = ""
                for m in msgs:
                    if m[0] == "execution_error":
                        err = m[1].get("exception_message", "")[:150]
                print(f"  FAIL: {err}")
                results.append({"name": t["name"], "status": "fail", "error": err})
                break
    else:
        print("  TIMEOUT")
        results.append({"name": t["name"], "status": "timeout"})

print("\n" + "=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)
ok = sum(1 for r in results if r["status"] == "success")
fail = sum(1 for r in results if r["status"] != "success")
for r in results:
    icon = "✓" if r["status"] == "success" else "✗"
    print(f"  {icon} {r['name']}: {r['status']}")
print(f"\n{ok} passed, {fail} failed out of {len(results)}")
PYEOF
