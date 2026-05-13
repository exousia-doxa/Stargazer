import os
import sys
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image

try:
    from java import jclass, jbyte, jarray
    from com.chaquo.python import Python
    JAVA_AVAILABLE = True
except ImportError:
    JAVA_AVAILABLE = False
    print("WARNING: Java interop not available - native solve will fail")
    sys.stdout.flush()

from astropy.io import fits
from astropy.wcs import WCS


def _zenith_radec_from_gps(latitude_deg, longitude_deg, iso_utc):
    """Return (RA_deg, Dec_deg) of the zenith at the given GPS lat/lon and
    UTC time, or (None, None) if the inputs are invalid. Used to turn a
    rough GPS fix into a positional hint for `solve-field -3/-4`.
    """
    try:
        from astropy.coordinates import EarthLocation, AltAz, SkyCoord
        from astropy.time import Time
        import astropy.units as u
        loc = EarthLocation.from_geodetic(
            lon=longitude_deg * u.deg, lat=latitude_deg * u.deg)
        t = Time(iso_utc)
        zenith = SkyCoord(alt=90 * u.deg, az=0 * u.deg,
                          frame=AltAz(obstime=t, location=loc))
        icrs = zenith.icrs
        return float(icrs.ra.deg), float(icrs.dec.deg)
    except Exception as e:
        print(f"WARNING: zenith RA/Dec computation failed: {e}")
        sys.stdout.flush()
        return None, None


def convert_image_to_fits(input_image, output_fits_path):
    """Convert JPEG or PNG image to FITS format for astrometry.net"""
    print(f"DEBUG: Converting image to FITS: {input_image}")
    sys.stdout.flush()
    
    # Open image with PIL
    img = Image.open(input_image)
    
    # Convert to grayscale if color
    if img.mode != 'L':
        img = img.convert('L')
    
    # Convert to numpy array
    img_array = np.array(img, dtype=np.uint8)
    
    # Create FITS HDU with image data
    hdu = fits.PrimaryHDU(data=img_array)
    hdul = fits.HDUList([hdu])
    
    # Write to FITS file
    hdul.writeto(output_fits_path, overwrite=True)
    print(f"DEBUG: FITS file created: {output_fits_path}")
    sys.stdout.flush()
    
    return output_fits_path

