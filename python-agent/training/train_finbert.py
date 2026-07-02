"""
train_finbert.py — Fine-tune ProsusAI/finbert on labeled signals using LoRA.

Requires: pip install peft datasets
Input:    training_data.json (produced by collect_labels.py)
Output:   ./checkpoints/finbert-signals/

Usage: python -m training.train_finbert
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
from dotenv import load_dotenv

load_dotenv()

BASE_MODEL = os.getenv("FINBERT_MODEL", "ProsusAI/finbert")
DATA_PATH  = "training_data.json"
OUTPUT_DIR = "./checkpoints/finbert-signals"
LABEL2ID   = {"positive": 0, "negative": 1, "neutral": 2}
ID2LABEL   = {v: k for k, v in LABEL2ID.items()}


def train():
    if not os.path.exists(DATA_PATH):
        print(f"Missing {DATA_PATH} — run: python -m training.collect_labels first.")
        return

    with open(DATA_PATH) as f:
        raw = json.load(f)

    if len(raw) < 30:
        print(f"Only {len(raw)} examples — need 30+ to train meaningfully.")
        return

    print(f"Training on {len(raw)} examples using base model: {BASE_MODEL}")

    dataset = Dataset.from_list(raw)
    dataset = dataset.map(lambda ex: {"labels": LABEL2ID[ex["label"]]})
    dataset = dataset.train_test_split(test_size=0.15, seed=42)

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

    def tokenize(batch):
        return tokenizer(batch["text"], truncation=True, max_length=512)

    dataset = dataset.map(tokenize, batched=True)

    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL, num_labels=3, id2label=ID2LABEL, label2id=LABEL2ID,
    )

    lora_config = LoraConfig(
        task_type      = TaskType.SEQ_CLS,
        r              = 8,
        lora_alpha     = 16,
        lora_dropout   = 0.1,
        target_modules = ["query", "value"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

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

    trainer = Trainer(
        model         = model,
        args          = training_args,
        train_dataset = dataset["train"],
        eval_dataset  = dataset["test"],
        tokenizer     = tokenizer,
        data_collator = DataCollatorWithPadding(tokenizer),
    )

    trainer.train()
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    print(f"\nFine-tuned model saved to: {OUTPUT_DIR}")
    print("Evaluate with: python -m training.evaluate_model")


if __name__ == "__main__":
    train()
