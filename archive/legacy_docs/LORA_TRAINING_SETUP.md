# Tower LoRA Training Pipeline

Comprehensive LoRA training system for anime characters using ComfyUI and Kohya training scripts.

## Overview

This system provides automated LoRA (Low-Rank Adaptation) training for anime characters, enabling consistent character generation across the Tower Anime Production pipeline. It includes:

- **Automated image generation** for training datasets using ComfyUI
- **Kohya training integration** for high-quality LoRA model training
- **Database tracking** of training progress and model locations
- **RESTful API** for integration with the main anime production system
- **Command-line tools** for training management

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Anime API     │    │   LoRA API      │    │  Training CLI   │
│   Port: 8321    │    │   Port: 8329    │    │                 │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────▼───────────────┐
                    │  LoRA Training Pipeline     │
                    │  - Image Generation         │
                    │  - Dataset Preparation      │
                    │  - Kohya Training          │
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │     Storage Layer           │
                    │ /mnt/1TB-storage/ComfyUI/   │
                    │ ├── models/loras/          │
                    │ ├── training_data/         │
                    │ └── output/                │
                    └─────────────────────────────┘
```

## System Requirements

- **ComfyUI**: Running on localhost:8188
- **PostgreSQL**: anime_production database
- **GPU**: NVIDIA GPU with CUDA support (recommended)
- **Storage**: Minimum 50GB free space for training data and models
- **Python**: 3.8+ with required dependencies

## Installation

### 1. Verify Prerequisites

```bash
# Test system status
cd /opt/tower-anime-production
python3 test_lora_setup.py
```

### 2. Start LoRA Training API Service

```bash
# Manual start for testing
cd /opt/tower-anime-production
python3 api/lora_training_api.py

# Or install as systemd service
sudo systemctl enable tower-lora-training
sudo systemctl start tower-lora-training
sudo systemctl status tower-lora-training
```

### 3. Verify Installation

```bash
# Check service health
curl http://localhost:8329/

# List characters
python3 scripts/lora_training_manager.py list

# Check system status
python3 scripts/lora_training_manager.py status
```

## Usage

### Command Line Interface

#### List Characters and Training Status
```bash
python3 scripts/lora_training_manager.py list
```

#### Train Single Character
```bash
python3 scripts/lora_training_manager.py train --character-id 15
```

#### Train All Untrained Characters
```bash
python3 scripts/lora_training_manager.py train-all
```

#### Check System Status
```bash
python3 scripts/lora_training_manager.py status
```

### REST API Endpoints

#### Main Anime API (Port 8321)

- `GET /api/anime/lora-training/status` - Get training status for all characters
- `GET /api/anime/characters/{id}/lora-status` - Get LoRA status for specific character
- `POST /api/anime/characters/{id}/train-lora` - Start training for character
- `POST /api/anime/lora-training/start-all` - Start training for all untrained characters

#### LoRA Training API (Port 8329)

- `GET /` - Health check
- `GET /characters` - List all characters with LoRA status
- `GET /characters/untrained` - List characters needing training
- `GET /training-jobs` - Get all training jobs
- `POST /training/start/{character_id}` - Start training for character
- `POST /training/start-all` - Start batch training
- `GET /training/status/{character_id}` - Get training status

### Example Usage

```bash
# Check what characters need training
curl http://localhost:8321/api/anime/lora-training/status | jq

# Start training for character ID 15 (Kai Nakamura)
curl -X POST http://localhost:8321/api/anime/characters/15/train-lora

# Check training progress
curl http://localhost:8329/training/status/15 | jq

