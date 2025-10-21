import os
import glob
import shutil
import subprocess
from pathlib import Path

from astropy.io import fits
from astropy.wcs import WCS

def plate_solve(input_image, output_directory, parameters):
    input_path = Path(input_image)
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)

    solve_field = shutil.which("solve-field")

    if not solve_field:
        raise FileNotFoundError("solve-field not found on PATH. Is astrometry.net installed?")

    cmd = [
        solve_field,
    ]
    cmd.extend(parameters)
    cmd.append("--dir")
    cmd.append(input_image + ".d")
    cmd.append("--wcs")
    cmd.append("./" + input_image + ".d/wcs.fits")
    cmd.append(input_image)

    process = subprocess.run(cmd, capture_output=True, text=True)

    if process.returncode != 0:
        raise RuntimeError(
            f"solve-field failed (returncode={process.returncode}).\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}"
        )

    return True