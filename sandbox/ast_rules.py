DISALLOWED_IMPORTS = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "requests",
    "urllib",
    "http",
    "ftplib",
    "paramiko",
    "shutil",
    "pickle",
    "marshal",
    "ctypes",
    "importlib",
}

ALLOWED_IMPORTS = {
    "pandas",
    "numpy",
    "json",
    "csv",
    "datetime",
    "math",
    "statistics",
    "matplotlib",
    "reportlab",
    "collections",
    "itertools",
    "pathlib",
}

DISALLOWED_CALLS = {"eval", "exec", "compile", "__import__", "getattr", "setattr", "delattr", "globals", "locals", "vars"}
APPROVED_ROOTS = ("/sandbox/input", "/sandbox/output", "/sandbox/work")
