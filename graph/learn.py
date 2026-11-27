"""Models that learn from the 30% of books whose LCC class is known.

- lda_projection: learns a linear map that pulls same-class books together (Linear Discriminant
  Analysis), then the graph is built from cosine in that space. This is "learning the similarity".
- GNNs (GCN, GraphSAGE, GAT) and an MLP with no graph: predict each held-out book's class. If a GNN
  beats the MLP, the graph's links carry information the book's own vector doesn't.

Small dense PyTorch versions: 1,000 nodes fit in memory, so no graph library is needed.
"""
import numpy as np
import torch
from scipy import sparse
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import f1_score
from torch import nn

from similarity import normalize


def lda_projection(x: np.ndarray, y: np.ndarray, train: np.ndarray) -> np.ndarray:
    """Cosine similarity after a class-separating projection fitted on the training books only."""
    lda = LinearDiscriminantAnalysis(solver="eigen", shrinkage="auto").fit(x[train], y[train])
    z = normalize(lda.transform(x))
    return z @ z.T


class GCN(nn.Module):
    """Two graph convolutions: each layer averages a book's features with its neighbours'."""

    def __init__(self, d_in, d_out, hidden=64):
        super().__init__()
        self.l1, self.l2, self.drop = nn.Linear(d_in, hidden), nn.Linear(hidden, d_out), nn.Dropout(0.5)

    def forward(self, x, adj):
        h = torch.relu(adj @ self.l1(self.drop(x)))
        return adj @ self.l2(self.drop(h))


class SAGE(nn.Module):
    """GraphSAGE (mean): keeps a book's own features separate from its neighbours' average."""

    def __init__(self, d_in, d_out, hidden=64):
        super().__init__()
        self.s1, self.n1 = nn.Linear(d_in, hidden), nn.Linear(d_in, hidden)
        self.s2, self.n2 = nn.Linear(hidden, d_out), nn.Linear(hidden, d_out)
        self.drop = nn.Dropout(0.5)

    def forward(self, x, adj):
        x = self.drop(x)
        h = self.drop(torch.relu(self.s1(x) + self.n1(adj @ x)))
        return self.s2(h) + self.n2(adj @ h)


class GAT(nn.Module):
    """Graph attention, one head per layer: learns how much each neighbour should count."""

    def __init__(self, d_in, d_out, hidden=64):
        super().__init__()
        self.l1, self.l2 = nn.Linear(d_in, hidden), nn.Linear(hidden, d_out)
        self.a1, self.a2 = nn.Linear(2 * hidden, 1), nn.Linear(2 * d_out, 1)
        self.drop = nn.Dropout(0.5)

    @staticmethod
    def attend(h, mask, att):
        d = h.shape[1]
        w = att.weight[0]
        e = torch.nn.functional.leaky_relu((h @ w[:d])[:, None] + (h @ w[d:])[None, :], 0.2)
        return torch.softmax(e.masked_fill(~mask, float("-inf")), dim=1) @ h

    def forward(self, x, adj):
        mask = adj > 0
        h = torch.nn.functional.elu(self.attend(self.l1(self.drop(x)), mask, self.a1))
        return self.attend(self.l2(self.drop(h)), mask, self.a2)


class MLP(nn.Module):
    """The same network with no graph at all: the baseline the GNNs have to beat."""

    def __init__(self, d_in, d_out, hidden=64):
        super().__init__()
        self.net = nn.Sequential(nn.Dropout(0.5), nn.Linear(d_in, hidden), nn.ReLU(), nn.Dropout(0.5),
                                 nn.Linear(hidden, d_out))

    def forward(self, x, adj):
        return self.net(x)


def norm_adj(a: sparse.csr_matrix, mean: bool = False) -> torch.Tensor:
    """GCN uses D^-1/2 (A+I) D^-1/2; GraphSAGE uses the plain neighbour mean D^-1 A."""
    a = sparse.csr_matrix(a, dtype=np.float32)
    if mean:
        d = np.asarray(a.sum(1)).ravel().clip(1)
        m = sparse.diags(1 / d) @ a
    else:
        a = a + sparse.eye(a.shape[0])
        d = np.asarray(a.sum(1)).ravel() ** -0.5
        m = sparse.diags(d) @ a @ sparse.diags(d)
    return torch.tensor(m.toarray(), dtype=torch.float32)


def train_gnn(kind: str, x: np.ndarray, a: sparse.csr_matrix, y: np.ndarray, train: np.ndarray,
              test: np.ndarray, epochs: int = 200, seed: int = 0) -> float:
    """Trains one model on the training books and returns macro-F1 on the held-out books."""
    torch.manual_seed(seed)
    n_cls = int(y.max()) + 1
    model = {"gcn": GCN, "sage": SAGE, "gat": GAT, "mlp": MLP}[kind](x.shape[1], n_cls)
    adj = norm_adj(a, mean=kind == "sage") if kind != "gat" else torch.tensor(
        (a + sparse.eye(a.shape[0])).toarray() > 0)
    xt, yt = torch.tensor(x, dtype=torch.float32), torch.tensor(y)
    tr = torch.tensor(train)
    opt = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=5e-4)
    for _ in range(epochs):
        model.train()
        opt.zero_grad()
        loss = nn.functional.cross_entropy(model(xt, adj)[tr], yt[tr])
        loss.backward()
        opt.step()
    model.eval()
    with torch.no_grad():
        pred = model(xt, adj).argmax(1).numpy()
    return float(f1_score(y[test], pred[test], average="macro"))
