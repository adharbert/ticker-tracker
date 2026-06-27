# Training Guide — FinBERT Fine-Tuning Pipeline

> Claude Code: implement all files in `python-agent/training/` using this spec.
> Read `docs/PHASES.md` — fine-tuning is Phase 3. Do not start until you have
> 30+ labeled signals from Phase 2 production runs.

---

## Why fine-tune FinBERT?

The base `ProsusAI/finbert` model was trained on general financial news. Your signal
pipeline generates labels for specific tickers and event types. After running Phase 2
for several days, you accumulate examples where FinBERT's sentiment was right or wrong.
Fine-tuning on your labeled data makes the model more accurate for your specific use case.

**Decision tree: do you need fine-tuning?**

```
Does base FinBERT sentiment agree with your human labels on 30+ examples?
│
├─ YES (>85% agreement) → Fine-tuning unlikely to help. Collect more data.
│
└─ NO → Is the disagreement systematic?
         │
         ├─ YES (e.g. "rate hike" consistently scored as neutral, not bearish)
         │    → Fine-tune with LoRA (this doc)
         │
         └─ NO (random errors) → Improve the impact_reasoner prompt first
```

---

## Step 1: Collect training labels

### `python-agent/training/collect_labels.py`

Exports all human-reviewed training examples from PostgreSQL in the format
expected by the fine-tuning script.

```python
import os, json, psycopg2

DB_CONN = os.getenv("DB_CONNECTION", "postgresql://postgres:postgres@localhost/news_market")
MIN_EXAMPLES = 30


def export_labels(output_path: str = "training_data.json"):
    """
    Export human-reviewed FinBERT labels from PostgreSQL.
    The training_examples table is populated during Phase 2 production runs.
    Human reviewer marks is_correct and optionally sets human_label.
    """
    conn = psycopg2.connect(DB_CONN)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT headline, body, finbert_label, finbert_score,
                   human_label, is_correct
            FROM training_examples
            WHERE is_correct IS NOT NULL
            ORDER BY created_at
        """)
        rows = cur.fetchall()

    conn.close()

    if len(rows) < MIN_EXAMPLES:
        print(f"Only {len(rows)} labeled examples — need {MIN_EXAMPLES}+ before fine-tuning.")
        return

    # Use human_label if provided, otherwise use finbert_label (when is_correct=True)
    examples = []
    for headline, body, finbert_label, score, human_label, is_correct in rows:
        label = human_label if human_label else (finbert_label if is_correct else None)
        if label is None:
            continue  # skip examples where model was wrong but no correction given

        text = (headline or "") + " " + (body or "")
        examples.append({
            "text":  text[:512].strip(),
            "label": label,       # positive | negative | neutral
        })

    with open(output_path, "w") as f:
        json.dump(examples, f, indent=2)

    print(f"Exported {len(examples)} labeled examples to {output_path}")
    label_dist = {}
    for ex in examples:
        label_dist[ex["label"]] = label_dist.get(ex["label"], 0) + 1
    print(f"Label distribution: {label_dist}")


if __name__ == "__main__":
    export_labels()
```

---

## Step 2: Fine-tune FinBERT with LoRA

### `python-agent/training/train_finbert.py`

Uses HuggingFace PEFT (Parameter-Efficient Fine-Tuning) with LoRA.
Requires GPU — even a single RTX 3060 (12GB) is sufficient.
For CPU-only: reduce `per_device_train_batch_size` to 1 and expect slow training.