def extract_astrometry_if_needed():
    if not JAVA_AVAILABLE:
        return None
    context = Python.getPlatform().getApplication().getApplicationContext()
    stargazer_dir = os.path.join(context.getFilesDir().getAbsolutePath(), "stargazer")
    astro_net_dir = os.path.join(stargazer_dir, "astrometry.net")
    
    # Check for a key file to see if extraction is needed
    if not os.path.exists(os.path.join(astro_net_dir, "lib", "libwcs.so")):
        print("Extracting astrometry.net.tar.gz...")
        sys.stdout.flush()
        
        # Clean up previous extraction attempts
        if os.path.exists(astro_net_dir):
            import shutil
            shutil.rmtree(astro_net_dir)
        os.makedirs(astro_net_dir)

        asset_manager = context.getAssets()
        try:
            # Try to open the new tar.gz file first
            input_stream = asset_manager.open("arm64-v8a/astrometry.net.tar.gz")
        except Exception:
            # Fallback to the old location for compatibility
            input_stream = asset_manager.open("astrometry.net.tar")
            
        tar_path = os.path.join(stargazer_dir, "astrometry.net.tar.gz")
        
        FileOutputStream = jclass("java.io.FileOutputStream")
        out_stream = FileOutputStream(tar_path)
        buffer = jarray(jbyte)(8192)
        while True:
            read = input_stream.read(buffer)
            if read == -1: break
            out_stream.write(buffer, 0, read)
        out_stream.close()
        input_stream.close()
        
        import tarfile
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(path=stargazer_dir)
        os.remove(tar_path)
        
        # Make binaries executable
        bin_dir = os.path.join(astro_net_dir, "bin")
        if os.path.exists(bin_dir):
            for filename in os.listdir(bin_dir):
                filepath = os.path.join(bin_dir, filename)
                if os.path.isfile(filepath):
                    os.chmod(filepath, 0o755)

    # Copy index files (assets/data/index-*.fits) into astrometry.net/data
    # if they aren't already there. They are packaged separately from the
    # tarball because astrometry.net's index files are large/optional.
    data_dir = os.path.join(astro_net_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    asset_manager = context.getAssets()
    try:
        asset_indexes = list(asset_manager.list("data") or [])
    except Exception as e:
        asset_indexes = []
        print(f"WARNING: could not list 'data' assets: {e}")
        sys.stdout.flush()

    # Remove any on-disk indexes that the APK no longer ships. This makes
    # `assets/data/` the single source of truth and prevents stale indexes
    # (e.g. low-scale ones removed from the APK) from being scanned by
    # `autoindex` and burning the cpulimit.
    wanted = {n for n in asset_indexes if n.endswith(".fits")}
    try:
        for existing in os.listdir(data_dir):
            if existing.endswith(".fits") and existing not in wanted:
                try:
                    os.remove(os.path.join(data_dir, existing))
                    print(f"DEBUG: removed stale index {existing}")
                    sys.stdout.flush()
                except OSError as e:
                    print(f"WARNING: could not remove stale index {existing}: {e}")
                    sys.stdout.flush()
    except OSError:
        pass

    for name in asset_indexes:
        if not name.endswith(".fits"):
            continue
        dst = os.path.join(data_dir, name)
        if os.path.exists(dst):
            continue
        try:
            stream = asset_manager.open("data/" + name)
        except Exception as e:
            print(f"WARNING: could not open asset data/{name}: {e}")
            sys.stdout.flush()
            continue
        FileOutputStream = jclass("java.io.FileOutputStream")
        out = FileOutputStream(dst)
        buf = jarray(jbyte)(8192)
        try:
            while True:
                read = stream.read(buf)
                if read == -1:
                    break
                out.write(buf, 0, read)
        finally:
            out.close()
            stream.close()
        print(f"DEBUG: extracted index {name}")
        sys.stdout.flush()

    return astro_net_dir


def plate_solve(input_image, output_directory, parameters, arguments_c={}):
    try:
        output_path = Path(output_directory)
        output_path.mkdir(parents=True, exist_ok=True)
        print(f"DEBUG: Output directory verified/created: {output_directory}")
        sys.stdout.flush()

        if not JAVA_AVAILABLE:
            raise RuntimeError("Java interop not available")
            
        astro_net_dir = extract_astrometry_if_needed()
        context = Python.getPlatform().getApplication().getApplicationContext()
        native_lib_dir = context.getApplicationInfo().nativeLibraryDir

        # The engine must be exec'd from nativeLibraryDir; binaries in the
        # app's writable data dir are blocked by Android's W^X / SELinux policy.
        # The bundled solve-field is too old to support --engine-path, so we
        # expose the engine to solve-field via a symlink on $PATH whose target
        # lives in nativeLibraryDir. execve() follows the symlink and the
        # SELinux check is applied to the resolved target, which is allowed.
        native_engine = os.path.join(native_lib_dir, "libastrometry-engine.so")
        shim_bin_dir = os.path.join(os.path.dirname(astro_net_dir), "shim_bin")
        os.makedirs(shim_bin_dir, exist_ok=True)
        engine_symlink = os.path.join(shim_bin_dir, "astrometry-engine")
        try:
            if os.path.islink(engine_symlink) or os.path.exists(engine_symlink):
                os.unlink(engine_symlink)
            os.symlink(native_engine, engine_symlink)
        except OSError as e:
            print(f"WARNING: could not create engine symlink: {e}")
            sys.stdout.flush()

        # Heal astrometry.cfg: strip unknown directives (e.g. a stale
        # `engine <path>` line from an older build) and replace any relative
        # `add_path` with an absolute path to our extracted data dir, plus
        # enable `autoindex` so the engine picks up index-*.fits there.
        cfg_path = os.path.join(astro_net_dir, "etc", "astrometry.cfg")
        abs_data_dir = os.path.join(astro_net_dir, "data")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r") as f:
                    cfg_lines = f.readlines()
                known_keys = (
                    "index", "add_path", "autoindex", "inparallel",
                    "minwidth", "maxwidth", "depths", "cpulimit",
                )
                cleaned = []
                saw_add_path = False
                saw_autoindex = False
                for line in cfg_lines:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        cleaned.append(line)
                        continue
                    parts = stripped.split(None, 1)
                    first = parts[0]
                    if first == "add_path":
                        cleaned.append(f"add_path {abs_data_dir}\n")
                        saw_add_path = True
                    elif first == "autoindex":
                        cleaned.append("autoindex\n")
                        saw_autoindex = True
                    elif first in known_keys:
                        cleaned.append(line)
                    else:
                        cleaned.append("# [stargazer-stripped] " + line)
                if not saw_add_path:
                    cleaned.append(f"add_path {abs_data_dir}\n")
                if not saw_autoindex:
                    cleaned.append("autoindex\n")
                with open(cfg_path, "w") as f:
                    f.writelines(cleaned)
                print(f"DEBUG: astrometry.cfg patched (add_path={abs_data_dir})")
                sys.stdout.flush()
            except Exception as e:
                print(f"WARNING: could not sanitize astrometry.cfg: {e}")
                sys.stdout.flush()

        # Convert input image to FITS to avoid needing image2pnm helper binary
        fits_image_path = str(output_path / "input.fits")
        convert_image_to_fits(input_image, fits_image_path)

        wcs_path = str(output_path / "wcs.fits")

        # Pre-process the caller-supplied parameters list:
        # * Translate the Stargazer sentinel "--stargazer-hint-from-gps
        #   <lat> <lon> <iso> <radius>" into proper -3/-4/-5 flags by
        #   computing the zenith RA/Dec at that lat/lon at that time.
        # * Pull out --stargazer-wall-timeout if present (Python-side only).
        wall_timeout = arguments_c.get("wall_timeout", 120)
        user_args = list(parameters)
        i = 0
        processed = []
        while i < len(user_args):
            tok = user_args[i]
            if tok == "--stargazer-hint-from-gps":
                try:
                    lat = float(user_args[i + 1])
                    lon = float(user_args[i + 2])
                    iso = user_args[i + 3]
                    radius = float(user_args[i + 4])
                except (IndexError, ValueError) as e:
                    print(f"WARNING: malformed --stargazer-hint-from-gps: {e}")
                    sys.stdout.flush()
                    i += 5
                    continue
                ra_deg, dec_deg = _zenith_radec_from_gps(lat, lon, iso)
                if ra_deg is not None and dec_deg is not None:
                    processed.extend(["-3", f"{ra_deg:.6f}",
                                      "-4", f"{dec_deg:.6f}",
                                      "-5", f"{radius:.3f}"])
                    print(f"DEBUG: positional hint -> RA={ra_deg:.3f} "
                          f"Dec={dec_deg:.3f} radius={radius}°")
                    sys.stdout.flush()
                i += 5
                continue
            if tok == "--stargazer-wall-timeout":
                try:
                    wall_timeout = max(1, int(float(user_args[i + 1])))
                except (IndexError, ValueError):
                    pass
                i += 2
                continue
            processed.append(tok)
            i += 1

        # Always-on infrastructure flags. Anything user-tunable lives in
        # `processed` (from the caller's preferences) -- not here.
        args = [
            "--no-plots", "--overwrite", "--fits-image",
            "--dir", output_directory,
            "--wcs", wcs_path,
            "-m", output_directory,
            "-y", "-9",
            "--uniformize", "0",
        ]

        # Use default config from extracted location
        default_config_path = os.path.join(astro_net_dir, "etc", "astrometry.cfg")
        if os.path.exists(default_config_path):
            args.extend(["--config", default_config_path])

        args.extend(processed)
        args.append(fits_image_path)

        # Warn about duplicate single-value flags (last wins on the engine
        # side, which silently overrides earlier values).
        single_value_flags = {"-l", "-L", "-H", "-u", "-z", "-y",
                              "--uniformize", "--config", "-3", "-4", "-5",
                              "--objs", "--parity"}
        seen = {}
        for i, tok in enumerate(args):
            if tok in single_value_flags:
                val = args[i + 1] if i + 1 < len(args) else "<missing>"
                if tok in seen:
                    print(f"WARNING: duplicate flag {tok}: "
                          f"previous value {seen[tok]!r} overridden by {val!r}")
                seen[tok] = val
        if "-l" in seen:
            print(f"DEBUG: effective cpulimit (-l) = {seen['-l']} seconds")
        print(f"DEBUG: wall-clock timeout = {wall_timeout} seconds")
        sys.stdout.flush()

        print(f"========== PLATE SOLVER STARTING ==========")
        solve_field_bin = os.path.join(native_lib_dir, "libsolve-field.so")
        print(f"Total arguments: {solve_field_bin} {' '.join(args)}")
        sys.stdout.flush()

        env = os.environ.copy()
        # nativeLibraryDir first: it is the only location Android allows
        # execve() from. The extracted lib dir is still useful for dlopen() of
        # shared objects that aren't packaged as jniLibs.
        env["LD_LIBRARY_PATH"] = native_lib_dir + ":" + os.path.join(astro_net_dir, "lib") + ":" + env.get("LD_LIBRARY_PATH", "")
        # shim_bin must come before astrometry.net/bin so that
        # `astrometry-engine` resolves to our symlink into nativeLibraryDir,
        # not to the (SELinux-blocked) ELF inside the data dir.
        env["PATH"] = shim_bin_dir + ":" + native_lib_dir + ":" + os.path.join(astro_net_dir, "bin") + ":" + env.get("PATH", "")
        
        if not os.path.exists(solve_field_bin):
            raise FileNotFoundError(f"Astrometry.net binary not found at {solve_field_bin}")

        # Stream child output line-by-line so progress is visible in logcat
        # in real time, and enforce a hard wall-clock timeout so an I/O-
        # blocked engine cannot sit forever (the engine's RLIMIT_CPU only
        # ticks while the process is on-CPU, so I/O hangs evade it).
        # `wall_timeout` was resolved during arg pre-processing above.
        import time
        env["PYTHONUNBUFFERED"] = "1"

        proc = subprocess.Popen(
            [solve_field_bin] + args,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge so order is preserved
            text=True,
            bufsize=1,                 # line-buffered on our side
        )

        start = time.monotonic()
        timed_out = False
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                print(line.rstrip())
                sys.stdout.flush()
                if time.monotonic() - start > wall_timeout:
                    timed_out = True
                    print(f"WARNING: wall-clock timeout {wall_timeout}s exceeded; killing solver")
                    sys.stdout.flush()
                    proc.kill()
                    break
            returncode = proc.wait(timeout=5)
        except Exception:
            proc.kill()
            proc.wait(timeout=5)
            raise

        elapsed = time.monotonic() - start
        print(f"============ SOLVER OUTPUT ENDS ============")
        print(f"DEBUG: solve-field returned code {returncode} after {elapsed:.1f}s")
        sys.stdout.flush()

        if timed_out:
            raise RuntimeError(f"Astrometry.net wall-clock timeout after {wall_timeout}s")
        if returncode != 0:
            raise RuntimeError(f"Astrometry.net failed with return code {returncode}")

        # Exit 0 with no WCS file means "no match found" -- a normal,
        # non-exceptional result. Report it cleanly instead of raising
        # a generic Astrometry.net failure.
        if not Path(wcs_path).exists():
            print("DEBUG: solver completed but produced no WCS (no match found)")
            sys.stdout.flush()
            return False

        return True
    except Exception as e:
        import traceback
        print(f"ERROR: plate_solve exception: {e}")
        print(f"ERROR: Traceback: {traceback.format_exc()}")
        sys.stdout.flush()
        raise RuntimeError(f"Failed to call Astrometry.net: {e}")
