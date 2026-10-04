# MatAnyone2 weights (optional, not shipped)

Stamp: **`2026-10-04-person-matte`**

HybridCut **does not ship** MatAnyone2 checkpoints. Max mode always produces an
**auto person matte via RVM** (quality pipeline) when weights are missing.

| Status chip / log | Meaning |
|-------------------|---------|
| **MatAnyone2 nincs — RVM ember-maszk** | Default. RVM (+ quality polish) runs. |
| **MatAnyone2 aktív** | Local `.pth` + importable `matanyone2` package detected. |

## License

MatAnyone2 (pq-yang/MatAnyone2) and `matanyone2.pth` are under **S-Lab License 1.0
(non-commercial)**. Do not redistribute weights in this product tree. Only point
at a file you obtained yourself for allowed use.

Upstream release (example):  
https://github.com/pq-yang/MatAnyone2/releases

## Local setup (Windows PowerShell)

```powershell
# 1) Download matanyone2.pth yourself (S-Lab NC) into e.g.:
#    $env:USERPROFILE\Documents\Models\matanyone2.pth

# 2) Install upstream MatAnyone2 into a local env (do NOT copy sources into HybridCut).
#    Follow pq-yang/MatAnyone2 README for PyTorch + package install.

# 3) Point HybridCut at the checkpoint before start:
$env:HYBRID_MATANYONE2_WEIGHTS = "$env:USERPROFILE\Documents\Models\matanyone2.pth"

cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_mobilenetv3_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847
# Status should show: MatAnyone2 aktív
```

Unset or leave empty to stay on RVM:

```powershell
Remove-Item Env:HYBRID_MATANYONE2_WEIGHTS -ErrorAction SilentlyContinue
```

## Without weights (recommended default)

1. Load video  
2. Click **Előnézet** — auto RVM person matte (CUDA if available, else CPU)  
3. Preview switches to **Cutout** when the matte is ready  
4. Optional **Kézi finomítás** (lasszó) only refines — it is **not** required  

Manual seed is **unioned** with the auto RVM alpha so a small yellow blob cannot
wipe the whole person matte.
