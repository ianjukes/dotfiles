import os
import sys
import time
from pathlib import Path

cache_home = os.environ.get("XDG_CACHE_HOME")
if cache_home is None:
    cache_home = Path.home() / ".cache"
else:
    cache_home = Path(cache_home)

history_path = cache_home / "python_history"
if history_path.is_dir():
    raise OSError(f"'{history_path}' cannot be a directory")

if not history_path.exists():
    with open(history_path, 'w') as file:
        file.write(f'# {history_path} created on {time.asctime()}')

if sys.version_info < (3, 13):

  import atexit
  import readline

  def write_history(path):
      import os
      import readline
      try:
          readline.write_history_file(path)
      except OSError:
          pass

  history = str(history_path)

  try:
      readline.read_history_file(history)
  except FileNotFoundError:
      pass

  atexit.register(write_history, history)
  del (atexit, readline, write_history, history)

del (os, sys, time, Path)
