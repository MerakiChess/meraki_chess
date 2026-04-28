# Task: Make Meraki super strong (鬼強) in wxgui.pyw - DONE

## Completed Steps
### 1. [x] Created TODO.md
### 2. [x] Edited wxgui.pyw:
   - game_ai_depth_ctrl: initial=5→18, max=20→30, label updated
   - match_meraki_depth_ctrl: initial=5→18, max=20→30, label updated
   - ai_move(): time_ms=1500→10000ms (10s deep thinking)
### 3. [x] Verified edits via read_file/diffs

## Result
Meraki now defaults to depth=18 (鬼強 level), 10s search time in "チェス対戦" tab. Stockfish match tab also boosted. Human/Meraki games now ultra-strong out-of-box.

**Test:** `python chess_engine/gui/wxgui.pyw` → "チェス対戦" tab, watch Meraki think 10s+ at depth 18.

wxgui.pyw updated successfully.
