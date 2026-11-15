import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_flatten


class CausalSelfAttention(nn.Module):
    """Multi-head attention with a causal mask (the same logic as step 3)."""

    def __init__(self, n_embd, n_head):
        super().__init__()
        assert n_embd % n_head == 0
        self.n_head = n_head
        self.head_dim = n_embd // n_head
        self.qkv = nn.Linear(n_embd, 3 * n_embd, bias=False)
        self.proj = nn.Linear(n_embd, n_embd, bias=False)

    def __call__(self, x):
        B, T, C = x.shape
        q, k, v = mx.split(self.qkv(x), 3, axis=-1)

        # (B, T, C) -> (B, n_head, T, head_dim)
        def heads(t):
            return t.reshape(B, T, self.n_head, self.head_dim).transpose(0, 2, 1, 3)

        q, k, v = heads(q), heads(k), heads(v)
        scores = (q @ k.transpose(0, 1, 3, 2)) * self.head_dim ** -0.5
        mask = mx.triu(mx.full((T, T), -mx.inf), k=1)
        w = mx.softmax(scores + mask, axis=-1)
        out = (w @ v).transpose(0, 2, 1, 3).reshape(B, T, C)
        return self.proj(out)


class MLP(nn.Module):
    def __init__(self, n_embd):
        super().__init__()
        self.fc = nn.Linear(n_embd, 4 * n_embd)
        self.proj = nn.Linear(4 * n_embd, n_embd)

    def __call__(self, x):
        return self.proj(nn.gelu(self.fc(x)))


class Block(nn.Module):
    """Pre-norm: attention and MLP, each with a residual connection."""

    def __init__(self, n_embd, n_head):
        super().__init__()
        self.ln1 = nn.LayerNorm(n_embd)
        self.attn = CausalSelfAttention(n_embd, n_head)
        self.ln2 = nn.LayerNorm(n_embd)
        self.mlp = MLP(n_embd)

    def __call__(self, x):
        x = x + self.attn(self.ln1(x))
        x = x + self.mlp(self.ln2(x))
        return x


class MiniGPT(nn.Module):
    def __init__(self, vocab_size, block_size, n_embd=32, n_head=4, n_layer=2):
        super().__init__()
        self.block_size = block_size
        self.tok_emb = nn.Embedding(vocab_size, n_embd)
        self.pos_emb = nn.Embedding(block_size, n_embd)
        self.blocks = [Block(n_embd, n_head) for _ in range(n_layer)]
        self.ln_f = nn.LayerNorm(n_embd)
        self.head = nn.Linear(n_embd, vocab_size, bias=False)

    def __call__(self, idx):
        B, T = idx.shape
        x = self.tok_emb(idx) + self.pos_emb(mx.arange(T))   # (B, T, C)
        for blk in self.blocks:
            x = blk(x)
        return self.head(self.ln_f(x))                       # (B, T, vocab)


if __name__ == "__main__":
    mx.random.seed(0)
    VOCAB, BLOCK = 65, 32
    model = MiniGPT(VOCAB, BLOCK)

    # 1. Output shape
    idx = mx.random.randint(0, VOCAB, (4, BLOCK))
    logits = model(idx)
    print("logits shape:", logits.shape)

    # 2. Initial loss: it should be close to ln(65) ≈ 4.17
    targets = mx.random.randint(0, VOCAB, (4, BLOCK))
    loss = nn.losses.cross_entropy(logits, targets).mean()
    print("initial loss:", round(loss.item(), 4))

    # 3. Number of parameters
    n_params = sum(p.size for _, p in tree_flatten(model.parameters()))
    print("parameters:", n_params)

    # 4. Causality test: changing token 20 must not affect the logits of positions 0 to 19
    idx2 = mx.concatenate(
        [idx[:, :20], mx.zeros((4, 1), dtype=idx.dtype), idx[:, 21:]], axis=1
    )
    same_before = mx.allclose(model(idx)[:, :20], model(idx2)[:, :20], atol=1e-5).item()
    same_at = mx.allclose(model(idx)[:, 20], model(idx2)[:, 20], atol=1e-5).item()
    print("positions 0-19 do not change:", same_before)
    print("position 20 does change:", not same_at)