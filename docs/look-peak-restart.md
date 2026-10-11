# HybridCut restart — look-peak (`2026-10-11-look-peak`)

Feature stamp: **`2026-10-11-look-peak`**.

Rebased onto tip **`2026-10-11-ai-tracks`**. Includes prior: ai-tracks (AI sáv + Polírozás) · person-fix2 / person-auto · paint-face · nobg-layer · concat-look · look2.

## Scope

**Visual shell only** — CSS, chrome, spacing, typography, colors, motion, empty/loading presentation.  
Cutout / person / RVM / paint / timeline / **AI sáv** **behavior unchanged**.

## Look notes

- CapCut desktop charcoal (`#0e0e0e`) + lime `#b8f000` primary; orange Max reserved
- Syne (display) + Figtree (body); HybridCut brand hero-weight in topbar + home
- Atmospheric layered gradients + micro-dot grain (not flat void)
- Preview-focused stage · dark timeline dock (`--ink-tl`) · lime playhead glow
- AI sáv lane chrome + Polírozás chip styling (visual only)
- Empty preview polish · Export top-right lime CTA · Hungarian labels
- Motions: `brand-sheen`, `preview-load`, `playhead-glow`, `stage-focus`

## Pull + start (GitHub)

```powershell
cd $env:USERPROFILE\Documents\HybridCut
git pull
Get-Content .\SYNC_VERSION.txt   # 2026-10-11-look-peak
.\install_to_videoeditor.ps1
cd $env:USERPROFILE\Documents\Videoeditor
$env:HYBRID_RVM_ONNX = "$PWD\models\rvm_resnet50_fp32.onnx"
.\hybrid_cut\start_hybrid_cuda.ps1
# http://127.0.0.1:3847 — hard-refresh (Ctrl+F5)
```

## Agent Store sync (no GitHub)

```powershell
& "$env:LOCALAPPDATA\Cursor\AgentStores\cursor_agent_stores\bc-41930eab-1501-4c19-acf3-0c9d63afbf4d\files\docs\capcut-features\sync_hybrid.ps1"
cd $env:USERPROFILE\Documents\Videoeditor
Get-Content .\hybrid_cut\SYNC_VERSION.txt   # expect: 2026-10-11-look-peak
.\run_hybrid.ps1
```

Hard-refresh **Ctrl+F5**. Check: HybridCut brand · charcoal/lime · dark timeline + AI sáv · Export · Gyors/Max + bake → `C:\bgcut`.
