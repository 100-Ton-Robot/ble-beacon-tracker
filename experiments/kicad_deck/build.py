"""Run the whole KiCad experiment: generate board, fill zones + DRC, export Gerbers/drill/renders, compare.

python build.py     (needs KiCad 10 installed; finds kicad-cli in LOCALAPPDATA or Program Files)
"""
import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "shield_deck.kicad_pcb")
OUT = os.path.join(HERE, "out")
GERB = os.path.join(OUT, "gerbers")


def find_cli():
    # winget installs per-user (LOCALAPPDATA); the manual installer defaults to Program Files
    hits = sorted(glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Programs\KiCad\*\bin\kicad-cli.exe"))
                  + glob.glob(r"C:\Program Files\KiCad\*\bin\kicad-cli.exe"))
    if not hits:
        sys.exit("kicad-cli not found; install KiCad (winget install KiCad.KiCad)")
    return hits[-1]


def run(*args):
    print(">", " ".join(os.path.basename(a) if os.path.isabs(a) else a for a in args))
    r = subprocess.run(args, capture_output=True, text=True)
    print((r.stdout + r.stderr).strip())
    return r.returncode


def main():
    cli = find_cli()
    subprocess.run([sys.executable, os.path.join(HERE, "make_deck_kicad.py")], check=True)
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(GERB)

    # DRC with zone refill; --save-board writes the filled zone back into the board file
    run(cli, "pcb", "drc", "--refill-zones", "--save-board", "--severity-all",
        "-o", os.path.join(OUT, "drc.rpt"), PCB)
    run(cli, "pcb", "export", "gerbers", "--layers",
        "F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,Edge.Cuts",
        "--use-drill-file-origin", "-o", GERB + os.sep, PCB)
    run(cli, "pcb", "export", "drill", "--format", "excellon", "--drill-origin", "plot",
        "--excellon-units", "mm", "-o", GERB + os.sep, PCB)
    for side in ("top", "bottom"):
        run(cli, "pcb", "render", "--side", side, "--width", "1200", "--height", "1200",
            "--background", "opaque", "-o", os.path.join(OUT, f"render_{side}.png"), PCB)

    subprocess.run([sys.executable, os.path.join(HERE, "compare.py")], check=True)


if __name__ == "__main__":
    main()
