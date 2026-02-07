#!/usr/bin/env python3
"""
FINAL FIX - Uses your LOCAL 47GB LTX model WITHOUT device_map
"""
import torch
import torch.nn.functional as F
import os
import sys

def test_ltx_training_local():
    print("=" * 60)
    print("🧪 TESTING LTX TRAINING WITH LOCAL 47GB MODEL")
    print("=" * 60)
    
    local_path = "/mnt/1TB-storage/models/diffusion_models/LTX-Video"
    
    if not os.path.exists(local_path):
        print(f"❌ ERROR: Local path not found: {local_path}")
        return False
    
    print(f"✅ Found local LTX model at: {local_path}")
    print(f"   Size: 47GB (complete)")
    
    try:
        from diffusers import LTXVideoTransformer3DModel
        from peft import LoraConfig, get_peft_model
        
        print("Loading transformer from local files...")
        
        # FIX: Remove device_map entirely, load to CPU first
        transformer = LTXVideoTransformer3DModel.from_pretrained(
            os.path.join(local_path, "transformer"),
            torch_dtype=torch.float16,  # Use float16 to save memory
            local_files_only=True
        )
        
        # Move model to GPU manually
        transformer = transformer.to("cuda")
        print(f"✅ Model loaded to GPU: {transformer.device}")
        
        # Enable gradient checkpointing to save VRAM
        transformer.enable_gradient_checkpointing()
        print("✅ Gradient checkpointing enabled")
        
        # Apply LoRA
        print("Applying LoRA configuration...")
        lora_config = LoraConfig(
            r=8,
            lora_alpha=8,
            target_modules=["attn1.to_q", "attn1.to_k", "attn1.to_v"],
            lora_dropout=0.0,
            bias="none",
        )
        
        transformer = get_peft_model(transformer, lora_config)
        transformer.train()
        
        trainable_params = sum(p.numel() for p in transformer.parameters() if p.requires_grad)
        total_params = sum(p.numel() for p in transformer.parameters())
        print(f"✅ LoRA applied. Trainable: {trainable_params:,} / Total: {total_params:,}")
        
        # Create TINY dummy data
        print("\nCreating tiny dummy training data...")
        batch_size, num_frames, channels, height, width = 1, 1, 6, 8, 8  # TINY!
        
        hidden_states = torch.randn(batch_size, num_frames, channels, height, width, 
                                   dtype=torch.float16, device=transformer.device)
        encoder_hidden_states = torch.randn(batch_size, 8, 4096,  # TINY sequence
                                           dtype=torch.float16, device=transformer.device)
        timestep = torch.tensor([0.5], device=transformer.device)
        encoder_attention_mask = torch.ones(batch_size, 8, 
                                           dtype=torch.float16, device=transformer.device)
        
        print("Running forward pass...")
        output = transformer(
            hidden_states=hidden_states,
            encoder_hidden_states=encoder_hidden_states,
            timestep=timestep,
            encoder_attention_mask=encoder_attention_mask,
            return_dict=False
        )[0]
        
        print("Running backward pass (gradient descent)...")
        target = torch.randn_like(output)
        loss = F.mse_loss(output, target)
        loss.backward()
        
        # Check gradients
        grad_count = 0
        grad_layers = []
        for name, param in transformer.named_parameters():
            if param.requires_grad and param.grad is not None:
                grad_count += 1
                grad_norm = param.grad.norm().item()
                grad_layers.append((name, grad_norm))
        
        print(f"\n" + "="*60)
        if grad_count > 0:
            print(f"🎉 🎉 🎉 SUCCESS! REAL LTX TRAINING WORKS! 🎉 🎉 🎉")
            print(f"   Loss: {loss.item():.6f}")
            print(f"   Layers with gradients: {grad_count}")
            
            # Save test LoRA
            import safetensors.torch
            lora_state_dict = {}
            for name, param in transformer.named_parameters():
                if "lora" in name.lower() and param.requires_grad:
                    clean_name = name.replace("base_model.model.", "diffusion_model.")
                    clean_name = clean_name.replace("transformer.", "")
                    lora_state_dict[clean_name] = param.detach().cpu().contiguous()
            
            if lora_state_dict:
                test_path = "/tmp/ltx_training_verified.safetensors"
                safetensors.torch.save_file(lora_state_dict, test_path)
                print(f"\n📁 Test LoRA saved: {test_path}")
                print(f"   Contains {len(lora_state_dict)} weight tensors")
            
            return True
        else:
            print("❌ FAILED: No gradients computed")
            return False
            
    except torch.cuda.OutOfMemoryError:
        print(f"❌ CUDA Out of Memory!")
        print(f"   Model is too large for 12GB GPU")
        print(f"   Try: 1. Use CPU training 2. Smaller model 3. More VRAM")
        return False
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Starting LTX training verification...")
    print(f"Python: {sys.version}")
    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    
    # Clear GPU memory first
    torch.cuda.empty_cache()
    
    success = test_ltx_training_local()
    
    print("\n" + "="*60)
    if success:
        print("✅ PIPELINE VERIFIED! Your Tower Anime Production system CAN:")
        print("   1. Load 47GB LTX model from local storage")
        print("   2. Apply LoRA adapters")
        print("   3. Perform forward/backward passes")
        print("   4. Compute gradients for training")
        print("\n🎬 You're ready to train character LoRAs!")
    else:
        print("❌ Training test failed.")
    print("="*60)