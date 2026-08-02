from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class TesseractOCR:
    """OCR adapter using Tesseract (pytesseract) with safe fallback."""

    def extract_text(self, content: bytes, filename: str = "", content_type: str = "") -> dict[str, Any]:
        settings = get_settings()
        if not settings.ocr_enabled:
            return {"engine": "disabled", "text": "", "confidence": 0.0}

        lower = (filename or "").lower()
        is_image = content_type.startswith("image/") or lower.endswith(
            (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")
        )
        if not is_image:
            # Best-effort plain text decode for non-images
            try:
                text = content.decode("utf-8", errors="ignore").strip()
            except Exception:  # noqa: BLE001
                text = ""
            return {"engine": "text-decode", "text": text[:5000], "confidence": 0.4 if text else 0.0}

        try:
            import io

            import pytesseract
            from PIL import Image

            if settings.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
            image = Image.open(io.BytesIO(content))
            text = pytesseract.image_to_string(image)
            return {
                "engine": "tesseract",
                "text": (text or "").strip(),
                "confidence": 0.85 if text and text.strip() else 0.2,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tesseract OCR unavailable: %s", exc)
            return {
                "engine": "fallback",
                "text": f"[OCR unavailable for {filename}. Install Tesseract + pytesseract + Pillow.]",
                "confidence": 0.0,
                "error": str(exc),
            }


tesseract_ocr = TesseractOCR()
