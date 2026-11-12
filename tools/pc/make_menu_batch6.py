import hashlib, os
# Batch 6 menu: the installed batch-5 menu with its titles renamed. Boot arguments are unchanged.
L = os.path.expanduser(r'~\Desktop\NABU_IPADOS_LAB')
raw = open(L + r'\host-setup\batch5\unixnu.toml', 'rb').read()
assert hashlib.sha256(raw).hexdigest() == '223185f089e0a56636db29ffa007ab0bff901ac7f312830a118770764ed4c227', 'menu input changed'
new = raw.decode().replace('(batch 5)', '(batch 6)')
assert new.count('(batch 6)') == 3
o = L + r'\host-setup\batch6'
os.makedirs(o, exist_ok=True)
open(o + r'\unixnu.toml', 'wb').write(new.encode())
print('menu', hashlib.sha256(new.encode()).hexdigest())
