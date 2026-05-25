import os
from decouple import config
print(f"DATABASE_URL from decouple: {config('DATABASE_URL', default='NOT FOUND')}")
print(f"DATABASE_URL from os.environ: {os.environ.get('DATABASE_URL', 'NOT FOUND')}")
