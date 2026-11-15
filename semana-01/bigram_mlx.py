import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim

words = open("names.txt").read().splitlines()
chars = sorted(set("".join(words)))
stoi = {c: i + 1 for i, c in enumerate(chars)}
stoi["."] = 0
itos = {i: c for c, i in stoi.items()}

xs, ys = [], []
for w in words:
    chs = ["."] + list(w) + ["."]
    for c1, c2 in zip(chs, chs[1:]):
        xs.append(stoi[c1]); ys.append(stoi[c2])
X = mx.array(xs)
Y = mx.array(ys)


class Bigram(nn.Module):
    def __init__(self, vocab):
        super().__init__()
        # Each row is the logit distribution of the next character
        # given the current character
        self.tok = nn.Embedding(vocab, vocab)

    def __call__(self, idx):
        return self.tok(idx)


def loss_fn(model, X, Y):
    logits = model(X)
    loss = nn.losses.cross_entropy(logits, Y, reduction="mean")
    reg = 0.01 * (model.tok.weight ** 2).mean()
    return loss + reg


model = Bigram(27)
optimizer = optim.SGD(learning_rate=50.0)
loss_and_grad = nn.value_and_grad(model, loss_fn)

for step in range(200):
    loss, grads = loss_and_grad(model, X, Y)
    optimizer.update(model, grads)
    mx.eval(model.parameters(), optimizer.state)
    if step % 50 == 0 or step == 199:
        print(f"step {step:3d}  loss {loss.item():.4f}")

# Sample names
mx.random.seed(2147483647)
for _ in range(10):
    out, ix = [], 0
    while True:
        logits = model(mx.array([ix]))[0]
        ix = mx.random.categorical(logits).item()
        if ix == 0:
            break
        out.append(itos[ix])
    print("".join(out))