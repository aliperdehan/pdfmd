"""Run one program under a time limit; used by pdfmd_lua/diagram.lua (v3.32.1), because Pandoc's `pandoc.pipe` has no time limit.

    python limited_run.py SECONDS PROGRAM [ARGUMENT ...]

Standard input goes to the program and its standard output comes back byte for byte (a picture written to standard output is
binary), its error output stays on this process's own. When the time is up the program is stopped with every process it started
(mmdc starts a browser) and this one exits with 124, after writing TIMEOUT_MARK to standard output so that the filter can tell
a stopped run from a failed one. 127: the program was not found. Nothing here imports pdfmd: the script runs by path.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys

TIMEOUT_MARK = "PDFMD-DIAGRAM-TIMEOUT"


def stop_tree(process: subprocess.Popen) -> None:
    """Kill the program and the processes it started."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            process.kill()


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: limited_run.py SECONDS PROGRAM [ARGUMENT ...]", file=sys.stderr)
        return 2
    seconds = float(argv[1])
    program = shutil.which(argv[2]) or argv[2]          # a Windows `mmdc.cmd` is found by its bare name here
    data = sys.stdin.buffer.read()
    flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    try:
        process = subprocess.Popen([program] + argv[3:], stdin=subprocess.PIPE, stdout=subprocess.PIPE, **flags)
    except OSError as error:
        print(f"{argv[2]}: {error}", file=sys.stderr)
        return 127
    try:
        out, _ = process.communicate(data, timeout=seconds)
    except subprocess.TimeoutExpired:
        stop_tree(process)
        try:
            process.communicate(timeout=5)                  # a grandchild in a session of its own may still hold a pipe open
        except subprocess.TimeoutExpired:
            pass
        print(f"{argv[2]} did not finish in {seconds:g} s and was stopped (the setting `diagram-timeout`: "
              "seconds, 0 = never draw diagrams, -1 = no limit)", file=sys.stderr)
        sys.stdout.write(TIMEOUT_MARK)
        sys.stdout.flush()
        return 124
    sys.stdout.buffer.write(out)
    sys.stdout.buffer.flush()
    return process.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv))