# Start training for all characters
curl -X POST http://localhost:8321/api/anime/lora-training/start-all
```

## Training Process

### 1. Dataset Generation
- Generates 20+ diverse training images per character using ComfyUI
- Creates various poses, expressions, and viewpoints
- Automatically generates captions for each image
- Organizes files in character-specific directories

### 2. LoRA Training
- Uses Kohya training scripts with optimized parameters
- Network dimension: 128, Alpha: 64
- Learning rate: 0.0001, Batch size: 1
- 10 epochs with checkpoints every 5 epochs
- Mixed precision (fp16) for memory efficiency

### 3. Model Management
- Saves trained models to `/mnt/1TB-storage/ComfyUI/models/loras/`
- Updates database with model paths
- Tracks training status and metadata

## Configuration

### Training Parameters

Edit `lora_training_pipeline.py` to modify:

```python
@dataclass
class TrainingConfig:
    resolution: int = 512        # Training resolution
    batch_size: int = 1         # Training batch size
    steps: int = 1000           # Training steps
    learning_rate: float = 0.0001  # Learning rate
    network_dim: int = 128      # LoRA network dimension
    network_alpha: int = 64     # LoRA network alpha
    optimizer: str = "AdamW8bit"  # Optimizer type
```

### Storage Paths

- **LoRA Models**: `/mnt/1TB-storage/ComfyUI/models/loras/`
- **Training Data**: `/mnt/1TB-storage/ComfyUI/training_data/`
- **Generated Images**: `/mnt/1TB-storage/ComfyUI/output/`

## Database Schema

### character_training_jobs Table

```sql
CREATE TABLE character_training_jobs (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id),
    target_asset_type VARCHAR(50) DEFAULT 'lora_v1',
    status VARCHAR(50) DEFAULT 'pending',
    required_approvals INTEGER,
    approved_images INTEGER,
    generated_images TEXT[],
    training_script_path TEXT,
    trained_model_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Monitoring

### Service Logs
```bash
# View API logs
sudo journalctl -u tower-lora-training -f

# View training progress
tail -f /opt/tower-anime-production/logs/anime_service.log
```

### Training Status

Characters can have the following training statuses:
- `not_started` - No training initiated
- `in_progress` - Training currently running
- `completed` - Training successfully completed
- `failed` - Training failed with errors
- `needs_approval` - Manual approval required

## Integration with Anime Production

The LoRA training system integrates seamlessly with the main anime production pipeline:

1. **Character Management**: Uses existing character database
2. **Workflow Integration**: LoRA models are automatically available for generation workflows
3. **API Compatibility**: Endpoints integrate with the main anime API
4. **Storage Consistency**: Uses shared storage infrastructure

## Troubleshooting

### Common Issues

**Database Connection Failed**
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Verify database credentials
psql -U patrick -d anime_production -c "SELECT 1"
```

**ComfyUI Connection Failed**
```bash
# Check if ComfyUI is running
curl http://localhost:8188
ps aux | grep ComfyUI
```

**Training Fails**
```bash
# Check Kohya scripts
ls -la /opt/tower-anime-production/training/kohya_real/train_network.py

# Check GPU availability
nvidia-smi
```

### Performance Optimization

- **GPU Memory**: Reduce batch size if running out of VRAM
- **Storage I/O**: Use SSD for training data directories
- **CPU Usage**: Limit concurrent training jobs based on system resources

## Current Status

### Trained Characters
- **Mei Kobayashi**: Has working LoRA model (`mei_working_v1.safetensors`)

### Characters Needing Training
- **Kai Nakamura** (ID: 15): Cyberpunk goblin hunter character
- **Goblin Slayer** (ID: 14): Cybernetic warrior character
- **Takeshi Sato** (ID: 11): Character without description
- **Yuki Tanaka** (ID: 10): Character without description
- **Rina Suzuki** (ID: 9): Character without description
- **Test_Samurai_Kaito** (ID: 16, 17): Duplicate test characters

### Next Steps
1. Train LoRA models for remaining characters
2. Test character consistency in generation workflows
3. Integrate trained LoRA models with ComfyUI workflows
4. Monitor and optimize training parameters

## Support

For issues or questions:
- Check logs: `sudo journalctl -u tower-lora-training`
- Run diagnostics: `python3 test_lora_setup.py`
- Check system status: `python3 scripts/lora_training_manager.py status`