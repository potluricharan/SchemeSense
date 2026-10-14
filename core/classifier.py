"""Document-type classification (Phase 2).

Two signals are combined:
  1. Keyword rule-based classifier over the OCR text (reliable on real scans).
  2. ResNet50 (via transformers / torch) image-embedding few-shot classifier. It
     compares the document image's ResNet50 embedding against reference centroid
     embeddings placed under `data/reference_images/<doc_type>/*.jpg|png`.

Drop-in transfer-learning note: to fine-tune ResNet50 on a labelled set instead,
train any torch classifier on top of this module's `embed()` features and replace
`classify_image()` accordingly -- the rest of the pipeline is unchanged.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

import numpy as np

from core import config

log = logging.getLogger(__name__)

DOC_TYPES = [
    "aadhaar",
    "income_certificate",
    "caste_certificate",
    "ration_card",
    "disability_certificate",
    "certificate",
]

KEYWORDS = {
    "aadhaar": ["aadhaar", "uidai", "unique identification", "enrolment", "goa", "resident of india", "govt of india"],
    "income_certificate": ["income certificate", "annual income", "family income", "gross income", "income & caste",
                           "revenue department", "tehsildar"],
    "caste_certificate": ["caste certificate", "caste ", "community", "sc/st", "caste validity", "obc", "scheduled castes"],
    "ration_card": ["ration", "ration card", "pds", "public distribution", "food security", "household", "smart ration",
                    "card holder", "family members"],
    "disability_certificate": ["disability", "disability certificate", "percentage of disability", "benchmark", "mental retardation"],
}


def classify_text(text: str) -> tuple[str, float]:
    if not text or "[OCR error" in text:
        return "certificate", 0.0
    low = text.lower()
    scores = {}
    for dtype, words in KEYWORDS.items():
        score = 0
        for w in words:
            if w.strip() in low:
                score += 1
        scores[dtype] = score
    best = max(scores, key=scores.get)
    best_score = scores[best]
    if best_score == 0:
        return "certificate", 0.0
    confidence = min(0.99, best_score / 2.0)
    return best, confidence


@lru_cache(maxsize=1)
def _load_resnet():
    from transformers import AutoModel

    model_name = "microsoft/resnet-50"
    model = AutoModel.from_pretrained(model_name)
    model.eval()
    return model


_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)


def _preprocess(image) -> np.ndarray:
    """Resize -> centre-crop 224 -> normalize to the ImageNet distribution.
    Done in PIL/numpy so no torchvision dependency is required."""
    import PIL.Image

    img = image.convert("RGB")
    w, h = img.size
    size = 256
    scale = size / min(w, h)
    img = img.resize((max(256, int(w * scale)), max(256, int(h * scale))),
                     PIL.Image.BILINEAR)
    cw, ch = img.size
    left = (cw - 224) // 2
    top = (ch - 224) // 2
    img = img.crop((left, top, left + 224, top + 224))
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr -= np.array(_IMAGENET_MEAN, dtype=np.float32)
    arr /= np.array(_IMAGENET_STD, dtype=np.float32)
    return arr.transpose(2, 0, 1)  # (C, H, W)


def embed(image) -> np.ndarray:
    """ResNet50 embedding (global avg pool, 2048-d) for an image, using a
    manual ImageNet preprocessing pipeline (no torchvision dependency)."""
    import torch

    model = _load_resnet()
    pixel_values = torch.from_numpy(_preprocess(image)[None, ...])
    with torch.no_grad():
        outputs = model(pixel_values=pixel_values)
    feat = outputs.pooler_output  # (1, 2048, 1, 1) for ResNet
    return feat.squeeze(0).reshape(-1).numpy()


def _reference_centroids() -> dict[str, np.ndarray]:
    import PIL.Image
    from PIL import ImageFile

    ImageFile.LOAD_TRUNCATED_IMAGES = True
    root = config.PROJECT_ROOT / "data" / "reference_images"
    centroids: dict[str, list] = {}
    if not root.exists():
        return {}
    for dtype in DOC_TYPES:
        folder = root / dtype
        if not folder.exists():
            continue
        vecs = []
        for f in sorted(os.listdir(folder))[:20]:
            if f.lower().endswith((".jpg", ".jpeg", ".png")):
                try:
                    img = PIL.Image.open(folder / f).convert("RGB")
                    vecs.append(embed(img))
                except Exception:
                    continue
        if vecs:
            centroids[dtype] = np.mean(vecs, axis=0)
            centroids[dtype + "__count"] = len(vecs)
    return centroids


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def classify_image(image) -> tuple[str, float]:
    centroids = _reference_centroids()
    if not centroids:
        return "certificate", 0.0
    try:
        vec = embed(image)
    except Exception as exc:
        log.exception("ResNet50 embed failed")
        return "certificate", 0.0
    sims = {dtype: _cosine(vec, centroids[dtype]) for dtype in centroids if not dtype.endswith("__count")}
    best = max(sims, key=sims.get)
    conf = sims[best]
    if conf < 0.5:
        return "certificate", conf
    return best, conf


def classify(data: bytes, ocr_text: str = "") -> dict:
    """Combined document classification.

    Returns {"doc_type", "confidence", "text_method", "image_method"}.
    """
    import PIL.Image
    from PIL import ImageFile

    ImageFile.LOAD_TRUNCATED_IMAGES = True

    txt_type, txt_conf = None, 0.0
    if ocr_text:
        txt_type, txt_conf = classify_text(ocr_text)

    img_type, img_conf = "certificate", 0.0
    try:
        img = PIL.Image.open(__import__("io").BytesIO(data)).convert("RGB")
        if img_type:
            img_type, img_conf = classify_image(img)
    except Exception:
        log.warning("image classification skipped")

    # Text keyword signal wins; image similarity raises confidence when agreeing.
    if txt_type and txt_type != "certificate":
        final_type = txt_type
        confidence = max(txt_conf, min(0.99, img_conf * 0.8 + 0.2)) if img_type == txt_type else txt_conf
    else:
        final_type = img_type
        confidence = img_conf

    return {
        "doc_type": final_type,
        "confidence": round(min(0.99, confidence), 3),
        "text_method": f"{txt_type}:{round(txt_conf,2)}" if txt_type else "none",
        "image_method": f"{img_type}:{round(img_conf,2)}",
    }