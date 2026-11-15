import mlx.core as mx
import mlx.nn as nn

mx.random.seed(0)
B, T, C, H = 2, 8, 16, 16   # batch, tokens, input channels, head dimension

x = mx.random.normal((B, T, C))

Wq = nn.Linear(C, H, bias=False)
Wk = nn.Linear(C, H, bias=False)
Wv = nn.Linear(C, H, bias=False)

q, k, v = Wq(x), Wk(x), Wv(x)            # each one: (B, T, H)

# Attention scores: (B, T, T)
scores = (q @ k.transpose(0, 2, 1)) / (H ** 0.5)

# Causal mask: token i may only attend to the j <= i
mask = mx.triu(mx.full((T, T), -mx.inf), k=1)
weights = mx.softmax(scores + mask, axis=-1)
out = weights @ v                         # (B, T, H)

print("output shape:", out.shape)
print("each row of weights sums to 1:", mx.allclose(weights.sum(-1), mx.ones((B, T))).item())
print("weights of token 0 (it only sees itself):", weights[0, 0, :4].tolist())

# Comparison with MLX's optimized implementation
ref = mx.fast.scaled_dot_product_attention(
    q[:, None], k[:, None], v[:, None], scale=H ** -0.5, mask="causal"
)[:, 0]
print("matches mx.fast:", mx.allclose(out, ref, atol=1e-5).item())