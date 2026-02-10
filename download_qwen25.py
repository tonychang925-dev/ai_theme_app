from huggingface_hub import hf_hub_download

hf_hub_download(
    repo_id="Qwen/Qwen2.5-1.5B-Instruct-GGUF",
    filename="qwen2.5-1.5b-instruct-q5_k_m.gguf",
    local_dir="model_service/models/qwen2.5",
    local_dir_use_symlinks=False,
)