```python
"""
Fine-tune ProsusAI/finbert on labeled signals using LoRA.
Produces a fine-tuned model saved to ./checkpoints/finbert-signals/.
"""
import json, os
import torch
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    DataCollatorWithPadding,
)
from peft import LoraConfig, get_peft_model, TaskType

# ── Config ────────────────────────────────────────────────────────────────────
BASE_MODEL   = os.getenv("FINBERT_MODEL", "ProsusAI/finbert")
DATA_PATH    = "training_data.json"
OUTPUT_DIR   = "./checkpoints/finbert-signals"
LABEL2ID     = {"positive": 0, "negative": 1, "neutral": 2}
ID2LABEL     = {v: k for k, v in LABEL2ID.items()}


# ── 1. Load data ──────────────────────────────────────────────────────────────
with open(DATA_PATH) as f:
    raw = json.load(f)

dataset = Dataset.from_list(raw)
dataset = dataset.map(lambda ex: {"labels": LABEL2ID[ex["label"]]})
dataset = dataset.train_test_split(test_size=0.15, seed=42)


# ── 2. Tokenize ───────────────────────────────────────────────────────────────
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

def tokenize(batch):
    return tokenizer(batch["text"], truncation=True, max_length=512)

dataset = dataset.map(tokenize, batched=True)


# ── 3. Load model + attach LoRA ───────────────────────────────────────────────
model = AutoModelForSequenceClassification.from_pretrained(
    BASE_MODEL,
    num_labels=3,
    id2label=ID2LABEL,
    label2id=LABEL2ID,
)

lora_config = LoraConfig(
    task_type    = TaskType.SEQ_CLS,
    r            = 8,              # LoRA rank — lower = fewer params = faster
    lora_alpha   = 16,
    lora_dropout = 0.1,
    target_modules = ["query", "value"],   # BERT attention heads
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()
# Typically: trainable params ~0.5% of total — that's the point of LoRA


# ── 4. Training args ──────────────────────────────────────────────────────────
training_args = TrainingArguments(
    output_dir                  = OUTPUT_DIR,
    num_train_epochs            = 5,
    per_device_train_batch_size = 8,
    per_device_eval_batch_size  = 16,
    learning_rate               = 2e-4,
    weight_decay                = 0.01,
    eval_strategy               = "epoch",
    save_strategy               = "epoch",
    load_best_model_at_end      = True,
    metric_for_best_model       = "eval_loss",
    fp16                        = torch.cuda.is_available(),
    report_to                   = "none",
    logging_steps               = 10,
)


# ── 5. Train ──────────────────────────────────────────────────────────────────
trainer = Trainer(
    model           = model,
    args            = training_args,
    train_dataset   = dataset["train"],
    eval_dataset    = dataset["test"],
    tokenizer       = tokenizer,
    data_collator   = DataCollatorWithPadding(tokenizer),
)

trainer.train()
trainer.save_model(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

print(f"\nFine-tuned model saved to: {OUTPUT_DIR}")
print("Test it with: python -c \"from evaluate_model import compare; compare()\"")
```

---

## Step 3: Evaluate fine-tuned vs base model

### `python-agent/training/evaluate_model.py`

Compares fine-tuned model accuracy against base FinBERT on the held-out test set.
Only swap in the fine-tuned model if it outperforms on your test set.

```python
"""
Compare fine-tuned FinBERT against base model on held-out test data.
Run this after train_finbert.py completes.
"""
import json, os
import torch
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
from peft import PeftModel

BASE_MODEL  = os.getenv("FINBERT_MODEL",   "ProsusAI/finbert")
TUNED_DIR   = "./checkpoints/finbert-signals"
TEST_PATH   = "test_data.json"            # manually curated, NOT in training set
LABEL2ID    = {"positive": 0, "negative": 1, "neutral": 2}


def load_base_pipeline():
    return pipeline("text-classification", model=BASE_MODEL, return_all_scores=True)


def load_tuned_pipeline():
    tokenizer = AutoTokenizer.from_pretrained(TUNED_DIR)
    base      = AutoModelForSequenceClassification.from_pretrained(BASE_MODEL)
    model     = PeftModel.from_pretrained(base, TUNED_DIR)
    model.eval()
    return pipeline("text-classification", model=model, tokenizer=tokenizer,
                    return_all_scores=True)


def top_label(results: list) -> str:
    return max(results, key=lambda r: r["score"])["label"]


def evaluate(pipe, examples: list) -> dict:
    correct = 0
    for ex in examples:
        prediction = top_label(pipe(ex["text"][:512])[0])
        if prediction.lower() == ex["label"].lower():
            correct += 1

    accuracy = correct / len(examples)
    return {"accuracy": accuracy, "correct": correct, "total": len(examples)}


def compare():
    if not os.path.exists(TEST_PATH):
        print(f"Test data not found: {TEST_PATH}")
        print("Create this file with examples NOT used in training.")
        return

    with open(TEST_PATH) as f:
        tests = json.load(f)

    if len(tests) < 10:
        print(f"Only {len(tests)} test examples — need at least 10 for a meaningful comparison.")
        return

    print("Loading base FinBERT...")
    base_result  = evaluate(load_base_pipeline(), tests)

    print("Loading fine-tuned model...")
    tuned_result = evaluate(load_tuned_pipeline(), tests)

    print(f"\nBase FinBERT ({BASE_MODEL}):")
    print(f"  Accuracy: {base_result['accuracy']:.1%} ({base_result['correct']}/{base_result['total']})")

    print(f"\nFine-tuned model ({TUNED_DIR}):")
    print(f"  Accuracy: {tuned_result['accuracy']:.1%} ({tuned_result['correct']}/{tuned_result['total']})")

    delta = tuned_result["accuracy"] - base_result["accuracy"]
    print(f"\nDelta: {delta:+.1%}")

    if delta > 0.05:
        print("\nFine-tuned model is meaningfully better. Update FINBERT_MODEL in .env to:")
        print(f"  FINBERT_MODEL={TUNED_DIR}")
    elif delta > 0:
        print("\nSmall improvement. Collect more labeled data before deploying.")
    else:
        print("\nNo improvement. Keep using base FinBERT. Check label quality.")


if __name__ == "__main__":
    compare()
```

