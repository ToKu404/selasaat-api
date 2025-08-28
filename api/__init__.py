# api/__init__.py

# Mengimpor router secara langsung agar mudah diakses
# saat seseorang melakukan "from api import router"
from .tripay import router

# Mendefinisikan apa saja yang bisa diakses
# ketika pengguna melakukan "from api import *"
__all__ = ["router"]