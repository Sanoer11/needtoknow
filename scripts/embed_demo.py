from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-small-en-v1.5")   # downloads once (~130 MB)

sentences = [
    "What does Neha earn?",
    "Neha Kapoor: INR 24 lakh per year",
    "annual leave days",
    "Employees get 24 days of paid leave per year",
    "Events flow through Kafka",
]

vectors = model.encode(sentences, normalize_embeddings=True)
print("Shape:", vectors.shape)          # (5, 384): 5 sentences, 384 numbers each
print("First 5 numbers of sentence 1:", vectors[0][:5])

# With normalized vectors, cosine similarity is just a dot product
sim = vectors @ vectors.T

print("\nSimilarity to each sentence:")
for i, s in enumerate(sentences):
    scores = "  ".join(f"{sim[i][j]:.2f}" for j in range(len(sentences)))
    print(f"{s[:35]:<35} {scores}")