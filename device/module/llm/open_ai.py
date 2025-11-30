import asyncio
import os
from typing import Any, Dict, List, Optional
from container import container
from module.llm.base import LLM

from openai import OpenAI
from config import LLM_API_KEY, LLM_BASE_URL
from log import setup_logger
logger = setup_logger(__name__)
semaphore = asyncio.Semaphore(3)

class OpenAIAgent(LLM):
    def __init__(self, base_url, api_key, model, extra_headers = None):
        default_headers: Dict[str, str] = {
            "User-Agent": os.environ.get("LLM_USER_AGENT", "curl/8.4.0"),
            "Accept": "application/json",
        }

        if extra_headers:
            default_headers.update(extra_headers)
            
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            default_headers=default_headers
        )
        self.model = model
        container.register("agent", self)
        
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
        async with semaphore:
            messages = []
            if history:
                messages.extend(history)
            messages.append({"role": "system", "content": prompt_system})
            if image is not None:
                base64_image = self.encode_image(image)
                messages.append(
                    {
                        "role": "user", 
                        "content": [
                            {"type": "text", "text": question}, 
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    })
            else:
                messages.append({"role": "user", "content": question})
                
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
            )
            processed_response = self._process_output_answer(response.choices[0].message.content)
            logger.debug(f"Processed response: {processed_response}")  
            return processed_response
        


async def main():
    llm = OpenAIAgent(LLM_BASE_URL, LLM_API_KEY, "google/gemma-3-27b-it-qat-q4_0-gguf:Q4_0")  
    answer = await llm.get_answer(
        question="Làm sao để nấu ăn ngon?",
        prompt_system="Bạn là trợ lý AI hữu ích.",
    )

if __name__ == "__main__":
    asyncio.run(main())
    