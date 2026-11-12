import hashlib, os
# Batch 8 menu: the installed batch-6 menu with its titles renamed. Boot arguments are unchanged.
L = os.path.expanduser(r'~\Desktop\NABU_IPADOS_LAB')
raw = open(L + r'\host-setup\batch6\unixnu.toml', 'rb').read()
assert hashlib.sha256(raw).hexdigest() == 'cd660c22cfd0a9185dfd03cc0af75758f878ad28ed09188468e80033aa17b349', 'menu input changed'
new = raw.decode().replace('(batch 6)', '(batch 8)')
assert new.count('(batch 8)') == 3
o = L + r'\host-setup\batch8'
os.makedirs(o, exist_ok=True)
open(o + r'\unixnu.toml', 'wb').write(new.encode())
print('menu', hashlib.sha256(new.encode()).hexdigest())
