# Training Guide — Fine-tuning Local Models with LoRA

> Read this before attempting to fine-tune any of the Ollama models.
> The key insight: start with prompt engineering. Fine-tune only after you have
> real production data showing where the base model consistently fails.

## Decision tree: do you need fine-tuning?

```
Does the base model (llama3.2 / mistral / phi3) with a good system prompt
correctly classify/map your columns?
    │
    ├─ YES (>90% accuracy on your data) → You're done. No fine-tuning needed.
    │
    └─ NO → Collect 100+ real examples where it fails
                │
                └─ Do the failures follow a pattern?
                       │
                       ├─ YES (e.g. it always misses your domain jargon)
                       │    → Fine-tune with LoRA (this doc)
                       │
                       └─ NO (random errors) → Improve the system prompt first
```

## Step 1: Collect training data from production runs

Every time an agent runs, log the prompt + response to a training table.
A human reviewer marks each response as correct or incorrect.
When you have 100+ correct examples per agent, you're ready to fine-tune.

### Database table for training data

```sql
CREATE TABLE training_examples (
    id          SERIAL PRIMARY KEY,
    agent       TEXT NOT NULL,          -- schema | classify | transform
    prompt      TEXT NOT NULL,          -- the full prompt sent to Ollama
    completion  TEXT NOT NULL,          -- the model's JSON response
    is_correct  BOOLEAN,                -- human-reviewed label
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

### Python script to export training data

```python
# python-agent/scripts/export_training_data.py
import psycopg2, json, os

DB_CONN = os.getenv("DB_CONNECTION")
AGENT   = "classify"   # change per run

conn = psycopg2.connect(DB_CONN)
with conn.cursor() as cur:
    cur.execute("""
        SELECT prompt, completion FROM training_examples
        WHERE agent = %s AND is_correct = true
    """, (AGENT,))
    rows = cur.fetchall()

# Alpaca format (used by Unsloth/LoRA trainers)
examples = [
    {
        "instruction": row[0],  # the system prompt + user prompt
        "input":       "",
        "output":      row[1],  # the correct JSON response
    }
    for row in rows
]

with open(f"training_data_{AGENT}.json", "w") as f:
    json.dump(examples, f, indent=2)

print(f"Exported {len(examples)} examples for agent: {AGENT}")
```

## Step 2: Fine-tune with Unsloth + LoRA

Unsloth is the recommended library for fine-tuning open models on consumer GPUs.
It supports llama3.2, mistral, and phi3 — exactly our stack.

### Setup (requires CUDA GPU — even a single RTX 3060 works)

```bash
pip install unsloth
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

### Training script: `python-agent/scripts/train_schema_agent.py`

```python
"""
Fine-tune llama3.2 for schema detection using LoRA.
Adapt model name and data path for classify/transform agents.
"""
from unsloth import FastLanguageModel
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments

# ── 1. Load base model ────────────────────────────────────────────────────
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name     = "unsloth/llama-3.2-3b-instruct",
    max_seq_length = 2048,
    load_in_4bit   = True,     # QLoRA — fits on 8GB VRAM
)

# ── 2. Attach LoRA adapter ────────────────────────────────────────────────
model = FastLanguageModel.get_peft_model(
    model,
    r              = 16,       # LoRA rank — higher = more capacity
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj"],
    lora_alpha     = 16,
    lora_dropout   = 0,
    bias           = "none",
    use_gradient_checkpointing = "unsloth",
)

# ── 3. Load your dataset ──────────────────────────────────────────────────
dataset = load_dataset("json", data_files="training_data_schema.json", split="train")

alpaca_prompt = """Below is an instruction that describes a task.
Write a response that appropriately completes the request.

### Instruction:
{}

### Response:
{}"""

def format_prompt(examples):
    return {
        "text": [
            alpaca_prompt.format(inst, out) + tokenizer.eos_token
            for inst, out in zip(examples["instruction"], examples["output"])
        ]
    }

dataset = dataset.map(format_prompt, batched=True)

# ── 4. Train ──────────────────────────────────────────────────────────────
trainer = SFTTrainer(
    model      = model,
    tokenizer  = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length     = 2048,
    args = TrainingArguments(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        num_train_epochs            = 3,
        learning_rate               = 2e-4,
        fp16                        = True,
        logging_steps               = 10,
        output_dir                  = "./checkpoints/schema-agent",
        save_strategy               = "epoch",
        report_to                   = "none",
    ),
)
trainer.train()

# ── 5. Save the fine-tuned model in GGUF format (for Ollama) ─────────────
model.save_pretrained_gguf(
    "schema-agent-fine-tuned",
    tokenizer,
    quantization_method = "q4_k_m",  # good balance of size vs quality
)

print("Model saved. Import into Ollama with:")
print("  ollama create schema-agent -f Modelfile")
```

