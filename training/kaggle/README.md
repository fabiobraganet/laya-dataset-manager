# Fine-tune smoke executor

`submit.sh` creates 64 explicitly synthetic typed `noul` decisions, validates the Laya notebook path, disables model publishing and submits a private Kaggle notebook. It is a pipeline smoke test: its success criteria are a completed Kaggle run and a generated checkpoint, not model quality.

Run from Ubuntu as the user that owns `~/.kaggle/kaggle.json`:

```bash
sudo bash training/kaggle/submit.sh
```
