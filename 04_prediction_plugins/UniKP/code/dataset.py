import torch
from torch.utils.data import Dataset


MAX_LEN = 220


def split(sm):
    arr = []
    two_char = {"Cl", "Ca", "Cu", "Br", "Be", "Ba", "Bi", "Si", "Se", "Sr", "Na", "Ni", "Rb", "Ra", "Xe", "Li", "Al", "As", "Ag", "Au", "Mg", "Mn", "Te", "Zn", "si", "se", "te", "He", "+2", "+3", "+4", "-2", "-3", "-4", "Kr", "Fe"}
    i = 0
    while i < len(sm) - 1:
        if sm[i] == "%":
            arr.append(sm[i : i + 3])
            i += 3
        elif sm[i : i + 2] in two_char:
            arr.append(sm[i : i + 2])
            i += 2
        else:
            arr.append(sm[i])
            i += 1
    if i == len(sm) - 1:
        arr.append(sm[i])
    return " ".join(arr)


class Seq2seqDataset(Dataset):
    def __init__(self, smiles, vocab, seq_len=MAX_LEN, transform=None):
        self.smiles = smiles
        self.vocab = vocab
        self.seq_len = seq_len
        self.transform = transform

    def __len__(self):
        return len(self.smiles)

    def __getitem__(self, item):
        sm = self.smiles[item]
        tokens = self.transform(sm) if self.transform else split(sm).split()
        if len(tokens) > self.seq_len - 2:
            tokens = tokens[: self.seq_len - 2]
        content = [self.vocab.stoi.get(token, self.vocab.unk_index) for token in tokens]
        encoded = [self.vocab.sos_index] + content + [self.vocab.eos_index]
        encoded.extend([self.vocab.pad_index] * (self.seq_len - len(encoded)))
        return torch.tensor(encoded)
