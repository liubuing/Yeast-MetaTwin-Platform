# Phase 2 Plugin Runtime Compatibility

Generated: 2026-07-17T09:57:09
Python: `3.10.20 (main, Jun 23 2026, 15:19:56) [MSC v.1944 64 bit (AMD64)]`
Executable: `C:\ymt\unikp_sklearn12\Scripts\python.exe`

| Plugin | Asset | Exists | Runtime status | Detail |
|---|---|---:|---|---|
| UniKP | trfm_12_23000.pkl | True | load_ok | <class 'collections.OrderedDict'> |
| UniKP | vocab.pkl | True | load_ok | <class 'build_vocab.WordVocab'> |
| UniKP | UniKP for kcat.pkl | True | load_ok | <class 'sklearn.ensemble._forest.ExtraTreesRegressor'> |
| UniKP | UniKP for Km.pkl | True | load_ok | <class 'sklearn.ensemble._forest.ExtraTreesRegressor'> |
| UniKP | UniKP for kcat_Km.pkl | True | load_ok | <class 'sklearn.ensemble._forest.ExtraTreesRegressor'> |
| UniKP | prot_t5_xl_uniref50 | True | load_ok | T5EncoderModel; vocab_size=128; d_model=1024; layers=24; params=1208141824 |

## Interpretation

Asset presence is not full biological validation. This report verifies that downloaded UniKP local assets, including the ProtT5 encoder dependency, load in the selected runtime. Complete UniKP prediction still requires end-to-end feature generation on target sequence/SMILES pairs.
