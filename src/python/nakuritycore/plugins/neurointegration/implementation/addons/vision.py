from __future__ import annotations
import asyncio
from ...abstract.addons.vision import AbstractOCRVisionAddon
from PIL import Image
import pytesseract
import io

class PytesseractOCRVisionAddon(AbstractOCRVisionAddon):
    async def ocr_image_bytes(self, image_bytes: bytes, meta: dict) -> str:
        # run blocking I/O in threadpool
        def _sync_ocr():
            img = Image.open(io.BytesIO(image_bytes)).convert("L")
            return pytesseract.image_to_string(img)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync_ocr)

# -------------------------
# Example usage
# -------------------------
# async def on_context(self, game, message, silent, ws):
#     # message could be dict or string; if dict with image -> let addon process
#     if isinstance(message, dict) and ("image" in message or "image_url" in message or "image_bytes" in message):
#         await self.vision_addon.handle_incoming(message, ws)
#     else:
#         # normal handling...
#         ...