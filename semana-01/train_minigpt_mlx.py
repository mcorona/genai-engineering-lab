import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from minigpt_mlx import MiniGPT

# Data: character-level tokenization
text = open("input.txt").read()
chars = sorted(set(text))
stoi = {c: i for i, c in enumerate(chars)}
itos = {i: c for c, i in stoi.items()}
V = len(chars)
data = mx.array([stoi[c] for c in text])

BLOCK, BATCH, STEPS, LR = 64, 32, 2000, 1e-3
n = int(0.9 * len(data))
train, val = data[:n], data[n:]


def get_batch(src):
    ix = mx.random.randint(0, len(src) - BLOCK - 1, (BATCH,)).tolist()
    x = mx.stack([src[i:i + BLOCK] for i in ix])
    y = mx.stack([src[i + 1:i + BLOCK + 1] for i in ix])
    return x, y


def loss_fn(model, x, y):
    return nn.losses.cross_entropy(model(x), y).mean()


def eval_loss(model, src, iters=20):
    total = 0.0
    for _ in range(iters):
        x, y = get_batch(src)
        total += loss_fn(model, x, y).item()
    return total / iters


model = MiniGPT(V, BLOCK, n_embd=64, n_head=4, n_layer=3)
opt = optim.AdamW(learning_rate=LR)
loss_and_grad = nn.value_and_grad(model, loss_fn)

mx.random.seed(0)
log = open("perdidas.csv", "w")
log.write("paso,train,val\n")

for step in range(STEPS + 1):
    x, y = get_batch(train)
    loss, grads = loss_and_grad(model, x, y)
    opt.update(model, grads)
    mx.eval(model.parameters(), opt.state)
    if step % 100 == 0:
        v = eval_loss(model, val)
        print(f"step {step:5d}  train {loss.item():.4f}  val {v:.4f}")
        log.write(f"{step},{loss.item():.4f},{v:.4f}\n")
log.close()


def generate(n=300, temp=0.8):
    idx = mx.array([[stoi.get("\n", 0)]])
    for _ in range(n):
        logits = model(idx[:, -BLOCK:])[:, -1, :] / temp
        nxt = mx.random.categorical(logits)
        idx = mx.concatenate([idx, nxt.reshape(1, 1)], axis=1)
    return "".join(itos[i] for i in idx[0].tolist())


print("\n--- sample ---")
print(generate())