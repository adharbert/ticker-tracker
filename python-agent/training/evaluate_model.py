"""
evaluate_model.py — Compare fine-tuned FinBERT against base model.

Run after train_finbert.py. Uses test_data.json (examples NOT in training set).
Only swap in the fine-tuned model if it outperforms base FinBERT by >5%.

Usage: python -m training.evaluate_model
"""

import json, os
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
from peft import PeftModel
from dotenv import load_dotenv

load_dotenv()

BASE_MODEL = os.getenv("FINBERT_MODEL", "ProsusAI/finbert")
TUNED_DIR  = "./checkpoints/finbert-signals"
TEST_PATH  = "test_data.json"


def load_base():
    return pipeline("text-classification", model=BASE_MODEL, top_k=None)


def load_tuned():
    tokenizer = AutoTokenizer.from_pretrained(TUNED_DIR)
    base  = AutoModelForSequenceClassification.from_pretrained(BASE_MODEL)
    model = PeftModel.from_pretrained(base, TUNED_DIR)
    model.eval()
    return pipeline("text-classification", model=model, tokenizer=tokenizer, top_k=None)


def top_label(result) -> str:
    return max(result, key=lambda r: r["score"])["label"]


def evaluate(pipe, examples: list) -> dict:
    correct = sum(
        1 for ex in examples
        if top_label(pipe(ex["text"][:512])[0]).lower() == ex["label"].lower()
    )
    return {"accuracy": correct / len(examples), "correct": correct, "total": len(examples)}


def compare():
    if not os.path.exists(TEST_PATH):
        print(f"Missing {TEST_PATH}")
        print("Create this file with labeled examples that were NOT used in training.")
        print('Format: [{"text": "headline body...", "label": "positive|negative|neutral"}, ...]')
        return

    with open(TEST_PATH) as f:
        tests = json.load(f)

    if len(tests) < 10:
        print(f"Only {len(tests)} test examples — need at least 10 for a meaningful comparison.")
        return

    if not os.path.exists(TUNED_DIR):
        print(f"Fine-tuned model not found at {TUNED_DIR}. Run train_finbert.py first.")
        return

    print(f"Evaluating on {len(tests)} test examples...\n")

    print("Loading base FinBERT...")
    base_result = evaluate(load_base(), tests)

    print("Loading fine-tuned model...")
    tuned_result = evaluate(load_tuned(), tests)

    print(f"\nBase FinBERT:    {base_result['accuracy']:.1%}  ({base_result['correct']}/{base_result['total']})")
    print(f"Fine-tuned model:{tuned_result['accuracy']:.1%}  ({tuned_result['correct']}/{tuned_result['total']})")

    delta = tuned_result["accuracy"] - base_result["accuracy"]
    print(f"Delta:           {delta:+.1%}")

    if delta > 0.05:
        print(f"\nFine-tuned model is meaningfully better (+{delta:.1%}).")
        print(f"To deploy, update FINBERT_MODEL in .env:\n  FINBERT_MODEL={TUNED_DIR}")
    elif delta > 0:
        print("\nSmall improvement. Collect more labeled data before deploying.")
    else:
        print("\nNo improvement. Keep using base FinBERT. Check label quality or improve prompts.")


if __name__ == "__main__":
    compare()
