

def _add_tool_dirs() -> None:
    """Let bundled SDR tools (rtl_power, rtl_test, hackrf_sweep) be found without editing PATH.

    Looks next to the program and in its tools/ sub-folders, e.g. the installer's
    ``tools\\rtl-sdr`` folder or tools a user unzipped into the application folder.
    """
    import os
    import sys
    base = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False)
                                           else os.path.dirname(__file__)))
    cands = [base, os.path.join(base, "tools")]
    tools = os.path.join(base, "tools")
    if os.path.isdir(tools):
        cands += [os.path.join(tools, d) for d in sorted(os.listdir(tools))
                  if os.path.isdir(os.path.join(tools, d))]
    path = os.environ.get("PATH", "").split(os.pathsep)
    add = [c for c in cands if os.path.isdir(c) and c not in path]
    if add:
        os.environ["PATH"] = os.pathsep.join(add + path)


_add_tool_dirs()
