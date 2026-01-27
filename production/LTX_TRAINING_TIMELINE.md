
🗓️ LTX LoRA TRAINING TIMELINE (7 Days)
=====================================

Day 1-2: Data Collection & Preparation
---------------------------------------
□ Collect reference videos for each action category
  - Martial arts scenes (10-20 clips)
  - Dance sequences (10-20 clips)
  - Intimate scenes (10-20 clips)
□ Extract frames (8 fps = 192 frames from 24fps video)
□ Auto-caption with BLIP/LLAVA
□ Manual caption refinement for accuracy

Day 3-4: Initial Training Runs
-------------------------------
□ Morning: Train 'martial_arts' LoRA (4 hours)
□ Afternoon: Train 'dancing' LoRA (4 hours)
□ Evening: Test generations, adjust parameters
□ Overnight: Train 'intimate' LoRAs (8 hours)

Day 5: Refinement & Combination
--------------------------------
□ Test LoRA combinations (character + action)
□ Fine-tune underperforming LoRAs
□ Create merged LoRAs for complex actions
□ Document optimal strength settings

Day 6: Integration Testing
---------------------------
□ Test with Tokyo Debt Desire characters
□ Verify VRAM usage stays under 12GB
□ Create production workflows
□ Batch generate test videos

Day 7: Production Deployment
-----------------------------
□ Move trained LoRAs to production
□ Update pipeline configurations
□ Create usage documentation
□ Set up automated generation queues

VRAM OPTIMIZATION TIPS:
- Train with batch_size=1
- Use gradient checkpointing
- Enable xformers
- Use 8-bit Adam optimizer
- Resolution: 512x384 max
- Clear VRAM between training runs
