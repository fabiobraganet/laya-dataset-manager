import base64, json
from pathlib import Path

UPSTREAM = "https://raw.githubusercontent.com/NandhaKishorM/laya/main/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb"

def prepare(run_dir: Path, kernel_ref: str, jsonl: str) -> None:
    """Build a private Kaggle kernel only from an immutable exported version."""
    import urllib.request
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "dataset.jsonl").write_text(jsonl, encoding="utf-8")
    notebook = json.load(urllib.request.urlopen(UPSTREAM, timeout=30))
    encoded = base64.b64encode(jsonl.encode()).decode()
    notebook["cells"].insert(0, {"cell_type":"code","execution_count":None,"metadata":{},"outputs":[],"source":["import base64\n",f"open('/kaggle/working/dataset.jsonl','wb').write(base64.b64decode('{encoded}'))\n"]})
    for cell in notebook.get("cells", []):
        source = "".join(cell.get("source", []))
        source = source.replace('load_dataset("LocalLLaMA/typed-decisions", "all", split="train")', 'load_dataset("json", data_files="/kaggle/working/dataset.jsonl", split="train")')
        if "UserSecretsClient" in source or "api.upload_folder" in source:
            source = "print('Publishing is managed by Laya Dataset Manager.')\n"
        cell["source"] = source.splitlines(keepends=True)
    (run_dir / "train.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
    (run_dir / "kernel-metadata.json").write_text(json.dumps({"id":kernel_ref,"title":kernel_ref.split("/",1)[1],"code_file":"train.ipynb","language":"python","kernel_type":"notebook","is_private":True,"enable_gpu":True,"enable_internet":True}), encoding="utf-8")
