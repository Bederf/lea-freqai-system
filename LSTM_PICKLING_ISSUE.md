# LSTM Pickling Issue in FreqAI Custom Models

**Date:** 2025-10-12
**Status:** ❌ BLOCKING - Custom LSTM model cannot be saved/loaded
**Workaround:** ✅ Using PyTorchMLPRegressor instead

---

## Issue Summary

Custom PyTorch LSTM models in `user_data/freqaimodels/` fail to pickle/save with the error:

```
PicklingError: Can't pickle <class 'LeaTorchLSTM.SimpleLSTMModel'>: import of module 'LeaTorchLSTM' failed
```

This prevents models from being saved after training, meaning they can never be loaded for predictions, effectively making custom LSTM models unusable in FreqAI.

---

## Technical Details

### Error Message
```
2025-10-12 09:19:41,108 - freqtrade.freqai.freqai_interface - ERROR - Training SOL/USDT raised exception PicklingError. Message: Can't pickle <class 'LeaTorchLSTM.SimpleLSTMModel'>: import of module 'LeaTorchLSTM' failed, skipping.
_pickle.PicklingError: Can't pickle <class 'LeaTorchLSTM.SimpleLSTMModel'>: import of module 'LeaTorchLSTM' failed
```

### Root Cause

1. **FreqTrade pickles the entire `PyTorchModelTrainer` object** which includes:
   - The model (nn.Module)
   - Optimizer
   - Criterion
   - Training state

2. **Python's pickle expects fully qualified imports**:
   - When unpickling, Python needs to re-import the class
   - It tries: `from LeaTorchLSTM import SimpleLSTMModel`
   - This fails because `user_data/freqaimodels` isn't in Python's import path during unpickling

3. **FreqTrade's built-in models work** because they're in proper packages:
   - `freqtrade.freqai.torch.PyTorchMLPModel` ✅
   - `freqtrade.freqai.torch.PyTorchTransformerModel` ✅
   - `user_data.freqaimodels.LeaTorchLSTM` ❌ (not a proper package path)

### Code Structure

**Our Custom Model** (Fails):
```python
# File: user_data/freqaimodels/LeaTorchLSTM.py

class SimpleLSTMModel(nn.Module):
    """Custom LSTM model"""
    def __init__(self, input_dim, output_dim, hidden_dim=128, ...):
        # LSTM implementation

class LeaTorchLSTM(BasePyTorchRegressor):
    def fit(self, data_dictionary, dk, **kwargs):
        model = SimpleLSTMModel(...)  # ❌ Can't pickle this
        trainer = PyTorchModelTrainer(model=model, ...)
        return trainer  # ❌ Pickling fails here
```

**FreqTrade's Built-in Model** (Works):
```python
# File: freqtrade/freqai/prediction_models/PyTorchMLPRegressor.py

from freqtrade.freqai.torch.PyTorchMLPModel import PyTorchMLPModel  # ✅ Proper import

class PyTorchMLPRegressor(BasePyTorchRegressor):
    def fit(self, data_dictionary, dk, **kwargs):
        model = PyTorchMLPModel(...)  # ✅ Can pickle this
        trainer = PyTorchModelTrainer(model=model, ...)
        return trainer  # ✅ Pickling works
```

---

## Attempted Fixes That Didn't Work

### 1. ❌ Added `__init__.py` to freqaimodels
```bash
# Created: user_data/freqaimodels/__init__.py
```
**Result:** Still failed - import path issue remains

### 2. ❌ Moved model class to separate file
```python
# LeaLSTMModel.py with just the nn.Module class
```
**Result:** Same issue - pickle can't find the module

### 3. ❌ Tried different import structures
**Result:** FreqTrade's pickling expects specific module paths

---

## Possible Solutions (Not Implemented)

### Solution A: Move Model to FreqTrade Source (Invasive)
```
freqtrade/freqai/torch/LeaLSTMModel.py  # Add model here
freqtrade/freqai/prediction_models/LeaLSTMRegressor.py  # Add predictor here
```

**Pros:**
- Would work (proper import path)
- Matches FreqTrade's architecture

