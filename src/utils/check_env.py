"""Print environment info: Python, PyTorch/CUDA, and key package versions.

Run with: python -m src.utils.check_env
"""

import platform
import sys

KEY_PACKAGES = [
    "numpy",
    "segmentation_models_pytorch",
    "transformers",
    "albumentations",
    "cv2",
]


def main() -> None:
    print(f"Python: {sys.version.split()[0]} ({platform.platform()})")

    try:
        import torch

        print(f"PyTorch: {torch.__version__}")
        cuda_available = torch.cuda.is_available()
        print(f"CUDA available: {cuda_available}")
        if cuda_available:
            print(f"GPU: {torch.cuda.get_device_name(0)}")
    except ImportError:
        print("PyTorch: not installed")

    for pkg in KEY_PACKAGES:
        try:
            module = __import__(pkg)
            version = getattr(module, "__version__", "unknown")
            print(f"{pkg}: {version}")
        except ImportError:
            print(f"{pkg}: not installed")


if __name__ == "__main__":
    main()
