# LoRA Studio User Guide

LoRA Studio is the production interface for anime character image generation, dataset curation, and LoRA training. Access it at:

```
https://<your-tower-ip>/lora-studio/
```

The UI has 7 tabs. This guide walks through each one in the order of a typical production workflow.

---

## 1. Characters Tab

**Purpose:** See all characters across all projects with their dataset status.

Each character card shows:
- **Name** and **project** (e.g., Mario — Super Mario Galaxy Anime Adventure)
- **Image count** — how many images are in their dataset
- **Checkpoint model** — which Stable Diffusion model generates their images
- **Design prompt** — the text description used for generation

Use this tab to get oriented. Characters with 0 images need generation. Characters with 10+ approved images are ready for training.

---

## 2. Generate Tab

**Purpose:** Create new images or videos for a character using ComfyUI.

### Steps:
1. Select a **character** from the dropdown
2. The character's SSOT settings load automatically (checkpoint, CFG, steps, sampler)
3. Choose **Image** or **Video** generation type
4. Optionally override the prompt, add negative prompt terms, or set a specific seed
5. Click **Generate**
6. A progress indicator shows: pending → running → completed
7. When done, the image appears in the Gallery tab

**Tips:**
- Video mode caps resolution at 512x512 and generates 16 frames
- If generation seems stuck, use the **Clear Stuck Jobs** button
- Each character uses their project's checkpoint — you don't pick a model manually

---

## 3. Gallery Tab

**Purpose:** Browse recent output from ComfyUI.

- Images are sorted newest-first
- Each entry shows filename, timestamp, and file size
- Click an image to view it full-size

Images here are raw ComfyUI output. To add them to a character's training dataset, use the Ingest tab or the ComfyUI scan feature.

---

## 4. Ingest Tab

**Purpose:** Import reference material into character datasets from multiple sources.

### Single Character Mode
- Paste a **YouTube URL**, select a character, set max frames and FPS
- The system downloads the video, extracts frames, and adds them to that character's dataset as pending

### Entire Project Mode
- Paste a **YouTube URL**, select a project
- Frames are extracted and each one is analyzed by the **llava vision model**
- Llava identifies which characters appear in each frame
- Frames are automatically sorted into the correct character datasets
- Frames where no character is recognized are skipped

### Other ingestion methods:
- **Upload image** — drag and drop or file picker, classified by llava
- **Upload video** — same frame extraction as YouTube, with llava filtering
- **Scan ComfyUI output** — finds new images in `/opt/ComfyUI/output/` and matches them to characters by filename or llava vision

All ingested images land in the **Approve** tab as pending.

---

## 5. Approve Tab

**Purpose:** Quality control for training data. This is where the feedback loop lives.

You'll see a grid of pending images across all characters. Each image shows:
- Character name and project
- The design prompt that was used
- Generation metadata (if available): seed, checkpoint, sampler

### Approving an image:
- Click the **approve** button (checkmark)
- The image is marked as approved and counts toward the training threshold (10 required)

### Rejecting an image with feedback:
This is the most important action in the system. When you reject:

1. Click the **reject** button
2. **Check the feedback category boxes** that apply:
   - **Wrong appearance** — colors, outfit, or features don't match the character
   - **Wrong style** — art style doesn't match the project (e.g., anime instead of 3D)
   - **Bad quality** — blurry, artifacts, distorted anatomy
   - **Not solo** — multiple characters when there should be one
   - **Wrong pose** — awkward or unnatural positioning
   - **Wrong expression** — facial expression doesn't fit the character
3. Optionally add free-text notes after the categories
4. Optionally **edit the design prompt** — this updates the character's prompt for all future generations
5. Submit

### What happens after rejection:
- Your feedback categories are stored and converted into **negative prompt terms**
- The system automatically queues a **regeneration** with those negatives added
- After **3+ structured rejections**, Echo Brain is consulted for prompt refinement ideas
- The next generated image should avoid the problems you flagged

### The feedback loop in practice:
1. Generate → get a bad image
2. Reject with "wrong_style" + "bad_quality"
3. System regenerates with "wrong art style, blurry, low quality" added to negatives
4. New image arrives in pending
5. If still wrong, reject again with more specific categories
6. Each rejection makes future generations better for that character

---

## 6. Train Tab

**Purpose:** Start and monitor LoRA training jobs.

### Prerequisites:
- A character needs **10 or more approved images** before training can start
- The character's project must have a checkpoint model configured

### Starting training:
1. Select a character
2. Set training parameters (epochs, learning rate, resolution) or use defaults
3. Click **Start Training**
4. The system frees GPU VRAM, launches the training script, and shows progress

### Monitoring:
- Job status: queued → running → completed/failed
- Training logs are streamed in real-time
- When complete, the LoRA file is saved to `/opt/ComfyUI/models/loras/`

---

## 7. Echo Brain Tab

**Purpose:** AI-assisted context and prompt improvement.

### Chat mode:
- Ask questions about any character, project, or production topic
- Echo Brain searches 54,000+ vectors of project history for relevant context
- Select a character from the dropdown to include their design prompt and project info as context

### Enhance Prompt mode:
- Paste a design prompt
- Echo Brain searches its memory for relevant context about that character
- Returns suggestions and related memories that may improve the prompt

### Example queries:
- "What should Mario look like in Illumination 3D style?"
- "What checkpoint works best for cyberpunk characters?"
- "Why do Bowser images keep having the wrong colors?"

---

## Common Workflows

### New character from scratch
1. **Characters** → verify the character exists with a design prompt
2. **Generate** → create 15-20 images
3. **Approve** → review each one, reject bad ones with categories
4. Wait for feedback-driven regenerations to fill in
5. Once 10 are approved → **Train**

### Importing reference from YouTube
1. **Ingest** → Entire Project mode → paste video URL
2. **Approve** → review llava-classified frames
3. Approve good references, reject misclassified ones

### Refining a character's look
1. **Approve** → reject images with specific categories
2. Edit the design prompt if the core description is wrong
3. Let the feedback loop run 3-5 cycles
4. Check **Echo Brain** for additional context if quality plateaus

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Generate button does nothing | Check if ComfyUI is running: `http://<host>:8188` |
| Gallery is empty | ComfyUI output directory may be empty or images haven't generated yet |
| Approve tab is empty | No pending images — generate some or run an ingestion |
| Echo Brain says "offline" | Check Echo Brain service: `http://<host>:8309/health` |
| Training won't start | Need 10+ approved images and a configured checkpoint |
| Ingested YouTube frames are all "skipped" | Llava couldn't identify characters — try a video with clearer character shots |
