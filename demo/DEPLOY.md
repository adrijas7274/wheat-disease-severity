# Deploying the demo to Hugging Face Spaces

The Space runs on the free CPU hardware (2 vCPU, 16 GB RAM). The first start takes several minutes: it installs
packages, and the app downloads SAM 2.1 tiny (156 MB, checksum verified) and the SegFormer-B0 base weights.

## 1. Build the Space folder (on your PC, in the repository)

```bash
.venv/Scripts/python -m src.demo.export_policy      # only if demo/final_policy.json is missing
.venv/Scripts/python -m src.demo.build_space        # creates dist/hf_space (about 16 MB)
```

Check `dist/hf_space`. It should hold `app.py`, `src/`, `configs/config.yaml`, `demo/final_policy.json`,
`demo/examples/` (3 CC BY 4.0 JIC photos + SOURCES.md), `checkpoints/segformer_b0.pt`, `requirements.txt`,
`README.md` and `.gitattributes`. **No PlantSeg images, gold ratings or experiment folders.**

## 2. Create the Space (in the browser)

1. Sign in at https://huggingface.co (create the account first).
2. Click your avatar, then **New Space**.
3. Name: e.g. `wheat-severity-demo`. Licence: **cc-by-nc-4.0**. SDK: **Gradio**. Hardware: **CPU basic (free)**.
   Visibility: start with **Private** and switch to Public after you have checked it.
4. Click **Create Space**.

## 3. Upload the files

Easiest, with the command line (from the repository):

```bash
.venv/Scripts/pip install -U "huggingface_hub[cli]"
.venv/Scripts/huggingface-cli login                 # paste a token with WRITE access (Settings -> Access Tokens)
.venv/Scripts/huggingface-cli upload <your-username>/wheat-severity-demo dist/hf_space . --repo-type space
```

Never commit or paste the token anywhere else. Alternative without the command line: on the Space page, **Files ->
Add file -> Upload files**, drag in the *contents* of `dist/hf_space` (keep the folder structure), commit.

## 4. Watch it start

Open the Space's **Logs** tab. The build installs `requirements.txt`; then the app prints
`Downloading SAM 2.1 tiny ...` and finally `Running on local URL`. The page then shows the demo.

If the build fails on `sam2` (it compiles an optional CUDA extension), add a Space variable
`SAM2_BUILD_CUDA` = `0` (Settings -> Variables and secrets) and click **Factory rebuild**.

## 5. Check before making it public

- Try each example: choose the disease, tap the middle of the main leaf; expect an answer in a few seconds.
- Read the disclaimer, limitations and credits on the page.
- Then Settings -> **Change visibility** -> Public, and put the link in the README (`TODO_DEMO_LINK`).

## Updating

Re-run `python -m src.demo.build_space --out dist/hf_space_new` and upload again with the same command (point it
at the new folder). The demo must stay on the frozen `final-v1` pipeline; `demo/final_policy.json` records the tag.
