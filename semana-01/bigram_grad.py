import torch
import torch.nn.functional as F

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
xs = torch.tensor(xs); ys = torch.tensor(ys)
n = xs.nelement()

g = torch.Generator().manual_seed(2147483647)
W = torch.randn((27, 27), generator=g, requires_grad=True)

for step in range(200):
    probs = F.softmax(W[xs], dim=1)                 # logits -> probabilities
    loss = -probs[torch.arange(n), ys].log().mean() + 0.01 * (W ** 2).mean()
    W.grad = None
    loss.backward()
    with torch.no_grad():
        W -= 50 * W.grad
    if step % 50 == 0 or step == 199:
        print(f"step {step:3d}  loss {loss.item():.4f}")

# Sample new names
with torch.no_grad():
    for _ in range(10):
        out, ix = [], 0
        while True:
            p = F.softmax(W[ix], dim=0)
            ix = torch.multinomial(p, 1, generator=g).item()
            if ix == 0:
                break
            out.append(itos[ix])
        print("".join(out))