---

## Step 4: Deploy fine-tuned model

If `evaluate_model.py` shows meaningful improvement (>5%), swap in the fine-tuned model:

```bash
# In python-agent/.env
FINBERT_MODEL=./checkpoints/finbert-signals

# The sentiment_agent.py already reads FINBERT_MODEL from env — no code changes needed.
# Restart the Python agent process to pick up the new model path.
```

The fine-tuned model loads from disk using `AutoModelForSequenceClassification`
plus the PEFT adapter — `sentiment_agent.py` already handles this through the
HuggingFace `pipeline()` interface.

---

## How training examples are collected (Phase 2)

During Phase 2, the Python agent automatically logs FinBERT outputs to PostgreSQL:

```python
# Add to agents/sentiment_agent.py after score_sentiment() returns
import psycopg2, os

def log_training_example(ticker: str, headline: str, body: str, sentiment_result: dict, signal_id: str = None):
    """Log FinBERT output for future training. Human reviews is_correct later."""
    conn = psycopg2.connect(os.getenv("DB_CONNECTION"))
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO training_examples
                    (ticker, headline, body, finbert_label, finbert_score, signal_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (ticker, headline, body,
                  sentiment_result["sentiment"],
                  sentiment_result["confidence"],
                  signal_id))
    conn.close()
```

Human review workflow:
1. Run Phase 2 for several days to accumulate 30+ signals
2. In PostgreSQL: `SELECT id, ticker, headline, finbert_label FROM training_examples WHERE is_correct IS NULL LIMIT 50`
3. For each row: set `is_correct = true` if the label looks right, or set `is_correct = false` AND `human_label = 'correct_label'`
4. Once 30+ examples are reviewed, run `collect_labels.py` then `train_finbert.py`

---

## Hardware requirements

| Setup                   | Time to train (50 examples) | Notes                              |
|-------------------------|-----------------------------|------------------------------------|
| CPU only                | ~30 min                     | Slow but works; reduce batch size  |
| NVIDIA RTX 3060 (12GB)  | ~2 min                      | Comfortable; recommended           |
| NVIDIA RTX 4090 (24GB)  | ~30 sec                     | Very fast; overkill for this scale |
| Rented GPU (RunPod)     | ~5 min (includes startup)   | ~$0.20/hr for an A4000             |

LoRA trains only ~0.5% of model parameters — this is why even a small GPU or CPU works.

---

## Claude Code instructions for this layer

1. Training scripts live in `python-agent/training/` and are run manually, not by the agent
2. Never mix training data with test data — `test_data.json` must contain examples
   that were never in `training_data.json`
3. The `PEFT` library (`pip install peft`) must be in `requirements.txt` for Phase 3
4. Fine-tuned model checkpoints are large (~400MB) — add `checkpoints/` to `.gitignore`
5. Only fine-tune when you have systematic errors — random errors are fixed by improving
   prompts or collecting more diverse training data
