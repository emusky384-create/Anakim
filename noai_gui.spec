# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = [], [], []

MODULES = [
    "torch", "diffusers", "transformers", "accelerate", "huggingface_hub",
    "safetensors", "controlnet_aux", "color_matcher", "skimage", "scipy",
    "cv2", "numpy", "PIL", "piexif", "watermark_remover", "watermark_profiles",
    "img2img_runner", "metadata_handler", "constants", "utils", "c2pa",
    "extractor", "injector", "cleaner", "cloner", "image_formats",
    "image_output", "progress", "download_ui", "ctrlregen",
]
for m in MODULES:
    try:
        d, b, h = collect_all(m)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

for m in ["torch", "diffusers", "transformers", "accelerate", "huggingface_hub",
          "safetensors", "numpy", "pillow", "piexif", "controlnet-aux",
          "color-matcher", "scikit-image"]:
    try:
        datas += copy_metadata(m)
    except Exception:
        pass

a = Analysis(
    ["app.py"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["matplotlib", "IPython", "pytest", "notebook", "torch.distributed"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name="NoAI-Watermark", console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="NoAI-Watermark")
