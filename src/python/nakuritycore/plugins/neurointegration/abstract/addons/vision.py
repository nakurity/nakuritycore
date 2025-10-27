# vision_addon.py
from __future__ import annotations
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional
import base64
import aiohttp

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class AbstractOCRVisionAddon(ABC):
    """
    Pluggable addon that provides OCR-based alternative vision for Neuro when
    the main vision pipeline is unavailable.

    Usage:
      - subclass and implement `ocr_image_bytes`
      - create instance and call `attach(backend)` from your backend subclass (e.g. in on_startup)
      - when your backend receives context/event payloads that include images,
        call addon.handle_incoming(payload, ws) so the addon can process them.

    Design notes:
      - The addon does not assume how images arrive. It accepts:
          * raw bytes via payload["image_bytes"] (base64 or bytes)
          * image URL via payload["image_url"]
          * or a dict payload containing an "image" key
      - After OCR, the addon reports plain-text context back to Neuro by calling
        backend.send_context(...) (this follows the CoolCat API's `send_context` semantics).
    """

    def __init__(self, backend, concurrency: int = 2):
        """
        backend: an instance of your AbstractNeuroBackend (or compatible) that
                 exposes an async method `send_context(message: str, silent: bool=True)`
                 and ideally `host/port` metadata (not strictly required).
        concurrency: max concurrent OCR workers
        """
        self.backend = backend
        self._queue: asyncio.Queue[tuple[bytes, dict[str, Any]]] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._concurrency = max(1, concurrency)

    def attach(self):
        """Start workers. Call this after your backend is ready (e.g. in on_startup)."""
        if self._running:
            return
        self._running = True
        for _ in range(self._concurrency):
            t = asyncio.create_task(self._worker_loop())
            self._workers.append(t)
        logger.debug("OCR addon attached and workers started (n=%d)", self._concurrency)

    async def detach(self):
        """Stop workers gracefully."""
        self._running = False
        # push sentinel items
        for _ in range(len(self._workers)):
            await self._queue.put((b"", {}))
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.debug("OCR addon detached")

    async def _worker_loop(self):
        while True:
            img_bytes, meta = await self._queue.get()
            if not self._running and not img_bytes:
                break  # sentinel when shutting down
            try:
                text = await self._safe_ocr(img_bytes, meta)
                if text and text.strip():
                    # send to Neuro via backend; backend must provide send_context
                    # This uses the same semantics as AbstractNeuroAPI.send_context().
                    try:
                        # prefer backend.send_context if present; fallback to generic send
                        send_ctx = getattr(self.backend, "send_context", None)
                        if send_ctx is None:
                            # some backends may have a differently named helper; try send_command_data
                            send_cmd = getattr(self.backend, "send_command_data", None)
                            if send_cmd:
                                # format a context command payload dict (caller may want orjson)
                                payload = {"command": "context", "game": meta.get("game"), "data": {"message": text, "silent": True}}
                                await send_cmd(payload)
                            else:
                                logger.warning("Backend has no send_context/send_command_data hook; OCR result dropped")
                        else:
                            await send_ctx(text, True)
                    except Exception:
                        logger.exception("Failed to send OCR context back to backend")
            except Exception:
                logger.exception("OCR worker error")
            finally:
                self._queue.task_done()

    async def _safe_ocr(self, img_bytes: bytes, meta: dict) -> str:
        try:
            return await self.ocr_image_bytes(img_bytes, meta)
        except Exception:
            logger.exception("ocr_image_bytes failed")
            return ""

    async def handle_incoming(self, payload: dict, ws=None):
        """
        Called by backend when it receives a payload that may contain image data.
        The payload may be the `data` value from the Neuro message, or an event dict.

        Recognised keys:
          - "image_bytes": base64-encoded string or raw bytes
          - "image_url": URL to fetch
          - "image": nested dict with either "url" or "bytes"
        meta may include "game", "source", etc. Passed to ocr handler.
        """
        img_bytes: Optional[bytes] = None
        meta = {"game": payload.get("game")}

        # raw b64 string
        if "image_bytes" in payload:
            v = payload["image_bytes"]
            if isinstance(v, str):
                try:
                    img_bytes = base64.b64decode(v)
                except Exception:
                    logger.exception("failed to decode base64 image_bytes")
                    return
            elif isinstance(v, (bytes, bytearray)):
                img_bytes = bytes(v)

        # image field
        if img_bytes is None and "image" in payload:
            img = payload["image"]
            if isinstance(img, dict):
                if "bytes" in img:
                    b = img["bytes"]
                    if isinstance(b, str):
                        try:
                            img_bytes = base64.b64decode(b)
                        except Exception:
                            logger.exception("failed to decode base64 image.bytes")
                            return
                    else:
                        img_bytes = bytes(b)
                elif "url" in img:
                    payload["image_url"] = img["url"]

        # fetch url if provided
        if img_bytes is None and "image_url" in payload:
            url = payload["image_url"]
            try:
                img_bytes = await self._fetch_url_bytes(url)
            except Exception:
                logger.exception("failed to fetch image url")
                return

        if img_bytes is None:
            logger.debug("No image found in payload for OCR")
            return

        # enqueue for OCR processing
        await self._queue.put((img_bytes, meta))

    async def _fetch_url_bytes(self, url: str) -> bytes:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, timeout=15) as resp:
                resp.raise_for_status()
                return await resp.read()

    @abstractmethod
    async def ocr_image_bytes(self, image_bytes: bytes, meta: dict) -> str:
        """
        Implement OCR on raw image bytes and return plain text.

        You can implement this with:
          - pytesseract (local Tesseract)
          - easyocr
          - cloud OCR (Google Vision, AWS Textract)
          - a custom ML model

        This is async so you can offload to threadpool or make async HTTP calls.
        """
        raise NotImplementedError
