# Deploying the demo to Hugging Face Spaces

> **Status (2026-11-22): not deployed.** Hugging Face now requires a PRO subscription to host Gradio or Docker
> Spaces, including on the free `cpu-basic` hardware (the upload returned `402 Payment Required`). The live demo is
> the Colab notebook instead (`notebooks/demo_colab.ipynb`). A private Space `AdrijaS722744/wheat-disease-severity`
> was created but holds no files. The prepared Space folder is kept (`python -m src.demo.build_space`).
>
> **Free hosting on ZeroGPU** may become possible once the Hugging Face account is 30 days old. Check then:
> 1. That the account can actually create or switch a Gradio Space to ZeroGPU hardware without PRO (Hugging Face's
>    rules change; read the current Spaces pricing and ZeroGPU pages first).
> 2. ZeroGPU runs on GPU only inside functions decorated with `@spaces.GPU` and needs the `spaces` package; the
>    pipeline here runs on CPU (`Pipeline(device="cpu")`), so decide whether to add the decorator around
>    `Pipeline.analyse` and pass `device="cuda"`, and re-check that the results match the CPU run (within 0.001 points
>    on the three examples).
> 3. ZeroGPU supports specific torch versions only; check that `torch==2.5.1` is one of them, or change it and
>    re-run the tests.
> 4. `sam2` is a source package: the Space build must install torch first and then
>    `SAM2_BUILD_CUDA=0 pip install --no-build-isolation sam2==1.1.0` (see `demo/requirements.txt`); a plain
>    `requirements.txt` line may build it in an isolated environment that downloads a second torch, or fail.
> 5. Free-tier quotas (GPU minutes per day for visitors) and cold-start time; say so on the Space page.
> 6. Then follow the steps below, choosing ZeroGPU instead of CPU basic, and replace the Colab badge in the README
>    with the Space link (or keep both).

The steps below were written for the free CPU hardware (2 vCPU, 16 GB RAM). The first start takes several minutes: it installs
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
- Then Settings -> **Change visibility** -> Public, and add the link to the top of the README.

## Updating

Re-run `python -m src.demo.build_space --out dist/hf_space_new` and upload again with the same command (point it
at the new folder). The demo must stay on the frozen `final-v1` pipeline; `demo/final_policy.json` records the tag.
