import sys

if sys.version_info < (3, 13):

  import atexit
  import os
  import readline
  import time
  from pathlib import Path

  def write_history(path):
      import os
      import readline
      try:
          readline.write_history_file(path)
      except OSError:
          pass

  cache_home = os.environ.get("XDG_CACHE_HOME")
  if cache_home is None:
      cache_home = Path.home() / ".cache"
  else:
      cache_home = Path(cache_home)

  history_path = cache_home / "python_history"
  if history_path.is_dir():
      raise OSError(f"'{history_path}' cannot be a directory")

  history = str(history_path)

  try:
      readline.read_history_file(history)
  except FileNotFoundError:
      pass

  # Prevents creation of default history if custom is empty
  if readline.get_current_history_length() == 0:
      readline.add_history(f'# File created at {time.asctime()}')

  atexit.register(write_history, history)
  del (atexit, os, readline, time, history, write_history)
