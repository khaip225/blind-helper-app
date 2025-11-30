import asyncio
import base64
import io
import json
from pprint import pformat
import re
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image

import httpx
import numpy as np

from abc import ABC, abstractmethod
from log import setup_logger
# Số lượng yêu cầu vllm tối đa có thể gửi đồng thời
logger = setup_logger(__name__)


class TokenLimitExceeded(Exception):
    """Exception raised when token limit is exceeded."""
    pass


class LLM(ABC):

    def __init__(self):
        pass
    
    def encode_image(self, image: Image.Image | np.ndarray) -> str:
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(
            buffered.getvalue()).decode('utf-8')
        return img_base64


    def _process_output_answer(self, answer: str):
        cleaned = answer.strip()

        # Loại bỏ code fence nếu có
        is_start_with_json = cleaned.startswith("```json") and cleaned.endswith("```")
        is_start_with_no_json = cleaned.startswith("```") and cleaned.endswith("```")
        if not(is_start_with_json or is_start_with_no_json):
            return answer
        
        if is_start_with_json:
            cleaned = cleaned[7:-3].strip()
        elif is_start_with_no_json:
            cleaned = cleaned[3:-3].strip()
        # Thử parse JSON
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"JSONDecodeError: {e}")
            logger.debug(f"Raw content: {cleaned}")

            # Thử sanitize: escape các dấu " chưa hợp lệ trong value
            sanitized = re.sub(r'(?<!\\)"', r'\"', cleaned)  # thêm escape
            try:
                return json.loads(sanitized)
            except Exception as e2:
                logger.error(f"Sanitize failed: {e2}")
                return json.loads(answer)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return answer
        
    @abstractmethod
    async def get_answer(
        self,
        question: str,
        prompt_system: str = "Bạn là trợ lý AI hữu ích.",
        image=None,
        history: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.01,
        top_p: float = 0.5,
        max_tokens: Optional[int] = None,
    ) -> str:
        pass
            
    async def get_batch_answer(
        self,
        questions: List[str],
        prompt_system: str = "Bạn là trợ lý AI hữu ích.",
        image=None,
        history: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.1,
        top_p: float = 0.1,
        max_tokens=None,
    ) -> List[str]:
        # Sử dụng asyncio.gather để gửi nhiều yêu cầu đồng thời
        tasks = [
            self.get_answer(
                question=q,
                prompt_system=prompt_system,
                image=image,
                history=history,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
            )
            for q in questions
        ]
        return await asyncio.gather(*tasks)


