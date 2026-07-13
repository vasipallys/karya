import torch
import os
from transformers import AutoModelForCausalLM, AutoTokenizer

# 1. Initialize tokenizer and causal LM model
# model_id = "Qwen/Qwen2.5-1.5B-Instruct"

local_model_path = "C:/mydrive/tools/SLM/qwen1B/1"  # Ensure this folder exists with model files

# Check if the model path exists
if not os.path.exists(local_model_path):
    raise FileNotFoundError(
        f"Local model path not found: {local_model_path}. "
        "Please ensure the 'qwen1B' directory exists and contains the model files."
    )

tokenizer = None
model = None

try:
    # Use trust_remote_code=True for Qwen models
    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(
        local_model_path,
        trust_remote_code=True,
        use_fast=False
    )

    print("Loading model...")
    model = AutoModelForCausalLM.from_pretrained(
        local_model_path,
        trust_remote_code=True,
        torch_dtype=torch.float16,      # Qwen 1.8B often works well with float16 or bfloat16
        device_map="auto",              # Automatically maps model layers to available devices
        low_cpu_mem_usage=True          # Helps with large models
    ).eval()                            # Set model to evaluation mode

    # Check if model loaded correctly and has a generate method
    if not hasattr(model, "generate"):
        raise RuntimeError(
            "Model does not support 'generate' method. "
            "Check model class and configuration."
        )

except Exception as e:
    raise RuntimeError(
        f"Failed to load Qwen model: {e}\n"
        "Ensure transformers, torch, and accelerate are installed correctly.\n"
        "Also check if model files in the Qwen directory are complete and not corrupted."
    )

# 2. Format message using Qwen's built-in template
messages = [
    {
        "role": "user",
        "content": "Explain gravity in one short sentence."
    }
]

text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True
)

# 3. Convert text to model input tensors
inputs = tokenizer([text], return_tensors="pt").to(model.device)

# 4. Generate token IDs
generated_ids = model.generate(
    **inputs,
    max_new_tokens=100
)

# 5. Trim the prompt tokens out of the generation
generated_ids = [
    output[len(inputs.input_ids[i]):]
    for i, output in enumerate(generated_ids)
]

# 6. Decode tokens into text
response = tokenizer.batch_decode(
    generated_ids,
    skip_special_tokens=True
)[0]

print(response)