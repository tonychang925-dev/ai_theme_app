#!/usr/bin/env python3
import subprocess
import time
import os
import signal

env = os.environ.copy()
env['DEEPSEEK_API_KEY'] = 'sk-9c627df8575e4b44822aa8b0bea0f04c'

proc = subprocess.Popen(
    ['python3', 'full_pipeline_test_framework.py', '--mode', 'mock', '--samples', '1', '--timeout', '10', '--no-cleanup'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    env=env,
    text=True,
    bufsize=1
)

try:
    # Wait for 20 seconds
    for i in range(20):
        line = proc.stdout.readline()
        if line:
            print(line.strip())
        if proc.poll() is not None:
            break
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    if proc.poll() is None:
        print("Killing process after timeout")
        proc.terminate()
        proc.wait(timeout=5)
    print("Test process ended")