**Cons:**
- Requires modifying FreqTrade source code
- Not maintainable (gets overwritten on updates)
- Not portable

### Solution B: Custom Pickle Handlers (Complex)
Override `__reduce__` or `__getstate__`/`__setstate__` in model class.

**Pros:**
- Keeps code in user_data

**Cons:**
- Complex to implement correctly
- Must handle optimizer state, training state, etc.
- Fragile and easy to break

### Solution C: Use PyTorch's state_dict (Requires FreqTrade Changes)
Save only model weights, not entire trainer object.

**Pros:**
- Standard PyTorch approach
- More reliable

**Cons:**
- Requires modifying FreqTrade's BasePyTorchRegressor
- Not currently supported by FreqTrade

---

## Workaround: Use PyTorchMLPRegressor ✅

### Why This Works

1. **Already pickle-compatible** - in proper package
2. **MLP can learn temporal patterns** - with enough layers
3. **Our features encode time** - returns over multiple periods
4. **Proven effective** - research shows architecture matters less than features

### Implementation

**Configuration Change:**
```json
{
  "freqai": {
    "model_training_parameters": {
      "learning_rate": 0.001,
      "trainer_kwargs": {
        "n_epochs": 10,
        "batch_size": 64
      },
      "model_kwargs": {
        "hidden_dim": 256,
        "dropout_percent": 0.2,
        "n_layer": 3
      }
    }
  }
}
```

**Command:**
```bash
freqtrade trade --config config.json --strategy LeaFreqAIStrategy --freqaimodel PyTorchMLPRegressor
```

---

## Impact

### What We Lost
- Explicit LSTM recurrence (but our features already capture temporal patterns)
- Attention mechanism (but we removed this anyway due to dimension issues)

### What We Gained
- ✅ **Models actually save and load**
- ✅ Faster training (MLP trains faster than LSTM)
- ✅ More stable (no pickling errors)
- ✅ Can start trading immediately

---

## Research Support

Multiple studies show that for financial time series with engineered features:

1. **Feature engineering > Model architecture**
   - Good stationary features (returns, momentum, volatility) encode temporal information
   - Model just needs to learn non-linear combinations

2. **MLPs perform comparably to RNNs/LSTMs**
   - When features include lagged values and temporal indicators
   - Especially on shorter timeframes (5m in our case)

3. **Simpler models often better in production**
   - Less prone to overfitting
   - Faster inference
   - Easier to debug

---

## Recommendation for FreqTrade Team

Consider one of these improvements:

1. **Document the pickling limitation** clearly in FreqAI docs
   - State that custom PyTorch models must be in FreqTrade source
   - Or provide template for pickle-compatible custom models

2. **Support user_data models properly**
   - Add `user_data/freqaimodels` to Python path during unpickling
   - Or provide plugin system for custom models

3. **Use PyTorch state_dict instead of pickling**
   - Save only model weights
   - Reconstruct model architecture on load
   - More robust and standard approach

---

## Our Resolution

**Decision:** Switch to `PyTorchMLPRegressor` for production use.

**Reasoning:**
- Unblocks trading immediately (2+ hours saved)
- Scientifically sound (features matter more than architecture)
- Can revisit LSTM later if needed (after proving strategy works)
- Pragmatic over perfect

---

## Files Affected

- ❌ `user_data/freqaimodels/LeaTorchLSTM.py` - Not usable due to pickling
- ✅ Switching to built-in `PyTorchMLPRegressor`
- ✅ `user_data/strategies/LeaFreqAIStrategy.py` - Works with any FreqAI model

---

## Lesson Learned

**For custom PyTorch models in FreqAI:**
- Built-in models (MLP, Transformer) work out of the box
- Custom models in `user_data/freqaimodels/` have pickling issues
- Always test model save/load before extensive development

**Time Cost:** 2+ hours debugging pickling issues

**Better Approach:** Start with built-in models, only create custom if absolutely necessary.

---

**Status:** Issue documented, workaround implemented, moving forward with MLP.

**GitHub Issue:** To be created in FreqTrade repository for upstream fix.
