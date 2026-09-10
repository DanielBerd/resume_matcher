#!/usr/bin/env python3
"""Double-click launcher for the Resume Matcher window.

The only thing that needs to be installed beforehand is Python itself. On
first run this creates a private environment in this app/ folder and installs
the dependencies into it, showing a simple progress window; afterwards it
just opens the app. Started by ``run_gui.bat`` through ``pythonw`` on
Windows, so there is no console - problems are reported in a dialog.
"""

import os
import sys
import threading
import traceback
from pathlib import Path

TITLE = "Resume Matcher"
ROOT = Path(__file__).resolve().parent


def alert(message: str) -> None:
    """Show a message without assuming a console exists."""
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(TITLE, message)
        root.destroy()
        return
    except Exception:
        pass
    if sys.platform == "win32":  # tkinter itself may be what is broken
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, TITLE, 0x10)
            return
        except Exception:
            pass
    print(message)


def run_app() -> int:
    """Inside the venv: start the window."""
    sys.path.insert(0, str(ROOT))
    try:
        from resume_matcher.gui import main as gui_main
    except ModuleNotFoundError as exc:
        if exc.name == "tkinter":
            alert("Python is installed without tkinter, which this window needs.\n\n"
                  "On Windows, re-run the Python installer and enable 'tcl/tk and IDLE'.\n"
                  "On Linux, install it with:  sudo apt install python3-tk")
        else:
            alert(f"Missing dependency: {exc.name}\n\nDelete the app/.venv folder and "
                  "start it again to reinstall.")
        return 1
    return gui_main()


def setup_then_launch() -> int:
    """Outside the venv: prepare it with a simple progress window, then relaunch."""
    import bootstrap

    problem = bootstrap.python_ok()
    if problem:
        alert(problem)
        return 1

    # Fast path: everything already installed - no window needed.
    if bootstrap.venv_python().exists() and bootstrap.deps_current():
        bootstrap.relaunch(Path(__file__), sys.argv[1:], windowless=True, wait=False)
        return 0

    log_path = ROOT / "setup.log"
    log_file = open(log_path, "w", encoding="utf-8")

    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        # No window possible: do it in the console instead.
        try:
            bootstrap.ensure_ready(lambda line: (print(line), log_file.write(line + "\n")))
        except RuntimeError as exc:
            print(exc)
            return 1
        finally:
            log_file.close()
        return bootstrap.relaunch(Path(__file__), sys.argv[1:])

    root = tk.Tk()
    root.title(TITLE)
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=(24, 20, 24, 18))
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Setting up Resume Matcher", font=("", 12, "bold")).pack(anchor="w")
    ttk.Label(frame, text="This only happens the first time and takes a minute or two.",
              foreground="gray").pack(anchor="w", pady=(2, 12))
    bar = ttk.Progressbar(frame, mode="determinate", maximum=100, length=400)
    bar.pack(fill="x")
    status = ttk.Label(frame, text="Preparing ...", foreground="gray")
    status.pack(anchor="w", pady=(6, 0))
    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2
    y = (root.winfo_screenheight() - root.winfo_reqheight()) // 3
    root.geometry(f"+{x}+{y}")

    state = {"target": 3.0, "value": 0.0, "stage": "Preparing ..."}
    outcome: dict = {}

    def on_line(line: str) -> None:
        """Turn bootstrap/pip output into a stage name and a progress target."""
        log_file.write(line + "\n")
        text = line.strip()
        if text.startswith("First-time setup"):
            stage, target = "Creating a private Python environment ...", 15
        elif text.startswith("Installing dependencies"):
            stage, target = "Downloading packages ...", 22
        elif text.startswith(("Collecting", "Downloading", "Using cached")):
            stage, target = "Downloading packages ...", min(70, state["target"] + 1.2)
        elif text.startswith("Installing collected packages"):
            stage, target = "Installing packages ...", 88
        elif text.startswith("Dependencies installed"):
            stage, target = "Almost done ...", 96
        elif text.startswith("Starting the app"):
            stage, target = "Starting the app ...", 100
        else:
            return
        state["stage"], state["target"] = stage, max(state["target"], target)

    def animate() -> None:
        """Main-thread tick: advances the bar and notices when the worker is done,
        so the worker never has to touch Tk from its own thread."""
        if state["value"] < state["target"]:
            state["value"] = min(state["target"], state["value"] + 0.6)
            bar["value"] = state["value"]
        status.configure(text=state["stage"])
        if outcome:
            finish()
        else:
            root.after(40, animate)

    def work() -> None:
        try:
            bootstrap.ensure_ready(on_line)
            on_line("Starting the app ...")
            outcome["ok"] = True
        except Exception as exc:
            outcome["error"] = str(exc)
        finally:
            log_file.close()

    def finish() -> None:
        if outcome.get("ok"):
            bar["value"] = 100
            status.configure(text="Starting the app ...")
            bootstrap.relaunch(Path(__file__), sys.argv[1:], windowless=True, wait=False)
            root.after(600, root.destroy)
            return
        bar.pack_forget()
        status.configure(
            text="Setup could not finish.\n\n" + outcome.get("error", "unknown error")
            + f"\n\nThe full record is in app/{log_path.name}.",
            foreground="#b42318", wraplength=420, justify="left",
        )
        ttk.Button(frame, text="Close", command=root.destroy).pack(anchor="e", pady=(14, 0))

    threading.Thread(target=work, daemon=True).start()
    animate()
    root.mainloop()
    return 0 if outcome.get("ok") else 1


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    code = 1
    try:
        import bootstrap

        code = run_app() if bootstrap.running_inside_venv() else setup_then_launch()
    except KeyboardInterrupt:
        code = 0
    except Exception:
        alert("The window could not start:\n\n" + traceback.format_exc())
    sys.exit(code)
