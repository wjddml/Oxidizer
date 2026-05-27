# src/llm/base_client.py
from abc import ABC, abstractmethod
from typing import List, Dict

class BaseLLMClient(ABC):
    """모든 LLM 클라이언트의 공통 인터페이스"""
    
    @abstractmethod
    def generate(self, messages: List[Dict[str, str]]) -> str:
        """
        LLM API를 호출하고 결과 텍스트를 반환합니다.
        :param messages: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}] 형태의 리스트
        :return: 생성된 코드 또는 텍스트 응답
        """
        pass