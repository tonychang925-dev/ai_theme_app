import torch
import numpy as np
from transformers import AutoTokenizer, AutoModel

MODEL_NAME = "bert-base-chinese"

def mean_pooling(last_hidden_state, attention_mask):
    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    return (last_hidden_state * mask).sum(1) / mask.sum(1)

def encode(text: str):
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModel.from_pretrained(MODEL_NAME)
    model.eval()

    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=128
    )

    with torch.no_grad():
        outputs = model(**inputs)

    emb = mean_pooling(outputs.last_hidden_state, inputs["attention_mask"])
    emb = emb[0].numpy()
    emb = emb / np.linalg.norm(emb)
    return emb

if __name__ == "__main__":
    v = encode("英伟达发布新一代AI算力芯片")
    print("向量维度:", v.shape)
    print("向量前5项:", v[:5])
