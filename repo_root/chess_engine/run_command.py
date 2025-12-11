import sys
import subprocess

# コマンドライン引数をチェック
if len(sys.argv) != 2:
    print("Usage: python script.py <fen>")
    sys.exit(1)

# 入力されたFEN文字列を取得
fen = sys.argv[1]

# PowerShellで実行するコマンドを構築
command = f'python -m chess_engine.cli.play --fen "{fen}" --depth 6 --time-ms 2000 --coeff "..\\chess_dataprocessing\\models\\logreg_coeffs.json" --alpha 0.35'

# PowerShellでコマンドを実行
subprocess.run(['powershell', '-Command', command])
