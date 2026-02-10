from model_service.text_encoder import TextEncoder

encoder = TextEncoder()
vec = encoder.encode("英伟达发布新一代AI算力芯片")

print(vec.shape)
print(vec[0][:5])