## Step 3: Import fine-tuned model into Ollama

After training, create a `Modelfile` and register with Ollama:

```
# Modelfile (save next to your .gguf file)
FROM ./schema-agent-fine-tuned/model.gguf

SYSTEM """
You are a data schema analyst. Given column names and sample values,
return a JSON object mapping each column to its inferred data type.
Return ONLY valid JSON. No explanation, no markdown.
"""

PARAMETER temperature 0.1
PARAMETER stop "<|eot_id|>"
```

```bash
# Register model with Ollama
ollama create schema-agent -f Modelfile

# Test it
ollama run schema-agent "Columns: [CustomerID, FirstName, Email, Balance]"
```

Then update your `.env`:
```bash
SCHEMA_MODEL=schema-agent     # was: llama3.2
```

## Step 4: Evaluate the fine-tuned model

Before deploying, compare performance on a held-out test set:

```python
# python-agent/scripts/evaluate_model.py
import httpx, json

OLLAMA_URL   = "http://localhost:11434/api/generate"
BASE_MODEL   = "llama3.2"
TUNED_MODEL  = "schema-agent"

# Load held-out test examples (not used in training)
with open("test_data_schema.json") as f:
    tests = json.load(f)

def call_model(model, prompt):
    r = httpx.post(OLLAMA_URL, json={
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": 0.1}
    }, timeout=60)
    return r.json()["response"]

correct_base  = 0
correct_tuned = 0

for ex in tests:
    base_out  = call_model(BASE_MODEL,  ex["instruction"])
    tuned_out = call_model(TUNED_MODEL, ex["instruction"])

    # Simple exact-match on JSON keys (use a better metric for production)
    expected = json.loads(ex["output"])
    try:
        if json.loads(base_out) == expected:  correct_base  += 1
    except: pass
    try:
        if json.loads(tuned_out) == expected: correct_tuned += 1
    except: pass

n = len(tests)
print(f"Base model   ({BASE_MODEL}):  {correct_base}/{n} = {correct_base/n*100:.1f}%")
print(f"Tuned model  ({TUNED_MODEL}): {correct_tuned}/{n} = {correct_tuned/n*100:.1f}%")
```

Only deploy the fine-tuned model if it outperforms the base model on your test set.

## Free model recommendations by agent task

| Agent task         | Recommended base model | Size   | Why                                    |
|--------------------|------------------------|--------|----------------------------------------|
| Schema detection   | llama3.2:3b            | 2 GB   | Strong instruction following, fast     |
| Column classif.    | mistral:7b             | 4 GB   | Better reasoning for ambiguous mapping |
| Transform rules    | phi3:mini              | 2.3 GB | Fast, good at structured output        |
| All tasks (slower) | llama3.2:8b            | 5 GB   | Best accuracy if you have the VRAM     |

All models pull free from Ollama:
```bash
ollama pull llama3.2        # 3b, default
ollama pull llama3.2:8b     # 8b, better accuracy
ollama pull mistral
ollama pull phi3
```

## Claude Code instructions for this layer

1. The training pipeline is intentionally separate from the agent runtime — don't mix them
2. Training scripts live in `python-agent/scripts/` and are run manually, not by the agent
3. The `training_examples` table should be populated by the agents themselves — add
   logging to each agent's `_callback` method to INSERT every prompt/response pair
4. Fine-tuning requires a GPU — for a small company, a single RTX 3060 (12GB) or
   rented GPU hour on RunPod/Vast.ai (~$0.20/hr) is sufficient for LoRA
5. Never fine-tune on incorrectly labeled data — human review of `is_correct` is essential
