import torch
import numpy as np
from transformers import AutoTokenizer, AutoModel
from typing import List


class TextEncoder:
    """
    本地 Transformer 文本编码器（单例使用）
    - 使用 mean pooling
    - 输出 L2 归一化向量
    """

    def __init__(
        self,
        model_name: str = "bert-base-chinese",
        max_length: int = 256,
        device: str | None = None
    ):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.max_length = max_length

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.model.to(self.device)
        self.model.eval()

    @staticmethod
    def _mean_pooling(last_hidden_state, attention_mask):
        mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
        return (last_hidden_state * mask).sum(1) / mask.sum(1)

    def encode(self, texts: List[str] | str) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]

        inputs = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt"
        )

        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)

        embeddings = self._mean_pooling(
            outputs.last_hidden_state,
            inputs["attention_mask"]
        )

        embeddings = embeddings.cpu().numpy()
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings
