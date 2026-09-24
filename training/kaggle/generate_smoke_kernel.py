"""Prepare a private Kaggle smoke run from Laya's official fine-tuning notebook."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOTEBOOK = ROOT / "laya_finetune_smoke.ipynb"
DATASET = ROOT / "synthetic_typed_decisions.jsonl"
UPSTREAM = "https://raw.githubusercontent.com/NandhaKishorM/laya/main/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb"

def example(index: int, urgent: bool) -> dict:
    return {
        "id": f"synthetic-{index:03d}",
        "state": json.dumps({"text": f"Cliente {index} solicita {'atendimento urgente' if urgent else 'atendimento normal'}."}, ensure_ascii=False),
        "questions": json.dumps({"urgente": {"type": "noul", "instructions": "O atendimento é urgente?"}}, ensure_ascii=False),
        "gold": json.dumps({"urgente": {"label": "true" if urgent else "false", "probabilities": {"false": 0.0 if urgent else 1.0, "true": 1.0 if urgent else 0.0}}}, ensure_ascii=False),
    }

def validate_examples(rows: list[dict]) -> None:
    """Reject malformed or non-synthetic input before a Kaggle submission."""
    if len(rows) < 2:
        raise ValueError("The smoke dataset must contain at least two examples.")

    labels = set()
    for position, row in enumerate(rows, start=1):
        required = {"id", "state", "questions", "gold"}
        if set(row) != required or not row["id"].startswith("synthetic-"):
            raise ValueError(f"Example {position} has an invalid synthetic schema.")

        state = json.loads(row["state"])
        questions = json.loads(row["questions"])
        gold = json.loads(row["gold"])
        if not isinstance(state.get("text"), str) or not state["text"].strip():
            raise ValueError(f"Example {position} has no state text.")
        if questions.get("urgente") != {
            "type": "noul", "instructions": "O atendimento é urgente?"
        }:
            raise ValueError(f"Example {position} has an invalid question.")

        answer = gold.get("urgente")
        if not isinstance(answer, dict) or answer.get("label") not in {"true", "false"}:
            raise ValueError(f"Example {position} has an invalid gold label.")
        probabilities = answer.get("probabilities")
        if (
            not isinstance(probabilities, dict)
            or set(probabilities) != {"true", "false"}
            or sum(probabilities.values()) != 1.0
        ):
            raise ValueError(f"Example {position} has invalid probabilities.")
        labels.add(answer["label"])

    if labels != {"true", "false"}:
        raise ValueError("The smoke dataset must contain both labels.")

def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    rows = [example(i, i % 2 == 0) for i in range(64)]
    validate_examples(rows)
    print(f"Validated {len(rows)} synthetic test examples.")
    dataset_text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
    DATASET.write_text(dataset_text, encoding="utf-8")
    subprocess.run(["curl", "-fsSL", UPSTREAM, "-o", str(NOTEBOOK)], check=True)
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    for cell in notebook["cells"]:
        source = "".join(cell.get("source", []))
        if 'ds_train = load_dataset("LocalLLaMA/typed-decisions", "all", split="train")' in source:
            source = source.replace(
                'ds_train = load_dataset("LocalLLaMA/typed-decisions", "all", split="train")',
                'from pathlib import Path\n'
                f'Path("/kaggle/working/synthetic_typed_decisions.jsonl").write_text({dataset_text!r}, encoding="utf-8")\n'
                'ds_train = load_dataset("json", data_files="/kaggle/working/synthetic_typed_decisions.jsonl", split="train")',
            )
            cell["source"] = source.splitlines(keepends=True)
        if 'assert n_gpu >= 2' in source:
            cell["source"] = [
                "import torch\n",
                "assert torch.cuda.is_available(), 'Kaggle GPU is required'\n",
                "print('GPU:', torch.cuda.get_device_name(0))\n",
            ]
        if 'torchrun --standalone --nproc_per_node=2' in source:
            cell["source"] = source.replace("torchrun --standalone --nproc_per_node=2", "torchrun --standalone --nproc_per_node=1").splitlines(keepends=True)
        if 'UserSecretsClient' in source or 'api.upload_folder' in source:
            cell["source"] = ["print('Model publishing disabled for this private smoke run.')\n"]
        if 'ds_test = load_dataset("LocalLLaMA/typed-decisions", "all", split="test")' in source:
            cell["source"] = ["print('Evaluation skipped: this smoke run validates training and checkpoint generation.')\n"]
        if 'for item in predictions:' in source or 'report = {' in source:
            cell["source"] = ["print('Metrics skipped: this smoke run validates training and checkpoint generation.')\n"]
    NOTEBOOK.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "kernel-metadata.json").write_text(json.dumps({
        "id": "fabiobraganet/laya-dataset-manager-fine-tune-smoke-test",
        "title": "Laya Dataset Manager - Fine-tune Smoke Test",
        "code_file": NOTEBOOK.name,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": "true",
        "enable_gpu": "true",
        "enable_internet": "true",
        "machine_shape": "NvidiaTeslaT4",
    }, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
